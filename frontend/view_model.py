"""Adapta las dos formas que devuelve el backend a un unico modelo de vista.

`POST /reconcile` devuelve un ReconciliationResult; `GET /reconciliations/{id}`
devuelve la fila de la base. La tarjeta no deberia conocer esa diferencia, asi
que se normaliza aca.

Regla importante: este modulo NO compara nada. Que valores estan en discrepancia
lo decidio el backend en checks.py; aca solo se traducen esos veredictos a
banderas de color.
"""

from decimal import Decimal, InvalidOperation

# Que check pinta en rojo que fila de la factura.
_CHECK_A_FILA = {
    "quantity_vs_po": "cantidad",
    "unit_price_vs_po": "precio unit.",
    "total_vs_po": "total",
}

_OBSERVADO = {"WARN", "FAIL"}


def _dec(valor) -> Decimal | None:
    if valor is None or valor == "":
        return None
    try:
        return Decimal(str(valor))
    except (InvalidOperation, ValueError):
        return None


def moneda(valor, simbolo: str = "Bs") -> str:
    """Bs 2.040,00 -> formato local, con separador de miles."""
    d = _dec(valor)
    if d is None:
        return "—"
    entero, _, decimales = f"{d:,.2f}".partition(".")
    entero = entero.replace(",", ".")
    return f"{simbolo} {entero},{decimales}"


def cantidad(valor, unidad: str = "") -> str:
    """24.000 -> '24 cajas'. Sin ceros decimales sobrantes."""
    d = _dec(valor)
    if d is None:
        return "—"
    texto = str(d.normalize())
    if d == d.to_integral_value():
        texto = str(d.quantize(Decimal("1")))
    return f"{texto} {unidad}".strip()


def desde_reconcile(resp: dict) -> dict:
    """Normaliza la respuesta de POST /reconcile."""
    invoice = resp.get("invoice") or {}
    po = resp.get("purchase_order") or {}
    return _construir(
        rec_id=resp.get("reconciliation_id"),
        invoice=invoice,
        invoice_lines=invoice.get("line_items") or [],
        po=po,
        po_lines=po.get("line_items") or [],
        checks=resp.get("checks") or [],
        note=resp.get("note", ""),
        verdict=resp.get("verdict", ""),
        auto_approved=bool(resp.get("auto_approved")),
        human_decision=resp.get("human_decision", "PENDING"),
        trace=(resp.get("trace") or {}).get("steps") or [],
        tiene_documento=True,
    )


def desde_detalle(row: dict) -> dict:
    """Normaliza la fila de GET /reconciliations/{id}."""
    invoice = row.get("raw_extraction") or {}
    po = {
        "po_number": row.get("po_number"),
        "supplier_name": row.get("supplier_name"),
        "supplier_tax_id": row.get("supplier_tax_id"),
        "total_amount": row.get("po_total"),
        "status": row.get("po_status"),
        "currency": row.get("currency") or "BOB",
    }
    return _construir(
        rec_id=row.get("id"),
        invoice=invoice,
        invoice_lines=invoice.get("line_items") or [],
        po=po if row.get("po_number") else {},
        po_lines=row.get("po_line_items") or [],
        checks=row.get("checks") or [],
        note=row.get("note") or "",
        verdict=row.get("verdict", ""),
        auto_approved=bool(row.get("auto_approved")),
        human_decision=row.get("human_decision", "PENDING"),
        trace=(row.get("trace") or {}).get("steps") or [],
        tiene_documento=bool(row.get("document_path")),
    )


def _construir(
    rec_id, invoice, invoice_lines, po, po_lines, checks, note, verdict,
    auto_approved, human_decision, trace, tiene_documento,
) -> dict:
    observados = {c["name"] for c in checks if c["status"] in _OBSERVADO}
    filas_en_rojo = {
        fila for name, fila in _CHECK_A_FILA.items() if name in observados
    }

    return {
        "rec_id": rec_id,
        "titulo": invoice.get("invoice_number") or "sin numero",
        "proveedor": invoice.get("supplier_name")
        or po.get("supplier_name")
        or "proveedor no identificado",
        "verdict": verdict,
        "auto_approved": auto_approved,
        "estado": "auto-aprobada" if auto_approved else "a revisar",
        "human_decision": human_decision,
        "note": note,
        "checks": checks,
        "trace": trace,
        "tiene_documento": tiene_documento,
        "po_numero": po.get("po_number"),
        "filas": _filas(invoice, invoice_lines, po, po_lines, filas_en_rojo),
    }


def _filas(invoice, invoice_lines, po, po_lines, en_rojo) -> list[dict]:
    """Las filas de la comparacion lado a lado.

    Cantidad y precio unitario solo tienen sentido como fila unica cuando el
    documento tiene una sola linea, que es el caso del mockup. Con varias
    lineas se listan una por una mas abajo.
    """
    filas: list[dict] = []
    unica_factura = invoice_lines[0] if len(invoice_lines) == 1 else None
    unica_po = po_lines[0] if len(po_lines) == 1 else None

    if unica_factura is not None:
        filas.append({
            "etiqueta": "cantidad",
            "factura": cantidad(unica_factura.get("quantity"), "unid."),
            "oc": cantidad(unica_po.get("quantity"), "unid.") if unica_po else "—",
            "discrepa": "cantidad" in en_rojo,
        })
        filas.append({
            "etiqueta": "precio unit.",
            "factura": moneda(unica_factura.get("unit_price")),
            "oc": moneda(unica_po.get("unit_price")) if unica_po else "—",
            "discrepa": "precio unit." in en_rojo,
        })

    filas.append({
        "etiqueta": "total",
        "factura": moneda(invoice.get("total_amount")),
        "oc": moneda(po.get("total_amount")) if po else "—",
        "discrepa": "total" in en_rojo,
    })
    filas.append({
        "etiqueta": "NIT",
        "factura": invoice.get("supplier_tax_id") or "—",
        "oc": po.get("supplier_tax_id") or invoice.get("supplier_tax_id") or "—",
        # El NIT es la clave de busqueda: si no coincidiera, no habria OC.
        "discrepa": False,
    })
    return filas


def lineas_detalladas(vm_invoice_lines, po_lines) -> list[dict]:
    """Para facturas multi-linea: cada linea con su contraparte en la OC."""
    por_desc = {(l.get("description") or "").strip().lower(): l for l in po_lines}
    salida = []
    for linea in vm_invoice_lines:
        desc = (linea.get("description") or "").strip()
        par = por_desc.get(desc.lower())
        salida.append({
            "descripcion": desc,
            "factura": f"{cantidad(linea.get('quantity'))} x {moneda(linea.get('unit_price'))}",
            "oc": (
                f"{cantidad(par.get('quantity'))} x {moneda(par.get('unit_price'))}"
                if par else "no figura en la OC"
            ),
            "discrepa": par is None
            or _dec(linea.get("quantity")) != _dec(par.get("quantity")),
        })
    return salida
