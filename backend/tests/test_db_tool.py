"""Tests de la herramienta de ERP contra MariaDB real.

Se saltan solos si la base no esta levantada, para que `pytest` siga siendo
util sin Docker. Levantar con: docker compose up -d
"""

from decimal import Decimal

import pytest

from backend.core.tools.db_tool import (
    fetch_purchase_orders_by_tax_id,
    list_purchase_orders,
    lookup_purchase_order,
)
from backend.db.session import check_connection, session_scope

pytestmark = pytest.mark.skipif(
    not check_connection(), reason="MariaDB no disponible (docker compose up -d)"
)


@pytest.fixture
def session():
    with session_scope() as s:
        yield s


def test_el_seed_cargo(session):
    ordenes = list_purchase_orders(session)
    assert len(ordenes) == 9
    assert {o.po_number for o in ordenes} >= {"OC-101", "OC-130"}


def test_los_montos_llegan_como_decimal(session):
    """Si esto devolviera float, las comparaciones de plata mentirian."""
    po = lookup_purchase_order(session, "3344556677")
    assert isinstance(po.total_amount, Decimal)
    assert po.total_amount == Decimal("5882.50")


def test_las_lineas_suman_el_total(session):
    po = lookup_purchase_order(session, "3344556677")
    assert len(po.line_items) == 4
    assert sum(li.line_total for li in po.line_items) == po.total_amount


def test_nit_inexistente_devuelve_none(session):
    """El caso que importa: la herramienta admite que no encontro nada."""
    assert lookup_purchase_order(session, "6677889900") is None


def test_desambigua_entre_varias_ordenes_del_mismo_proveedor(session):
    """Importadora Santa Cruz tiene dos ordenes abiertas: OC-101 y OC-135.

    Se elige la de monto mas cercano al facturado, como haria un operador."""
    candidatas = fetch_purchase_orders_by_tax_id(session, "4820156023")
    assert len(candidatas) == 2

    cerca = lookup_purchase_order(session, "4820156023", Decimal("3400.00"))
    assert cerca.po_number == "OC-101"

    lejos = lookup_purchase_order(session, "4820156023", Decimal("5150.00"))
    assert lejos.po_number == "OC-135"


def test_la_consulta_no_es_vulnerable_a_inyeccion(session):
    """Parametro malicioso: se trata como dato, no como SQL."""
    assert lookup_purchase_order(session, "' OR '1'='1") is None
