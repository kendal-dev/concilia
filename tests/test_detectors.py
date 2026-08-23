"""Tests de los detectores de honestidad.

Estos detectores son los que deciden si el agente puede confiar en lo que leyo:
verifican que cada valor extraido exista de verdad en el texto crudo del OCR.
Los usa `backend/core/llm/qvac.py` en cada
extraccion; corren sin OCR, sin modelo y sin base de datos.
"""
import pytest

from confidence.detectors import (
    formato_impreso,
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


# ------------------------------------------------------- separador de miles
# R029 lo destapo: el OCR leyo "1,630.20" y el detector solo generaba "1630.20",
# asi que marcaba como inventado un total que estaba impreso en el ticket. Un
# falso positivo aca es peor que no tener detector.

@pytest.mark.parametrize("impreso", ["1,630.20", "1.630,20", "1630.20", "1630,20"])
def test_un_total_de_cuatro_cifras_se_reconoce_lo_escriban_como_lo_escriban(impreso):
    ok, ratio = valor_aparece(
        1630.2, f"FACTURA 13065\nTOTAL Bs\n{impreso}\nP4074135", es_numero=True)
    assert ok and ratio == 1.0


def test_las_variantes_cubren_las_dos_convenciones_de_agrupamiento():
    """El dataset mezcla tickets malayos y facturas bolivianas."""
    v = variantes_numero(1630.2)
    assert {"1,630.20", "1.630,20", "1630.20", "1630,2"} <= v


def test_un_importe_de_tres_cifras_no_inventa_separador():
    """Agrupar por debajo de mil solo produciria ruido."""
    assert not any("," in x and "." in x for x in variantes_numero(817.95))


def test_el_arreglo_no_vuelve_permisivo_al_detector():
    """Un numero que no esta sigue sin estar, aunque el texto tenga otro parecido."""
    assert valor_aparece(9999.99, "TOTAL Bs\n1,630.20\n", es_numero=True)[0] is False


def test_el_valor_que_ve_el_operador_no_depende_del_orden_ascii():
    """Antes salia de sorted(variantes)[0] y cambiaba solo al agregar variantes."""
    assert formato_impreso(1630.2, es_numero=True) == "1,630.20"
    assert formato_impreso(639.73, es_numero=True) == "639.73"
    assert formato_impreso("F-00731") == "F-00731"
