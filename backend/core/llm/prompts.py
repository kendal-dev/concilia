"""Plantillas de prompt.

Escritas pensando en un modelo de 1-4B: instrucciones cortas, un solo trabajo
por prompt, esquema explicito y prohibicion expresa de inventar. Viven aca
separadas del orquestador para poder iterarlas sin tocar la logica.
"""

from decimal import Decimal

from backend.core.schemas import (
    Check,
    CheckStatus,
    ExtractedInvoice,
    PurchaseOrderRecord,
)

EXTRACTION_SYSTEM = """Sos un transcriptor de documentos. Tu unico trabajo es \
leer la imagen y copiar lo que dice.

NO razones, NO calcules, NO completes lo que no ves.
Si un campo no es legible, devolve null. Nunca lo inventes.

Respondes EXCLUSIVAMENTE con un objeto JSON con este esquema:
{
  "supplier_tax_id": string|null,   // NIT del proveedor
  "supplier_name":   string|null,
  "invoice_number":  string|null,
  "invoice_date":    string|null,
  "subtotal":        number|null,   // monto antes de impuestos
  "tax_amount":      number|null,   // IVA
  "total_amount":    number|null,   // total cobrado, sin simbolo de moneda
  "currency":        string|null,
  "line_items": [
    {"description": string, "quantity": number|null,
     "unit_price": number|null, "line_total": number|null}
  ],
  "confidence": {"supplier_tax_id": 0.0-1.0, "total_amount": 0.0-1.0}
}

Sin texto antes ni despues del JSON. Sin bloques de codigo. Sin explicaciones."""

RETRY_TEMPLATE = """Tu respuesta anterior fue rechazada por el validador.

Error: {error}

Corregilo y devolve UNICAMENTE el objeto JSON valido. Sin texto alrededor."""


TRIAGE_SYSTEM = """Sos un auditor de cuentas por pagar. Recibis datos ya \
verificados por el sistema y escribis una nota interna breve.

Reglas:
- Usa SOLO los datos que te doy. No inventes montos, cantidades ni proveedores.
- Las diferencias YA fueron calculadas y verificadas. Repetilas, no las recalcules.
- 2 o 3 oraciones como maximo.
- Decile al operador que accion tomar.

Respondes con texto plano, sin JSON ni formato."""

_SIMBOLO = {"PASS": "OK", "WARN": "ATENCION", "FAIL": "FALLA", "SKIPPED": "NO EVALUADO"}


def build_retry_prompt(error: str) -> str:
    return RETRY_TEMPLATE.format(error=error)


def build_triage_prompt(
    invoice: ExtractedInvoice,
    po: PurchaseOrderRecord,
    delta: Decimal,
    checks: list[Check] | None = None,
) -> str:
    """Arma el prompt de la Fase 4 con todo ya calculado.

    El modelo nunca ve la imagen ni la base de datos: solo estos resumenes.
    Eso evita la amnesia de contexto que aparece cuando se le pide extraer y
    razonar en la misma llamada. Los checks entran como hechos establecidos,
    de modo que el modelo tenga que redactar, no deducir.
    """
    lines = [
        "=== DATOS EXTRAIDOS DE LA FACTURA FISICA ===",
        f"Proveedor: {invoice.supplier_name or 'no legible'}",
        f"NIT: {invoice.supplier_tax_id}",
        f"Numero de factura: {invoice.invoice_number or 'no legible'}",
        f"Fecha: {invoice.invoice_date or 'no legible'}",
        f"Total cobrado: {invoice.total_amount} {invoice.currency or ''}".strip(),
    ]
    lines += _formatear_lineas("Lineas facturadas", _lineas_factura(invoice))

    lines += [
        "",
        "=== REGISTRO OFICIAL RECUPERADO DEL ERP ===",
        f"Orden de compra: {po.po_number}",
        f"Proveedor: {po.supplier_name}",
        f"Estado de la orden: {po.status}",
        f"Total autorizado: {po.total_amount} {po.currency}",
    ]
    lines += _formatear_lineas("Lineas autorizadas", _lineas_po(po))

    lines += ["", "=== DIFERENCIA (calculada por el sistema, no la recalcules) ==="]
    if delta > 0:
        lines.append(f"La factura cobra {delta} MAS de lo autorizado.")
    elif delta < 0:
        lines.append(f"La factura cobra {abs(delta)} MENOS de lo autorizado.")
    else:
        lines.append("Los montos coinciden exactamente.")

    if po.status == "CANCELLED":
        lines.append("ATENCION: la orden de compra figura CANCELADA.")

    if checks:
        lines += ["", "=== VERIFICACIONES YA EJECUTADAS POR EL SISTEMA ==="]
        for c in checks:
            if c.status is CheckStatus.SKIPPED:
                continue
            lines.append(f"[{_SIMBOLO[c.status.value]}] {c.label}: {c.detail}")

    lines += ["", "Escribi la nota interna para el operador."]
    return "\n".join(lines)


def _lineas_factura(invoice: ExtractedInvoice) -> list[str]:
    return [
        f"- {li.description}: {_num(li.quantity)} x {_num(li.unit_price)} "
        f"= {_num(li.line_total)}"
        for li in invoice.line_items
    ]


def _lineas_po(po: PurchaseOrderRecord) -> list[str]:
    return [
        f"- {li.description}: {_num(li.quantity)} x {_num(li.unit_price)} "
        f"= {_num(li.line_total)}"
        for li in po.line_items
    ]


def _formatear_lineas(titulo: str, lineas: list[str]) -> list[str]:
    if not lineas:
        return []
    return [f"{titulo}:"] + lineas


def _num(valor: Decimal | None) -> str:
    """Sin ceros decimales sobrantes, para no gastar tokens en '24.000'."""
    if valor is None:
        return "?"
    normalizado = valor.normalize()
    if normalizado == normalizado.to_integral_value():
        return str(normalizado.quantize(Decimal("1")))
    return str(normalizado)
