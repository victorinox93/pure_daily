import os
import requests
import pandas as pd
from datetime import datetime, timezone

PURE_BASE_URL = "https://pure.udem.edu.mx/ws/api"
PURE_API_KEY = os.environ["PURE_API_KEY"]

headers = {
    "api-key": PURE_API_KEY,
    "Accept": "application/json"
}

def fetch_research_outputs(max_records=7000, page_size=100):
    url = f"{PURE_BASE_URL}/research-outputs"
    all_items = []
    offset = 0

    while len(all_items) < max_records:
        params = {"size": page_size, "offset": offset}
        response = requests.get(url, headers=headers, params=params, timeout=60)
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

def get_text_value(value):
    if value is None:
        return None

    if isinstance(value, str):
        return value

    if isinstance(value, dict):
        if "value" in value:
            return value.get("value")

        for lang in ["es_MX", "es_ES", "en_US", "en_GB"]:
            if lang in value:
                return value.get(lang)

        for v in value.values():
            if isinstance(v, str):
                return v

        return str(value)

    return str(value)

def extract_name_from_person_obj(person_obj):
    if not isinstance(person_obj, dict):
        return None

    name = person_obj.get("name")

    if isinstance(name, dict):
        first_name = name.get("firstName") or name.get("first") or name.get("givenName")
        last_name = name.get("lastName") or name.get("last") or name.get("familyName")

        full_name = " ".join([x for x in [first_name, last_name] if x])
        if full_name:
            return full_name

        text_name = get_text_value(name)
        if text_name:
            return text_name

    if isinstance(name, str):
        return name

    return (
        person_obj.get("displayName")
        or person_obj.get("systemName")
        or person_obj.get("name")
        or person_obj.get("uuid")
    )

def extract_contributor_names(item):
    contributors = item.get("contributors", [])
    names = []

    if not isinstance(contributors, list):
        return None

    for contributor in contributors:
        if not isinstance(contributor, dict):
            continue

        name = None
        person = contributor.get("person")

        if isinstance(person, dict):
            name = extract_name_from_person_obj(person)

        if not name:
            contributor_name = contributor.get("name")

            if isinstance(contributor_name, dict):
                first_name = contributor_name.get("firstName") or contributor_name.get("first") or contributor_name.get("givenName")
                last_name = contributor_name.get("lastName") or contributor_name.get("last") or contributor_name.get("familyName")
                name = " ".join([x for x in [first_name, last_name] if x])

                if not name:
                    name = get_text_value(contributor_name)

            elif isinstance(contributor_name, str):
                name = contributor_name

        if not name:
            name = contributor.get("displayName") or contributor.get("systemName") or contributor.get("uuid")

        if name:
            names.append(str(name))

    return "; ".join(names) if names else None

def extract_org_name(org_obj):
    if not isinstance(org_obj, dict):
        return None

    name = (
        org_obj.get("name")
        or org_obj.get("displayName")
        or org_obj.get("systemName")
        or org_obj.get("externalId")
        or org_obj.get("uuid")
    )

    if isinstance(name, dict):
        return get_text_value(name)

    return name

def extract_organizations(item):
    orgs = item.get("organizations", [])
    names = []

    if not isinstance(orgs, list):
        return None

    for org in orgs:
        name = extract_org_name(org)
        if name:
            names.append(str(name))

    return "; ".join(names) if names else None

def extract_managing_organization(item):
    return extract_org_name(item.get("managingOrganization"))

def main():
    records = fetch_research_outputs(max_records=7000, page_size=100)

    rows = []

    for item in records:
        rows.append({
            "fecha_consulta": datetime.now(timezone.utc).date().isoformat(),
            "pure_id": item.get("pureId"),
            "uuid": item.get("uuid"),
            "tipo": item.get("typeDiscriminator"),
            "titulo": get_text_value(item.get("title")),
            "autores": extract_contributor_names(item),
            "total_autores": item.get("totalNumberOfContributors"),
            "organizaciones": extract_organizations(item),
            "organizacion_responsable": extract_managing_organization(item),
            "created_by": item.get("createdBy"),
            "created_date": item.get("createdDate"),
            "modified_by": item.get("modifiedBy"),
            "modified_date": item.get("modifiedDate"),
            "portal_url": item.get("portalUrl"),
            "version": item.get("version"),
            "system_name": item.get("systemName")
        })

    df = pd.DataFrame(rows)

    df["created_date"] = pd.to_datetime(df["created_date"], errors="coerce", utc=True)
    df["modified_date"] = pd.to_datetime(df["modified_date"], errors="coerce", utc=True)

    df["created_date_mty"] = df["created_date"].dt.tz_convert("America/Monterrey")
    df["modified_date_mty"] = df["modified_date"].dt.tz_convert("America/Monterrey")

    df["created_day_mty"] = df["created_date_mty"].dt.date
    df["modified_day_mty"] = df["modified_date_mty"].dt.date
    df["created_month"] = df["created_date_mty"].dt.to_period("M").astype(str)

    hoy_mty = pd.Timestamp.now(tz="America/Monterrey").date()

    nuevos_hoy = df[df["created_day_mty"] == hoy_mty].copy()
    modificados_hoy = df[df["modified_day_mty"] == hoy_mty].copy()

    os.makedirs("data", exist_ok=True)

    df.to_csv("data/pure_research_outputs_completo_con_autores.csv", index=False, encoding="utf-8-sig")
    nuevos_hoy.to_csv("data/pure_nuevos_hoy_con_autores.csv", index=False, encoding="utf-8-sig")
    modificados_hoy.to_csv("data/pure_modificados_hoy_con_autores.csv", index=False, encoding="utf-8-sig")

    resumen_diario_nuevo = pd.DataFrame([{
        "fecha": str(hoy_mty),
        "total_research_outputs": len(df),
        "nuevos_hoy": len(nuevos_hoy),
        "modificados_hoy": len(modificados_hoy),
        "con_autores": df["autores"].notna().sum(),
        "con_organizacion_responsable": df["organizacion_responsable"].notna().sum(),
        "fecha_maxima_creacion": df["created_date_mty"].max(),
        "fecha_maxima_modificacion": df["modified_date_mty"].max()
    }])

    resumen_path = "data/pure_resumen_diario.csv"

    if os.path.exists(resumen_path):
        resumen_anterior = pd.read_csv(resumen_path)
        resumen = pd.concat([resumen_anterior, resumen_diario_nuevo], ignore_index=True)
        resumen = resumen.drop_duplicates(subset=["fecha"], keep="last")
    else:
        resumen = resumen_diario_nuevo

    resumen.to_csv(resumen_path, index=False, encoding="utf-8-sig")

if __name__ == "__main__":
    main()
