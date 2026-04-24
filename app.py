import pandas as pd
import streamlit as st
import plotly.express as px

st.set_page_config(
    page_title="Tablero Pure UDEM",
    page_icon="📊",
    layout="wide"
)

@st.cache_data
def load_data():
    df = pd.read_csv("data/pure_research_outputs_completo_con_autores.csv")
    resumen = pd.read_csv("data/pure_resumen_diario.csv")

    # Convertir fechas base usando UTC para evitar error de zonas horarias mixtas
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

    # Crear fechas en hora Monterrey desde las fechas base
    df["created_date_mty"] = df["created_date"].dt.tz_convert("America/Monterrey")
    df["modified_date_mty"] = df["modified_date"].dt.tz_convert("America/Monterrey")

    df["created_day_mty"] = df["created_date_mty"].dt.date
    df["modified_day_mty"] = df["modified_date_mty"].dt.date
    df["created_month"] = df["created_date_mty"].dt.to_period("M").astype(str)

    # Fechas del resumen
    if "fecha" in resumen.columns:
        resumen["fecha"] = pd.to_datetime(resumen["fecha"], errors="coerce").dt.date.astype(str)

    return df, resumen

df, resumen = load_data()

st.title("Tablero de Research Outputs en Pure")
st.caption("Actualizado automáticamente desde la API de Pure UDEM")

ultima_fecha = resumen["fecha"].max() if not resumen.empty else "Sin fecha"

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric("Total research outputs", f"{len(df):,}")

with col2:
    nuevos_ultimo_dia = int(resumen.sort_values("fecha").tail(1)["nuevos_hoy"].iloc[0])
    st.metric("Nuevos último corte", nuevos_ultimo_dia)

with col3:
    modificados_ultimo_dia = int(resumen.sort_values("fecha").tail(1)["modificados_hoy"].iloc[0])
    st.metric("Modificados último corte", modificados_ultimo_dia)

with col4:
    st.metric("Última actualización", ultima_fecha)

st.divider()

with st.sidebar:
    st.header("Filtros")

    tipos = sorted(df["tipo"].dropna().unique())
    tipo_sel = st.multiselect("Tipo de registro", tipos, default=tipos)

    orgs = sorted(df["organizacion_responsable"].dropna().unique())
    org_sel = st.multiselect("Organización responsable", orgs)

    busqueda = st.text_input("Buscar en título o autores")

df_filtrado = df[df["tipo"].isin(tipo_sel)].copy()

if org_sel:
    df_filtrado = df_filtrado[df_filtrado["organizacion_responsable"].isin(org_sel)]

if busqueda:
    texto = busqueda.lower()
    df_filtrado = df_filtrado[
        df_filtrado["titulo"].fillna("").str.lower().str.contains(texto)
        | df_filtrado["autores"].fillna("").str.lower().str.contains(texto)
    ]

st.subheader("Resumen del conjunto filtrado")

c1, c2, c3 = st.columns(3)

with c1:
    st.metric("Registros filtrados", f"{len(df_filtrado):,}")

with c2:
    st.metric("Con autores", f"{df_filtrado['autores'].notna().sum():,}")

with c3:
    st.metric("Con organización responsable", f"{df_filtrado['organizacion_responsable'].notna().sum():,}")

st.divider()

col_g1, col_g2 = st.columns(2)

with col_g1:
    resumen_tipo = (
        df_filtrado.groupby("tipo")
        .size()
        .reset_index(name="total")
        .sort_values("total", ascending=False)
    )

    fig_tipo = px.bar(
        resumen_tipo,
        x="tipo",
        y="total",
        title="Research outputs por tipo",
        text="total"
    )

    fig_tipo.update_layout(xaxis_title="", yaxis_title="Total")
    st.plotly_chart(fig_tipo, use_container_width=True)

with col_g2:
    resumen_org = (
        df_filtrado.groupby("organizacion_responsable")
        .size()
        .reset_index(name="total")
        .sort_values("total", ascending=False)
        .head(20)
    )

    fig_org = px.bar(
        resumen_org,
        x="total",
        y="organizacion_responsable",
        title="Top 20 organizaciones responsables",
        orientation="h",
        text="total"
    )

    fig_org.update_layout(xaxis_title="Total", yaxis_title="")
    st.plotly_chart(fig_org, use_container_width=True)

st.subheader("Tendencia mensual")

resumen_mes = (
    df_filtrado.groupby("created_month")
    .size()
    .reset_index(name="total")
    .sort_values("created_month")
)

fig_mes = px.line(
    resumen_mes,
    x="created_month",
    y="total",
    markers=True,
    title="Research outputs creados por mes"
)

fig_mes.update_layout(xaxis_title="Mes de creación", yaxis_title="Total")
st.plotly_chart(fig_mes, use_container_width=True)

st.subheader("Actividad diaria detectada")

fig_diario = px.line(
    resumen.sort_values("fecha"),
    x="fecha",
    y=["nuevos_hoy", "modificados_hoy"],
    markers=True,
    title="Nuevos y modificados por día"
)

fig_diario.update_layout(xaxis_title="Fecha", yaxis_title="Registros")
st.plotly_chart(fig_diario, use_container_width=True)

st.subheader("Últimos registros modificados")

ultimos = df_filtrado.sort_values("modified_date_mty", ascending=False)[
    [
        "pure_id",
        "tipo",
        "titulo",
        "autores",
        "organizacion_responsable",
        "created_date_mty",
        "modified_date_mty",
        "portal_url"
    ]
].head(100)

st.dataframe(
    ultimos,
    use_container_width=True,
    hide_index=True,
    column_config={
        "portal_url": st.column_config.LinkColumn("Liga Pure")
    }
)
