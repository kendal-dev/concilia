"""Dashboard del Operador.

Toda la inferencia corre en el backend local; esta app solo consume su API.
El operador sube una factura, ve el dictamen del agente y los datos que lo
justifican lado a lado, y decide: aprobar o escalar.
"""

import streamlit as st

from frontend import api_client, view_model
from frontend.components import invoice_card, stats_row, styles

st.set_page_config(
    page_title="Reconciliación de Facturas",
    page_icon="📄",
    layout="wide",
)
styles.inyectar()


def main() -> None:
    estado = _estado_backend()
    if estado is None:
        return

    motor = _selector_de_motor(estado)

    st.markdown("### Reconciliación de facturas")
    st.caption(
        "Agente local. Ningún dato de factura sale de esta máquina — "
        f"motor de inferencia: `{motor or estado.get('llm_client', 'desconocido')}`."
    )

    _fila_stats()
    st.divider()
    _zona_de_carga(motor)
    _resultado_reciente()
    _cola_de_revision()


# ======================================================================
# BLOQUE TEMPORAL — selector de motor de pruebas.
#
# Existe solo mientras QVAC no este integrado: permite demostrar el pipeline
# completo con clientes deterministas sin editar el .env ni reiniciar nada.
#
# PARA QUITARLO cuando QvacLLMClient este listo, borrar:
#   1. esta funcion y la linea `motor = _selector_de_motor(estado)` en main()
#   2. el parametro `motor` de _zona_de_carga() y de api_client.reconcile()
#   3. el Form `llm_client` del endpoint POST /reconcile
#   4. CLIENTES_DE_PRUEBA y el argumento `override` de get_llm_client()
# ======================================================================

_ETIQUETAS_MOTOR = {
    "stub": "Stub — respuestas deterministas",
    "flaky": "Flaky — falla 2 veces, prueba el retry loop",
}


def _selector_de_motor(estado: dict) -> str | None:
    """Devuelve el motor de prueba elegido, o None para usar el del backend."""
    disponibles = estado.get("test_clients") or []
    if not disponibles:
        return None

    opciones = ["(el configurado en el backend)", *disponibles]
    elegido = st.sidebar.radio(
        "Motor de inferencia",
        opciones,
        format_func=lambda o: _ETIQUETAS_MOTOR.get(o, o),
        key="motor_prueba",
        help=(
            "Provisional: QVAC todavia no esta integrado, asi que el agente "
            "corre contra clientes de prueba. Este selector desaparece cuando "
            "la inferencia local este conectada."
        ),
    )
    st.sidebar.caption(
        "⚠️ Modo de pruebas. Sin inferencia real: las respuestas del modelo "
        "estan simuladas. Todo lo demas del pipeline —verificaciones, "
        "reintentos, veredicto y traza— corre de verdad."
    )
    return None if elegido == opciones[0] else elegido


def _estado_backend() -> dict | None:
    """Sin backend no hay nada que mostrar; se dice claramente y se corta."""
    try:
        estado = api_client.health()
    except api_client.BackendError as exc:
        st.error(str(exc))
        return None

    if estado.get("db") != "connected":
        st.warning(
            "El backend responde pero no alcanza la base de datos. "
            "Levantala con: docker compose up -d"
        )
    return estado


def _fila_stats() -> None:
    try:
        stats_row.render(api_client.stats())
    except api_client.BackendError as exc:
        st.error(str(exc))


def _zona_de_carga(motor: str | None = None) -> None:
    archivo = st.file_uploader(
        "Subir factura",
        type=["jpg", "jpeg", "png", "webp", "pdf"],
        help="Foto, escaneo o PDF. El documento no sale del dispositivo.",
    )
    if archivo is None:
        return

    # Evita reprocesar el mismo archivo en cada rerun de Streamlit. El motor
    # entra en la firma a proposito: cambiarlo SI debe reprocesar, que es
    # justamente como se comparan dos motores sobre el mismo documento.
    firma = (archivo.name, archivo.size, motor)
    if st.session_state.get("firma_procesada") == firma:
        return

    with st.spinner("El agente está leyendo el documento…"):
        try:
            respuesta = api_client.reconcile(
                archivo.name, archivo.getvalue(), archivo.type, motor=motor
            )
        except api_client.BackendError as exc:
            st.error(str(exc))
            return

    st.session_state["firma_procesada"] = firma
    st.session_state["ultimo_resultado"] = respuesta
    st.rerun()


def _resultado_reciente() -> None:
    respuesta = st.session_state.get("ultimo_resultado")
    if not respuesta:
        return
    st.markdown("#### Resultado")
    invoice_card.render(view_model.desde_reconcile(respuesta), key_prefix="nuevo_")


def _cola_de_revision() -> None:
    """Lo que quedo pendiente de decision humana.

    Lista compacta mas una tarjeta completa para la seleccionada. Se evita a
    proposito envolver cada tarjeta en un expander: la tarjeta ya contiene el
    expander de la traza, y Streamlit no permite anidarlos.
    """
    try:
        filas = api_client.listar_reconciliaciones(limit=25)
    except api_client.BackendError as exc:
        st.error(str(exc))
        return

    reciente = st.session_state.get("ultimo_resultado") or {}
    ya_mostrada = reciente.get("reconciliation_id")
    pendientes = [
        f
        for f in filas
        if f.get("human_decision") == "PENDING" and f["id"] != ya_mostrada
    ]

    st.divider()
    if not pendientes:
        st.success("No hay facturas pendientes de revisión.")
        return

    st.markdown(f"#### Cola de revisión · {len(pendientes)} pendiente(s)")

    # La tarjeta abierta va ARRIBA de la lista: con una cola larga, ponerla
    # abajo la deja fuera de pantalla justo cuando el operador la necesita.
    seleccionada = st.session_state.get("cola_seleccionada")
    if seleccionada and any(f["id"] == seleccionada for f in pendientes):
        _detalle_de_cola(seleccionada)

    for fila in pendientes:
        _fila_de_cola(fila, activa=fila["id"] == seleccionada)


def _fila_de_cola(fila: dict, activa: bool) -> None:
    col_factura, col_proveedor, col_verdict, col_boton = st.columns([2, 3, 1.4, 1.2])
    col_factura.write(fila.get("invoice_number") or fila["source_filename"])
    col_proveedor.write(fila.get("supplier_name") or "proveedor no identificado")
    col_verdict.caption(fila["verdict"])

    if col_boton.button("Ocultar" if activa else "Revisar", key=f"sel{fila['id']}"):
        st.session_state["cola_seleccionada"] = None if activa else fila["id"]
        st.rerun()


def _detalle_de_cola(rec_id: int) -> None:
    try:
        detalle = api_client.obtener_reconciliacion(rec_id)
    except api_client.BackendError as exc:
        st.error(str(exc))
        return
    invoice_card.render(view_model.desde_detalle(detalle), key_prefix="cola_")


main()
