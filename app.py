import pandas as pd
import streamlit as st
import plotly.express as px

# ============================================================
# CONFIGURACIÓN GENERAL
# ============================================================

st.set_page_config(
    page_title="Tablero Pure UDEM",
    page_icon="📊",
    layout="wide"
)

# ============================================================
# CARGA DE DATOS
# ============================================================

@st.cache_data
def load_data():
    df = pd.read_csv("data/pure_research_outputs_completo_con_autores.csv")
    resumen = pd.read_csv("data/pure_resumen_diario.csv")

    # Fechas base
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

    # Fechas en hora Monterrey
    df["created_date_mty"] = df["created_date"].dt.tz_convert("America/Monterrey")
    df["modified_date_mty"] = df["modified_date"].dt.tz_convert("America/Monterrey")

    df["created_day_mty"] = df["created_date_mty"].dt.date
    df["modified_day_mty"] = df["modified_date_mty"].dt.date
    df["created_month"] = df["created_date_mty"].dt.to_period("M").astype(str)

    # Limpiar campos clave
    for col in [
        "tipo",
        "titulo",
        "autores",
        "organizacion_responsable",
        "organizaciones",
        "workflow",
        "portal_url"
    ]:
        if col in df.columns:
            df[col] = df[col].replace({"": pd.NA, "nan": pd.NA, "None": pd.NA})

    # Resumen diario
    if "fecha" in resumen.columns:
        resumen["fecha"] = pd.to_datetime(
            resumen["fecha"],
            errors="coerce"
        ).dt.date

    return df, resumen


@st.cache_data
def load_daily_files():
    nuevos = pd.read_csv("data/pure_nuevos_hoy_con_autores.csv")
    modificados = pd.read_csv("data/pure_modificados_hoy_con_autores.csv")

    return nuevos, modificados


df, resumen = load_data()
nuevos, modificados = load_daily_files()

# ============================================================
# ENCABEZADO
# ============================================================

st.title("Tablero Pure UDEM")
st.caption("Seguimiento diario de research outputs registrados y modificados en Pure")

ultima_fecha = None

if not resumen.empty and "fecha" in resumen.columns:
    ultima_fecha = resumen["fecha"].max()

# ============================================================
# SIDEBAR / FILTROS
# ============================================================

with st.sidebar:
    st.header("Filtros")

    tipos = sorted(df["tipo"].dropna().unique()) if "tipo" in df.columns else []
    tipo_sel = st.multiselect(
        "Tipo de registro",
        tipos,
        default=tipos
    )

    orgs = (
        sorted(df["organizacion_responsable"].dropna().unique())
        if "organizacion_responsable" in df.columns
        else []
    )

    org_sel = st.multiselect(
        "Organización responsable",
        orgs
    )

    anios_disponibles = sorted(
        df["created_date_mty"].dropna().dt.year.unique(),
        reverse=True
    )

    anios_sel = st.multiselect(
        "Año de creación",
        anios_disponibles,
        default=anios_disponibles
    )

    busqueda = st.text_input(
        "Buscar por título o autor"
    )

    st.divider()

    st.caption("Los filtros afectan las gráficas y tablas principales del tablero.")


# ============================================================
# APLICAR FILTROS
# ============================================================

df_filtrado = df.copy()

if tipo_sel:
    df_filtrado = df_filtrado[df_filtrado["tipo"].isin(tipo_sel)]

if org_sel:
    df_filtrado = df_filtrado[
        df_filtrado["organizacion_responsable"].isin(org_sel)
    ]

if anios_sel:
    df_filtrado = df_filtrado[
        df_filtrado["created_date_mty"].dt.year.isin(anios_sel)
    ]

if busqueda:
    texto = busqueda.lower().strip()

    df_filtrado = df_filtrado[
        df_filtrado["titulo"].fillna("").str.lower().str.contains(texto)
        | df_filtrado["autores"].fillna("").str.lower().str.contains(texto)
    ]


# ============================================================
# KPIs PRINCIPALES
# ============================================================

total_registros = len(df)
total_filtrado = len(df_filtrado)
con_autores = df["autores"].notna().sum()
con_org = df["organizacion_responsable"].notna().sum()

col1, col2, col3, col4, col5, col6 = st.columns(6)

with col1:
    st.metric("Total registros", f"{total_registros:,}")

with col2:
    st.metric("Filtrados", f"{total_filtrado:,}")

with col3:
    st.metric("Nuevos último corte", f"{len(nuevos):,}")

with col4:
    st.metric("Modificados último corte", f"{len(modificados):,}")

with col5:
    st.metric("Con autores", f"{con_autores:,}")

with col6:
    st.metric("Última actualización", str(ultima_fecha))


st.divider()

# ============================================================
# TABS
# ============================================================

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "Resumen ejecutivo",
    "Actividad diaria",
    "Producción",
    "Calidad de datos",
    "Tabla completa"
])

# ============================================================
# TAB 1: RESUMEN EJECUTIVO
# ============================================================

with tab1:
    st.subheader("Resumen ejecutivo")

    c1, c2 = st.columns([1, 1])

    with c1:
        resumen_tipo = (
            df_filtrado.groupby("tipo", dropna=False)
            .size()
            .reset_index(name="total")
            .sort_values("total", ascending=True)
        )

        fig_tipo = px.bar(
            resumen_tipo,
            x="total",
            y="tipo",
            orientation="h",
            text="total",
            title="Research outputs por tipo"
        )

        fig_tipo.update_layout(
            height=500,
            xaxis_title="Total de registros",
            yaxis_title="",
            showlegend=False,
            margin=dict(l=10, r=10, t=60, b=10)
        )

        st.plotly_chart(fig_tipo, use_container_width=True)

    with c2:
        resumen_org = (
            df_filtrado.dropna(subset=["organizacion_responsable"])
            .groupby("organizacion_responsable")
            .size()
            .reset_index(name="total")
            .sort_values("total", ascending=False)
            .head(15)
            .sort_values("total", ascending=True)
        )

        if resumen_org.empty:
            st.info("No hay datos de organización responsable con los filtros actuales.")
        else:
            fig_org = px.bar(
                resumen_org,
                x="total",
                y="organizacion_responsable",
                orientation="h",
                text="total",
                title="Top 15 organizaciones responsables"
            )

            fig_org.update_layout(
                height=600,
                xaxis_title="Total de registros",
                yaxis_title="",
                showlegend=False,
                margin=dict(l=10, r=10, t=60, b=10)
            )

            st.plotly_chart(fig_org, use_container_width=True)

    st.subheader("Participación por tipo")

    resumen_tipo_pie = (
        df_filtrado.groupby("tipo")
        .size()
        .reset_index(name="total")
        .sort_values("total", ascending=False)
    )

    if not resumen_tipo_pie.empty:
        fig_dona = px.pie(
            resumen_tipo_pie,
            names="tipo",
            values="total",
            hole=0.5,
            title="Distribución porcentual por tipo"
        )

        fig_dona.update_layout(
            height=500,
            margin=dict(l=10, r=10, t=60, b=10)
        )

        st.plotly_chart(fig_dona, use_container_width=True)
    else:
        st.info("No hay datos disponibles para mostrar la distribución por tipo.")


# ============================================================
# TAB 2: ACTIVIDAD DIARIA
# ============================================================

with tab2:
    st.subheader("Actividad diaria detectada")

    if resumen.empty:
        st.info("Todavía no hay histórico diario suficiente.")
    else:
        resumen_plot = resumen.copy()
        resumen_plot = resumen_plot.sort_values("fecha")

        columnas_actividad = [
            col for col in ["nuevos_hoy", "modificados_hoy"]
            if col in resumen_plot.columns
        ]

        if columnas_actividad:
            fig_diario = px.bar(
                resumen_plot,
                x="fecha",
                y=columnas_actividad,
                barmode="group",
                title="Nuevos y modificados por día"
            )

            fig_diario.update_layout(
                height=450,
                xaxis_title="Fecha",
                yaxis_title="Registros",
                legend_title="Indicador",
                margin=dict(l=10, r=10, t=60, b=10)
            )

            st.plotly_chart(fig_diario, use_container_width=True)

        st.subheader("Bitácora diaria")

        columnas_resumen = [
            col for col in [
                "fecha",
                "total_research_outputs",
                "nuevos_hoy",
                "modificados_hoy",
                "con_autores",
                "con_organizacion_responsable",
                "fecha_maxima_creacion",
                "fecha_maxima_modificacion"
            ]
            if col in resumen.columns
        ]

        st.dataframe(
            resumen[columnas_resumen].sort_values("fecha", ascending=False),
            use_container_width=True,
            hide_index=True
        )

    st.divider()

    st.subheader("Nuevos registros del último corte")

    if nuevos.empty:
        st.info("No se detectaron registros nuevos en el último corte.")
    else:
        columnas_nuevos = [
            col for col in [
                "pure_id",
                "tipo",
                "titulo",
                "autores",
                "total_autores",
                "organizacion_responsable",
                "created_date_mty",
                "portal_url"
            ]
            if col in nuevos.columns
        ]

        st.dataframe(
            nuevos[columnas_nuevos],
            use_container_width=True,
            hide_index=True,
            column_config={
                "portal_url": st.column_config.LinkColumn("Liga Pure")
            }
        )

    st.subheader("Registros modificados del último corte")

    if modificados.empty:
        st.info("No se detectaron registros modificados en el último corte.")
    else:
        columnas_modificados = [
            col for col in [
                "pure_id",
                "tipo",
                "titulo",
                "autores",
                "total_autores",
                "organizacion_responsable",
                "modified_date_mty",
                "portal_url"
            ]
            if col in modificados.columns
        ]

        st.dataframe(
            modificados[columnas_modificados],
            use_container_width=True,
            hide_index=True,
            column_config={
                "portal_url": st.column_config.LinkColumn("Liga Pure")
            }
        )


# ============================================================
# TAB 3: PRODUCCIÓN
# ============================================================

with tab3:
    st.subheader("Producción y tendencias")

    resumen_mes = (
        df_filtrado.groupby("created_month")
        .size()
        .reset_index(name="total")
        .sort_values("created_month")
    )

    resumen_mes_24 = resumen_mes.tail(24)

    if resumen_mes_24.empty:
        st.info("No hay datos mensuales disponibles con los filtros actuales.")
    else:
        fig_mes = px.bar(
            resumen_mes_24,
            x="created_month",
            y="total",
            text="total",
            title="Research outputs creados por mes (últimos 24 meses)"
        )

        fig_mes.update_layout(
            height=450,
            xaxis_title="Mes de creación",
            yaxis_title="Total de registros",
            margin=dict(l=10, r=10, t=60, b=10)
        )

        st.plotly_chart(fig_mes, use_container_width=True)

    c1, c2 = st.columns([1, 1])

    with c1:
        st.subheader("Top autores")

        autores_series = (
            df_filtrado["autores"]
            .dropna()
            .str.split(";")
            .explode()
            .str.strip()
        )

        autores_series = autores_series[autores_series != ""]

        if autores_series.empty:
            st.info("No hay autores disponibles con los filtros actuales.")
        else:
            top_autores = autores_series.value_counts().reset_index()
            top_autores.columns = ["autor", "total"]
            top_autores = (
                top_autores
                .head(15)
                .sort_values("total", ascending=True)
            )

            fig_autores = px.bar(
                top_autores,
                x="total",
                y="autor",
                orientation="h",
                text="total",
                title="Top 15 autores"
            )

            fig_autores.update_layout(
                height=600,
                xaxis_title="Total de registros",
                yaxis_title="",
                showlegend=False,
                margin=dict(l=10, r=10, t=60, b=10)
            )

            st.plotly_chart(fig_autores, use_container_width=True)

    with c2:
        st.subheader("Top organizaciones internas")

        if "organizaciones" in df_filtrado.columns:
            org_series = (
                df_filtrado["organizaciones"]
                .dropna()
                .str.split(";")
                .explode()
                .str.strip()
            )

            org_series = org_series[org_series != ""]

            if org_series.empty:
                st.info("No hay organizaciones internas disponibles.")
            else:
                top_orgs = org_series.value_counts().reset_index()
                top_orgs.columns = ["organizacion", "total"]
                top_orgs = (
                    top_orgs
                    .head(15)
                    .sort_values("total", ascending=True)
                )

                fig_top_orgs = px.bar(
                    top_orgs,
                    x="total",
                    y="organizacion",
                    orientation="h",
                    text="total",
                    title="Top 15 organizaciones internas"
                )

                fig_top_orgs.update_layout(
                    height=600,
                    xaxis_title="Total de registros",
                    yaxis_title="",
                    showlegend=False,
                    margin=dict(l=10, r=10, t=60, b=10)
                )

                st.plotly_chart(fig_top_orgs, use_container_width=True)
        else:
            st.info("No existe la columna de organizaciones internas.")

    st.subheader("Últimos registros creados")

    ultimos_creados = df_filtrado.sort_values(
        "created_date_mty",
        ascending=False
    )

    columnas_ultimos_creados = [
        col for col in [
            "pure_id",
            "tipo",
            "titulo",
            "autores",
            "organizacion_responsable",
            "created_date_mty",
            "portal_url"
        ]
        if col in ultimos_creados.columns
    ]

    st.dataframe(
        ultimos_creados[columnas_ultimos_creados].head(100),
        use_container_width=True,
        hide_index=True,
        column_config={
            "portal_url": st.column_config.LinkColumn("Liga Pure")
        }
    )

    st.subheader("Últimos registros modificados")

    ultimos_modificados = df_filtrado.sort_values(
        "modified_date_mty",
        ascending=False
    )

    columnas_ultimos_modificados = [
        col for col in [
            "pure_id",
            "tipo",
            "titulo",
            "autores",
            "organizacion_responsable",
            "modified_date_mty",
            "portal_url"
        ]
        if col in ultimos_modificados.columns
    ]

    st.dataframe(
        ultimos_modificados[columnas_ultimos_modificados].head(100),
        use_container_width=True,
        hide_index=True,
        column_config={
            "portal_url": st.column_config.LinkColumn("Liga Pure")
        }
    )


# ============================================================
# TAB 4: CALIDAD DE DATOS
# ============================================================

with tab4:
    st.subheader("Calidad de datos")

    sin_autores = df[df["autores"].isna()]
    sin_org_responsable = df[df["organizacion_responsable"].isna()]
    sin_titulo = df[df["titulo"].isna()]

    if "workflow" in df.columns:
        sin_workflow = df[df["workflow"].isna()]
    else:
        sin_workflow = pd.DataFrame()

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        st.metric("Sin autores", f"{len(sin_autores):,}")

    with c2:
        st.metric("Sin org. responsable", f"{len(sin_org_responsable):,}")

    with c3:
        st.metric("Sin título", f"{len(sin_titulo):,}")

    with c4:
        st.metric("Sin workflow", f"{len(sin_workflow):,}")

    st.divider()

    columnas_calidad = [
        col for col in [
            "pure_id",
            "tipo",
            "titulo",
            "autores",
            "organizacion_responsable",
            "created_date_mty",
            "modified_date_mty",
            "portal_url"
        ]
        if col in df.columns
    ]

    with st.expander("Ver registros sin autores"):
        if sin_autores.empty:
            st.success("No se encontraron registros sin autores.")
        else:
            st.dataframe(
                sin_autores[columnas_calidad].head(500),
                use_container_width=True,
                hide_index=True,
                column_config={
                    "portal_url": st.column_config.LinkColumn("Liga Pure")
                }
            )

    with st.expander("Ver registros sin organización responsable"):
        if sin_org_responsable.empty:
            st.success("No se encontraron registros sin organización responsable.")
        else:
            st.dataframe(
                sin_org_responsable[columnas_calidad].head(500),
                use_container_width=True,
                hide_index=True,
                column_config={
                    "portal_url": st.column_config.LinkColumn("Liga Pure")
                }
            )

    with st.expander("Ver registros sin título"):
        if sin_titulo.empty:
            st.success("No se encontraron registros sin título.")
        else:
            st.dataframe(
                sin_titulo[columnas_calidad].head(500),
                use_container_width=True,
                hide_index=True,
                column_config={
                    "portal_url": st.column_config.LinkColumn("Liga Pure")
                }
            )

    with st.expander("Ver registros sin workflow"):
        if sin_workflow.empty:
            st.success("No se encontraron registros sin workflow.")
        else:
            st.dataframe(
                sin_workflow[columnas_calidad].head(500),
                use_container_width=True,
                hide_index=True,
                column_config={
                    "portal_url": st.column_config.LinkColumn("Liga Pure")
                }
            )


# ============================================================
# TAB 5: TABLA COMPLETA
# ============================================================

with tab5:
    st.subheader("Tabla completa filtrada")

    st.caption(
        "Esta tabla refleja los filtros seleccionados en la barra lateral."
    )

    columnas_tabla = [
        col for col in [
            "pure_id",
            "uuid",
            "tipo",
            "titulo",
            "autores",
            "total_autores",
            "organizacion_responsable",
            "organizaciones",
            "created_date_mty",
            "modified_date_mty",
            "workflow",
            "portal_url"
        ]
        if col in df_filtrado.columns
    ]

    st.dataframe(
        df_filtrado[columnas_tabla],
        use_container_width=True,
        hide_index=True,
        column_config={
            "portal_url": st.column_config.LinkColumn("Liga Pure")
        }
    )

    csv_filtrado = df_filtrado[columnas_tabla].to_csv(
        index=False,
        encoding="utf-8-sig"
    )

    st.download_button(
        label="Descargar tabla filtrada CSV",
        data=csv_filtrado,
        file_name="pure_research_outputs_filtrado.csv",
        mime="text/csv"
    )
