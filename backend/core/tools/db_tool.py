"""La herramienta del agente: consultar el ERP.

Es la unica pieza que toca la base de datos durante la reconciliacion. El LLM
nunca ve SQL ni escribe consultas; Python ejecuta la herramienta y le entrega
el resultado ya limpio. Cuando no hay resultado se devuelve None sin adornos,
para que el orquestador pueda decir "no encontre la orden" en vez de inventarla.
"""

from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.core.schemas import LineItem, PurchaseOrderRecord

_PO_COLUMNS = """
    id, po_number, supplier_tax_id, supplier_name,
    currency, total_amount, status, issued_at
"""


def _load_line_items(session: Session, po_id: int) -> list[LineItem]:
    rows = session.execute(
        text(
            "SELECT description, quantity, unit_price, line_total "
            "FROM po_line_items WHERE po_id = :po_id ORDER BY id"
        ),
        {"po_id": po_id},
    ).mappings()
    return [LineItem(**dict(r)) for r in rows]


def _to_record(session: Session, row: dict, with_lines: bool = True) -> PurchaseOrderRecord:
    return PurchaseOrderRecord(
        id=row["id"],
        po_number=row["po_number"],
        supplier_tax_id=row["supplier_tax_id"],
        supplier_name=row["supplier_name"],
        currency=row["currency"],
        total_amount=row["total_amount"],
        status=row["status"],
        issued_at=str(row["issued_at"]),
        line_items=_load_line_items(session, row["id"]) if with_lines else [],
    )


def fetch_purchase_orders_by_tax_id(
    session: Session, tax_id: str
) -> list[PurchaseOrderRecord]:
    """Todas las ordenes abiertas contra un proveedor. Consulta parametrizada."""
    rows = session.execute(
        text(
            f"SELECT {_PO_COLUMNS} FROM purchase_orders "
            "WHERE supplier_tax_id = :tax_id ORDER BY id"
        ),
        {"tax_id": tax_id},
    ).mappings()
    return [_to_record(session, dict(r)) for r in rows]


def lookup_purchase_order(
    session: Session,
    tax_id: str,
    invoice_total: Decimal | None = None,
) -> PurchaseOrderRecord | None:
    """Busca la orden de compra que corresponde a una factura.

    Un proveedor puede tener varias ordenes abiertas. Cuando hay ambiguedad se
    elige la de monto mas cercano al facturado, que es como desambigua un
    operador humano. Empate -> la mas antigua.
    """
    candidates = fetch_purchase_orders_by_tax_id(session, tax_id)
    if not candidates:
        return None
    if len(candidates) == 1 or invoice_total is None:
        return candidates[0]
    return min(candidates, key=lambda po: (abs(po.total_amount - invoice_total), po.id))


def list_purchase_orders(session: Session) -> list[PurchaseOrderRecord]:
    """Listado completo para el dashboard del operador."""
    rows = session.execute(
        text(f"SELECT {_PO_COLUMNS} FROM purchase_orders ORDER BY id")
    ).mappings()
    return [_to_record(session, dict(r)) for r in rows]
