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


def extraer_campo(texto, campos):
    if isinstance(campos, str):
        campos = [campos]

    for campo in campos:
        patron = rf"\*?{campo}\*?:\s*(.*)"
        m = re.search(
            patron,
            texto,
            flags=re.IGNORECASE
        )
        if m:
            return m.group(1).strip()

    return ""


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

        # Considerar Robot 80 aunque venga como usuario o dentro del mensaje
        if "Robot 80" not in usuario and "Robot 80" not in mensaje:
            continue

        aplicacion = extraer_campo(
            mensaje,
            ["Aplicacion", "Aplicación"]
        )

        paso = extraer_campo(
            mensaje,
            "Paso"
        )

        operadores = extraer_campo(
            mensaje,
            "Operadores"
        )

        detalle = extraer_campo(
            mensaje,
            "Detalle"
        )

        mensaje_error = extraer_campo(
            mensaje,
            "Mensaje"
        )

        filas.append({
            "fecha": fecha,
            "hora": hora,
            "usuario": usuario,
            "aplicacion": aplicacion,
            "paso": paso,
            "operadores": operadores,
            "detalle": detalle,
            "mensaje_error": mensaje_error,
            "mensaje_original": mensaje
        })

    df_robot = pd.DataFrame(filas)

    if len(df_robot) == 0:
        st.warning("No se encontraron mensajes relacionados a Robot 80.")
        st.stop()

    # Aceptar alertas que tengan al menos un campo útil
    df = df_robot[
        (df_robot["aplicacion"] != "") |
        (df_robot["paso"] != "") |
        (df_robot["operadores"] != "")
    ].copy()

    mensajes_descartados = len(df_robot) - len(df)

    if len(df) == 0:
        st.error("Se encontraron mensajes de Robot 80, pero ninguno con campos útiles.")
        st.dataframe(
            df_robot,
            use_container_width=True
        )
        st.stop()

    df["fecha_dt"] = pd.to_datetime(
        df["fecha"],
        format="%d-%m-%y",
        errors="coerce"
    )

    st.subheader("Filtros")

    col1, col2, col3, col4 = st.columns(4)

    rango = col1.date_input(
        "Rango de fechas",
        value=(
            df["fecha_dt"].min(),
            df["fecha_dt"].max()
        )
    )

    apps = sorted([
        x for x in df["aplicacion"].dropna().unique()
        if x != ""
    ])

    pasos = sorted([
        x for x in df["paso"].dropna().unique()
        if x != ""
    ])

    # Operadores individuales para filtro
    df_ops_base = df.copy()
    df_ops_base["operador_individual"] = df_ops_base["operadores"].str.split(",")
    df_ops_base = df_ops_base.explode("operador_individual")
    df_ops_base["operador_individual"] = df_ops_base["operador_individual"].str.strip()

    operadores_ind = sorted([
        x for x in df_ops_base["operador_individual"].dropna().unique()
        if x != ""
    ])

    app_sel = col2.multiselect(
        "Aplicación",
        apps
    )

    paso_sel = col3.multiselect(
        "Paso",
        pasos
    )

    operador_sel = col4.multiselect(
        "Operador",
        operadores_ind
    )

    df_filtrado = df.copy()

    if len(rango) == 2:
        inicio = pd.to_datetime(rango[0])
        fin = pd.to_datetime(rango[1])

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
        patron_operador = "|".join([
            re.escape(op)
            for op in operador_sel
        ])

        df_filtrado = df_filtrado[
            df_filtrado["operadores"].str.contains(
                patron_operador,
                na=False,
                regex=True
            )
        ]

    c1, c2, c3, c4, c5 = st.columns(5)

    c1.metric(
        "Alertas",
        len(df_filtrado)
    )

    c2.metric(
        "Apps afectadas",
        df_filtrado["aplicacion"].nunique()
    )

    c3.metric(
        "Pasos afectados",
        df_filtrado["paso"].nunique()
    )

    c4.metric(
        "Mensajes Robot 80",
        len(df_robot)
    )

    c5.metric(
        "Descartados",
        mensajes_descartados
    )

    st.subheader("Alertas por día")

    diario = (
        df_filtrado
        .groupby("fecha_dt")
        .size()
        .reset_index(name="cantidad")
        .sort_values("fecha_dt")
    )

    if len(diario) > 0:
        fig = px.line(
            diario,
            x="fecha_dt",
            y="cantidad",
            markers=True,
            text="cantidad"
        )

        fig.update_traces(
            textposition="top center"
        )

        st.plotly_chart(
            fig,
            use_container_width=True
        )

    g1, g2 = st.columns(2)

    with g1:
        st.subheader("Top aplicaciones")

        top_apps = (
            df_filtrado[df_filtrado["aplicacion"] != ""]
            .groupby("aplicacion")
            .size()
            .reset_index(name="cantidad")
            .sort_values("cantidad", ascending=True)
        )

        if len(top_apps) > 0:
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
        st.subheader("Top pasos")

        top_pasos = (
            df_filtrado[df_filtrado["paso"] != ""]
            .groupby("paso")
            .size()
            .reset_index(name="cantidad")
            .sort_values("cantidad", ascending=True)
        )

        if len(top_pasos) > 0:
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

    st.subheader("Operadores afectados")

    df_ops = df_filtrado.copy()
    df_ops["operador_individual"] = df_ops["operadores"].str.split(",")
    df_ops = df_ops.explode("operador_individual")
    df_ops["operador_individual"] = df_ops["operador_individual"].str.strip()

    top_ops = (
        df_ops[df_ops["operador_individual"] != ""]
        .groupby("operador_individual")
        .size()
        .reset_index(name="cantidad")
        .sort_values("cantidad", ascending=True)
    )

    if len(top_ops) > 0:
        fig_ops = px.bar(
            top_ops,
            x="cantidad",
            y="operador_individual",
            orientation="h",
            text="cantidad"
        )

        st.plotly_chart(
            fig_ops,
            use_container_width=True
        )

    st.subheader("Tabla filtrada")

    columnas = [
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
        "resultado_robot_80.csv",
        "text/csv"
    )

else:

    st.info("Sube un TXT")
