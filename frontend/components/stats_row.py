"""La fila superior: procesadas / auto-aprobadas / a revisar."""

import streamlit as st


def render(stats: dict) -> None:
    columnas = st.columns(4)
    tarjetas = [
        ("procesadas", stats.get("procesadas", 0), ""),
        ("auto-aprobadas", stats.get("auto_aprobadas", 0), "stat-ok"),
        ("a revisar", stats.get("a_revisar", 0), "stat-warn"),
        ("escaladas", stats.get("escaladas", 0), ""),
    ]
    for col, (etiqueta, valor, clase) in zip(columnas, tarjetas):
        with col:
            st.markdown(
                f'<div class="stat-label">{etiqueta}</div>'
                f'<div class="stat-valor {clase}">{valor}</div>',
                unsafe_allow_html=True,
            )
