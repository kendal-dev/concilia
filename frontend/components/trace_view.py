"""La traza del agente, colapsada.

No esta en el mockup, pero es lo que demuestra que el dictamen es auditable:
que fases corrieron, cuanto tardaron y cuantos reintentos hizo falta. Colapsada
no ensucia la pantalla y esta ahi cuando alguien pregunta "como llego a esto".
"""

import streamlit as st

_NOMBRE_FASE = {
    "extraction": "Lectura del documento",
    "lookup": "Consulta al ERP",
    "verification": "Verificación en código",
    "reasoning": "Redacción de la nota",
    "persist": "Registro del dictamen",
}


def render(pasos: list[dict], key_prefix: str = "") -> None:
    if not pasos:
        return

    reintentos = sum(p.get("retries", 0) for p in pasos)
    titulo = "Cómo llegó a esto"
    if reintentos:
        titulo += f" · {reintentos} reintento(s) del modelo"

    with st.expander(titulo, expanded=False):
        for i, paso in enumerate(pasos, 1):
            nombre = _NOMBRE_FASE.get(paso["phase"], paso["phase"])
            linea = f"**{i}. {nombre}** — {paso['summary']}"
            if paso.get("duration_ms"):
                linea += f"  ·  {paso['duration_ms']} ms"
            st.markdown(linea)
            if paso.get("error"):
                st.caption(f"⚠ {paso['error']}")
