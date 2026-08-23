"""Tests del motor de verificacion determinista.

Ninguno de estos toca un LLM ni la base de datos: es aritmetica pura, que es
exactamente el punto del modulo.
"""

from decimal import Decimal

from backend.core.checks import (
    all_clear,
    check_line_sum,
    check_po_status,
    check_quantity_vs_po,
    check_tax,
    check_total_vs_po,
    check_unit_price_vs_po,
    match_lines,
    run_checks,
)
from backend.core.schemas import (
    CheckStatus,
    ExtractedInvoice,
    ExtractedLineItem,
    LineItem,
    PurchaseOrderRecord,
)


def linea(desc, qty, precio, total):
    return ExtractedLineItem(
        description=desc,
        quantity=Decimal(qty),
        unit_price=Decimal(precio),
        line_total=Decimal(total),
    )


def factura(**kw) -> ExtractedInvoice:
    base = dict(
        supplier_tax_id="1023874015",
        supplier_name="Distribuidora del Oriente",
        invoice_number="F-00842",
        total_amount=Decimal("2040.00"),
        currency="BOB",
    )
    base.update(kw)
    return ExtractedInvoice(**base)


def oc113() -> PurchaseOrderRecord:
    """La orden del mockup: 20 cajas a Bs 85.00."""
    return PurchaseOrderRecord(
        id=4,
        po_number="OC-113",
        supplier_tax_id="1023874015",
        supplier_name="Distribuidora del Oriente",
        currency="BOB",
        total_amount=Decimal("1700.00"),
        status="OPEN",
        issued_at="2026-07-15",
        line_items=[
            LineItem(
                description="Aceite comestible caja x12",
                quantity=Decimal("20"),
                unit_price=Decimal("85.00"),
                line_total=Decimal("1700.00"),
            )
        ],
    )


# ---------------------------------------------------------------------
# El caso del mockup, extremo a extremo
# ---------------------------------------------------------------------

def test_el_caso_del_mockup_produce_los_tres_estados():
    """24 cajas facturadas vs 20 autorizadas: suma e impuestos OK, cantidad no."""
    inv = factura(
        subtotal=Decimal("1805.31"),
        tax_amount=Decimal("234.69"),
        line_items=[linea("Aceite comestible caja x12", "24", "85.00", "2040.00")],
    )
    por_nombre = {c.name: c for c in run_checks(inv, oc113())}

    assert por_nombre["line_sum"].status is CheckStatus.PASS
    assert por_nombre["tax"].status is CheckStatus.PASS
    assert por_nombre["quantity_vs_po"].status is CheckStatus.WARN
    assert por_nombre["unit_price_vs_po"].status is CheckStatus.PASS
    assert por_nombre["total_vs_po"].status is CheckStatus.FAIL
    assert "24" in por_nombre["quantity_vs_po"].detail
    assert "20" in por_nombre["quantity_vs_po"].detail


# ---------------------------------------------------------------------
# Suma de lineas
# ---------------------------------------------------------------------

def test_suma_de_lineas_cuadra():
    inv = factura(
        total_amount=Decimal("1000.00"),
        line_items=[linea("A", "2", "300", "600.00"), linea("B", "1", "400", "400.00")],
    )
    assert check_line_sum(inv).status is CheckStatus.PASS


def test_suma_de_lineas_descuadrada():
    inv = factura(
        total_amount=Decimal("1000.00"),
        line_items=[linea("A", "2", "300", "600.00"), linea("B", "1", "300", "300.00")],
    )
    check = check_line_sum(inv)
    assert check.status is CheckStatus.FAIL
    assert check.actual == "900.00"


def test_sin_lineas_el_check_se_declara_no_evaluable():
    """No verificar no es lo mismo que verificar con exito."""
    assert check_line_sum(factura(line_items=[])).status is CheckStatus.SKIPPED


# ---------------------------------------------------------------------
# Impuestos
# ---------------------------------------------------------------------

def test_iva_correcto_al_13_por_ciento():
    inv = factura(
        subtotal=Decimal("3000.00"),
        tax_amount=Decimal("390.00"),
        total_amount=Decimal("3390.00"),
    )
    assert check_tax(inv).status is CheckStatus.PASS


def test_iva_que_no_es_el_13_por_ciento():
    inv = factura(
        subtotal=Decimal("384.00"),
        tax_amount=Decimal("68.00"),
        total_amount=Decimal("452.00"),
    )
    # El desglose suma bien, pero 68 no es el 13% de 384.
    check = check_tax(inv)
    assert check.status is CheckStatus.FAIL
    assert "49.92" in check.detail


def test_el_redondeo_del_iva_escala_con_el_monto():
    """Una tolerancia fija daria falsos positivos en facturas grandes.

    5559.73 x 13% da 722.76; la factura declara 722.77. Es redondeo, no error.
    """
    grande = factura(
        subtotal=Decimal("5559.73"),
        tax_amount=Decimal("722.77"),
        total_amount=Decimal("6282.50"),
    )
    assert check_tax(grande).status is CheckStatus.PASS

    # El mismo centavo de diferencia sobre un monto chico tambien pasa.
    chico = factura(
        subtotal=Decimal("100.00"),
        tax_amount=Decimal("13.01"),
        total_amount=Decimal("113.01"),
    )
    assert check_tax(chico).status is CheckStatus.PASS


def test_subtotal_mas_iva_que_no_da_el_total():
    inv = factura(
        subtotal=Decimal("1000.00"),
        tax_amount=Decimal("130.00"),
        total_amount=Decimal("1200.00"),
    )
    assert check_tax(inv).status is CheckStatus.FAIL


def test_sin_desglose_de_impuestos_es_skipped():
    assert check_tax(factura()).status is CheckStatus.SKIPPED


# ---------------------------------------------------------------------
# Emparejado de lineas
# ---------------------------------------------------------------------

def test_empareja_pese_al_ruido_de_ocr():
    """Acentos, mayusculas y espacios de mas no son discrepancias reales."""
    inv_lines = [linea("ACEITE  COMESTIBLE Caja X12", "20", "85.00", "1700.00")]
    pares, huerfanas = match_lines(inv_lines, oc113().line_items)
    assert len(pares) == 1
    assert not huerfanas


def test_linea_que_no_figura_en_la_oc_se_reporta():
    inv = factura(
        total_amount=Decimal("2100.00"),
        line_items=[
            linea("Aceite comestible caja x12", "20", "85.00", "1700.00"),
            linea("Recargo por combustible", "1", "400.00", "400.00"),
        ],
    )
    check = check_quantity_vs_po(inv, oc113())
    assert check.status is CheckStatus.WARN
    assert "Recargo por combustible" in check.detail


def test_precio_unitario_distinto_se_detecta():
    inv = factura(line_items=[linea("Aceite comestible caja x12", "20", "99.00", "1980.00")])
    assert check_unit_price_vs_po(inv, oc113()).status is CheckStatus.WARN


# ---------------------------------------------------------------------
# Total y estado de la OC
# ---------------------------------------------------------------------

def test_total_vs_oc():
    assert check_total_vs_po(factura(total_amount=Decimal("1700.00")), oc113()).status is CheckStatus.PASS
    assert check_total_vs_po(factura(), oc113()).status is CheckStatus.FAIL


def test_una_diferencia_de_un_centavo_no_es_discrepancia():
    """Tolerancia de redondeo: si esto fallara, media demo seria falso positivo."""
    inv = factura(total_amount=Decimal("1700.01"))
    assert check_total_vs_po(inv, oc113()).status is CheckStatus.PASS


def test_orden_cancelada_falla():
    po = oc113()
    po.status = "CANCELLED"
    assert check_po_status(po).status is CheckStatus.FAIL


def test_orden_cerrada_advierte():
    po = oc113()
    po.status = "CLOSED"
    assert check_po_status(po).status is CheckStatus.WARN


# ---------------------------------------------------------------------
# Politica de auto-aprobacion
# ---------------------------------------------------------------------

def test_all_clear_exige_que_todo_haya_pasado():
    inv = factura(
        subtotal=Decimal("1504.42"),
        tax_amount=Decimal("195.58"),
        total_amount=Decimal("1700.00"),
        line_items=[linea("Aceite comestible caja x12", "20", "85.00", "1700.00")],
    )
    assert all_clear(run_checks(inv, oc113()))


def test_un_skipped_nunca_auto_aprueba():
    """Sin lineas ni desglose de IVA no hay nada verificado que respalde un pago."""
    inv = factura(total_amount=Decimal("1700.00"))
    checks = run_checks(inv, oc113())
    assert any(c.status is CheckStatus.SKIPPED for c in checks)
    assert not all_clear(checks)


def test_sin_oc_solo_corren_los_checks_internos():
    checks = run_checks(factura(), None)
    assert {c.name for c in checks} == {"line_sum", "tax"}


def test_ningun_check_devuelve_float():
    """Si un importe se colara como float, las comparaciones mentirian."""
    inv = factura(
        subtotal=Decimal("1805.31"),
        tax_amount=Decimal("234.69"),
        line_items=[linea("Aceite comestible caja x12", "24", "85.00", "2040.00")],
    )
    for check in run_checks(inv, oc113()):
        for valor in (check.expected, check.actual):
            assert valor is None or isinstance(valor, str)
