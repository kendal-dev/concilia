"""Orquestacion del contrato: cruce -> explicacion -> confianza.

Separado de `main.py` a proposito: esta funcion no sabe si el contrato vino del OCR o
de un fixture, y por eso los tests y el motor de conciliacion pueden correr sin
inferencia. Es lo que desbloquea trabajar en paralelo.
"""
import time
from datetime import datetime, timezone

from confidence.scorer import evaluar
from reconcile import rules
from reconcile.matcher import cruzar


def nuevo_contrato(receipt_id, source_image):
    return {
        "receipt_id": receipt_id,
        "source_image": source_image,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "ocr": {"raw_text": "", "engine": None, "route": "ocr",
                "duration_s": 0.0, "quality_flags": []},
        "extracted": {
            "vendor": {"value": None, "confidence": 0.0, "source_span": ""},
            "date": {"value": None, "confidence": 0.0, "source_span": ""},
            "total": {"value": None, "confidence": 0.0, "source_span": ""},
            "currency": {"value": None, "confidence": 0.0, "source_span": ""},
            "items": [],
            "parser_repairs": [],
        },
        "reconciliation": {},
        "confidence_overall": 0.0,
        "latency_s": 0.0,
    }


def conciliar(contrato, repo, umbral=None, guardar=False):
    """Cruza contra el libro, genera la explicacion y calcula la confianza."""
    t0 = time.time()
    ext = contrato.get("extracted", {})

    rec = cruzar(ext, repo)
    contrato["reconciliation"] = rec

    evaluar(contrato, umbral=umbral)

    patron, texto = rules.explicar(rec, ext)
    rec["explanation_pattern"] = patron
    rec["explanation"] = texto

    contrato["latency_s"] = round(
        contrato.get("ocr", {}).get("duration_s", 0.0) + (time.time() - t0), 2)

    if guardar:
        try:
            repo.guardar_conciliacion(_limpio(contrato))
        except Exception as e:  # la persistencia no puede tumbar la corrida
            contrato.setdefault("warnings", []).append(f"no se guardo en MariaDB: {e}")
    return contrato


def _limpio(contrato):
    """Copia sin los campos internos con guion bajo (no van a la base ni al disco)."""
    import copy
    c = copy.deepcopy(contrato)
    rec = c.get("reconciliation", {})
    for k in [k for k in rec if k.startswith("_")]:
        rec.pop(k)
    return c


def serializable(contrato):
    return _limpio(contrato)
