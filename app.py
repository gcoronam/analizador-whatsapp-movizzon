import streamlit as st
import pandas as pd
import re

st.title("Analizador de TXT WhatsApp - Movizzon")

archivo = st.file_uploader("Selecciona archivo TXT", type=["txt"])

if archivo:

    texto = archivo.read().decode("utf-8")

    patron = r"(\d{1,2}-\d{1,2}-\d{2}), (\d{1,2}:\d{1,2}:\d{1,2}) - (.*?): (.*)"

    datos=[]

    for linea in texto.split("\n"):

        m = re.match(patron,linea)

        if m:

            fecha,hora,usuario,mensaje = m.groups()

            robot = "Robot" in mensaje

            datos.append([
                fecha,
                hora,
                usuario,
                mensaje,
                robot
            ])

    df = pd.DataFrame(
        datos,
        columns=[
            "fecha",
            "hora",
            "usuario",
            "mensaje",
            "robot"
        ]
    )

    c1,c2,c3 = st.columns(3)

    c1.metric(
        "Mensajes",
        len(df)
    )

    c2.metric(
        "Alertas robot",
        df["robot"].sum()
    )

    c3.metric(
        "Usuarios",
        df["usuario"].nunique()
    )

    st.subheader("Tabla")

    st.dataframe(
        df,
        use_container_width=True
    )

else:

    st.info("Sube un TXT")
