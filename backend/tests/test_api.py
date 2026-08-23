"""Tests de la capa HTTP contra la base real.

Se saltan solos si MariaDB no esta levantada.
"""

import pytest
from fastapi.testclient import TestClient

from backend.api.main import app
from backend.db.session import check_connection

pytestmark = pytest.mark.skipif(
    not check_connection(), reason="MariaDB no disponible (docker compose up -d)"
)


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def reconciliacion(client) -> dict:
    """Sube el caso del mockup una vez por corrida y devuelve el resultado.

    Alcance de modulo a proposito: estos tests escriben en la base real, y una
    fixture por test dejaria una fila nueva por cada uno.
    """
    r = client.post(
        "/reconcile",
        files={"file": ("factura_oriente.jpg", b"imagen-de-prueba", "image/jpeg")},
        # Motor determinista explicito. Estos tests verifican el ORQUESTADOR - las
        # fases, los checks, el veredicto, la persistencia - no la calidad de la
        # inferencia. Sin este override toman el LLM_CLIENT del .env: con
        # LLM_CLIENT=qvac, el OCR corre de verdad sobre `b"imagen-de-prueba"`, que
        # no es una imagen, devuelve UNCERTAIN con razon, y el test falla por algo
        # que no esta probando. La calidad del motor real se mide en eval/, contra
        # los 31 recibos y su ground truth.
        data={"llm_client": "stub"},
    )
    assert r.status_code == 200
    return r.json()


def test_health_reporta_la_db(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["db"] == "connected"


def test_el_caso_del_mockup_extremo_a_extremo(reconciliacion):
    assert reconciliacion["verdict"] == "MISMATCH"
    assert reconciliacion["auto_approved"] is False
    assert reconciliacion["amount_delta"] == "340.00"
    assert reconciliacion["purchase_order"]["po_number"] == "OC-113"

    por_nombre = {c["name"]: c["status"] for c in reconciliacion["checks"]}
    assert por_nombre["quantity_vs_po"] == "WARN"
    assert por_nombre["line_sum"] == "PASS"
    assert por_nombre["tax"] == "PASS"


def test_la_traza_incluye_la_fase_de_verificacion(reconciliacion):
    fases = [p["phase"] for p in reconciliacion["trace"]["steps"]]
    assert fases == ["extraction", "lookup", "verification", "reasoning", "persist"]


def test_archivo_vacio_es_rechazado(client):
    r = client.post("/reconcile", files={"file": ("x.jpg", b"", "image/jpeg")})
    assert r.status_code == 400


def test_stats_devuelve_los_contadores_del_dashboard(client):
    body = client.get("/stats").json()
    assert set(body) >= {"procesadas", "auto_aprobadas", "a_revisar", "escaladas"}
    assert body["procesadas"] == body["auto_aprobadas"] + body["a_revisar"]


def test_el_detalle_trae_las_lineas_de_la_oc(client, reconciliacion):
    """El dashboard necesita las lineas para comparar cantidad vs OC."""
    detalle = client.get(f"/reconciliations/{reconciliacion['reconciliation_id']}").json()
    assert detalle["po_number"] == "OC-113"
    assert detalle["po_line_items"][0]["description"] == "Aceite comestible caja x12"
    # Las columnas JSON llegan hidratadas, no como texto.
    assert isinstance(detalle["checks"], list)


def test_el_documento_original_se_puede_recuperar(client, reconciliacion):
    r = client.get(f"/reconciliations/{reconciliacion['reconciliation_id']}/document")
    assert r.status_code == 200
    assert r.content == b"imagen-de-prueba"


def test_la_decision_se_persiste(client, reconciliacion):
    rec_id = reconciliacion["reconciliation_id"]
    assert reconciliacion["human_decision"] == "PENDING"

    r = client.post(
        f"/reconciliations/{rec_id}/decision",
        json={"decision": "ESCALATED", "decided_by": "denzel"},
    )
    assert r.status_code == 200

    detalle = client.get(f"/reconciliations/{rec_id}").json()
    assert detalle["human_decision"] == "ESCALATED"
    assert detalle["decided_by"] == "denzel"
    assert detalle["decided_at"] is not None


def test_pending_no_es_una_decision(client, reconciliacion):
    r = client.post(
        f"/reconciliations/{reconciliacion['reconciliation_id']}/decision",
        json={"decision": "PENDING"},
    )
    assert r.status_code == 400


def test_decidir_sobre_un_id_inexistente_da_404(client):
    r = client.post(
        "/reconciliations/999999/decision", json={"decision": "APPROVED"}
    )
    assert r.status_code == 404
