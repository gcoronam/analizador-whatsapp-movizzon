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
    m = re.search(patron, texto)
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

        filas.append({
            "fecha": fecha,
            "hora": hora,
            "usuario": usuario,
            "aplicacion": extraer_campo(mensaje, "Aplicacion"),
            "paso": extraer_campo(mensaje, "Paso"),
            "operadores": extraer_campo(mensaje, "Operadores"),
            "detalle": extraer_campo(mensaje, "Detalle"),
            "mensaje_error": extraer_campo(mensaje, "Mensaje"),
            "mensaje_original": mensaje,
            "robot": "Robot" in usuario or "Robot" in mensaje
        })

    df = pd.DataFrame(filas)

    df["fecha_dt"] = pd.to_datetime(
        df["fecha"],
        format="%d-%m-%y",
        errors="coerce"
    )

    df_alertas = df[
        (df["aplicacion"] != "") |
        (df["paso"] != "") |
        (df["operadores"] != "")
    ].copy()

    st.subheader("Filtros")

    colf1, colf2, colf3, colf4 = st.columns(4)

    fecha_min = df_alertas["fecha_dt"].min()
    fecha_max = df_alertas["fecha_dt"].max()

    rango_fechas = colf1.date_input(
        "Rango de fechas",
        value=(fecha_min, fecha_max)
    )

    apps = sorted([
        x for x in df_alertas["aplicacion"].dropna().unique()
        if x != ""
    ])

    pasos = sorted([
        x for x in df_alertas["paso"].dropna().unique()
        if x != ""
    ])

    operadores = sorted([
        x for x in df_alertas["operadores"].dropna().unique()
        if x != ""
    ])

    app_sel = colf2.multiselect("Aplicación", apps)
    paso_sel = colf3.multiselect("Paso", pasos)
    operador_sel = colf4.multiselect("Operadores", operadores)

    df_filtrado = df_alertas.copy()

    if len(rango_fechas) == 2:
        inicio = pd.to_datetime(rango_fechas[0])
        fin = pd.to_datetime(rango_fechas[1])

        df_filtrado = df_filtrado[
            (df_filtrado["fecha_dt"] >= inicio) &
            (df_filtrado["fecha_dt"] <= fin)
        ]

    if app_sel:
        df_filtrado = df_filtrado[
            df_filtrado["aplicacion"].isin(app_sel)
        ]

    if paso_sel:
        df_filtrado = df_filtrado[
            df_filtrado["paso"].isin(paso_sel)
        ]

    if operador_sel:
        df_filtrado = df_filtrado[
            df_filtrado["operadores"].isin(operador_sel)
        ]

    c1, c2, c3, c4 = st.columns(4)

    c1.metric("Mensajes totales", len(df))
    c2.metric("Alertas filtradas", len(df_filtrado))
    c3.metric("Apps afectadas", df_filtrado["aplicacion"].nunique())
    c4.metric("Pasos afectados", df_filtrado["paso"].nunique())

    st.subheader("Alertas por día")

    alertas_dia = (
        df_filtrado
        .groupby("fecha_dt")
        .size()
        .reset_index(name="alertas")
        .sort_values("fecha_dt")
    )

    if len(alertas_dia) > 0:
        fig_dia = px.line(
            alertas_dia,
            x="fecha_dt",
            y="alertas",
            markers=True,
            title="Cantidad de alertas por fecha"
        )

        st.plotly_chart(
            fig_dia,
            use_container_width=True
        )

    colg1, colg2 = st.columns(2)

    with colg1:
        st.subheader("Top aplicaciones")

        top_apps = (
            df_filtrado
            .groupby("aplicacion")
            .size()
            .reset_index(name="alertas")
            .sort_values("alertas", ascending=True)
            .tail(10)
        )

        if len(top_apps) > 0:
            fig_apps = px.bar(
                top_apps,
                x="alertas",
                y="aplicacion",
                orientation="h",
                text="alertas",
                title="Aplicaciones con más alertas"
            )

            st.plotly_chart(
                fig_apps,
                use_container_width=True
            )

    with colg2:
        st.subheader("Top pasos afectados")

        top_pasos = (
            df_filtrado
            .groupby("paso")
            .size()
            .reset_index(name="alertas")
            .sort_values("alertas", ascending=True)
            .tail(10)
        )

        if len(top_pasos) > 0:
            fig_pasos = px.bar(
                top_pasos,
                x="alertas",
                y="paso",
                orientation="h",
                text="alertas",
                title="Pasos con más alertas"
            )

            st.plotly_chart(
                fig_pasos,
                use_container_width=True
            )

    st.subheader("Matriz fecha vs aplicación")

    matriz_fecha_app = pd.pivot_table(
        df_filtrado,
        index="fecha",
        columns="aplicacion",
        values="paso",
        aggfunc="count",
        fill_value=0
    )

    st.dataframe(
        matriz_fecha_app,
        use_container_width=True
    )

    st.subheader("Operadores afectados")

    df_ops = df_filtrado.copy()
    df_ops["operador_individual"] = df_ops["operadores"].str.split(",")
    df_ops = df_ops.explode("operador_individual")
    df_ops["operador_individual"] = df_ops["operador_individual"].str.strip()

    top_ops = (
        df_ops[df_ops["operador_individual"] != ""]
        .groupby("operador_individual")
        .size()
        .reset_index(name="alertas")
        .sort_values("alertas", ascending=True)
    )

    if len(top_ops) > 0:
        fig_ops = px.bar(
            top_ops,
            x="alertas",
            y="operador_individual",
            orientation="h",
            text="alertas",
            title="Operadores con más alertas"
        )

        st.plotly_chart(
            fig_ops,
            use_container_width=True
        )

    st.subheader("Tabla filtrada")

    columnas_visibles = [
        "fecha",
        "hora",
        "usuario",
        "aplicacion",
        "paso",
        "operadores",
        "mensaje_error",
        "detalle"
    ]

    st.dataframe(
        df_filtrado[columnas_visibles],
        use_container_width=True,
        hide_index=True
    )

    csv = df_filtrado[columnas_visibles].to_csv(
        index=False
    ).encode("utf-8")

    st.download_button(
        "Descargar tabla filtrada CSV",
        csv,
        "analisis_whatsapp_filtrado.csv",
        "text/csv"
    )

else:
    st.info("Sube un TXT")
