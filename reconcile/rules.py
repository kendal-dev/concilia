"""Explicaciones por REGLA, nunca por modelo.

El brief pide una frase que un humano verifique en 5 segundos. Generarla con el modelo
seria mas lento, menos confiable y alucinable. Aqui son deterministas y siempre hay una:
el caso generico cubre lo que no encaje en ningun patron.
"""

TOL = 0.01


def _digitos(x):
    return sorted(c for c in f"{x:.2f}" if c.isdigit())


def transpuestos(a, b):
    """Mismos digitos en distinto orden: 247.50 vs 274.50."""
    if a is None or b is None or abs(a - b) < TOL:
        return False
    return _digitos(a) == _digitos(b)


def diferencia_iva(a, b, tasa=0.13, tolerancia=0.02):
    """La diferencia relativa se parece al IVA boliviano (13%)."""
    if not a or not b:
        return False
    base = max(abs(a), abs(b))
    if base == 0:
        return False
    return abs(abs(a - b) / base - tasa / (1 + tasa)) < tolerancia or \
        abs(abs(a - b) / min(abs(a), abs(b)) - tasa) < tolerancia


def decimal_corrido(a, b, tolerancia=0.02):
    """Un monto es ~10x el otro: 247.50 vs 24.75."""
    if not a or not b:
        return False
    alto, bajo = max(abs(a), abs(b)), min(abs(a), abs(b))
    if bajo == 0:
        return False
    return abs(alto / bajo - 10.0) < tolerancia * 10


def explicar(reconciliacion, extraido, vendor_texto=""):
    """Devuelve (patron, explicacion). Muta nada."""
    veredicto = reconciliacion.get("verdict")
    registro = reconciliacion.get("_registro")
    total = _v(extraido.get("total"))
    duplicados = reconciliacion.get("_duplicados") or []

    if veredicto == "UNCERTAIN":
        return "sin_lectura", "No pude leer el total con seguridad. Requiere revision humana."

    if veredicto == "NO_MATCH":
        nombre = vendor_texto or _v(extraido.get("vendor")) or "proveedor desconocido"
        fecha = _v(extraido.get("date")) or "fecha desconocida"
        return "sin_par", f"Sin registro para '{nombre}' alrededor de {fecha}."

    libro = float(registro["monto"]) if registro else None

    if duplicados and veredicto == "MATCH":
        ids = ", ".join(f"#{d['id']}" for d in duplicados[:2])
        return "duplicado", (f"Coincide, pero el libro tiene otro cargo identico "
                             f"({ids}) por {libro:.2f} el mismo dia.")

    if veredicto == "MATCH":
        return "coincide", (f"Coincide con el registro #{registro['id']} "
                            f"({registro['proveedor']}, {libro:.2f}).")

    # MISMATCH
    delta = round(total - libro, 2)
    if transpuestos(total, libro):
        return "transposicion", (f"Ticket {total:.2f} vs libro {libro:.2f} - "
                                 f"posible transposicion de digitos.")
    if decimal_corrido(total, libro):
        return "decimal_corrido", (f"Ticket {total:.2f} vs libro {libro:.2f} - "
                                   f"posible corrimiento de decimal.")
    if diferencia_iva(total, libro):
        return "iva", (f"Diferencia de {abs(delta):.2f} entre {total:.2f} y {libro:.2f} - "
                       f"compatible con IVA del 13% no registrado.")
    if duplicados:
        ids = ", ".join(f"#{d['id']}" for d in duplicados[:2])
        return "duplicado", (f"Monto distinto y ademas hay cargos repetidos en el libro "
                             f"({ids}).")
    return "generico", (f"Ticket {total:.2f} vs libro {libro:.2f} - "
                        f"diferencia de {abs(delta):.2f}.")


def _v(campo):
    return campo.get("value") if isinstance(campo, dict) else campo
