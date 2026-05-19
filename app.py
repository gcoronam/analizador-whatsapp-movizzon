import streamlit as st
import pandas as pd
import re

st.title("Analizador de TXT WhatsApp - Movizzon")

archivo = st.file_uploader("Selecciona archivo TXT", type=["txt"])

def extraer_campo(texto, campo):
    patron = rf"\*{campo}:\*\s*(.*)"
    m = re.search(patron, texto)
    return m.group(1).strip() if m else ""

if archivo:
    texto = archivo.read().decode("utf-8", errors="ignore")

    patron = r"\[(\d{1,2}[-/]\d{1,2}[-/]\d{2}),\s([^]]+?)\]\s(.+?):\s(.*?)(?=\n\[\d{1,2}[-/]\d{1,2}[-/]\d{2},|\Z)"

    matches = re.findall(patron, texto, flags=re.DOTALL)

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

    st.write("Mensajes detectados:", len(df))

    if len(df) == 0:
        st.error("No se detectaron mensajes. Mostrando primeras líneas del TXT para ajustar formato:")
        st.code(texto[:2000])
    else:
        df_robot = df[df["robot"] == True]

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Mensajes", len(df))
        c2.metric("Alertas robot", len(df_robot))
        c3.metric("Apps", df_robot["aplicacion"].nunique())
        c4.metric("Pasos", df_robot["paso"].nunique())

        st.subheader("Detalle completo")
        st.dataframe(df, use_container_width=True)

else:
    st.info("Sube un TXT")
