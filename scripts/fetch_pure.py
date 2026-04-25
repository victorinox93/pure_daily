import os
import requests
import pandas as pd
from datetime import datetime, timezone

# ============================================================
# CONFIGURACIÓN
# ============================================================

PURE_BASE_URL = "https://pure.udem.edu.mx/ws/api"
PURE_API_KEY = os.environ["PURE_API_KEY"]

headers = {
    "api-key": PURE_API_KEY,
    "Accept": "application/json"
}

GENERIC_VALUES = {
    "person",
    "organization",
    "organisation",
    "organisational unit",
    "organizational unit",
    "external organization",
    "external organisation",
    "unknown",
    "none",
    "nan",
    ""
}


# ============================================================
# DESCARGA DESDE PURE
# ============================================================

def fetch_research_outputs(max_records=7000, page_size=100):
    url = f"{PURE_BASE_URL}/research-outputs"
    all_items = []
    offset = 0

    while len(all_items) < max_records:
        params = {
            "size": page_size,
            "offset": offset
        }

        response = requests.get(
            url,
            headers=headers,
            params=params,
            timeout=60
        )

        print("Offset:", offset, "| Status:", response.status_code)

        response.raise_for_status()

        data = response.json()
        items = data.get("items", [])

        if not items:
            break

        all_items.extend(items)

        if len(items) < page_size:
            break

        offset += page_size

    return all_items[:max_records]


# ============================================================
# LIMPIEZA Y EXTRACCIÓN DE TEXTO
# ============================================================

def clean_text(value):
    if value is None:
        return None

    value = str(value).strip()

    if not value:
        return None

    if value.lower() in GENERIC_VALUES:
        return None

    return value


def get_text_value(value):
    """
    Extrae texto de campos de Pure.
    Evita devolver valores genéricos como Person u Organization.
    """
    if value is None:
        return None

    if isinstance(value, str):
        return clean_text(value)

    if isinstance(value, dict):
        preferred_keys = [
            "value",
            "text",
            "en_GB",
            "en_US",
            "es_MX",
            "es_ES",
            "name",
            "title",
            "displayName",
            "systemName"
        ]

        for key in preferred_keys:
            if key in value:
                result = get_text_value(value.get(key))
                if result:
                    return result

        for v in value.values():
            result = get_text_value(v)
            if result:
                return result

        return None

    if isinstance(value, list):
        for v in value:
            result = get_text_value(v)
            if result:
                return result

        return None

    return clean_text(value)


def deduplicate_keep_order(values):
    cleaned = []
    seen = set()

    for value in values:
        value = clean_text(value)

        if not value:
            continue

        key = value.lower()

        if key not in seen:
            cleaned.append(value)
            seen.add(key)

    return cleaned


# ============================================================
# EXTRACCIÓN DE AUTORES
# ============================================================

def extract_name_parts(name_obj):
    """
    Extrae nombre y apellido cuando Pure trae objetos con firstName / lastName.
    """
    if not isinstance(name_obj, dict):
        return None

    first_name = (
        name_obj.get("firstName")
        or name_obj.get("first")
        or name_obj.get("givenName")
        or name_obj.get("forename")
    )

    last_name = (
        name_obj.get("lastName")
        or name_obj.get("last")
        or name_obj.get("familyName")
        or name_obj.get("surname")
    )

    full_name = " ".join([
        str(x).strip()
        for x in [first_name, last_name]
        if x is not None and str(x).strip()
    ])

    return clean_text(full_name)


def extract_name_from_person_obj(person_obj):
    """
    Extrae nombres reales de personas internas.
    Evita devolver el texto genérico 'Person'.
    """
    if not isinstance(person_obj, dict):
        return None

    # Caso común: name con firstName / lastName
    name = extract_name_parts(person_obj.get("name"))
    if name:
        return name

    # Campos alternativos
    for key in [
        "displayName",
        "systemName",
        "fullName",
        "knownAs",
        "name"
    ]:
        value = get_text_value(person_obj.get(key))
        if value:
            return value

    return None


def extract_external_person_name(contributor):
    """
    Extrae nombre de autores externos o contribuidores sin objeto person.
    """
    if not isinstance(contributor, dict):
        return None

    # Caso común: contributor["name"] con firstName / lastName
    name = extract_name_parts(contributor.get("name"))
    if name:
        return name

    # Campo name como texto o diccionario alternativo
    name = get_text_value(contributor.get("name"))
    if name:
        return name

    # Campos alternativos
    for key in [
        "displayName",
        "systemName",
        "fullName",
        "knownAs"
    ]:
        value = get_text_value(contributor.get(key))
        if value:
            return value

    return None


def extract_contributor_names(item):
    """
    Extrae autores reales desde contributors.
    """
    contributors = item.get("contributors", [])
    names = []

    if not isinstance(contributors, list):
        return None

    for contributor in contributors:
        if not isinstance(contributor, dict):
            continue

        name = None

        # Persona interna
        person = contributor.get("person")
        if isinstance(person, dict):
            name = extract_name_from_person_obj(person)

        # Persona externa o nombre directo
        if not name:
            name = extract_external_person_name(contributor)

        if name:
            names.append(name)

    unique_names = deduplicate_keep_order(names)

    return "; ".join(unique_names) if unique_names else None


def extract_internal_contributor_uuids(item):
    """
    Extrae UUIDs de personas internas si existen dentro de contributors.
    """
    contributors = item.get("contributors", [])
    uuids = []

    if not isinstance(contributors, list):
        return None

    for contributor in contributors:
        if not isinstance(contributor, dict):
            continue

        person = contributor.get("person")

        if isinstance(person, dict):
            uuid = clean_text(person.get("uuid"))
            if uuid:
                uuids.append(uuid)

    unique_uuids = deduplicate_keep_order(uuids)

    return "; ".join(unique_uuids) if unique_uuids else None


# ============================================================
# EXTRACCIÓN DE ORGANIZACIONES
# ============================================================

def extract_org_name(org_obj):
    """
    Extrae nombres reales de organizaciones.
    Evita devolver el texto genérico 'Organization'.
    """
    if not isinstance(org_obj, dict):
        return None

    # Algunos objetos vienen como referencia con uuid/name
    for key in [
        "name",
        "displayName",
        "systemName",
        "externalName",
        "title"
    ]:
        value = get_text_value(org_obj.get(key))
        if value:
            return value

    # A veces la organización viene anidada
    for key in [
        "organisationalUnit",
        "organizationalUnit",
        "organization",
        "organisation",
        "externalOrganization",
        "externalOrganisation"
    ]:
        nested = org_obj.get(key)

        if isinstance(nested, dict):
            value = extract_org_name(nested)
            if value:
                return value

    return None


def extract_organizations(item):
    """
    Extrae organizaciones internas del campo organizations.
    """
    orgs = item.get("organizations", [])
    names = []

    if not isinstance(orgs, list):
        return None

    for org in orgs:
        name = extract_org_name(org)
        if name:
            names.append(name)

    unique_names = deduplicate_keep_order(names)

    return "; ".join(unique_names) if unique_names else None


def extract_external_organizations(item):
    """
    Extrae organizaciones externas del campo externalOrganizations.
    """
    orgs = item.get("externalOrganizations", [])
    names = []

    if not isinstance(orgs, list):
        return None

    for org in orgs:
        name = extract_org_name(org)
        if name:
            names.append(name)

    unique_names = deduplicate_keep_order(names)

    return "; ".join(unique_names) if unique_names else None


def extract_managing_organization(item):
    """
    Extrae la organización responsable del registro.
    """
    org = item.get("managingOrganization")
    return extract_org_name(org)


# ============================================================
# EXTRACCIÓN DE OTROS CAMPOS
# ============================================================

def extract_workflow_step(item):
    """
    Extrae el estado de workflow si existe.
    """
    workflow = item.get("workflow")

    if not isinstance(workflow, dict):
        return None

    step = workflow.get("step")

    if isinstance(step, dict):
        return get_text_value(
            step.get("term")
            or step.get("name")
            or step.get("value")
            or step
        )

    return get_text_value(step)


def extract_publication_status(item):
    """
    Extrae estatus de publicación si existe.
    """
    statuses = item.get("publicationStatuses", [])

    if not isinstance(statuses, list) or len(statuses) == 0:
        return None

    values = []

    for status in statuses:
        if not isinstance(status, dict):
            continue

        pub_status = status.get("publicationStatus")

        if isinstance(pub_status, dict):
            value = get_text_value(
                pub_status.get("term")
                or pub_status.get("name")
                or pub_status.get("value")
                or pub_status
            )
        else:
            value = get_text_value(pub_status)

        if value:
            values.append(value)

    unique_values = deduplicate_keep_order(values)

    return "; ".join(unique_values) if unique_values else None


def extract_journal_title(item):
    """
    Extrae nombre de revista si existe.
    """
    journal = item.get("journalAssociation")

    if not isinstance(journal, dict):
        return None

    # Estructuras comunes
    for key in ["title", "name", "journal", "systemName"]:
        value = journal.get(key)

        if isinstance(value, dict):
            result = get_text_value(value)
            if result:
                return result

        if isinstance(value, str):
            result = clean_text(value)
            if result:
                return result

    # Buscar más profundo si viene anidado
    for value in journal.values():
        result = get_text_value(value)
        if result:
            return result

    return None


def extract_year_from_publication_status(item):
    """
    Intenta extraer año de publicación desde publicationStatuses.
    """
    statuses = item.get("publicationStatuses", [])

    if not isinstance(statuses, list):
        return None

    years = []

    for status in statuses:
        if not isinstance(status, dict):
            continue

        date_value = (
            status.get("publicationDate")
            or status.get("date")
            or status.get("year")
        )

        if isinstance(date_value, dict):
            year = date_value.get("year")
            if year:
                years.append(str(year))

        elif date_value:
            text = str(date_value)
            if len(text) >= 4 and text[:4].isdigit():
                years.append(text[:4])

    unique_years = deduplicate_keep_order(years)

    return "; ".join(unique_years) if unique_years else None


# ============================================================
# CONSTRUCCIÓN DEL DATAFRAME
# ============================================================

def build_dataframe(records):
    rows = []

    for item in records:
        rows.append({
            "fecha_consulta": datetime.now(timezone.utc).date().isoformat(),
            "pure_id": item.get("pureId"),
            "uuid": item.get("uuid"),
            "tipo": item.get("typeDiscriminator"),
            "titulo": get_text_value(item.get("title")),
            "autores": extract_contributor_names(item),
            "person_uuids": extract_internal_contributor_uuids(item),
            "total_autores": item.get("totalNumberOfContributors"),
            "organizaciones": extract_organizations(item),
            "organizaciones_externas": extract_external_organizations(item),
            "organizacion_responsable": extract_managing_organization(item),
            "estatus_publicacion": extract_publication_status(item),
            "anio_publicacion": extract_year_from_publication_status(item),
            "revista": extract_journal_title(item),
            "workflow": extract_workflow_step(item),
            "created_by": item.get("createdBy"),
            "created_date": item.get("createdDate"),
            "modified_by": item.get("modifiedBy"),
            "modified_date": item.get("modifiedDate"),
            "portal_url": item.get("portalUrl"),
            "version": item.get("version"),
            "system_name": item.get("systemName")
        })

    df = pd.DataFrame(rows)

    # Fechas
    df["created_date"] = pd.to_datetime(
        df["created_date"],
        errors="coerce",
        utc=True
    )

    df["modified_date"] = pd.to_datetime(
        df["modified_date"],
        errors="coerce",
        utc=True
    )

    df["created_date_mty"] = df["created_date"].dt.tz_convert("America/Monterrey")
    df["modified_date_mty"] = df["modified_date"].dt.tz_convert("America/Monterrey")

    df["created_day_mty"] = df["created_date_mty"].dt.date
    df["modified_day_mty"] = df["modified_date_mty"].dt.date
    df["created_month"] = df["created_date_mty"].dt.to_period("M").astype(str)

    return df


# ============================================================
# EXPORTACIÓN
# ============================================================

def export_outputs(df):
    hoy_mty = pd.Timestamp.now(tz="America/Monterrey").date()

    nuevos_hoy = df[df["created_day_mty"] == hoy_mty].copy()
    modificados_hoy = df[df["modified_day_mty"] == hoy_mty].copy()

    os.makedirs("data", exist_ok=True)

    df.to_csv(
        "data/pure_research_outputs_completo_con_autores.csv",
        index=False,
        encoding="utf-8-sig"
    )

    nuevos_hoy.to_csv(
        "data/pure_nuevos_hoy_con_autores.csv",
        index=False,
        encoding="utf-8-sig"
    )

    modificados_hoy.to_csv(
        "data/pure_modificados_hoy_con_autores.csv",
        index=False,
        encoding="utf-8-sig"
    )

    resumen_diario_nuevo = pd.DataFrame([{
        "fecha": str(hoy_mty),
        "total_research_outputs": len(df),
        "nuevos_hoy": len(nuevos_hoy),
        "modificados_hoy": len(modificados_hoy),
        "con_autores": df["autores"].notna().sum(),
        "con_organizaciones": df["organizaciones"].notna().sum(),
        "con_organizacion_responsable": df["organizacion_responsable"].notna().sum(),
        "fecha_maxima_creacion": df["created_date_mty"].max(),
        "fecha_maxima_modificacion": df["modified_date_mty"].max()
    }])

    resumen_path = "data/pure_resumen_diario.csv"

    if os.path.exists(resumen_path):
        resumen_anterior = pd.read_csv(resumen_path)
        resumen = pd.concat(
            [resumen_anterior, resumen_diario_nuevo],
            ignore_index=True
        )
        resumen = resumen.drop_duplicates(subset=["fecha"], keep="last")
    else:
        resumen = resumen_diario_nuevo

    resumen.to_csv(
        resumen_path,
        index=False,
        encoding="utf-8-sig"
    )

    resumen_tipo = (
        df.groupby("tipo", dropna=False)
        .size()
        .reset_index(name="total")
        .sort_values("total", ascending=False)
    )

    resumen_tipo.to_csv(
        "data/pure_resumen_tipo.csv",
        index=False,
        encoding="utf-8-sig"
    )

    resumen_mes = (
        df.groupby("created_month", dropna=False)
        .size()
        .reset_index(name="total")
        .sort_values("created_month")
    )

    resumen_mes.to_csv(
        "data/pure_resumen_mes.csv",
        index=False,
        encoding="utf-8-sig"
    )

    resumen_org_responsable = (
        df.dropna(subset=["organizacion_responsable"])
        .groupby("organizacion_responsable")
        .size()
        .reset_index(name="total")
        .sort_values("total", ascending=False)
    )

    resumen_org_responsable.to_csv(
        "data/pure_resumen_organizacion_responsable.csv",
        index=False,
        encoding="utf-8-sig"
    )

    print("\nArchivos generados:")
    print("- data/pure_research_outputs_completo_con_autores.csv")
    print("- data/pure_nuevos_hoy_con_autores.csv")
    print("- data/pure_modificados_hoy_con_autores.csv")
    print("- data/pure_resumen_diario.csv")
    print("- data/pure_resumen_tipo.csv")
    print("- data/pure_resumen_mes.csv")
    print("- data/pure_resumen_organizacion_responsable.csv")

    print("\nResumen:")
    print("Total registros:", len(df))
    print("Nuevos hoy:", len(nuevos_hoy))
    print("Modificados hoy:", len(modificados_hoy))
    print("Con autores:", df["autores"].notna().sum())
    print("Con organizaciones:", df["organizaciones"].notna().sum())
    print("Con organización responsable:", df["organizacion_responsable"].notna().sum())


# ============================================================
# MAIN
# ============================================================

def main():
    records = fetch_research_outputs(max_records=7000, page_size=100)

    print("\nRegistros descargados:", len(records))

    df = build_dataframe(records)

    # Validación rápida para detectar si aún aparecen valores genéricos
    print("\nPrimeros autores extraídos:")
    print(df["autores"].dropna().head(10).to_string(index=False))

    print("\nPrimeras organizaciones extraídas:")
    print(df["organizaciones"].dropna().head(10).to_string(index=False))

    print("\nPrimeras organizaciones responsables:")
    print(df["organizacion_responsable"].dropna().head(10).to_string(index=False))

    export_outputs(df)


if __name__ == "__main__":
    main()
