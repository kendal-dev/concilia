"""Contratos de datos entre las fases del pipeline.

Todo importe monetario viaja como Decimal, nunca float: comparar plata con
floats produce falsos mismatches por redondeo (0.1 + 0.2 != 0.3).
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Verdict(str, Enum):
    MATCH = "MATCH"
    MISMATCH = "MISMATCH"
    NO_PO_FOUND = "NO_PO_FOUND"
    # El agente no logro extraer datos confiables. Preferimos decir "no se"
    # antes que inventar un numero.
    UNCERTAIN = "UNCERTAIN"


class HumanDecision(str, Enum):
    """El agente triajea, el humano decide. Nunca se salta este paso."""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    ESCALATED = "ESCALATED"


class Phase(str, Enum):
    EXTRACTION = "extraction"
    LOOKUP = "lookup"
    # Verificacion determinista: corre en Python, sin tocar el modelo.
    VERIFICATION = "verification"
    REASONING = "reasoning"
    PERSIST = "persist"


# ---------------------------------------------------------------------
# Fase 2: lo que el LLM debe devolver al leer el documento.
# ---------------------------------------------------------------------

class ExtractedLineItem(BaseModel):
    """Una linea de la factura fisica. Todo opcional salvo la descripcion:
    un modelo pequenio a menudo lee el texto pero no los numeros."""

    model_config = ConfigDict(extra="forbid")

    description: str
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    line_total: Decimal | None = None


class ExtractedInvoice(BaseModel):
    """Salida validada de la fase de extraccion.

    `extra="forbid"` es intencional: si el modelo inventa un campo que no
    pedimos, queremos que la validacion falle y se dispare el reintento, no
    que el dato basura entre silenciosamente al pipeline.
    """

    model_config = ConfigDict(extra="forbid")

    supplier_tax_id: str | None = None
    supplier_name: str | None = None
    invoice_number: str | None = None
    # Fecha como string: los modelos pequenios devuelven formatos inconsistentes
    # y no vale la pena tirar toda la extraccion por eso.
    invoice_date: str | None = None
    subtotal: Decimal | None = None
    tax_amount: Decimal | None = None
    total_amount: Decimal | None = None
    currency: str | None = None
    line_items: list[ExtractedLineItem] = Field(default_factory=list)
    # Confianza declarada por el modelo, por campo (0.0 - 1.0).
    confidence: dict[str, float] = Field(default_factory=dict)

    def has_minimum_data(self) -> bool:
        """Sin NIT y sin monto no hay nada contra que reconciliar."""
        return self.supplier_tax_id is not None and self.total_amount is not None


# ---------------------------------------------------------------------
# Fase 3: lo que devuelve el ERP.
# ---------------------------------------------------------------------

class LineItem(BaseModel):
    description: str
    quantity: Decimal
    unit_price: Decimal
    line_total: Decimal


class PurchaseOrderRecord(BaseModel):
    id: int
    po_number: str
    supplier_tax_id: str
    supplier_name: str
    currency: str
    total_amount: Decimal
    status: str
    issued_at: str
    line_items: list[LineItem] = Field(default_factory=list)


# ---------------------------------------------------------------------
# Traza de auditoria: lo que el operador (y el jurado) miran.
# ---------------------------------------------------------------------

class TraceStep(BaseModel):
    phase: Phase
    summary: str
    input: Any = None
    output: Any = None
    duration_ms: int = 0
    retries: int = 0
    error: str | None = None


class AgentTrace(BaseModel):
    steps: list[TraceStep] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=datetime.now)

    def add(self, step: TraceStep) -> None:
        self.steps.append(step)

    @property
    def total_retries(self) -> int:
        return sum(s.retries for s in self.steps)


# ---------------------------------------------------------------------
# Verificacion determinista. Estos modelos viven aca y no en checks.py
# para que checks.py pueda importarlos sin ciclo.
# ---------------------------------------------------------------------

class CheckStatus(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"
    # No evaluable con los datos que se pudieron leer. Es de primera clase:
    # un check sin datos se declara no evaluable, no se inventa un resultado.
    SKIPPED = "SKIPPED"


class Check(BaseModel):
    """Una verificacion calculada integramente en Python.

    Ninguno de estos valores pasa por el modelo. Es lo que el dashboard
    muestra como "verificado por codigo".
    """

    name: str
    label: str
    status: CheckStatus
    detail: str
    expected: str | None = None
    actual: str | None = None


class ReconciliationResult(BaseModel):
    verdict: Verdict
    # Politica de auto-aprobacion resuelta en codigo: MATCH y ningun check
    # en WARN/FAIL. Vive aca para que el frontend no la reimplemente.
    auto_approved: bool = False
    # Verificaciones deterministas. El frontend las muestra como
    # "verificado por codigo" para separarlas visualmente de la prosa del LLM.
    checks: list[Check] = Field(default_factory=list)
    note: str
    invoice: ExtractedInvoice | None = None
    purchase_order: PurchaseOrderRecord | None = None
    # Calculado por Python, no por el modelo. Positivo = la factura cobra de mas.
    amount_delta: Decimal | None = None
    trace: AgentTrace
    invoice_id: int | None = None
    reconciliation_id: int | None = None
    human_decision: HumanDecision = HumanDecision.PENDING

    @property
    def ui_state(self) -> str:
        """Los cuatro veredictos colapsados a los dos estados del dashboard."""
        return "auto-aprobada" if self.auto_approved else "a revisar"
