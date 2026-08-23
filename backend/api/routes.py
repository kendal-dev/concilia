"""Endpoints HTTP.

Capa fina a proposito: validar entrada, llamar al core, serializar salida.
Cero logica de negocio aca; toda vive en backend/core/.
"""

from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.config import get_settings
from backend.core.llm.factory import CLIENTES_DE_PRUEBA, get_llm_client
from backend.core.orchestrator import reconcile
from backend.core.schemas import (
    HumanDecision,
    PurchaseOrderRecord,
    ReconciliationResult,
)
from backend.core.tools.db_tool import list_purchase_orders
from backend.db.repository import (
    get_reconciliation,
    get_stats,
    list_reconciliations,
    record_decision,
)
from backend.db.session import check_connection, session_scope

router = APIRouter()

MAX_UPLOAD_BYTES = 10 * 1024 * 1024


class DecisionRequest(BaseModel):
    decision: HumanDecision
    decided_by: str = "operador"


@router.get("/health")
def health() -> dict:
    db_ok = check_connection()
    return {
        "status": "ok" if db_ok else "degraded",
        "db": "connected" if db_ok else "unreachable",
        "llm_client": get_settings().llm_client,
        # Con esto el dashboard arma su selector de motor de diagnostico.
        "test_clients": list(CLIENTES_DE_PRUEBA),
    }


@router.get("/stats")
def stats() -> dict:
    """La fila superior del dashboard."""
    with session_scope() as session:
        return get_stats(session)


@router.post("/reconcile", response_model=ReconciliationResult)
async def reconcile_invoice(
    file: UploadFile = File(...),
    # Permite forzar un cliente determinista para UNA request, sin tocar el .env
    # ni reiniciar el backend. Sin este campo corre el motor de settings (QVAC).
    llm_client: str | None = Form(None),
) -> ReconciliationResult:
    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="El archivo esta vacio.")
    if len(image_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="El archivo supera los 10 MB.")

    filename = file.filename or "sin_nombre"
    settings = get_settings()
    try:
        llm = get_llm_client(filename, override=llm_client)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    with session_scope() as session:
        return reconcile(
            session,
            llm,
            image_bytes,
            filename,
            max_retries=settings.llm_max_retries,
            content_type=file.content_type,
        )


@router.get("/purchase-orders", response_model=list[PurchaseOrderRecord])
def purchase_orders() -> list[PurchaseOrderRecord]:
    with session_scope() as session:
        return list_purchase_orders(session)


@router.get("/reconciliations")
def reconciliations(limit: int = 50) -> list[dict]:
    with session_scope() as session:
        return list_reconciliations(session, limit=limit)


@router.get("/reconciliations/{reconciliation_id}")
def reconciliation_detail(reconciliation_id: int) -> dict:
    with session_scope() as session:
        detalle = get_reconciliation(session, reconciliation_id)
    if detalle is None:
        raise HTTPException(status_code=404, detail="Reconciliacion inexistente.")
    return detalle


@router.get("/reconciliations/{reconciliation_id}/document")
def reconciliation_document(reconciliation_id: int) -> FileResponse:
    """Devuelve el documento original que origino el dictamen."""
    with session_scope() as session:
        detalle = get_reconciliation(session, reconciliation_id)
    if detalle is None:
        raise HTTPException(status_code=404, detail="Reconciliacion inexistente.")

    ruta = detalle.get("document_path")
    if not ruta or not Path(ruta).is_file():
        raise HTTPException(
            status_code=404, detail="No se conserva el documento original."
        )
    return FileResponse(
        ruta,
        media_type=detalle.get("content_type") or "application/octet-stream",
        filename=detalle["source_filename"],
    )


@router.post("/reconciliations/{reconciliation_id}/decision")
def decide(reconciliation_id: int, body: DecisionRequest) -> dict:
    """Registra la decision del operador: aprobar o escalar a compras."""
    if body.decision is HumanDecision.PENDING:
        raise HTTPException(
            status_code=400, detail="PENDING no es una decision; usa APPROVED o ESCALATED."
        )
    with session_scope() as session:
        if not record_decision(session, reconciliation_id, body.decision, body.decided_by):
            raise HTTPException(status_code=404, detail="Reconciliacion inexistente.")
    return {"id": reconciliation_id, "human_decision": body.decision.value}
