"""El orquestador: Python al mando, el LLM como herramienta.

Las cinco fases del pipeline viven aca. El punto de diseno central es que el
modelo nunca hace dos trabajos en la misma llamada: extrae, se detiene, Python
consulta el ERP, y recien entonces el modelo razona sobre datos ya limpios.
Eso evita la amnesia de contexto que hunde a los modelos de 1-4B.

Toda la aritmetica la hace Python. Al modelo solo se le pide prosa.
"""

import json
import re
import time
from decimal import Decimal

from pydantic import ValidationError
from sqlalchemy.orm import Session

from backend.core.checks import all_clear, run_checks
from backend.core.llm.base import LLMClient
from backend.core.llm.prompts import build_retry_prompt, build_triage_prompt
from backend.core.schemas import (
    AgentTrace,
    Check,
    CheckStatus,
    ExtractedInvoice,
    Phase,
    PurchaseOrderRecord,
    ReconciliationResult,
    TraceStep,
    Verdict,
)
from backend.core.tools.db_tool import lookup_purchase_order
from backend.db.repository import (
    attach_document,
    save_invoice,
    save_reconciliation,
    store_document,
)

# Diferencia por debajo de la cual se considera coincidencia. Cubre redondeos
# de centavos sin dejar pasar un sobrecargo real.
MATCH_TOLERANCE = Decimal("0.01")

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def _salvage_json(raw: str) -> str | None:
    """Primera linea de defensa antes de gastar un reintento.

    Los modelos pequenios envuelven el JSON en bloques de codigo o lo rodean de
    prosa aunque se les prohiba explicitamente. Eso es ruido de formato, no un
    error de contenido: lo limpiamos en vez de castigarlo con un reintento.
    """
    fenced = _FENCE_RE.search(raw)
    if fenced:
        raw = fenced.group(1)

    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end <= start:
        return None
    return raw[start : end + 1]


def _parse_extraction(raw: str) -> ExtractedInvoice:
    """Convierte texto crudo del modelo en un objeto validado, o revienta."""
    candidate = _salvage_json(raw)
    if candidate is None:
        raise ValueError("La respuesta no contiene ningun objeto JSON.")
    try:
        payload = json.loads(candidate, parse_float=Decimal)
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON malformado: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise ValueError("El JSON de nivel superior no es un objeto.")
    return ExtractedInvoice.model_validate(payload)


def _evidencia(llm: LLMClient) -> dict | None:
    """Texto crudo del OCR y verificacion de procedencia, si el cliente los produjo.

    Es lo que hace auditable a la extraccion: el track pide que el sistema muestre
    su razonamiento, y en un pipeline de dos etapas ese razonamiento ES el texto
    intermedio del OCR. Sin esto la evidencia existia pero moria dentro del cliente,
    visible solo desde eval/runner.py y nunca en pantalla.

    Se lee con getattr a proposito: el contrato de LLMClient no la exige, y los
    clientes deterministas (stub, flaky) no la tienen. Devuelven None y la traza
    queda exactamente como estaba.
    """
    ev = getattr(llm, "ultima_evidencia", None)
    if not ev:
        return None
    return {
        "texto_ocr": ev.get("texto_ocr", ""),
        "valores_verificados": ev.get("valores_verificados") or {},
        "ocr": ev.get("ocr") or {},
        "rotacion": ev.get("rotacion"),
        "motivo": ev.get("motivo"),
    }


def _extract_with_retries(
    llm: LLMClient,
    image_bytes: bytes,
    trace: AgentTrace,
    max_retries: int,
) -> ExtractedInvoice | None:
    """Fase 2. Self-correction loop: el error de validacion se le devuelve al
    modelo para que se corrija. Si se agotan los intentos devolvemos None, que
    el llamador traduce a UNCERTAIN. Nunca se completa a mano lo que falto."""
    started = time.perf_counter()
    feedback: str | None = None
    last_error = ""

    for attempt in range(max_retries):
        raw = llm.extract_invoice(image_bytes, feedback=feedback)
        try:
            invoice = _parse_extraction(raw)
        except (ValueError, ValidationError) as exc:
            last_error = _short_error(exc)
            feedback = build_retry_prompt(last_error)
            continue

        trace.add(
            TraceStep(
                phase=Phase.EXTRACTION,
                summary=f"Documento leido en {attempt + 1} intento(s).",
                input=_evidencia(llm),
                output=invoice.model_dump(mode="json"),
                duration_ms=_elapsed_ms(started),
                retries=attempt,
            )
        )
        return invoice

    trace.add(
        TraceStep(
            phase=Phase.EXTRACTION,
            summary=f"Extraccion fallida tras {max_retries} intentos.",
            input=_evidencia(llm),
            duration_ms=_elapsed_ms(started),
            retries=max_retries,
            error=last_error,
        )
    )
    return None


def _lookup(
    session: Session, invoice: ExtractedInvoice, trace: AgentTrace
) -> PurchaseOrderRecord | None:
    """Fase 3. El LLM se detiene aca: la busqueda la hace Python."""
    started = time.perf_counter()
    po = lookup_purchase_order(
        session, invoice.supplier_tax_id, invoice.total_amount
    )
    trace.add(
        TraceStep(
            phase=Phase.LOOKUP,
            summary=(
                f"Orden {po.po_number} recuperada del ERP."
                if po
                else f"Sin orden de compra para el NIT {invoice.supplier_tax_id}."
            ),
            input={"supplier_tax_id": invoice.supplier_tax_id},
            output=po.model_dump(mode="json") if po else None,
            duration_ms=_elapsed_ms(started),
        )
    )
    return po


def _verify(
    invoice: ExtractedInvoice,
    po: PurchaseOrderRecord | None,
    trace: AgentTrace,
) -> list[Check]:
    """Verificacion determinista, antes de que el modelo opine.

    Corre entera en Python. Los resultados entran al prompt de triaje como
    hechos ya establecidos, no como algo que el modelo deba calcular.
    """
    started = time.perf_counter()
    checks = run_checks(invoice, po)
    fallidos = [c for c in checks if c.status in (CheckStatus.WARN, CheckStatus.FAIL)]
    trace.add(
        TraceStep(
            phase=Phase.VERIFICATION,
            summary=(
                f"{len(checks)} verificaciones ejecutadas en codigo, "
                f"{len(fallidos)} con observaciones."
            ),
            output=[c.model_dump(mode="json") for c in checks],
            duration_ms=_elapsed_ms(started),
        )
    )
    return checks


def _reason(
    llm: LLMClient,
    invoice: ExtractedInvoice,
    po: PurchaseOrderRecord,
    delta: Decimal,
    checks: list[Check],
    trace: AgentTrace,
) -> str:
    """Fase 4. El delta y los checks ya estan calculados; al modelo solo se le
    pide la nota en prosa."""
    started = time.perf_counter()
    prompt = build_triage_prompt(invoice, po, delta, checks)
    note = llm.reason_triage(prompt).strip()

    # Un modelo pequenio a veces devuelve vacio o basura. Hay fallback.
    if not note:
        note = _fallback_note(po, delta)
        error = "El modelo devolvio una nota vacia; se uso el texto de respaldo."
    else:
        error = None

    trace.add(
        TraceStep(
            phase=Phase.REASONING,
            summary="Nota de auditoria redactada.",
            input=prompt,
            output=note,
            duration_ms=_elapsed_ms(started),
            error=error,
        )
    )
    return note


def _fallback_note(po: PurchaseOrderRecord, delta: Decimal) -> str:
    if delta == 0:
        return f"El monto facturado coincide con la orden {po.po_number}."
    direccion = "mas" if delta > 0 else "menos"
    return (
        f"La factura cobra {abs(delta)} {direccion} que la orden {po.po_number} "
        f"({po.total_amount} autorizados). Revisar antes de aprobar."
    )


class DocumentPayload:
    """El archivo subido, para poder servirlo despues como evidencia."""

    def __init__(self, data: bytes, filename: str, content_type: str | None) -> None:
        self.data = data
        self.filename = filename
        self.content_type = content_type


def reconcile(
    session: Session,
    llm: LLMClient,
    image_bytes: bytes,
    filename: str,
    max_retries: int = 3,
    content_type: str | None = None,
) -> ReconciliationResult:
    """Ejecuta el pipeline completo y persiste el resultado con su traza."""
    trace = AgentTrace()
    doc = DocumentPayload(image_bytes, filename, content_type)

    # --- Fase 2: extraccion ------------------------------------------------
    invoice = _extract_with_retries(llm, image_bytes, trace, max_retries)

    if invoice is None:
        return _finish(
            session, trace, doc,
            invoice=None,
            po=None,
            checks=[],
            verdict=Verdict.UNCERTAIN,
            delta=None,
            note=(
                "No se pudo leer el documento de forma confiable tras varios "
                "intentos. Se requiere revision manual."
            ),
        )

    if not invoice.has_minimum_data():
        faltante = "NIT del proveedor" if not invoice.supplier_tax_id else "monto total"
        return _finish(
            session, trace, doc,
            invoice=invoice,
            po=None,
            checks=_verify(invoice, None, trace),
            verdict=Verdict.UNCERTAIN,
            delta=None,
            note=(
                f"El documento se leyo pero falta el {faltante}, que es "
                "imprescindible para reconciliar. Se requiere revision manual."
            ),
        )

    # --- Fase 3: herramienta (el modelo no participa) ----------------------
    po = _lookup(session, invoice, trace)

    # --- Verificacion determinista, antes de que el modelo opine -----------
    checks = _verify(invoice, po, trace)

    if po is None:
        # Sin registro en el ERP no hay nada que comparar. No se llama al
        # modelo: pedirle que opine sin datos es invitarlo a confabular.
        return _finish(
            session, trace, doc,
            invoice=invoice,
            po=None,
            checks=checks,
            verdict=Verdict.NO_PO_FOUND,
            delta=None,
            note=(
                f"No existe orden de compra para el NIT {invoice.supplier_tax_id} "
                f"({invoice.supplier_name or 'proveedor no identificado'}). "
                "Verificar si el proveedor esta dado de alta o si el NIT se leyo mal."
            ),
        )

    # --- Fase 4: razonamiento sobre datos limpios --------------------------
    # La resta la hace Python. Los modelos pequenios fallan en aritmetica y no
    # hay ninguna razon para delegarsela.
    delta = invoice.total_amount - po.total_amount
    note = _reason(llm, invoice, po, delta, checks, trace)

    coincide = abs(delta) <= MATCH_TOLERANCE and po.status != "CANCELLED"
    verdict = Verdict.MATCH if coincide else Verdict.MISMATCH

    return _finish(session, trace, doc, invoice, po, checks, verdict, delta, note)


def _finish(
    session: Session,
    trace: AgentTrace,
    doc: DocumentPayload,
    invoice: ExtractedInvoice | None,
    po: PurchaseOrderRecord | None,
    checks: list[Check],
    verdict: Verdict,
    delta: Decimal | None,
    note: str,
) -> ReconciliationResult:
    """Fase 5: persistir todo, incluida la traza que justifica el dictamen."""
    started = time.perf_counter()

    # Politica de auto-aprobacion: en codigo, no en el modelo. Exige veredicto
    # MATCH *y* que todo lo evaluable haya pasado. Un SKIPPED no auto-aprueba.
    auto_approved = verdict is Verdict.MATCH and all_clear(checks)

    invoice_id = save_invoice(session, doc.filename, invoice)
    document_path = store_document(invoice_id, doc.data, doc.filename)
    attach_document(session, invoice_id, document_path, doc.content_type)

    trace.add(
        TraceStep(
            phase=Phase.PERSIST,
            summary=(
                f"Dictamen {verdict.value} registrado"
                + (" y auto-aprobado." if auto_approved else "; queda a revisar.")
            ),
            duration_ms=_elapsed_ms(started),
        )
    )
    reconciliation_id = save_reconciliation(
        session,
        invoice_id=invoice_id,
        po_id=po.id if po else None,
        verdict=verdict,
        auto_approved=auto_approved,
        amount_delta=delta,
        note=note,
        checks=checks,
        trace=trace,
    )
    return ReconciliationResult(
        verdict=verdict,
        auto_approved=auto_approved,
        checks=checks,
        note=note,
        invoice=invoice,
        purchase_order=po,
        amount_delta=delta,
        trace=trace,
        invoice_id=invoice_id,
        reconciliation_id=reconciliation_id,
    )


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _short_error(exc: Exception) -> str:
    """Mensaje compacto para reinyectar en el prompt. Un ValidationError crudo
    de Pydantic es demasiado largo y confunde a un modelo pequenio."""
    if isinstance(exc, ValidationError):
        partes = [
            f"{'.'.join(str(p) for p in e['loc']) or 'raiz'}: {e['msg']}"
            for e in exc.errors()[:3]
        ]
        return "; ".join(partes)
    return str(exc)
