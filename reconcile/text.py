"""Normalizacion de texto compartida.

Vive en un solo lugar a proposito: el seed (`scripts/gen_dataset.py`) precalcula
`proveedores.nombre_norm` con esta misma funcion. Si el seed y el matcher normalizaran
distinto, el fuzzy compararia peras con manzanas y ningun MATCH cerraria.
"""
import unicodedata


def normalizar(s: str) -> str:
    """minusculas, sin tildes, espacios colapsados."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.split())


def normalizar_espacios(s: str) -> str:
    """Colapsa saltos de linea y espacios multiples, conserva tildes y mayusculas.

    La usa el detector de `source_span`: el OCR mete saltos de linea arbitrarios,
    y comparar sin colapsarlos produce falsos negativos.
    """
    return " ".join((s or "").split())
