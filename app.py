import streamlit as st
import pandas as pd
import re
import plotly.express as px

st.set_page_config(page_title="Analizador WhatsApp Movizzon", layout="wide")

st.title("Analizador de TXT WhatsApp - Movizzon")

archivo = st.file_uploader("Selecciona archivo TXT", type=["txt"])


def limpiar_texto(x):
    if not isinstance(x, str):
        return ""

    x = x.replace("\u200e", "")
    x = x.replace("\u200f", "")
    x = x.replace("\xa0", " ")
    x = re.sub(r"\s+", " ", x)

    return x.strip()


def extraer_campo(texto, campos):
    if isinstance(campos, str):
        campos = [campos]

    texto = texto.replace("\n", " ")

    campos_posibles = [
        "Aplicacion",
        "Aplicación",
        "Canal",
        "Paso",
        "Operadores",
        "Operadores afectados",
        "Detalle",
        "Mensaje"
    ]

    for campo in campos:
        patron = (
            rf"\*?\s*{re.escape(campo)}\s*:?\s*\*?\s*"
            rf"(.*?)"
            rf"(?=\s\*?\s*("
            + "|".join([re.escape(c) for c in campos_posibles])
            + rf")\s*:?\s*\*?|$)"
        )

        m = re.search(
            patron,
            texto,
            flags=re.IGNORECASE
        )

        if m:
            valor = m.group(1).strip()
            valor = valor.replace("*", "").strip()
            return valor

    return ""


@st.cache_data
def parsear_whatsapp(texto):
    inicio_msg = re.compile(
        r"[\u200e\u200f]?\[(\d{1,2}[-/]\d{1,2}[-/]\d{2}),\s([^\]]+?)\]\s([^:\n]+?):",
        flags=re.MULTILINE
    )

    matches = list(inicio_msg.finditer(texto))
    filas = []

    for i, m in enumerate(matches):
        fecha = limpiar_texto(m.group(1))
        hora = limpiar_texto(m.group(2))
        usuario = limpiar_texto(m.group(3))

        inicio_contenido = m.end()
        fin_contenido = matches[i + 1].start() if i + 1 < len(matches) else len(texto)

        mensaje = limpiar_texto(texto[inicio_contenido:fin_contenido])

        usuario_norm = usuario.lower().replace("~", "").strip()

        if "robot 80" not in usuario_norm:
            continue

        aplicacion = extraer_campo(
            mensaje,
            ["Aplicacion", "Aplicación", "Canal"]
        )

        paso = extraer_campo(
            mensaje,
            "Paso"
        )

        operadores = extraer_campo(
            mensaje,
            ["Operadores afectados", "Operadores"]
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

    return pd.DataFrame(filas)


if archivo:
    texto = archivo.read().decode("utf-8", errors="ignore")

    df_robot = parsear_whatsapp(texto)

    if len(df_robot) == 0:
        st.warning("No se encontraron mensajes cuyo emisor real sea Robot 80.")
        st.stop()

    df = df_robot[
        (df_robot["aplicacion"] != "") |
        (df_robot["paso"] != "") |
        (df_robot["operadores"] != "")
    ].copy()

    if len(df) == 0:
        st.error("Se encontraron mensajes de Robot 80, pero ninguno tiene campos reconocibles.")
        st.dataframe(df_robot, use_container_width=True)
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
        value=(df["fecha_dt"].min(), df["fecha_dt"].max())
    )

    apps = sorted([
        x for x in df["aplicacion"].dropna().unique()
        if x != ""
    ])

    pasos = sorted([
        x for x in df["paso"].dropna().unique()
        if x != ""
    ])

    df_ops_base = df.copy()
    df_ops_base["operador_individual"] = df_ops_base["operadores"].str.split(",")
    df_ops_base = df_ops_base.explode("operador_individual")
    df_ops_base["operador_individual"] = df_ops_base["operador_individual"].str.strip()

    operadores = sorted([
        x for x in df_ops_base["operador_individual"].dropna().unique()
        if x != ""
    ])

    app_sel = col2.multiselect("Aplicación / Canal", apps)
    paso_sel = col3.multiselect("Paso", pasos)
    operador_sel = col4.multiselect("Operador", operadores)

    df_filtrado = df.copy()

    if len(rango) == 2:
        inicio = pd.to_datetime(rango[0])
        fin = pd.to_datetime(rango[1])

        df_filtrado = df_filtrado[
            (df_filtrado["fecha_dt"] >= inicio) &
            (df_filtrado["fecha_dt"] <= fin)
        ]

    if app_sel:
        df_filtrado = df_filtrado[df_filtrado["aplicacion"].isin(app_sel)]

    if paso_sel:
        df_filtrado = df_filtrado[df_filtrado["paso"].isin(paso_sel)]

    if operador_sel:
        patron_operador = "|".join([re.escape(op) for op in operador_sel])

        df_filtrado = df_filtrado[
            df_filtrado["operadores"].str.contains(
                patron_operador,
                na=False,
                regex=True
            )
        ]

    c1, c2, c3, c4 = st.columns(4)

    c1.metric("Alertas Robot 80", len(df_filtrado))
    c2.metric("Apps / Canales afectados", df_filtrado["aplicacion"].nunique())
    c3.metric("Pasos afectados", df_filtrado["paso"].nunique())
    c4.metric("Mensajes Robot 80 detectados", len(df_robot))

    st.subheader("Alertas por día")

    diario = (
        df_filtrado
        .groupby("fecha_dt")
        .size()
        .reset_index(name="cantidad")
        .sort_values("fecha_dt")
    )

    if len(diario) > 0:
        fig_dia = px.line(
            diario,
            x="fecha_dt",
            y="cantidad",
            markers=True,
            text="cantidad"
        )

        fig_dia.update_traces(textposition="top center")

        st.plotly_chart(fig_dia, use_container_width=True)

    g1, g2 = st.columns(2)

    with g1:
        st.subheader("Top aplicaciones / canales")

        top_apps = (
            df_filtrado[df_filtrado["aplicacion"] != ""]
            .groupby("aplicacion")
            .size()
            .reset_index(name="cantidad")
            .sort_values("cantidad", ascending=True)
            .tail(10)
        )

        if len(top_apps) > 0:
            fig_apps = px.bar(
                top_apps,
                x="cantidad",
                y="aplicacion",
                orientation="h",
                text="cantidad"
            )

            st.plotly_chart(fig_apps, use_container_width=True)

    with g2:
        st.subheader("Top pasos")

        top_pasos = (
            df_filtrado[df_filtrado["paso"] != ""]
            .groupby("paso")
            .size()
            .reset_index(name="cantidad")
            .sort_values("cantidad", ascending=True)
            .tail(10)
        )

        if len(top_pasos) > 0:
            fig_pasos = px.bar(
                top_pasos,
                x="cantidad",
                y="paso",
                orientation="h",
                text="cantidad"
            )

            st.plotly_chart(fig_pasos, use_container_width=True)

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

        st.plotly_chart(fig_ops, use_container_width=True)

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

    csv = df_filtrado[columnas].to_csv(index=False).encode("utf-8")

    st.download_button(
        "Descargar CSV",
        csv,
        "resultado_robot_80.csv",
        "text/csv"
    )

else:
    st.info("Sube un TXT")
