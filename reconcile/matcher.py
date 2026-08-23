"""Cascada de cruce recibo -> libro de gastos.

| Nivel | Estrategia                                   | Confianza | Veredicto |
|-------|----------------------------------------------|-----------|-----------|
| 1     | proveedor exacto + fecha + monto             | 1.00      | MATCH     |
| 2     | proveedor fuzzy + fecha + monto              | 0.85      | MATCH     |
| 3     | proveedor (exacto o fuzzy) + fecha +-3d,     | 0.75      | MISMATCH  |
|       | monto DISTINTO                               |           |           |
| 4     | fecha +-3d + monto exacto, sin proveedor     | 0.70      | MATCH     |
| 5     | monto exacto en el mismo mes                 | 0.50      | MATCH     |
| -     | nada                                         | -         | NO_MATCH  |

El nivel 3 es el que hace existir a `MISMATCH`: si todos los niveles exigieran monto
exacto, un gasto con el monto alterado en el libro caeria en `NO_MATCH` y el sistema
nunca podria decir "el ticket dice 247 y tu libro dice 274".

Fuzzy de proveedor: obligatorio. El OCR devuelve nombres mutilados ("FARMAC1A CRUZ").
Con ~26 proveedores no hace falta fuzzy en SQL: se traen todos una vez y se compara
en Python con difflib sobre `nombre_norm`.
"""
from difflib import SequenceMatcher

from .text import normalizar

UMBRAL_FUZZY = 0.75


def mejor_proveedor(vendor_ocr, proveedores, umbral=UMBRAL_FUZZY):
    """Devuelve (registro_proveedor, ratio) o (None, 0.0)."""
    v = normalizar(vendor_ocr)
    if not v:
        return None, 0.0
    mejor, ratio_mejor = None, 0.0
    for p in proveedores:
        r = SequenceMatcher(None, v, p["nombre_norm"]).ratio()
        if r > ratio_mejor:
            mejor, ratio_mejor = p, r
    if ratio_mejor >= umbral:
        return mejor, round(ratio_mejor, 3)
    return None, round(ratio_mejor, 3)


def _valor(campo):
    return campo.get("value") if isinstance(campo, dict) else campo


def cruzar(extraido, repo):
    """extraido = bloque `extracted` del contrato. Devuelve el bloque `reconciliation`
    sin explicacion (la pone `rules.explicar`)."""
    vendor = _valor(extraido.get("vendor")) or ""
    fecha = _valor(extraido.get("date"))
    total = _valor(extraido.get("total"))

    base = {
        "matched_record_id": None,
        "match_strategy": None,
        "match_confidence": 0.0,
        "verdict": "NO_MATCH",
        "delta": None,
        "explanation": "",
        "human_review_required": False,
        "_registro": None,
        "_fuzzy_ratio": 0.0,
        "_duplicados": [],
    }

    if total is None:
        base["verdict"] = "UNCERTAIN"
        base["match_strategy"] = None
        return base

    proveedores = repo.listar_proveedores_norm()
    prov, ratio = mejor_proveedor(vendor, proveedores)
    base["_fuzzy_ratio"] = ratio
    prov_norm = prov["nombre_norm"] if prov else None
    exacto_de_nombre = bool(prov) and normalizar(vendor) == prov["nombre_norm"]

    # --- nivel 1 y 2: proveedor + fecha + monto ---
    if prov_norm and fecha:
        filas = repo.buscar_exacto(prov_norm, fecha, total)
        if filas:
            return _cerrar(base, filas[0], repo,
                           "exact" if exacto_de_nombre else "fuzzy_vendor",
                           1.00 if exacto_de_nombre else 0.85, "MATCH", total)

    # --- nivel 3: mismo proveedor y fecha cercana, monto distinto -> MISMATCH ---
    if prov_norm and fecha:
        filas = repo.buscar_por_proveedor_fecha(prov_norm, fecha, tolerancia_dias=3)
        if filas:
            fila = min(filas, key=lambda f: abs(float(f["monto"]) - total))
            return _cerrar(base, fila, repo, "vendor_date", 0.75, "MISMATCH", total)

    # --- nivel 4: sin proveedor confiable, pero fecha y monto calzan ---
    if fecha:
        filas = repo.buscar_por_monto(total, fecha=fecha, tolerancia_dias=3)
        if filas:
            return _cerrar(base, filas[0], repo, "date_amount", 0.70, "MATCH", total)

        # --- nivel 5: monto exacto en el mes ---
        filas = repo.buscar_por_monto_en_mes(total, fecha)
        if filas:
            return _cerrar(base, filas[0], repo, "amount_only", 0.50, "MATCH", total)
    else:
        filas = repo.buscar_por_monto(total)
        if filas:
            return _cerrar(base, filas[0], repo, "amount_only", 0.50, "MATCH", total)

    return base


def _cerrar(base, fila, repo, estrategia, confianza, veredicto, total):
    delta = round(total - float(fila["monto"]), 2)
    base.update({
        "matched_record_id": fila["id"],
        "match_strategy": estrategia,
        "match_confidence": confianza,
        "verdict": veredicto if abs(delta) > 0.001 or veredicto != "MATCH" else "MATCH",
        "delta": delta,
        "_registro": dict(fila),
        # version serializable del registro: viaja al JSON guardado y a la vista
        "matched_record": {
            "id": fila["id"],
            "proveedor": fila.get("proveedor"),
            "fecha": str(fila.get("fecha")),
            "monto": float(fila["monto"]),
        },
    })
    if abs(delta) > 0.001 and veredicto == "MATCH":
        base["verdict"] = "MISMATCH"
    try:
        dups = repo.buscar_duplicados(float(fila["monto"]), fila["fecha"])
        base["_duplicados"] = [d for d in dups if d["id"] != fila["id"]]
    except Exception:
        base["_duplicados"] = []
    return base
