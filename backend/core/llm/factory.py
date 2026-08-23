"""Selector de cliente LLM segun configuracion.

La Fase 4 agrega la rama "qvac" aqui y nada mas cambia en el pipeline.
"""

from backend.config import get_settings
from backend.core.llm.base import LLMClient
from backend.core.llm.stub import FlakyLLMClient, StubLLMClient

# --- TEMPORAL: switch de motor desde la UI --------------------------------
# Mientras QVAC no este integrado, el dashboard puede elegir el motor por
# request para poder demostrar el pipeline sin tocar el .env. Cuando
# QvacLLMClient exista, se borra CLIENTES_DE_PRUEBA junto con el selector del
# frontend y el parametro `override` vuelve a ser innecesario.
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
