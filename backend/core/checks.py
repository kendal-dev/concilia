"""Verificacion determinista de una factura contra su orden de compra.

Este modulo entero corre SIN TOCAR EL LLM. Cada numero que sale de aca lo
calculo Python. Es lo que el dashboard muestra como "verificado por codigo",
separado visualmente de la prosa que redacta el modelo.

La postura frente a la falta de datos es la misma que en el resto del sistema:
si no se pudo leer lo necesario, el check es SKIPPED. No se adivina.
"""

import re
import unicodedata
from decimal import Decimal
from difflib import get_close_matches

from backend.core.schemas import (
    Check,
    CheckStatus,
    ExtractedInvoice,
    ExtractedLineItem,
    LineItem,
    PurchaseOrderRecord,
)

# Tolerancia de un centavo: absorbe redondeos sin dejar pasar un sobrecargo.
TOLERANCE = Decimal("0.01")

# IVA Bolivia.
TAX_RATE = Decimal("0.13")
# El IVA se calcula sobre montos ya redondeados, asi que el residuo crece con
# el monto: una tolerancia fija daria falsos positivos en facturas grandes.
TAX_TOLERANCE_MIN = Decimal("0.50")
TAX_TOLERANCE_RATE = Decimal("0.001")


def _tolerancia_iva(subtotal: Decimal) -> Decimal:
    return max(TAX_TOLERANCE_MIN, (subtotal * TAX_TOLERANCE_RATE).copy_abs())

# Umbral de similitud para emparejar descripciones de linea.
_MATCH_CUTOFF = 0.8


def _normalize(text: str) -> str:
    """Minusculas, sin acentos, espacios colapsados.

    El OCR de un documento arrugado devuelve la misma descripcion escrita de
    formas ligeramente distintas; normalizar evita que eso cuente como
    discrepancia real.
    """
    sin_acentos = "".join(
        c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"\s+", " ", sin_acentos).strip().lower()


def match_lines(
    invoice_lines: list[ExtractedLineItem], po_lines: list[LineItem]
) -> tuple[list[tuple[ExtractedLineItem, LineItem]], list[ExtractedLineItem]]:
    """Empareja lineas de la factura con lineas de la OC por descripcion.

    Devuelve (pares, huerfanas). Una linea sin par no es un error silencioso:
    el llamador la reporta como advertencia explicita.
    """
    disponibles = {_normalize(li.description): li for li in po_lines}
    pares: list[tuple[ExtractedLineItem, LineItem]] = []
    huerfanas: list[ExtractedLineItem] = []

    for inv_line in invoice_lines:
        clave = _normalize(inv_line.description)
        if clave in disponibles:
            pares.append((inv_line, disponibles.pop(clave)))
            continue
        # Coincidencia aproximada para tolerar ruido de OCR.
        cercanas = get_close_matches(clave, list(disponibles), n=1, cutoff=_MATCH_CUTOFF)
        if cercanas:
            pares.append((inv_line, disponibles.pop(cercanas[0])))
        else:
            huerfanas.append(inv_line)

    return pares, huerfanas


def _skip(name: str, label: str, motivo: str) -> Check:
    return Check(name=name, label=label, status=CheckStatus.SKIPPED, detail=motivo)


# ---------------------------------------------------------------------
# Checks internos del documento (no necesitan la OC)
# ---------------------------------------------------------------------

def check_line_sum(invoice: ExtractedInvoice) -> Check:
    """Coherencia interna: las lineas deben sumar el total cobrado."""
    name, label = "line_sum", "suma de lineas"

    if not invoice.line_items:
        return _skip(name, label, "La factura no tiene lineas legibles.")
    if invoice.total_amount is None:
        return _skip(name, label, "No se pudo leer el total de la factura.")
    if any(li.line_total is None for li in invoice.line_items):
        return _skip(name, label, "Alguna linea no tiene importe legible.")

    suma = sum((li.line_total for li in invoice.line_items), Decimal("0"))
    diff = suma - invoice.total_amount

    if abs(diff) <= TOLERANCE:
        return Check(
            name=name, label=label, status=CheckStatus.PASS,
            detail=_plural(len(invoice.line_items), "linea suma", "lineas suman")
            + " el total declarado.",
            expected=str(invoice.total_amount), actual=str(suma),
        )
    return Check(
        name=name, label=label, status=CheckStatus.FAIL,
        detail=f"Las lineas suman {suma} pero el total declarado es {invoice.total_amount}.",
        expected=str(invoice.total_amount), actual=str(suma),
    )


def check_tax(invoice: ExtractedInvoice) -> Check:
    """Subtotal + IVA debe dar el total, y el IVA debe ser el 13%."""
    name, label = "tax", "impuestos"

    if invoice.subtotal is None or invoice.tax_amount is None:
        return _skip(name, label, "La factura no declara subtotal e impuesto por separado.")
    if invoice.total_amount is None:
        return _skip(name, label, "No se pudo leer el total de la factura.")

    suma = invoice.subtotal + invoice.tax_amount
    if abs(suma - invoice.total_amount) > TOLERANCE:
        return Check(
            name=name, label=label, status=CheckStatus.FAIL,
            detail=f"Subtotal mas impuesto da {suma}, pero el total es {invoice.total_amount}.",
            expected=str(invoice.total_amount), actual=str(suma),
        )

    esperado = (invoice.subtotal * TAX_RATE).quantize(Decimal("0.01"))
    if abs(invoice.tax_amount - esperado) > _tolerancia_iva(invoice.subtotal):
        return Check(
            name=name, label=label, status=CheckStatus.FAIL,
            detail=(
                f"El IVA declarado es {invoice.tax_amount}, pero el 13% de "
                f"{invoice.subtotal} son {esperado}."
            ),
            expected=str(esperado), actual=str(invoice.tax_amount),
        )

    return Check(
        name=name, label=label, status=CheckStatus.PASS,
        detail=f"Subtotal {invoice.subtotal} + IVA 13% {invoice.tax_amount} = {invoice.total_amount}.",
        expected=str(esperado), actual=str(invoice.tax_amount),
    )


# ---------------------------------------------------------------------
# Checks contra la orden de compra
# ---------------------------------------------------------------------

def _line_field_check(
    invoice: ExtractedInvoice,
    po: PurchaseOrderRecord,
    name: str,
    label: str,
    campo: str,
    unidad: str,
) -> Check:
    """Compara un campo linea a linea contra la OC. Sirve para cantidad y
    precio unitario, que se verifican igual pero informan distinto."""
    if not invoice.line_items:
        return _skip(name, label, "La factura no tiene lineas legibles.")
    if not po.line_items:
        return _skip(name, label, f"La orden {po.po_number} no tiene lineas cargadas.")

    pares, huerfanas = match_lines(invoice.line_items, po.line_items)

    if not pares:
        return Check(
            name=name, label=label, status=CheckStatus.WARN,
            detail="Ninguna linea de la factura coincide con la orden de compra.",
        )

    diferencias: list[str] = []
    for inv_line, po_line in pares:
        valor_factura = getattr(inv_line, campo)
        if valor_factura is None:
            continue
        valor_po = getattr(po_line, campo)
        if abs(valor_factura - valor_po) > TOLERANCE:
            diferencias.append(
                f"{inv_line.description}: {_fmt(valor_factura)} vs "
                f"{_fmt(valor_po)} {unidad}".strip()
            )

    # Huerfanas y diferencias no se excluyen: una factura puede traer una linea
    # que no figura en la orden Y ademas cobrar otra con la cantidad cambiada.
    # Retornar solo lo primero que aparecia descartaba la otra mitad del motivo.
    observaciones: list[str] = []
    if huerfanas:
        nombres = ", ".join(li.description for li in huerfanas)
        observaciones.append(f"No figura(n) en la orden: {nombres}")
    if diferencias:
        observaciones.append("; ".join(diferencias))

    if observaciones:
        return Check(
            name=name, label=label, status=CheckStatus.WARN,
            detail=". ".join(observaciones) + ".",
            expected=_fmt(getattr(pares[0][1], campo)) if diferencias else None,
            actual=_fmt(getattr(pares[0][0], campo)) if diferencias else None,
        )

    return Check(
        name=name, label=label, status=CheckStatus.PASS,
        detail="Coincide en " + _plural(len(pares), "la linea comparada", "las lineas comparadas") + ".",
    )


def check_quantity_vs_po(invoice: ExtractedInvoice, po: PurchaseOrderRecord) -> Check:
    return _line_field_check(
        invoice, po, "quantity_vs_po", "cantidad vs OC", "quantity", "unidades"
    )


def check_unit_price_vs_po(invoice: ExtractedInvoice, po: PurchaseOrderRecord) -> Check:
    return _line_field_check(
        invoice, po, "unit_price_vs_po", "precio unit. vs OC", "unit_price", ""
    )


def check_total_vs_po(invoice: ExtractedInvoice, po: PurchaseOrderRecord) -> Check:
    name, label = "total_vs_po", "total vs OC"

    if invoice.total_amount is None:
        return _skip(name, label, "No se pudo leer el total de la factura.")

    delta = invoice.total_amount - po.total_amount
    if abs(delta) <= TOLERANCE:
        return Check(
            name=name, label=label, status=CheckStatus.PASS,
            detail=f"El total facturado coincide con la orden {po.po_number}.",
            expected=str(po.total_amount), actual=str(invoice.total_amount),
        )

    direccion = "mas" if delta > 0 else "menos"
    return Check(
        name=name, label=label, status=CheckStatus.FAIL,
        detail=(
            f"La factura cobra {abs(delta)} {direccion} que la orden "
            f"{po.po_number} ({po.total_amount} autorizados)."
        ),
        expected=str(po.total_amount), actual=str(invoice.total_amount),
    )


def check_po_status(po: PurchaseOrderRecord) -> Check:
    name, label = "po_status", "estado de la OC"

    if po.status == "CANCELLED":
        return Check(
            name=name, label=label, status=CheckStatus.FAIL,
            detail=f"La orden {po.po_number} figura CANCELADA. No corresponde pagarla.",
            actual=po.status,
        )
    if po.status == "CLOSED":
        return Check(
            name=name, label=label, status=CheckStatus.WARN,
            detail=f"La orden {po.po_number} ya estaba cerrada.",
            actual=po.status,
        )
    return Check(
        name=name, label=label, status=CheckStatus.PASS,
        detail=f"La orden {po.po_number} esta vigente ({po.status}).",
        actual=po.status,
    )


# ---------------------------------------------------------------------
# Entrada publica
# ---------------------------------------------------------------------

def run_checks(
    invoice: ExtractedInvoice, po: PurchaseOrderRecord | None
) -> list[Check]:
    """Corre todas las verificaciones. Sin OC solo aplican las internas."""
    checks = [check_line_sum(invoice), check_tax(invoice)]
    if po is None:
        return checks
    checks += [
        check_quantity_vs_po(invoice, po),
        check_unit_price_vs_po(invoice, po),
        check_total_vs_po(invoice, po),
        check_po_status(po),
    ]
    return checks


def all_clear(checks: list[Check]) -> bool:
    """True solo si todo lo evaluable paso.

    Un SKIPPED nunca habilita la auto-aprobacion: no verificar no es lo mismo
    que verificar con exito.
    """
    return bool(checks) and all(c.status is CheckStatus.PASS for c in checks)


def _plural(n: int, singular: str, plural: str) -> str:
    """Concordancia: "1 linea suma" vs "3 lineas suman"."""
    return f"{n} {singular}" if n == 1 else f"{n} {plural}"


def _fmt(valor: Decimal | None) -> str:
    """Quita ceros decimales sobrantes: 24.000 -> 24, 85.50 -> 85.50."""
    if valor is None:
        return "-"
    normalizado = valor.normalize()
    # normalize() puede dar notacion exponencial en enteros grandes (1E+2).
    if normalizado == normalizado.to_integral_value():
        return str(normalizado.quantize(Decimal("1")))
    return str(normalizado)
