"""Tests del modelo de vista.

Lo que se prueba aca es que el frontend NO reinventa la logica del backend:
las banderas de color salen de los checks, no de comparar valores de nuevo.
"""

from frontend import view_model as vm

RESPUESTA_MOCKUP = {
    "reconciliation_id": 7,
    "verdict": "MISMATCH",
    "auto_approved": False,
    "human_decision": "PENDING",
    "note": "Se facturaron 4 unidades de mas.",
    "checks": [
        {"name": "line_sum", "label": "suma de lineas", "status": "PASS", "detail": ""},
        {"name": "tax", "label": "impuestos", "status": "PASS", "detail": ""},
        {"name": "quantity_vs_po", "label": "cantidad vs OC", "status": "WARN", "detail": ""},
        {"name": "unit_price_vs_po", "label": "precio unit. vs OC", "status": "PASS", "detail": ""},
        {"name": "total_vs_po", "label": "total vs OC", "status": "FAIL", "detail": ""},
    ],
    "trace": {"steps": [{"phase": "extraction", "summary": "", "retries": 0}]},
    "invoice": {
        "invoice_number": "F-00842",
        "supplier_name": "Distribuidora del Oriente",
        "supplier_tax_id": "1023874015",
        "total_amount": "2040.00",
        "line_items": [
            {
                "description": "Aceite comestible caja x12",
                "quantity": "24",
                "unit_price": "85.00",
                "line_total": "2040.00",
            }
        ],
    },
    "purchase_order": {
        "po_number": "OC-113",
        "supplier_name": "Distribuidora del Oriente",
        "supplier_tax_id": "1023874015",
        "total_amount": "1700.00",
        "status": "OPEN",
        "line_items": [
            {
                "description": "Aceite comestible caja x12",
                "quantity": "20",
                "unit_price": "85.00",
                "line_total": "1700.00",
            }
        ],
    },
}


def filas_por_etiqueta(v: dict) -> dict:
    return {f["etiqueta"]: f for f in v["filas"]}


# ---------------------------------------------------------------------
# Formato
# ---------------------------------------------------------------------

def test_moneda_usa_formato_local():
    assert vm.moneda("2040.00") == "Bs 2.040,00"
    assert vm.moneda("85") == "Bs 85,00"
    assert vm.moneda("1234567.5") == "Bs 1.234.567,50"


def test_moneda_sin_valor_no_inventa_un_cero():
    assert vm.moneda(None) == "—"
    assert vm.cantidad(None) == "—"


def test_cantidad_sin_ceros_sobrantes():
    assert vm.cantidad("24.000", "unid.") == "24 unid."
    assert vm.cantidad("2.500") == "2.5"


# ---------------------------------------------------------------------
# El caso del mockup
# ---------------------------------------------------------------------

def test_arma_la_tarjeta_del_mockup():
    v = vm.desde_reconcile(RESPUESTA_MOCKUP)
    assert v["titulo"] == "F-00842"
    assert v["proveedor"] == "Distribuidora del Oriente"
    assert v["estado"] == "a revisar"
    assert v["po_numero"] == "OC-113"

    filas = filas_por_etiqueta(v)
    assert filas["cantidad"]["factura"] == "24 unid."
    assert filas["cantidad"]["oc"] == "20 unid."
    assert filas["total"]["factura"] == "Bs 2.040,00"
    assert filas["total"]["oc"] == "Bs 1.700,00"


def test_el_rojo_sale_de_los_checks_no_de_comparar_de_nuevo():
    """Si el backend dice que la cantidad esta observada, se pinta. Si no, no.

    El frontend nunca compara los valores por su cuenta.
    """
    v = vm.desde_reconcile(RESPUESTA_MOCKUP)
    filas = filas_por_etiqueta(v)
    assert filas["cantidad"]["discrepa"] is True
    assert filas["total"]["discrepa"] is True
    assert filas["precio unit."]["discrepa"] is False
    assert filas["NIT"]["discrepa"] is False


def test_sin_checks_observados_nada_se_pinta_en_rojo():
    limpio = dict(RESPUESTA_MOCKUP)
    limpio["checks"] = [
        {**c, "status": "PASS"} for c in RESPUESTA_MOCKUP["checks"]
    ]
    v = vm.desde_reconcile(limpio)
    assert not any(f["discrepa"] for f in v["filas"])


# ---------------------------------------------------------------------
# Casos degradados
# ---------------------------------------------------------------------

def test_sin_orden_de_compra_la_columna_derecha_queda_vacia():
    sin_po = dict(RESPUESTA_MOCKUP, purchase_order=None, verdict="NO_PO_FOUND")
    v = vm.desde_reconcile(sin_po)
    assert v["po_numero"] is None
    assert filas_por_etiqueta(v)["total"]["oc"] == "—"


def test_documento_ilegible_no_rompe_la_tarjeta():
    ilegible = {
        "reconciliation_id": 9,
        "verdict": "UNCERTAIN",
        "auto_approved": False,
        "human_decision": "PENDING",
        "note": "Se requiere revision manual.",
        "checks": [],
        "trace": {"steps": []},
        "invoice": {"line_items": []},
        "purchase_order": None,
    }
    v = vm.desde_reconcile(ilegible)
    assert v["titulo"] == "sin numero"
    assert v["proveedor"] == "proveedor no identificado"
    # Sin lineas no se muestran cantidad ni precio: no hay nada que mostrar.
    assert set(filas_por_etiqueta(v)) == {"total", "NIT"}


def test_multilinea_no_muestra_cantidad_como_fila_unica():
    """Con varias lineas, un solo numero de 'cantidad' seria enganioso."""
    multi = dict(RESPUESTA_MOCKUP)
    multi["invoice"] = dict(
        RESPUESTA_MOCKUP["invoice"],
        line_items=[
            {"description": "A", "quantity": "3", "unit_price": "10", "line_total": "30"},
            {"description": "B", "quantity": "1", "unit_price": "20", "line_total": "20"},
        ],
    )
    v = vm.desde_reconcile(multi)
    assert "cantidad" not in filas_por_etiqueta(v)
    assert "total" in filas_por_etiqueta(v)


# ---------------------------------------------------------------------
# La otra forma de respuesta
# ---------------------------------------------------------------------

def test_la_fila_de_la_db_produce_la_misma_tarjeta():
    """Las dos formas del backend deben dar el mismo modelo de vista."""
    fila = {
        "id": 7,
        "verdict": "MISMATCH",
        "auto_approved": 0,
        "human_decision": "PENDING",
        "note": "Se facturaron 4 unidades de mas.",
        "checks": RESPUESTA_MOCKUP["checks"],
        "trace": RESPUESTA_MOCKUP["trace"],
        "raw_extraction": RESPUESTA_MOCKUP["invoice"],
        "po_number": "OC-113",
        "supplier_name": "Distribuidora del Oriente",
        "supplier_tax_id": "1023874015",
        "po_total": "1700.00",
        "po_status": "OPEN",
        "currency": "BOB",
        "po_line_items": RESPUESTA_MOCKUP["purchase_order"]["line_items"],
        "document_path": "storage/documents/7.jpg",
    }
    desde_db = vm.desde_detalle(fila)
    desde_api = vm.desde_reconcile(RESPUESTA_MOCKUP)

    assert desde_db["filas"] == desde_api["filas"]
    assert desde_db["titulo"] == desde_api["titulo"]
    assert desde_db["estado"] == desde_api["estado"]
