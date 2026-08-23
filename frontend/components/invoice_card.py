"""La tarjeta de reconciliacion: el corazon del dashboard.

Muestra lado a lado lo extraido del documento y lo que dice el ERP, para que el
operador audite la decision en cinco segundos. No compara nada por su cuenta:
que valores estan en discrepancia ya lo decidio el backend.

La tarjeta se emite como UN solo bloque HTML. Streamlit sanea cada bloque
markdown por separado, asi que un <div> abierto en una llamada y cerrado en otra
nunca envuelve nada; y sus contenedores nativos comparten el mismo testid que
todos los bloques verticales de la pagina, sin selector estable al que
engancharse. Un bloque autocontenido evita ambos problemas.
"""

from html import escape

import streamlit as st

from frontend import api_client
from frontend.components import checks_row, trace_view


def render(vm: dict, key_prefix: str = "") -> None:
    st.markdown(_html(vm), unsafe_allow_html=True)
    _acciones(vm, key_prefix)
    trace_view.render(vm["trace"], key_prefix)


def _html(vm: dict) -> str:
    badge = "badge-aprobada" if vm["auto_approved"] else "badge-revisar"
    titulo_oc = (
        f'orden de compra {escape(str(vm["po_numero"]))}'
        if vm["po_numero"]
        else "sin orden de compra asociada"
    )
    clase_banner = "banner banner-ok" if vm["auto_approved"] else "banner"

    return f"""
<div class="tarjeta">
  <div class="tarjeta-encabezado">
    <span class="titulo-factura">\U0001f4c4 {escape(vm["titulo"])} · {escape(vm["proveedor"])}</span>
    <span class="badge {badge}">{escape(vm["estado"])}</span>
  </div>
  <div class="comparacion">
    <div>
      <div class="col-titulo">extraído de la factura</div>
      {_filas(vm["filas"], "factura", pintar=True)}
    </div>
    <div>
      <div class="col-titulo">{titulo_oc}</div>
      {_filas(vm["filas"], "oc", pintar=False)}
    </div>
  </div>
  <div class="{clase_banner}">{escape(vm["note"])}</div>
  {checks_row.html(vm["checks"])}
</div>
"""


def _filas(filas: list[dict], lado: str, pintar: bool) -> str:
    """Las filas de un lado. El rojo solo se aplica del lado de la factura."""
    salida = []
    for fila in filas:
        clase = "fila-valor discrepa" if (pintar and fila["discrepa"]) else "fila-valor"
        salida.append(
            f'<div class="fila">'
            f'<span class="fila-etiqueta">{escape(fila["etiqueta"])}</span>'
            f'<span class="{clase}">{escape(fila[lado])}</span>'
            f"</div>"
        )
    return "".join(salida)


def _acciones(vm: dict, key_prefix: str) -> None:
    rec_id = vm["rec_id"]

    if vm["human_decision"] != "PENDING":
        etiqueta = {
            "APPROVED": "Aprobada por el operador.",
            "ESCALATED": "Escalada a compras.",
        }.get(vm["human_decision"], vm["human_decision"])
        st.caption(f"Decisión registrada: {etiqueta}")
        return

    col_ok, col_esc, col_doc, _resto = st.columns([1, 1.4, 1.6, 3])
    with col_ok:
        if st.button("Aprobar", key=f"{key_prefix}ok{rec_id}"):
            _decidir(rec_id, "APPROVED")
    with col_esc:
        if st.button("Escalar a compras", key=f"{key_prefix}esc{rec_id}"):
            _decidir(rec_id, "ESCALATED")
    with col_doc:
        _boton_documento(vm, key_prefix)


def _decidir(rec_id: int, decision: str) -> None:
    try:
        api_client.decidir(rec_id, decision)
    except api_client.BackendError as exc:
        st.error(str(exc))
        return
    st.rerun()


def _boton_documento(vm: dict, key_prefix: str) -> None:
    """El documento original, como evidencia de la decision."""
    clave = f"{key_prefix}doc{vm['rec_id']}"
    contenido = tipo = None

    if vm["tiene_documento"]:
        try:
            contenido, tipo = api_client.descargar_documento(vm["rec_id"])
        except api_client.BackendError:
            contenido = None

    if contenido is None:
        st.button(
            "Ver documento original",
            key=clave,
            disabled=True,
            help="No se conserva el archivo de esta reconciliación.",
        )
        return

    st.download_button(
        "Ver documento original",
        data=contenido,
        file_name=f"{vm['titulo']}.jpg",
        mime=tipo,
        key=clave,
    )
