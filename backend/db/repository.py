"""Persistencia de la traza de auditoria y de la decision humana.

Separado de db_tool.py a proposito: db_tool es la herramienta que el agente
usa para razonar, esto es el registro de lo que el agente decidio y de lo que
el humano resolvio despues.
"""

import json
from decimal import Decimal
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.core.schemas import (
    AgentTrace,
    Check,
    ExtractedInvoice,
    HumanDecision,
    Verdict,
)

# El documento original se guarda en disco y la DB solo lleva la ruta. Todo
# local: el archivo nunca sale de la maquina.
STORAGE_DIR = Path("storage/documents")

_EXTENSIONES_OK = {".jpg", ".jpeg", ".png", ".webp", ".pdf", ".tif", ".tiff"}


def store_document(invoice_id: int, data: bytes, filename: str) -> str:
    """Guarda el archivo subido como evidencia y devuelve su ruta.

    El nombre lo pone el sistema a partir del id, nunca el usuario: un nombre
    de archivo entrante es entrada no confiable y no debe poder escribir fuera
    del directorio de almacenamiento.
    """
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    sufijo = Path(filename).suffix.lower()
    if sufijo not in _EXTENSIONES_OK:
        sufijo = ".bin"
    destino = STORAGE_DIR / f"{invoice_id}{sufijo}"
    destino.write_bytes(data)
    return str(destino).replace("\\", "/")


def save_invoice(
    session: Session, filename: str, invoice: ExtractedInvoice | None
) -> int:
    """Guarda lo extraido del documento. Se guarda incluso si la extraccion
    fallo (invoice=None): un documento ilegible tambien es un hecho auditable."""
    params = {
        "filename": filename,
        "tax_id": invoice.supplier_tax_id if invoice else None,
        "invoice_number": invoice.invoice_number if invoice else None,
        "subtotal": invoice.subtotal if invoice else None,
        "tax_amount": invoice.tax_amount if invoice else None,
        "total": invoice.total_amount if invoice else None,
        "raw": invoice.model_dump_json() if invoice else None,
    }
    result = session.execute(
        text(
            "INSERT INTO invoices "
            "(source_filename, supplier_tax_id, invoice_number, subtotal, "
            " tax_amount, total_amount, raw_extraction) "
            "VALUES (:filename, :tax_id, :invoice_number, :subtotal, "
            "        :tax_amount, :total, :raw)"
        ),
        params,
    )
    session.flush()
    return int(result.lastrowid)


def attach_document(
    session: Session, invoice_id: int, path: str, content_type: str | None
) -> None:
    session.execute(
        text(
            "UPDATE invoices SET document_path = :path, content_type = :ct "
            "WHERE id = :id"
        ),
        {"path": path, "ct": content_type, "id": invoice_id},
    )


def save_reconciliation(
    session: Session,
    invoice_id: int,
    po_id: int | None,
    verdict: Verdict,
    auto_approved: bool,
    amount_delta: Decimal | None,
    note: str,
    checks: list[Check],
    trace: AgentTrace,
) -> int:
    result = session.execute(
        text(
            "INSERT INTO reconciliations "
            "(invoice_id, po_id, verdict, auto_approved, amount_delta, note, checks, trace) "
            "VALUES (:invoice_id, :po_id, :verdict, :auto, :delta, :note, :checks, :trace)"
        ),
        {
            "invoice_id": invoice_id,
            "po_id": po_id,
            "verdict": verdict.value,
            "auto": auto_approved,
            "delta": amount_delta,
            "note": note,
            "checks": json.dumps([json.loads(c.model_dump_json()) for c in checks]),
            # model_dump_json de por medio para que Decimal y datetime salgan
            # serializados como los espera la columna JSON.
            "trace": json.dumps(json.loads(trace.model_dump_json())),
        },
    )
    session.flush()
    return int(result.lastrowid)


def record_decision(
    session: Session, reconciliation_id: int, decision: HumanDecision, decided_by: str
) -> bool:
    """Registra la decision del operador. Devuelve False si el id no existe."""
    result = session.execute(
        text(
            "UPDATE reconciliations "
            "SET human_decision = :decision, decided_by = :by, decided_at = NOW() "
            "WHERE id = :id"
        ),
        {"decision": decision.value, "by": decided_by, "id": reconciliation_id},
    )
    return result.rowcount > 0


# ---------------------------------------------------------------------
# Lecturas para el dashboard
# ---------------------------------------------------------------------

_DETALLE_SELECT = """
    r.id, r.verdict, r.auto_approved, r.amount_delta, r.note, r.checks, r.trace,
    r.human_decision, r.decided_by, r.decided_at, r.created_at,
    i.id AS invoice_id, i.source_filename, i.supplier_tax_id, i.invoice_number,
    i.subtotal, i.tax_amount, i.total_amount AS invoice_total,
    i.raw_extraction, i.document_path, i.content_type,
    p.id AS po_id, p.po_number, p.supplier_name, p.status AS po_status,
    p.currency, p.total_amount AS po_total
    FROM reconciliations r
    JOIN invoices i ON i.id = r.invoice_id
    LEFT JOIN purchase_orders p ON p.id = r.po_id
"""


def _hidratar(row: dict) -> dict:
    """MariaDB devuelve las columnas JSON como texto; el dashboard las quiere
    como estructuras."""
    d = dict(row)
    for campo in ("checks", "trace", "raw_extraction"):
        if isinstance(d.get(campo), str):
            d[campo] = json.loads(d[campo])
    return d


def list_reconciliations(session: Session, limit: int = 50) -> list[dict]:
    """Historial para el dashboard, mas reciente primero."""
    rows = session.execute(
        text(f"SELECT {_DETALLE_SELECT} ORDER BY r.id DESC LIMIT :limit"),
        {"limit": limit},
    ).mappings()
    return [_hidratar(r) for r in rows]


def get_reconciliation(session: Session, reconciliation_id: int) -> dict | None:
    """Detalle completo. Incluye las lineas de la OC para que el dashboard
    pueda mostrar la comparacion linea a linea sin una segunda llamada."""
    row = session.execute(
        text(f"SELECT {_DETALLE_SELECT} WHERE r.id = :id"),
        {"id": reconciliation_id},
    ).mappings().first()
    if row is None:
        return None

    detalle = _hidratar(row)
    detalle["po_line_items"] = []
    if detalle.get("po_id"):
        lineas = session.execute(
            text(
                "SELECT description, quantity, unit_price, line_total "
                "FROM po_line_items WHERE po_id = :po_id ORDER BY id"
            ),
            {"po_id": detalle["po_id"]},
        ).mappings()
        detalle["po_line_items"] = [dict(l) for l in lineas]
    return detalle


def get_stats(session: Session) -> dict:
    """La fila superior del dashboard: procesadas / auto-aprobadas / a revisar."""
    row = session.execute(
        text(
            "SELECT COUNT(*) AS procesadas, "
            "       COALESCE(SUM(auto_approved = 1), 0) AS auto_aprobadas, "
            "       COALESCE(SUM(auto_approved = 0), 0) AS a_revisar, "
            "       COALESCE(SUM(human_decision = 'PENDING'), 0) AS pendientes, "
            "       COALESCE(SUM(human_decision = 'ESCALATED'), 0) AS escaladas "
            "FROM reconciliations"
        )
    ).mappings().first()
    return {k: int(v) for k, v in dict(row).items()}
