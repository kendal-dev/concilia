"""Selector de cliente LLM segun configuracion.

La Fase 4 agrega la rama "qvac" aqui y nada mas cambia en el pipeline.
"""

from backend.config import get_settings
from backend.core.llm.base import LLMClient
from backend.core.llm.stub import FlakyLLMClient, StubLLMClient

# --- switch de motor de diagnostico ---------------------------------------
# El motor real es el de settings (qvac). Estos dos son deterministas y se
# pueden forzar por request desde la UI para correr el MISMO documento con y
# sin modelo: si el veredicto cambia, el fallo estuvo en la lectura; si no
# cambia, esta en las verificaciones o en el ERP. Tambien mantienen la suite
# de tests libre de inferencia.
CLIENTES_DE_PRUEBA: tuple[str, ...] = ("stub", "flaky")
# --------------------------------------------------------------------------


def get_llm_client(filename: str = "", override: str | None = None) -> LLMClient:
    """Devuelve el cliente configurado, o el que pida `override`.

    `override` solo acepta clientes de prueba: la UI no debe poder forzar una
    configuracion de produccion que el operador no eligio en el .env.
    """
    if override:
        kind = override.lower()
        if kind not in CLIENTES_DE_PRUEBA:
            raise ValueError(
                f"Motor de prueba desconocido: {override!r}. "
                f"Opciones: {', '.join(CLIENTES_DE_PRUEBA)}."
            )
    else:
        kind = get_settings().llm_client.lower()

    if kind == "stub":
        return StubLLMClient(filename)
    if kind == "flaky":
        # Util para demostrar el retry loop en vivo durante la demo.
        return FlakyLLMClient(fail_times=2, filename=filename)
    if kind == "qvac":
        # Import diferido a proposito: `qvac.py` arrastra el SDK de tetherto y el
        # worker de bare. Importarlo arriba obligaria a tener el entorno de
        # inferencia montado para correr los tests del backend, que no lo usan.
        from backend.core.llm.qvac import QvacLLMClient

        return QvacLLMClient(filename)
    raise ValueError(f"LLM_CLIENT desconocido: {kind!r}")
