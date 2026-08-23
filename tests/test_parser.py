"""El parser tiene que sobrevivir a lo que un 4B cuantizado realmente devuelve."""
import pytest

from extract.parser import ErrorValidacion, parsear, validar

LIMPIO = '{"vendor": {"value": "X", "confidence": 0.9, "source_span": "X"}}'


def test_json_limpio_no_registra_reparaciones():
    d, rep = parsear(LIMPIO)
    assert d["vendor"]["value"] == "X" and rep == []


def test_quita_fences_de_markdown():
    d, rep = parsear("```json\n" + LIMPIO + "\n```")
    assert d["vendor"]["value"] == "X"
    assert "fences_markdown" in rep


def test_quita_preambulo():
    d, rep = parsear("Claro, aqui tenes el JSON:\n" + LIMPIO)
    assert d["vendor"]["value"] == "X"
    assert "preambulo_recortado" in rep


def test_quita_comas_finales():
    d, rep = parsear('{"a": 1, "b": [1, 2,],}')
    assert d["a"] == 1 and "comas_finales" in rep


def test_texto_vacio_es_error():
    with pytest.raises(ErrorValidacion):
        parsear("   ")


def test_sin_json_es_error():
    with pytest.raises(ErrorValidacion):
        parsear("no pude leer el recibo, lo siento")


def test_validar_normaliza_campos_faltantes():
    out = validar({"total": {"value": "1234,50", "confidence": 0.7,
                             "source_span": "TOTAL 1234,50"}})
    assert out["total"]["value"] == 1234.50
    assert out["vendor"]["value"] is None and out["vendor"]["confidence"] == 0.0


def test_validar_rechaza_fecha_no_iso():
    with pytest.raises(ErrorValidacion):
        validar({"date": {"value": "14/08/2026", "confidence": 0.9}})


def test_validar_rechaza_confianza_fuera_de_rango():
    with pytest.raises(ErrorValidacion):
        validar({"total": {"value": 10, "confidence": 3.0}})


def test_validar_acepta_total_null():
    """No leer el total es una respuesta valida, no un error de esquema."""
    out = validar({"total": {"value": None, "confidence": 0.0, "source_span": ""}})
    assert out["total"]["value"] is None


def test_validar_descarta_items_malformados():
    out = validar({"items": ["basura", {"desc": "x", "qty": 2, "unit_price": 3.5}]})
    assert len(out["items"]) == 1 and out["items"][0]["qty"] == 2.0


@pytest.mark.parametrize("entrada,esperado", [
    (247.5, 247.50),
    ("247.50", 247.50),
    ("1234,50", 1234.50),
    ("1,234.50", 1234.50),
    ("1.234,50", 1234.50),
    ("Bs 1.500", 1500.0),
    ("RM 33.90", 33.90),
    ("", None),
    ("ilegible", None),
])
def test_a_monto_maneja_las_dos_convenciones(entrada, esperado):
    from extract.parser import a_monto
    assert a_monto(entrada) == esperado
