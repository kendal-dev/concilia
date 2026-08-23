"""Smoke test del selector de motor en el dashboard.

TEMPORAL: se borra junto con el switch cuando QVAC este integrado.
"""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from frontend import api_client

# Desde Streamlit 1.62 las rutas relativas de AppTest.from_file se resuelven
# contra el archivo que la llama, no contra el cwd. Absoluta y listo.
APP = str(Path(__file__).resolve().parents[1] / "app.py")

SALUD = {"status": "ok", "db": "connected", "llm_client": "stub",
         "test_clients": ["stub", "flaky"]}


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setattr(api_client, "health", lambda: SALUD)
    monkeypatch.setattr(api_client, "stats", lambda: {})
    monkeypatch.setattr(api_client, "listar_reconciliaciones", lambda limit=50: [])
    return AppTest.from_file(APP, default_timeout=30)


def test_el_selector_aparece_con_las_opciones_del_backend(app):
    at = app.run()
    assert not at.exception
    # `options` devuelve las etiquetas ya formateadas, no las claves.
    etiquetas = at.sidebar.radio[0].options
    assert etiquetas[0] == "(el configurado en el backend)"
    assert etiquetas[1].startswith("Stub")
    assert etiquetas[2].startswith("Flaky")


def test_por_defecto_no_fuerza_ningun_motor(app):
    at = app.run()
    assert at.sidebar.radio[0].value == "(el configurado en el backend)"
    # La cabecera cae al motor que reporta el backend.
    assert any("stub" in c.value for c in at.caption)


def test_elegir_flaky_lo_refleja_en_la_cabecera(app):
    at = app.run()
    at.sidebar.radio[0].set_value("flaky").run()
    assert not at.exception
    assert any("flaky" in c.value for c in at.caption)


def test_sin_test_clients_el_selector_no_se_dibuja(monkeypatch):
    """Cuando el backend deje de publicarlos, la UI vuelve sola a su estado
    normal: el switch no se queda colgado como codigo muerto visible."""
    monkeypatch.setattr(api_client, "health", lambda: {**SALUD, "test_clients": []})
    monkeypatch.setattr(api_client, "stats", lambda: {})
    monkeypatch.setattr(api_client, "listar_reconciliaciones", lambda limit=50: [])
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception
    assert len(at.sidebar.radio) == 0
