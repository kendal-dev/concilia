"""Interfaz del cliente LLM.

Los metodos devuelven TEXTO CRUDO a proposito. El parseo y la validacion son
responsabilidad del orquestador, que es donde vive la ingenieria de fiabilidad.
Si esta interfaz devolviera objetos ya validados estariamos escondiendo el
problema real: un modelo de 1-4B devuelve JSON roto a menudo, y el sistema
tiene que verlo para poder reaccionar.

La Fase 4 solo agrega una implementacion QvacLLMClient aqui abajo; el
orquestador no cambia.
"""

from abc import ABC, abstractmethod


class LLMClient(ABC):
    @abstractmethod
    def extract_invoice(self, image_bytes: bytes, feedback: str | None = None) -> str:
        """Fase 2: leer el documento y devolver JSON con los campos clave.

        `feedback` lleva el error de validacion del intento anterior para que
        el modelo se autocorrija en el reintento.
        """

    @abstractmethod
    def reason_triage(self, prompt: str) -> str:
        """Fase 4: redactar la nota de auditoria comparando factura vs ERP.

        El delta numerico ya lo calculo Python; aqui solo se pide prosa.
        """
