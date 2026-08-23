"""Unica capa que habla HTTP con el backend.

Ningun componente conoce URLs. Si el backend no esta arriba, esto devuelve un
error legible en vez de un stacktrace en medio de la demo.
"""

import os

import requests

BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8123")
TIMEOUT = 120  # la inferencia local puede tardar; con QVAC real, mas todavia


class BackendError(RuntimeError):
    """El backend no respondio o respondio mal. Mensaje apto para pantalla."""


def _pedir(metodo: str, ruta: str, **kwargs):
    try:
        r = requests.request(metodo, f"{BASE_URL}{ruta}", timeout=TIMEOUT, **kwargs)
    except requests.ConnectionError as exc:
        raise BackendError(
            f"No hay backend escuchando en {BASE_URL}. "
            "Levantalo con: uvicorn backend.api.main:app --port 8123"
        ) from exc
    except requests.Timeout as exc:
        raise BackendError("El backend tardo demasiado en responder.") from exc

    if r.status_code >= 400:
        detalle = ""
        try:
            detalle = r.json().get("detail", "")
        except ValueError:
            detalle = r.text[:200]
        raise BackendError(f"El backend respondio {r.status_code}: {detalle}")
    return r


def health() -> dict:
    return _pedir("GET", "/health").json()


def stats() -> dict:
    return _pedir("GET", "/stats").json()


def reconcile(
    nombre: str,
    data: bytes,
    content_type: str | None,
    motor: str | None = None,
) -> dict:
    """`motor` es TEMPORAL: fuerza un cliente de prueba (stub/flaky) para esta
    request sin tocar el .env. Se quita cuando QVAC este integrado."""
    archivos = {"file": (nombre, data, content_type or "application/octet-stream")}
    datos = {"llm_client": motor} if motor else None
    return _pedir("POST", "/reconcile", files=archivos, data=datos).json()


def listar_reconciliaciones(limit: int = 50) -> list[dict]:
    return _pedir("GET", f"/reconciliations?limit={limit}").json()


def obtener_reconciliacion(rec_id: int) -> dict:
    return _pedir("GET", f"/reconciliations/{rec_id}").json()


def descargar_documento(rec_id: int) -> tuple[bytes, str]:
    r = _pedir("GET", f"/reconciliations/{rec_id}/document")
    return r.content, r.headers.get("content-type", "application/octet-stream")


def decidir(rec_id: int, decision: str, operador: str = "operador") -> dict:
    return _pedir(
        "POST",
        f"/reconciliations/{rec_id}/decision",
        json={"decision": decision, "decided_by": operador},
    ).json()
