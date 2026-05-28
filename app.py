import streamlit as st
import pandas as pd
import re
import plotly.express as px

st.set_page_config(
    page_title="Analizador de Alertas WhatsApp",
    layout="wide"
)

st.title("Analizador de Alertas WhatsApp")

archivo = st.file_uploader(
    "Selecciona archivo TXT",
    type=["txt"]
)


def limpiar_texto(x):
    if not isinstance(x, str):
        return ""

    x = x.replace("\u200e", "")
    x = x.replace("\u200f", "")
    x = x.replace("\xa0", " ")
    x = re.sub(r"\s+", " ", x)

    return x.strip()


def normalizar_fecha(fecha):
    fecha = limpiar_texto(fecha)

    formatos = [
        "%d-%m-%y",
        "%d/%m/%y",
        "%d/%m/%Y",
        "%d-%m-%Y"
    ]

    for fmt in formatos:
        try:
            return pd.to_datetime(fecha, format=fmt)
        except Exception:
            pass

    return pd.NaT


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


def es_emisor_robot(usuario):
    usuario_norm = limpiar_texto(usuario).lower()
    usuario_norm = usuario_norm.replace("~", "").strip()

    emisores_robot = [
        "robot 80",
        "+57 312 3277684",
        "573123277684"
    ]

    return any(e in usuario_norm for e in emisores_robot)


@st.cache_data
def parsear_whatsapp(texto):
    texto = texto.replace("\r\n", "\n").replace("\r", "\n")

    patrones = [
        # Formato con corchetes:
        # [25-11-25, 8:20:52 p. m.] ~ Robot 80:
        re.compile(
            r"[\u200e\u200f]?\[(\d{1,2}[-/]\d{1,2}[-/]\d{2,4}),\s([^\]]+?)\]\s([^:\n]+?):",
            flags=re.MULTILINE
        ),

        # Formato sin corchetes:
        # 1/5/2026, 10:00 a. m. - +57 312 3277684:
        re.compile(
            r"[\u200e\u200f]?(\d{1,2}[-/]\d{1,2}[-/]\d{2,4}),\s(.+?)\s-\s([^:\n]+?):",
            flags=re.MULTILINE
        )
    ]

    matches = []

    for patron in patrones:
        encontrados = list(patron.finditer(texto))
        if len(encontrados) > len(matches):
            matches = encontrados

    filas = []

    for i, m in enumerate(matches):
        fecha = limpiar_texto(m.group(1))
        hora = limpiar_texto(m.group(2))
        usuario = limpiar_texto(m.group(3))

        inicio_contenido = m.end()
        fin_contenido = matches[i + 1].start() if i + 1 < len(matches) else len(texto)

        mensaje = limpiar_texto(texto[inicio_contenido:fin_contenido])

        if not es_emisor_robot(usuario):
            continue

        # Excluir mensajes de espera del bot
        if "esperando el mensaje" in mensaje.lower():
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
    texto = archivo.read().decode(
        "utf-8",
        errors="ignore"
    )

    df_robot = parsear_whatsapp(texto)

    if len(df_robot) == 0:
        st.warning("No se encontraron mensajes cuyo emisor sea Robot 80 o el número robot configurado.")
        st.stop()

    df_robot["fecha_dt"] = df_robot["fecha"].apply(normalizar_fecha)
    df_robot = df_robot.dropna(subset=["fecha_dt"])

    df = df_robot[
        (df_robot["aplicacion"] != "") |
        (df_robot["paso"] != "") |
        (df_robot["operadores"] != "")
    ].copy()

    tiene_estructura = len(df) > 0

    if not tiene_estructura:
        st.warning(
            "Se detectaron mensajes del robot, pero no contienen campos estructurados como Aplicacion, Canal, Paso, Operadores o Detalle. "
            "Probablemente el TXT exportó las alertas como multimedia omitida."
        )

        c1, c2 = st.columns(2)

        c1.metric(
            "Mensajes robot detectados",
            len(df_robot)
        )

        c2.metric(
            "Alertas estructuradas",
            0
        )

        st.subheader("Mensajes detectados")

        columnas_robot = [
            "fecha",
            "hora",
            "usuario",
            "mensaje_original"
        ]

        st.dataframe(
            df_robot[columnas_robot],
            use_container_width=True,
            hide_index=True
        )

        csv_robot = df_robot[columnas_robot].to_csv(
            index=False
        ).encode("utf-8")

        st.download_button(
            "Descargar CSV mensajes robot",
            csv_robot,
            "mensajes_robot_detectados.csv",
            "text/csv"
        )

        st.stop()

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

    app_sel = col2.multiselect(
        "Aplicación / Canal",
        apps
    )

    paso_sel = col3.multiselect(
        "Paso",
        pasos
    )

    operador_sel = col4.multiselect(
        "Operador",
        operadores
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

    c1, c2, c3, c4 = st.columns(4)

    c1.metric(
        "Alertas Robot",
        len(df_filtrado)
    )

    c2.metric(
        "Apps / Canales afectados",
        df_filtrado["aplicacion"].nunique()
    )

    c3.metric(
        "Pasos afectados",
        df_filtrado["paso"].nunique()
    )

    c4.metric(
        "Mensajes robot detectados",
        len(df_robot)
    )

    st.subheader("Alertas por día")

    diario = (
        df_filtrado
        .groupby("fecha_dt")
        .size()
        .reset_index(name="cantidad")
        .sort_values("fecha_dt")
    )

    detalle_dia = (
        df_filtrado[df_filtrado["aplicacion"] != ""]
        .groupby(["fecha_dt", "aplicacion"])
        .size()
        .reset_index(name="cantidad_app")
        .sort_values(["fecha_dt", "cantidad_app"], ascending=[True, False])
    )

    def construir_detalle_aplicaciones(fecha):
        data_fecha = detalle_dia[
            detalle_dia["fecha_dt"] == fecha
        ].copy()

        if len(data_fecha) == 0:
            return "Sin detalle de aplicación/canal"

        top = data_fecha.head(5)

        lineas = []

        for _, row in top.iterrows():
            app = row["aplicacion"]
            cantidad = row["cantidad_app"]
            lineas.append(f"{app}: {cantidad}")

        if len(data_fecha) > 5:
            otros = data_fecha.iloc[5:]["cantidad_app"].sum()
            lineas.append(f"Otros: {otros}")

        return "<br>".join(lineas)

    if len(diario) > 0:

        diario["detalle_apps"] = diario["fecha_dt"].apply(
            construir_detalle_aplicaciones
        )

        fig_dia = px.line(
            diario,
            x="fecha_dt",
            y="cantidad",
            markers=True,
            text="cantidad"
        )

        fig_dia.update_traces(
            textposition="top center",
            customdata=diario["detalle_apps"],
            hovertemplate=(
                "<b>Fecha:</b> %{x|%d-%m-%Y}<br>"
                "<b>Total alertas:</b> %{y}<br><br>"
                "<b>Distribución por aplicación/canal:</b><br>"
                "%{customdata}"
                "<extra></extra>"
            )
        )

        fig_dia.update_layout(
            xaxis_title="Fecha",
            yaxis_title="Cantidad de alertas",
            hoverlabel=dict(
                align="left"
            )
        )

        st.plotly_chart(
            fig_dia,
            use_container_width=True
        )

    else:
        st.info("No hay datos para graficar con los filtros seleccionados.")

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

            fig_apps.update_layout(
                xaxis_title="Cantidad de alertas",
                yaxis_title="Aplicación / Canal"
            )

            st.plotly_chart(
                fig_apps,
                use_container_width=True
            )
        else:
            st.info("No hay aplicaciones/canales para mostrar.")

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

            fig_pasos.update_layout(
                xaxis_title="Cantidad de alertas",
                yaxis_title="Paso"
            )

            st.plotly_chart(
                fig_pasos,
                use_container_width=True
            )
        else:
            st.info("No hay pasos para mostrar.")

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

        fig_ops.update_layout(
            xaxis_title="Cantidad de alertas",
            yaxis_title="Operador"
        )

        st.plotly_chart(
            fig_ops,
            use_container_width=True
        )
    else:
        st.info("No hay operadores para mostrar.")

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

    csv = df_filtrado[columnas].to_csv(
        index=False
    ).encode("utf-8")

    st.download_button(
        "Descargar CSV",
        csv,
        "resultado_robot.csv",
        "text/csv"
    )

else:
    st.info("Sube un TXT")
