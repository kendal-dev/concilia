"""Tests del selector de motor de pruebas.

TEMPORAL: este archivo se borra junto con el switch, cuando QVAC este
integrado y el motor deje de elegirse desde la UI.
"""

import pytest
from fastapi.testclient import TestClient

from backend.api.main import app
from backend.core.llm.factory import get_llm_client
from backend.core.llm.stub import FlakyLLMClient, StubLLMClient
from backend.db.session import check_connection


def test_sin_override_manda_la_configuracion():
    assert isinstance(get_llm_client("match.jpg"), StubLLMClient)


def test_el_override_elige_el_cliente():
    assert isinstance(get_llm_client("match.jpg", override="flaky"), FlakyLLMClient)
    assert isinstance(get_llm_client("match.jpg", override="stub"), StubLLMClient)


def test_el_override_no_distingue_mayusculas():
    assert isinstance(get_llm_client("match.jpg", override="FLAKY"), FlakyLLMClient)


def test_la_ui_no_puede_forzar_un_cliente_que_no_sea_de_prueba():
    """El switch es para demos; no debe abrir la puerta a otra configuracion."""
    with pytest.raises(ValueError):
        get_llm_client("match.jpg", override="qvac")
    with pytest.raises(ValueError):
        get_llm_client("match.jpg", override="inventado")


# --- Capa HTTP: necesitan la base real ------------------------------------

requiere_db = pytest.mark.skipif(
    not check_connection(), reason="MariaDB no disponible (docker compose up -d)"
)


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@requiere_db
def test_health_publica_los_motores_de_prueba(client):
    assert client.get("/health").json()["test_clients"] == ["stub", "flaky"]


@requiere_db
def test_reconcile_acepta_el_motor_por_request(client):
    """Con flaky el agente absorbe dos respuestas rotas y llega al mismo
    veredicto: es la prueba de que el retry loop hace su trabajo."""
    r = client.post(
        "/reconcile",
        files={"file": ("factura_match.jpg", b"imagen-de-prueba", "image/jpeg")},
        data={"llm_client": "flaky"},
    )
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["verdict"] == "MATCH"

    extraccion = cuerpo["trace"]["steps"][0]
    assert extraccion["phase"] == "extraction"
    assert extraccion["retries"] == 2


@requiere_db
def test_reconcile_rechaza_un_motor_desconocido(client):
    r = client.post(
        "/reconcile",
        files={"file": ("factura_match.jpg", b"imagen-de-prueba", "image/jpeg")},
        data={"llm_client": "gpt-en-la-nube"},
    )
    assert r.status_code == 400
    assert "desconocido" in r.json()["detail"]
