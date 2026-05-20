import streamlit as st
import pandas as pd
import re
import plotly.express as px

st.set_page_config(
    page_title="Analizador WhatsApp Movizzon",
    layout="wide"
)

st.title("Analizador de TXT WhatsApp - Movizzon")

archivo = st.file_uploader(
    "Selecciona archivo TXT",
    type=["txt"]
)


def extraer_campo(texto, campo):

    patron = rf"\*{campo}:\*\s*(.*)"

    m = re.search(
        patron,
        texto
    )

    return m.group(1).strip() if m else ""


if archivo:

    texto = archivo.read().decode(
        "utf-8",
        errors="ignore"
    )

    patron = r"\[(\d{1,2}[-/]\d{1,2}[-/]\d{2}),\s([^]]+?)\]\s(.+?):\s(.*?)(?=\n\[\d{1,2}[-/]\d{1,2}[-/]\d{2},|\Z)"

    matches = re.findall(
        patron,
        texto,
        flags=re.DOTALL
    )

    filas = []

    for fecha, hora, usuario, mensaje in matches:

        mensaje = mensaje.strip()

        # SOLO ROBOT 80
        if "Robot 80" not in usuario:
            continue

        filas.append({
            "fecha": fecha,
            "hora": hora,
            "usuario": usuario,
            "aplicacion": extraer_campo(
                mensaje,
                "Aplicacion"
            ),
            "paso": extraer_campo(
                mensaje,
                "Paso"
            ),
            "operadores": extraer_campo(
                mensaje,
                "Operadores"
            ),
            "detalle": extraer_campo(
                mensaje,
                "Detalle"
            ),
            "mensaje_error": extraer_campo(
                mensaje,
                "Mensaje"
            ),
            "mensaje_original": mensaje,
            "robot": True
        })

    df = pd.DataFrame(filas)

    if len(df) == 0:
        st.warning(
            "No se encontraron mensajes de Robot 80"
        )
        st.stop()

    df["fecha_dt"] = pd.to_datetime(
        df["fecha"],
        format="%d-%m-%y",
        errors="coerce"
    )

    st.subheader("Filtros")

    col1,col2,col3,col4 = st.columns(4)

    fecha_min = df["fecha_dt"].min()
    fecha_max = df["fecha_dt"].max()

    rango = col1.date_input(
        "Rango de fechas",
        value=(fecha_min,fecha_max)
    )

    aplicaciones = sorted(
        df["aplicacion"]
        .dropna()
        .unique()
    )

    pasos = sorted(
        df["paso"]
        .dropna()
        .unique()
    )

    operadores = sorted(
        df["operadores"]
        .dropna()
        .unique()
    )

    app_sel = col2.multiselect(
        "Aplicación",
        aplicaciones
    )

    paso_sel = col3.multiselect(
        "Paso",
        pasos
    )

    operador_sel = col4.multiselect(
        "Operadores",
        operadores
    )

    df_filtrado = df.copy()

    if len(rango)==2:

        inicio = pd.to_datetime(
            rango[0]
        )

        fin = pd.to_datetime(
            rango[1]
        )

        df_filtrado = df_filtrado[
            (df_filtrado["fecha_dt"]>=inicio)
            &
            (df_filtrado["fecha_dt"]<=fin)
        ]

    if app_sel:

        df_filtrado = df_filtrado[
            df_filtrado["aplicacion"]
            .isin(app_sel)
        ]

    if paso_sel:

        df_filtrado = df_filtrado[
            df_filtrado["paso"]
            .isin(paso_sel)
        ]

    if operador_sel:

        df_filtrado = df_filtrado[
            df_filtrado["operadores"]
            .isin(operador_sel)
        ]

    c1,c2,c3,c4 = st.columns(4)

    c1.metric(
        "Alertas",
        len(df_filtrado)
    )

    c2.metric(
        "Apps afectadas",
        df_filtrado["aplicacion"]
        .nunique()
    )

    c3.metric(
        "Pasos afectados",
        df_filtrado["paso"]
        .nunique()
    )

    c4.metric(
        "Operadores",
        df_filtrado["operadores"]
        .nunique()
    )

    st.subheader(
        "Alertas por día"
    )

    diario = (
        df_filtrado
        .groupby("fecha_dt")
        .size()
        .reset_index(
            name="cantidad"
        )
    )

    fig = px.line(
        diario,
        x="fecha_dt",
        y="cantidad",
        markers=True
    )

    st.plotly_chart(
        fig,
        use_container_width=True
    )

    g1,g2 = st.columns(2)

    with g1:

        st.subheader(
            "Top aplicaciones"
        )

        top_apps = (
            df_filtrado
            .groupby("aplicacion")
            .size()
            .reset_index(
                name="cantidad"
            )
            .sort_values(
                "cantidad"
            )
        )

        fig_apps = px.bar(
            top_apps,
            x="cantidad",
            y="aplicacion",
            orientation="h",
            text="cantidad"
        )

        st.plotly_chart(
            fig_apps,
            use_container_width=True
        )

    with g2:

        st.subheader(
            "Top pasos"
        )

        top_pasos = (
            df_filtrado
            .groupby("paso")
            .size()
            .reset_index(
                name="cantidad"
            )
            .sort_values(
                "cantidad"
            )
        )

        fig_pasos = px.bar(
            top_pasos,
            x="cantidad",
            y="paso",
            orientation="h",
            text="cantidad"
        )

        st.plotly_chart(
            fig_pasos,
            use_container_width=True
        )

    st.subheader(
        "Tabla filtrada"
    )

    columnas = [

        "fecha",
        "hora",
        "aplicacion",
        "paso",
        "operadores",
        "mensaje_error",
        "detalle"

    ]

    st.dataframe(
        df_filtrado[columnas],
        use_container_width=True,
        hide_index=True
    )

    csv = (
        df_filtrado[columnas]
        .to_csv(index=False)
        .encode("utf-8")
    )

    st.download_button(
        "Descargar CSV",
        csv,
        "resultado.csv",
        "text/csv"
    )

else:

    st.info(
        "Sube un TXT"
    )
