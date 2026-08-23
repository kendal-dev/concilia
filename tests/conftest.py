"""Repositorio en memoria: los tests corren sin Docker ni MariaDB.

Implementa la misma interfaz que `reconcile.repository.Repositorio` sobre listas.
Si la interfaz real cambia, estos tests fallan - que es exactamente lo que se quiere.
"""
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from reconcile.text import normalizar  # noqa: E402

PROVEEDORES = [
    {"id": 1, "nombre": "Farmacia Cruz"},
    {"id": 2, "nombre": "Ferreteria San Martin"},
    {"id": 3, "nombre": "Pinturas Monopol Ltda."},
]
for p in PROVEEDORES:
    p["nombre_norm"] = normalizar(p["nombre"])

GASTOS = [
    {"id": 10, "proveedor_id": 1, "fecha": date(2026, 8, 14), "monto": 247.50},
    {"id": 11, "proveedor_id": 1, "fecha": date(2026, 8, 20), "monto": 274.00},
    {"id": 12, "proveedor_id": 2, "fecha": date(2026, 8, 15), "monto": 90.00},
    {"id": 13, "proveedor_id": 3, "fecha": date(2026, 2, 11), "monto": 639.73},
    {"id": 14, "proveedor_id": 3, "fecha": date(2026, 2, 11), "monto": 639.73},  # duplicado
]
for g in GASTOS:
    prov = next(p for p in PROVEEDORES if p["id"] == g["proveedor_id"])
    g["proveedor"] = prov["nombre"]
    g["proveedor_norm"] = prov["nombre_norm"]
    g["categoria"] = "varios"
    g["descripcion"] = ""
    g["nit"] = None


def _f(v):
    if isinstance(v, date):
        return v
    return date.fromisoformat(str(v)[:10]) if v else None


class RepoFalso:
    def __init__(self, gastos=None, proveedores=None):
        self.gastos = [dict(g) for g in (gastos or GASTOS)]
        self.proveedores = [dict(p) for p in (proveedores or PROVEEDORES)]
        self.guardados = []

    def listar_proveedores_norm(self):
        return self.proveedores

    def buscar_exacto(self, proveedor_norm, fecha, monto):
        d = _f(fecha)
        return [g for g in self.gastos
                if g["proveedor_norm"] == proveedor_norm and g["fecha"] == d
                and abs(g["monto"] - monto) < 0.011]

    def buscar_por_proveedor_fecha(self, proveedor_norm, fecha, tolerancia_dias=3):
        d = _f(fecha)
        if d is None:
            return []
        return sorted([g for g in self.gastos
                       if g["proveedor_norm"] == proveedor_norm
                       and abs((g["fecha"] - d).days) <= tolerancia_dias],
                      key=lambda g: abs((g["fecha"] - d).days))

    def buscar_por_monto(self, monto, fecha=None, tolerancia_dias=3, tolerancia_monto=0.01):
        cand = [g for g in self.gastos if abs(g["monto"] - monto) <= tolerancia_monto]
        if fecha is None:
            return cand
        d = _f(fecha)
        return [g for g in cand if abs((g["fecha"] - d).days) <= tolerancia_dias]

    def buscar_por_monto_en_mes(self, monto, fecha, tolerancia_monto=0.01):
        d = _f(fecha)
        if d is None:
            return []
        return [g for g in self.gastos
                if abs(g["monto"] - monto) <= tolerancia_monto
                and g["fecha"].year == d.year and g["fecha"].month == d.month]

    def buscar_duplicados(self, monto, fecha, tolerancia_monto=0.01):
        d = _f(fecha)
        return [g for g in self.gastos
                if abs(g["monto"] - monto) <= tolerancia_monto and g["fecha"] == d]

    def guardar_conciliacion(self, contrato):
        self.guardados.append(contrato)
        return len(self.guardados)


@pytest.fixture
def repo():
    return RepoFalso()


def contrato_base(raw_text, vendor, fecha, total, span_total=None, items=None,
                  receipt_id="R999", conf=0.9, flags=None):
    return {
        "receipt_id": receipt_id,
        "source_image": f"data/receipts/{receipt_id}.jpg",
        "ocr": {"raw_text": raw_text, "engine": "qvac-ocr", "route": "ocr",
                "duration_s": 1.0, "quality_flags": flags or []},
        "extracted": {
            "vendor": {"value": vendor, "confidence": conf, "source_span": vendor or ""},
            "date": {"value": fecha, "confidence": conf, "source_span": "14/08/2026"},
            "total": {"value": total, "confidence": conf,
                      "source_span": span_total if span_total is not None
                      else f"TOTAL Bs {total}"},
            "currency": {"value": "BOB", "confidence": 0.99, "source_span": "Bs"},
            "items": items or [],
            "parser_repairs": [],
        },
        "reconciliation": {},
        "confidence_overall": 0.0,
        "latency_s": 0.0,
    }
