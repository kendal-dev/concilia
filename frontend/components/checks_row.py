"""La fila "verificado por codigo".

Es la pieza que separa visualmente lo que calculo Python de lo que redacto el
modelo. Todo lo que aparece aca salio de backend/core/checks.py, que no toca
el LLM en ningun momento.

Devuelve HTML en vez de renderizar: va incrustada dentro del bloque unico de
la tarjeta.
"""

from html import escape

import streamlit as st

_ESTILO = {
    "PASS": ("chk-pass", "\u2713"),
    "WARN": ("chk-warn", "\u26a0"),
    "FAIL": ("chk-fail", "\u2717"),
    "SKIPPED": ("chk-skip", "\u2013"),
}


def html(checks: list[dict]) -> str:
    if not checks:
        return ""

    partes = []
    for c in checks:
        clase, icono = _ESTILO.get(c["status"], ("chk-skip", "\u2013"))
        # El detalle va como tooltip: la fila se mantiene escaneable de un
        # vistazo y el porque queda a un hover de distancia.
        partes.append(
            f'<span class="chk {clase}" title="{escape(c["detail"])}">'
            f'{icono} {escape(c["label"])}</span>'
        )

    return (
        '<div class="checks">verificado por código: ' + "".join(partes) + "</div>"
    )


def render(checks: list[dict]) -> None:
    """Version suelta, por si se necesita fuera de la tarjeta."""
    marcado = html(checks)
    if marcado:
        st.markdown(marcado, unsafe_allow_html=True)
