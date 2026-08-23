"""Tests de los detectores de honestidad.

Estos detectores son los que deciden si el agente puede confiar en lo que leyo:
verifican que cada valor extraido exista de verdad en el texto crudo del OCR, y que
la aritmetica del documento cierre. Los usa `backend/core/llm/qvac.py` en cada
extraccion; corren sin OCR, sin modelo y sin base de datos.
"""
import pytest

from confidence.detectors import (
    coherencia_aritmetica,
    span_verificado,
    valor_aparece,
    variantes_numero,
)

# Texto real del OCR de data/receipts/R002.jpg, recortado. Los errores de lectura
# ("RH" por "RM", el espacio antes de la coma) son los que devolvio el motor.
OCR_R002 = """(Co.REG
933109-X )
Lot
1851-A
TOTAL
RM 33 ,92
TOTAL RoundED
RH 33,90
CASH
RH 50.00"""


# ------------------------------------------------- verificacion de procedencia
@pytest.mark.parametrize("valor", [33.9, 33.90, 33.92, 50.0])
def test_numero_impreso_con_coma_y_cero_final_se_reconoce(valor):
    """El modelo devuelve 33.9 y el ticket dice "RH 33,90".

    Marcar eso como inventado seria un falso positivo del detector de honestidad,
    y eso es peor que no tener detector: hunde la confianza de un dato correcto.
    """
    ok, ratio = valor_aparece(valor, OCR_R002, es_numero=True)
    assert ok, f"{valor} esta en el ticket y se marco como inventado (sim {ratio})"


def test_numero_inventado_se_detecta():
    """El caso que el track quiere ver atrapado: un total que no esta en el papel."""
    ok, _ = valor_aparece(999.99, OCR_R002, es_numero=True)
    assert ok is False


def test_texto_tolera_los_espacios_que_mete_el_ocr():
    assert valor_aparece("933109-X", OCR_R002)[0] is True
    assert valor_aparece("999999-Z", OCR_R002)[0] is False


def test_variantes_cubre_las_dos_convenciones_decimales():
    v = variantes_numero(33.9)
    assert {"33.90", "33.9", "33,90", "33,9"} <= v


def test_span_tolera_saltos_de_linea_del_ocr():
    """El OCR corta lineas donde quiere; eso no puede invalidar un span correcto."""
    ok, ratio = span_verificado("TOTAL Bs 247.50", "...\nTOTAL  Bs\n247.50\n...")
    assert ok and ratio >= 0.9


def test_span_no_tolera_invencion():
    assert span_verificado("TOTAL Bs 999.99", OCR_R002)[0] is False


def test_texto_vacio_no_verifica_nada():
    assert valor_aparece(33.9, "", es_numero=True)[0] is False


# ------------------------------------------------------ coherencia aritmetica
def test_sin_items_el_detector_no_aplica():
    """Un taxi o un puesto de mercado no traen desglose. Penalizarlos seria
    inventar incertidumbre donde no la hay."""
    assert coherencia_aritmetica([], 100.0) == ("no_aplica", None)


def test_detecta_desvio_real():
    items = [{"qty": 2, "unit_price": 10.0}, {"qty": 1, "unit_price": 5.0}]
    estado, delta = coherencia_aritmetica(items, 100.0)
    assert estado == "desvia" and delta == -75.0


def test_tolera_un_boliviano_de_redondeo():
    assert coherencia_aritmetica([{"qty": 2, "unit_price": 10.0}], 20.5)[0] == "ok"


def test_items_sin_importes_legibles_no_aplican():
    """Si el OCR no pudo leer cantidades ni precios, no hay nada que sumar."""
    items = [{"desc": "algo", "qty": None, "unit_price": None}]
    assert coherencia_aritmetica(items, 50.0)[0] == "no_aplica"
