"""La traza del agente, colapsada.

No esta en el mockup, pero es lo que demuestra que el dictamen es auditable:
que fases corrieron, cuanto tardaron y cuantos reintentos hizo falta. Colapsada
no ensucia la pantalla y esta ahi cuando alguien pregunta "como llego a esto".

En la fase de extraccion muestra ademas la evidencia de la etapa 1: el texto
crudo que produjo el OCR y la verificacion de procedencia de cada valor. Ese
texto intermedio es la razon de ser del pipeline de dos etapas — con un
multimodal monolitico no habria nada que mostrar aca — y hasta que se expuso
solo era visible desde eval/runner.py.
"""

from html import escape

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
            _evidencia_ocr(paso, f"{key_prefix}{i}")


def _evidencia_ocr(paso: dict, clave: str) -> None:
    """La evidencia de la etapa 1, solo en la fase de extraccion.

    `input` lleva otra cosa en las demas fases (el prompt de triaje es un string),
    y con los motores de prueba no lleva nada: por eso el doble guardia.
    """
    ev = paso.get("input")
    if paso.get("phase") != "extraction" or not isinstance(ev, dict):
        return

    st.markdown(_meta(ev), unsafe_allow_html=True)

    verificados = ev.get("valores_verificados") or {}
    if verificados:
        st.markdown(_procedencia(verificados), unsafe_allow_html=True)

    texto = ev.get("texto_ocr") or ""
    if texto:
        st.markdown(
            '<div class="proc-tit">texto crudo del OCR — etapa 1, '
            "antes de que el modelo lo interprete</div>",
            unsafe_allow_html=True,
        )
        st.text_area(
            "texto crudo del OCR",
            texto,
            height=170,
            disabled=True,
            key=f"ocr_{clave}",
            label_visibility="collapsed",
        )
    elif ev.get("motivo"):
        st.caption(f"Sin texto: {ev['motivo']}.")


def _meta(ev: dict) -> str:
    """Motor, latencia y banderas de calidad del OCR, en una linea."""
    ocr = ev.get("ocr") or {}
    partes = []
    if ocr.get("engine"):
        partes.append(escape(str(ocr["engine"])))
    if ocr.get("duration_s") is not None:
        partes.append(f"{ocr['duration_s']} s")
    if ocr.get("bloques") is not None:
        partes.append(f"{ocr['bloques']} bloques")
    if ocr.get("confianza_media_ocr") is not None:
        partes.append(f"confianza {ocr['confianza_media_ocr']}")
    for bandera in ocr.get("quality_flags") or []:
        partes.append(escape(str(bandera)))

    rot = ev.get("rotacion") or {}
    if rot.get("aplicada"):
        partes.append(f"rotada {rot['aplicada']}°")

    if not partes:
        return ""
    return f'<div class="proc-meta">{" · ".join(partes)}</div>'


def _procedencia(verificados: dict) -> str:
    """Cada valor extraido, buscado dentro del texto crudo del OCR.

    Prueba procedencia, no correccion: un numero leido de la linea equivocada
    aparece en el texto y aun asi es el campo equivocado. Descarta la
    alucinacion, que es lo unico que promete.
    """
    filas = []
    for campo, d in verificados.items():
        if d.get("aparece_en_ocr"):
            marca = '<span class="proc-marca proc-si">✓ está en el OCR</span>'
        else:
            marca = '<span class="proc-marca proc-no">✗ no está en el OCR</span>'
        sim = d.get("similitud")
        sim_html = f'<span class="proc-sim">{sim}</span>' if sim is not None else ""
        filas.append(
            '<div class="proc-fila">'
            f'<span class="proc-campo">{escape(str(campo))}</span>'
            f'<span class="proc-valor">{escape(str(d.get("valor", "")))}</span>'
            f"{marca}{sim_html}"
            "</div>"
        )
    return (
        '<div class="proc-tit">procedencia — cada valor buscado en el texto '
        "del OCR</div>" + "".join(filas)
    )
