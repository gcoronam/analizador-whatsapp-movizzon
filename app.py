import streamlit as st
import pandas as pd
import re
import plotly.express as px
from io import BytesIO
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak
)

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
        "Dispositivos",
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
            ["Operadores afectados", "Operadores", "Dispositivos"]
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


def detectar_tecnologia(aplicacion):
    app = limpiar_texto(aplicacion).lower()

    # Orden intencional:
    # Huawei antes que Android, porque algunos flujos pueden mencionar APP pero son Huawei.
    if "huawei" in app:
        return "Huawei"
    if "android" in app:
        return "Android"
    if "ios" in app:
        return "iOS"
    if "web" in app:
        return "Web"

    return "Sin tecnología"


def detectar_canal(aplicacion):
    app = limpiar_texto(aplicacion).lower()

    if "web" in app:
        return "Web"
    if "android" in app or "ios" in app or "huawei" in app or "app" in app:
        return "App"

    return "Sin canal identificado"


def detectar_tipo_alerta(mensaje_error):
    mensaje = limpiar_texto(mensaje_error).lower()

    if "lentitud" in mensaje:
        return "Lentitud"

    return "Afectación"


def calcular_uptime(total_afectacion, minutos_periodo=1440):
    minutos_afectacion = total_afectacion * 5
    uptime = ((minutos_periodo - minutos_afectacion) / minutos_periodo) * 100

    if uptime < 0:
        uptime = 0

    return uptime, minutos_afectacion


def formatear_porcentaje(valor):
    return f"{valor:.2f}%".replace(".", ",")


def limitar_texto(texto, largo=80):
    texto = limpiar_texto(texto)

    if len(texto) <= largo:
        return texto

    return texto[:largo - 3] + "..."


def construir_resumen_ejecutivo(df_reporte, cliente):
    total_alertas = len(df_reporte)
    total_lentitud = len(df_reporte[df_reporte["tipo_alerta"] == "Lentitud"])
    total_afectacion = len(df_reporte[df_reporte["tipo_alerta"] == "Afectación"])
    uptime_global, minutos_afectacion = calcular_uptime(total_afectacion)

    canal_resumen = (
        df_reporte
        .groupby("canal")
        .size()
        .reset_index(name="cantidad")
        .sort_values("cantidad", ascending=False)
    )

    texto_canales = []

    for _, row in canal_resumen.iterrows():
        texto_canales.append(f"{row['cantidad']} alertas en {row['canal']}")

    detalle_canales = ", ".join(texto_canales)

    resumen = (
        f"Durante la jornada analizada se registraron {total_alertas} alertas en {cliente}: "
        f"{detalle_canales}. "
        f"El desglose general fue de {total_lentitud} alertas de lentitud y "
        f"{total_afectacion} alertas de afectación con impacto en el uptime, "
        f"que representaron {minutos_afectacion} minutos de afectación. "
        f"El uptime global estimado fue de {formatear_porcentaje(uptime_global)}."
    )

    return resumen


def crear_tabla_kpis(df_reporte, agrupacion="canal"):
    resumen = (
        df_reporte
        .groupby(agrupacion)
        .agg(
            total_alertas=("tipo_alerta", "count"),
            alertas_lentitud=("tipo_alerta", lambda x: (x == "Lentitud").sum()),
            alertas_afectacion=("tipo_alerta", lambda x: (x == "Afectación").sum())
        )
        .reset_index()
    )

    resumen["minutos_afectacion"] = resumen["alertas_afectacion"] * 5
    resumen["uptime"] = resumen["alertas_afectacion"].apply(
        lambda x: formatear_porcentaje(calcular_uptime(x)[0])
    )

    return resumen


def crear_barra_superior():
    barra = Table(
        [["", "", ""]],
        colWidths=[5.5 * cm, 5.5 * cm, 7 * cm],
        rowHeights=[0.25 * cm]
    )

    barra.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#D71920")),
        ("BACKGROUND", (1, 0), (1, 0), colors.HexColor("#F6A400")),
        ("BACKGROUND", (2, 0), (2, 0), colors.HexColor("#0067A6")),
        ("BOX", (0, 0), (-1, -1), 0, colors.white),
    ]))

    return barra


def generar_informe_pdf(df_filtrado, cliente="Cliente", fuente="Grupo de Alertas Globales Whatsapp"):
    buffer = BytesIO()

    df_reporte = df_filtrado.copy()

    if len(df_reporte) == 0:
        return buffer

    df_reporte["canal"] = df_reporte["aplicacion"].apply(detectar_canal)
    df_reporte["tecnologia"] = df_reporte["aplicacion"].apply(detectar_tecnologia)
    df_reporte["tipo_alerta"] = df_reporte["mensaje_error"].apply(detectar_tipo_alerta)

    fecha_min = df_reporte["fecha_dt"].min()
    fecha_max = df_reporte["fecha_dt"].max()

    if fecha_min == fecha_max:
        fecha_analizada = fecha_min.strftime("%d/%m/%Y")
    else:
        fecha_analizada = f"{fecha_min.strftime('%d/%m/%Y')} al {fecha_max.strftime('%d/%m/%Y')}"

    fecha_emision = datetime.now().strftime("%d/%m/%Y")

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=1.2 * cm,
        leftMargin=1.2 * cm,
        topMargin=1.2 * cm,
        bottomMargin=1.2 * cm
    )

    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle(
        name="TituloMovizzon",
        parent=styles["Title"],
        fontSize=24,
        leading=28,
        textColor=colors.HexColor("#263442"),
        spaceAfter=18
    ))

    styles.add(ParagraphStyle(
        name="Subtitulo",
        parent=styles["Heading2"],
        fontSize=15,
        leading=18,
        textColor=colors.HexColor("#263442"),
        spaceBefore=14,
        spaceAfter=8
    ))

    styles.add(ParagraphStyle(
        name="TextoNormal",
        parent=styles["BodyText"],
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#263442")
    ))

    styles.add(ParagraphStyle(
        name="TextoPequeno",
        parent=styles["BodyText"],
        fontSize=7,
        leading=9,
        textColor=colors.HexColor("#263442")
    ))

    elementos = []

    elementos.append(crear_barra_superior())
    elementos.append(Spacer(1, 0.8 * cm))
    elementos.append(Paragraph("Informe Diario Movizzon", styles["TituloMovizzon"]))

    metadata = [
        ["FECHA ANALIZADA", "HORARIO CONSIDERADO", "FUENTE", "FECHA DE EMISIÓN"],
        [fecha_analizada, "00:00 a 23:59 hrs", fuente, fecha_emision]
    ]

    tabla_meta = Table(
        metadata,
        colWidths=[4.4 * cm, 4.4 * cm, 5.2 * cm, 4.2 * cm]
    )

    tabla_meta.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F2F5F7")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#263442")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#D9DEE3")),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D9DEE3")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
    ]))

    elementos.append(tabla_meta)
    elementos.append(Spacer(1, 0.4 * cm))

    elementos.append(Paragraph("1 Resumen ejecutivo", styles["Subtitulo"]))

    resumen_ejecutivo = construir_resumen_ejecutivo(
        df_reporte,
        cliente
    )

    caja_resumen = Table(
        [[Paragraph(resumen_ejecutivo, styles["TextoNormal"])]],
        colWidths=[18.2 * cm]
    )

    caja_resumen.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#D9DEE3")),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))

    elementos.append(caja_resumen)
    elementos.append(Spacer(1, 0.4 * cm))

    total_alertas = len(df_reporte)
    total_lentitud = len(df_reporte[df_reporte["tipo_alerta"] == "Lentitud"])
    total_afectacion = len(df_reporte[df_reporte["tipo_alerta"] == "Afectación"])
    uptime_global, minutos_afectacion = calcular_uptime(total_afectacion)

    elementos.append(Paragraph("2 KPIs de la jornada", styles["Subtitulo"]))

    kpi_data = [
        ["Total alertas", "Alertas de lentitud", "Alertas de Afectación", "Minutos de Afectación", "Uptime"],
        [
            str(total_alertas),
            str(total_lentitud),
            str(total_afectacion),
            f"{minutos_afectacion} min",
            formatear_porcentaje(uptime_global)
        ]
    ]

    tabla_kpi = Table(
        kpi_data,
        colWidths=[3.6 * cm, 3.6 * cm, 3.8 * cm, 3.8 * cm, 3.4 * cm]
    )

    tabla_kpi.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EAF2F8")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("FONTSIZE", (0, 1), (-1, 1), 16),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#D9DEE3")),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D9DEE3")),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))

    elementos.append(tabla_kpi)
    elementos.append(Spacer(1, 0.25 * cm))

    nota = (
        "Nota: El Uptime considera 5 minutos de afectación por cada alerta de afectación. "
        "Las alertas de lentitud no descuentan Uptime."
    )

    elementos.append(Paragraph(nota, styles["TextoPequeno"]))

    elementos.append(Paragraph("3 KPIs por canal", styles["Subtitulo"]))

    kpis_canal = crear_tabla_kpis(df_reporte, "canal")

    data_canal = [
        ["Canal", "Total alertas", "Alertas de lentitud", "Alertas de Afectación", "Minutos de Afectación", "Uptime"]
    ]

    for _, row in kpis_canal.iterrows():
        data_canal.append([
            row["canal"],
            str(row["total_alertas"]),
            str(row["alertas_lentitud"]),
            str(row["alertas_afectacion"]),
            f"{row['minutos_afectacion']} min",
            row["uptime"]
        ])

    tabla_canal = Table(
        data_canal,
        colWidths=[4.2 * cm, 2.5 * cm, 3 * cm, 3.2 * cm, 3.4 * cm, 2 * cm]
    )

    tabla_canal.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EAF2F8")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#D9DEE3")),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D9DEE3")),
        ("ALIGN", (1, 1), (-1, -1), "CENTER"),
    ]))

    elementos.append(tabla_canal)
    elementos.append(PageBreak())

    elementos.append(crear_barra_superior())
    elementos.append(Spacer(1, 0.8 * cm))
    elementos.append(Paragraph("4 Distribución de alertas", styles["Subtitulo"]))

    top_etapas = (
        df_reporte
        .groupby(["aplicacion", "paso"])
        .size()
        .reset_index(name="total_alertas")
        .sort_values("total_alertas", ascending=False)
        .head(10)
    )

    top_etapas["participacion"] = top_etapas["total_alertas"] / total_alertas

    data_top = [
        ["Posición", "Flujo", "Etapa", "Total alertas", "Participación"]
    ]

    for idx, row in top_etapas.reset_index(drop=True).iterrows():
        data_top.append([
            str(idx + 1),
            Paragraph(limitar_texto(row["aplicacion"], 55), styles["TextoPequeno"]),
            Paragraph(limitar_texto(row["paso"], 45), styles["TextoPequeno"]),
            str(row["total_alertas"]),
            formatear_porcentaje(row["participacion"] * 100)
        ])

    tabla_top = Table(
        data_top,
        colWidths=[1.5 * cm, 6 * cm, 4 * cm, 3 * cm, 3 * cm]
    )

    tabla_top.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EAF2F8")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#D9DEE3")),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D9DEE3")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (0, 1), (0, -1), "CENTER"),
        ("ALIGN", (3, 1), (-1, -1), "CENTER"),
    ]))

    elementos.append(Paragraph("Top etapas con más alertas", styles["TextoNormal"]))
    elementos.append(tabla_top)
    elementos.append(Spacer(1, 0.5 * cm))

    tecnologia = (
        df_reporte
        .groupby("tecnologia")
        .size()
        .reset_index(name="total_alertas")
        .sort_values("total_alertas", ascending=False)
    )

    tecnologia["participacion"] = tecnologia["total_alertas"] / total_alertas

    data_tec = [
        ["Tecnología", "Total alertas", "Participación"]
    ]

    for _, row in tecnologia.iterrows():
        data_tec.append([
            row["tecnologia"],
            str(row["total_alertas"]),
            formatear_porcentaje(row["participacion"] * 100)
        ])

    tabla_tec = Table(
        data_tec,
        colWidths=[6 * cm, 4 * cm, 4 * cm]
    )

    tabla_tec.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EAF2F8")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#D9DEE3")),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D9DEE3")),
        ("ALIGN", (1, 1), (-1, -1), "CENTER"),
    ]))

    elementos.append(Paragraph("Alertas por tecnología", styles["TextoNormal"]))
    elementos.append(tabla_tec)
    elementos.append(PageBreak())

    elementos.append(crear_barra_superior())
    elementos.append(Spacer(1, 0.8 * cm))
    elementos.append(Paragraph("5 Hallazgos relevantes", styles["Subtitulo"]))

    hallazgos = []

    for canal in df_reporte["canal"].dropna().unique():
        df_canal = df_reporte[df_reporte["canal"] == canal]

        total_canal = len(df_canal)
        lentitud_canal = len(df_canal[df_canal["tipo_alerta"] == "Lentitud"])
        afectacion_canal = len(df_canal[df_canal["tipo_alerta"] == "Afectación"])
        uptime_canal, _ = calcular_uptime(afectacion_canal)

        tecnologia_top = (
            df_canal
            .groupby("tecnologia")
            .size()
            .sort_values(ascending=False)
        )

        paso_top = (
            df_canal
            .groupby("paso")
            .size()
            .sort_values(ascending=False)
        )

        mensaje_top = (
            df_canal
            .groupby("mensaje_error")
            .size()
            .sort_values(ascending=False)
        )

        hallazgos.append(
            f"<b>{canal}</b> - {total_canal} alertas - uptime {formatear_porcentaje(uptime_canal)}"
        )

        if lentitud_canal >= afectacion_canal:
            hallazgos.append(
                "Predominaron las alertas de lentitud, por lo que el impacto principal se asocia a degradación de la experiencia más que a afectación del uptime."
            )
        else:
            hallazgos.append(
                "Predominaron las alertas de afectación con impacto en el uptime, por lo que conviene priorizar la revisión de los flujos que las originaron."
            )

        if len(tecnologia_top) > 0:
            hallazgos.append(
                f"La tecnología con más alertas fue {tecnologia_top.index[0]}, con {tecnologia_top.iloc[0]} alertas."
            )

        if len(paso_top) > 0:
            hallazgos.append(
                f"El paso con mayor recurrencia fue {paso_top.index[0]}, con {paso_top.iloc[0]} alertas."
            )

        if len(mensaje_top) > 0 and limpiar_texto(mensaje_top.index[0]) != "":
            hallazgos.append(
                f"El mensaje más frecuente fue '{mensaje_top.index[0]}', presente en {mensaje_top.iloc[0]} alertas."
            )

        hallazgos.append("<br/>")

    for h in hallazgos:
        elementos.append(Paragraph(h, styles["TextoNormal"]))
        elementos.append(Spacer(1, 0.12 * cm))

    elementos.append(PageBreak())

    elementos.append(crear_barra_superior())
    elementos.append(Spacer(1, 0.8 * cm))
    elementos.append(Paragraph("6 Detalle de alertas de la jornada", styles["Subtitulo"]))
    elementos.append(Paragraph("Alertas extraídas desde el chat exportado. Una fila por alerta.", styles["TextoNormal"]))
    elementos.append(Spacer(1, 0.3 * cm))

    df_detalle = df_reporte.sort_values(["fecha_dt", "hora"]).copy()

    data_detalle = [
        ["Fecha", "Hora alerta", "Flujo", "Canal", "Etapa", "Tecnología", "Operadores", "Mensaje"]
    ]

    for _, row in df_detalle.iterrows():
        data_detalle.append([
            row["fecha_dt"].strftime("%d/%m/%Y"),
            limpiar_texto(row["hora"])[:5],
            Paragraph(limitar_texto(row["aplicacion"], 45), styles["TextoPequeno"]),
            Paragraph(limitar_texto(row["canal"], 25), styles["TextoPequeno"]),
            Paragraph(limitar_texto(row["paso"], 35), styles["TextoPequeno"]),
            Paragraph(limitar_texto(row["tecnologia"], 20), styles["TextoPequeno"]),
            Paragraph(limitar_texto(row["operadores"], 45), styles["TextoPequeno"]),
            Paragraph(limitar_texto(row["mensaje_error"] if row["mensaje_error"] else "Sin mensaje", 55), styles["TextoPequeno"])
        ])

    tabla_detalle = Table(
        data_detalle,
        colWidths=[
            1.8 * cm,
            1.6 * cm,
            3.4 * cm,
            2.1 * cm,
            2.7 * cm,
            2.1 * cm,
            2.8 * cm,
            2.8 * cm
        ],
        repeatRows=1
    )

    tabla_detalle.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EAF2F8")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 6),
        ("BOX", (0, 0), (-1, -1), 0.4, colors.HexColor("#D9DEE3")),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D9DEE3")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))

    elementos.append(tabla_detalle)

    doc.build(elementos)
    buffer.seek(0)

    return buffer


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

    df["canal"] = df["aplicacion"].apply(detectar_canal)
    df["tecnologia"] = df["aplicacion"].apply(detectar_tecnologia)
    df["tipo_alerta"] = df["mensaje_error"].apply(detectar_tipo_alerta)

    tiene_estructura = len(df) > 0

    if not tiene_estructura:
        st.warning(
            "Se detectaron mensajes del robot, pero no contienen campos estructurados como Aplicacion, Canal, Paso, Operadores, Dispositivos o Detalle. "
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

    col1, col2, col3, col4, col5 = st.columns(5)

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

    tecnologias = sorted([
        x for x in df["tecnologia"].dropna().unique()
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
        "Operador / Dispositivo",
        operadores
    )

    tecnologia_sel = col5.multiselect(
        "Tecnología",
        tecnologias
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

    if tecnologia_sel:
        df_filtrado = df_filtrado[
            df_filtrado["tecnologia"].isin(tecnologia_sel)
        ]

    c1, c2, c3, c4, c5 = st.columns(5)

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
        "Tecnologías afectadas",
        df_filtrado["tecnologia"].nunique()
    )

    c5.metric(
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

    st.subheader("Operadores / dispositivos afectados")

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
            yaxis_title="Operador / Dispositivo"
        )

        st.plotly_chart(
            fig_ops,
            use_container_width=True
        )
    else:
        st.info("No hay operadores/dispositivos para mostrar.")

    st.subheader("Alertas por tecnología")

    top_tecnologia = (
        df_filtrado[df_filtrado["tecnologia"] != ""]
        .groupby("tecnologia")
        .size()
        .reset_index(name="cantidad")
        .sort_values("cantidad", ascending=True)
    )

    if len(top_tecnologia) > 0:
        fig_tecnologia = px.bar(
            top_tecnologia,
            x="cantidad",
            y="tecnologia",
            orientation="h",
            text="cantidad"
        )

        fig_tecnologia.update_layout(
            xaxis_title="Cantidad de alertas",
            yaxis_title="Tecnología"
        )

        st.plotly_chart(
            fig_tecnologia,
            use_container_width=True
        )
    else:
        st.info("No hay tecnología para mostrar.")

    st.subheader("Informe PDF")

    col_pdf1, col_pdf2 = st.columns(2)

    cliente_reporte = col_pdf1.text_input(
        "Nombre cliente / proyecto",
        value="BancoEstado"
    )

    fuente_reporte = col_pdf2.text_input(
        "Fuente del informe",
        value="Grupo de Alertas Globales Whatsapp"
    )

    if len(df_filtrado) > 0:
        pdf_buffer = generar_informe_pdf(
            df_filtrado,
            cliente=cliente_reporte,
            fuente=fuente_reporte
        )

        st.download_button(
            label="Descargar informe PDF",
            data=pdf_buffer,
            file_name="informe_diario_movizzon.pdf",
            mime="application/pdf"
        )
    else:
        st.info("No hay datos filtrados para generar el informe PDF.")

    st.subheader("Tabla filtrada")

    columnas = [
        "fecha",
        "hora",
        "usuario",
        "aplicacion",
        "canal",
        "tecnologia",
        "paso",
        "operadores",
        "tipo_alerta",
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
