"""Un test por veredicto + los detectores de honestidad.

Suite de regresion: mientras esto pase, el motor de conciliacion funciona sin OCR,
sin modelo y sin base de datos.
"""
import pytest

from confidence.detectors import coherencia_aritmetica, span_verificado
from pipeline import conciliar
from reconcile import rules
from reconcile.matcher import mejor_proveedor
from reconcile.text import normalizar
from tests.conftest import contrato_base

RAW_OK = "FARMAC1A CRUZ\nNIT 123456\n14/08/2026\nTOTAL  Bs 247.50\nGRACIAS"


# ---------------------------------------------------------------- veredictos
def test_match_exacto(repo):
    c = contrato_base(RAW_OK, "Farmacia Cruz", "2026-08-14", 247.50,
                      span_total="TOTAL  Bs 247.50")
    conciliar(c, repo)
    assert c["reconciliation"]["verdict"] == "MATCH"
    assert c["reconciliation"]["match_strategy"] == "exact"
    assert c["confidence_overall"] >= 0.6


def test_match_por_fuzzy_de_proveedor(repo):
    """El OCR devuelve el nombre mutilado: el fuzzy tiene que reconocerlo igual."""
    c = contrato_base(RAW_OK, "FARMAC1A CRU", "2026-08-14", 247.50,
                      span_total="TOTAL  Bs 247.50")
    conciliar(c, repo)
    assert c["reconciliation"]["verdict"] == "MATCH"
    assert c["reconciliation"]["match_strategy"] == "fuzzy_vendor"


def test_mismatch_por_transposicion(repo):
    raw = "FARMACIA CRUZ\n20/08/2026\nTOTAL Bs 247.00"
    c = contrato_base(raw, "Farmacia Cruz", "2026-08-20", 247.00,
                      span_total="TOTAL Bs 247.00")
    conciliar(c, repo)
    rec = c["reconciliation"]
    assert rec["verdict"] == "MISMATCH"
    assert rec["explanation_pattern"] == "transposicion"
    assert "247" in rec["explanation"] and "274" in rec["explanation"]
    assert rec["human_review_required"] is True


def test_no_match(repo):
    raw = "PANADERIA LA ESPIGA\n01/01/2020\nTOTAL Bs 5.00"
    c = contrato_base(raw, "Panaderia La Espiga", "2020-01-01", 5.00,
                      span_total="TOTAL Bs 5.00")
    conciliar(c, repo)
    assert c["reconciliation"]["verdict"] == "NO_MATCH"
    assert c["reconciliation"]["explanation_pattern"] == "sin_par"


def test_uncertain_cuando_no_hay_total(repo):
    """El modelo no pudo leer el total. El sistema NO adivina."""
    c = contrato_base("FARMACIA CRUZ\nTOTAL ilegible", "Farmacia Cruz",
                      "2026-08-14", None, span_total="")
    c["extracted"]["total"]["confidence"] = 0.0
    conciliar(c, repo)
    assert c["reconciliation"]["verdict"] == "UNCERTAIN"
    assert c["reconciliation"]["human_review_required"] is True


def test_duplicado_detectado(repo):
    raw = "Pinturas Monopol Ltda.\n11/02/2026\nTotal Bs. 639.73"
    c = contrato_base(raw, "Pinturas Monopol Ltda.", "2026-02-11", 639.73,
                      span_total="Total Bs. 639.73")
    conciliar(c, repo)
    assert c["reconciliation"]["verdict"] == "MATCH"
    assert c["reconciliation"]["explanation_pattern"] == "duplicado"


# ------------------------------------------------------- honestidad / vetos
def test_span_inventado_fuerza_uncertain(repo):
    """El modelo dice haber leido "TOTAL Bs 999.99", pero eso no esta en el OCR.
    Es el caso que el track quiere ver atrapado."""
    c = contrato_base(RAW_OK, "Farmacia Cruz", "2026-08-14", 247.50,
                      span_total="TOTAL Bs 999.99")
    conciliar(c, repo)
    det = c["confidence_detail"]
    assert det["spans"]["total"]["verificado"] is False
    assert c["confidence_overall"] <= 0.40
    assert c["reconciliation"]["verdict"] == "UNCERTAIN"


def test_span_tolera_whitespace_del_ocr():
    """Doble espacio y salto de linea NO pueden marcar un span correcto como inventado."""
    ok, ratio = span_verificado("TOTAL Bs 247.50", "...\nTOTAL  Bs\n247.50\n...")
    assert ok and ratio >= 0.9


def test_span_no_tolera_invencion():
    ok, _ = span_verificado("TOTAL Bs 999.99", RAW_OK)
    assert ok is False


def test_aritmetica_no_aplica_sin_items():
    """Un taxi o un puesto de mercado no traen desglose: no se penaliza."""
    assert coherencia_aritmetica([], 100.0) == ("no_aplica", None)


def test_aritmetica_detecta_desvio():
    items = [{"qty": 2, "unit_price": 10.0}, {"qty": 1, "unit_price": 5.0}]
    estado, delta = coherencia_aritmetica(items, 100.0)
    assert estado == "desvia" and delta == -75.0


def test_aritmetica_ok_dentro_de_tolerancia():
    items = [{"qty": 2, "unit_price": 10.0}]
    assert coherencia_aritmetica(items, 20.5)[0] == "ok"


def test_veto_aritmetico_baja_la_confianza(repo):
    items = [{"qty": 1, "unit_price": 1.0}]
    c = contrato_base(RAW_OK, "Farmacia Cruz", "2026-08-14", 247.50,
                      span_total="TOTAL  Bs 247.50", items=items)
    conciliar(c, repo)
    assert c["confidence_overall"] <= 0.55
    assert any("items" in v for v in c["confidence_detail"]["vetos"])


def test_ruta_multimodal_tiene_techo(repo):
    c = contrato_base("", "Farmacia Cruz", "2026-08-14", 247.50, span_total="")
    c["ocr"]["route"] = "multimodal_fallback"
    conciliar(c, repo)
    assert c["confidence_overall"] <= 0.70
    assert c["confidence_detail"]["spans"]["total"]["verificado"] is None


# ------------------------------------------------------------- utilidades
def test_normalizacion_compartida():
    assert normalizar("  FERRETERÍA  San   Martín ") == "ferreteria san martin"


def test_fuzzy_bajo_umbral_no_inventa_proveedor(repo):
    prov, ratio = mejor_proveedor("XYZ COMERCIAL", repo.listar_proveedores_norm())
    assert prov is None


@pytest.mark.parametrize("a,b,esperado", [
    (247.50, 274.50, True),
    (1630.20, 1360.20, True),
    (247.50, 248.50, False),
])
def test_transposicion(a, b, esperado):
    assert rules.transpuestos(a, b) is esperado


def test_decimal_corrido():
    assert rules.decimal_corrido(247.50, 24.75) is True
    assert rules.decimal_corrido(247.50, 274.50) is False
