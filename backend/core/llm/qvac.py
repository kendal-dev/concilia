"""Cliente LLM real, sobre QVAC. Es la Fase reservada en `base.py` y `factory.py`.

El orquestador no cambia: esta clase cumple el mismo contrato que el stub y devuelve
TEXTO CRUDO, tal como pide la interfaz. El parseo, la validacion y el reintento siguen
viviendo donde ya estaban.

## Dos etapas, no una

`extract_invoice` no le pasa la imagen a un multimodal. Hace dos llamadas:

    imagen -> [ETAPA 1: OCR ggml-ocr]  -> texto crudo
                                        -> [ETAPA 2: llamacpp-completion] -> JSON

El motivo no es de rendimiento, es de auditabilidad: el track pide que el sistema
muestre su razonamiento, y **el texto crudo del OCR ES ese razonamiento**. Con un
multimodal monolitico no hay nada intermedio que mostrarle a un humano, y no hay
contra que verificar si el modelo invento un numero. Con dos etapas, si, y de ahi
sale `ultima_evidencia`.

## Por que un hilo con su propio event loop

La interfaz `LLMClient` es sincronica y el SDK de QVAC es async. La salida facil seria
`asyncio.run()` por llamada, pero eso levanta y tira el worker de `bare` y recarga los
modelos en CADA factura: segundos de carga por documento, y una demo que se arrastra.
En su lugar hay un loop en un hilo daemon que vive lo que vive el proceso, con el par
de OCR y el modelo de texto cargados una sola vez.
"""

import asyncio
import json
import os
import threading
import time

import tetherto.qvac_sdk as q

from backend.core.llm.base import LLMClient
from backend.core.llm.prompts import EXTRACTION_SYSTEM, TRIAGE_SYSTEM
from confidence.detectors import span_verificado
from ocr.engine import MotorOCR, _dic, url_registry

# Modelo de texto por defecto. Se puede fijar otro con QVAC_MODEL_TEXT (ruta local o
# registry://) o elegir por nombre con QVAC_MODEL_TEXT_NAME.
MODELO_TEXTO_POR_DEFECTO = "Qwen3.5-4B-Q4_K_M"

# Extraccion: determinista. Un recibo no es una tarea creativa.
GEN_EXTRACCION = {"temp": 0.0, "predict": 1024}
# Triaje: una pizca de temperatura para que la nota no salga robotica.
GEN_TRIAJE = {"temp": 0.3, "predict": 320}

# Respuesta vacia y honesta cuando el OCR no devolvio nada legible. El orquestador
# la valida sin problema y `has_minimum_data()` da False -> UNCERTAIN. Es exactamente
# el comportamiento que queremos: sin datos no se inventa un numero.
SIN_LECTURA = json.dumps({
    "supplier_tax_id": None, "supplier_name": None, "invoice_number": None,
    "invoice_date": None, "subtotal": None, "tax_amount": None,
    "total_amount": None, "currency": None, "line_items": [],
    "confidence": {},
})


class _Motor:
    """Worker de QVAC compartido por todo el proceso. Se arranca una sola vez."""

    _instancia = None
    _candado = threading.Lock()

    @classmethod
    def instancia(cls):
        with cls._candado:
            if cls._instancia is None:
                cls._instancia = cls()
            return cls._instancia

    def __init__(self):
        self._loop = asyncio.new_event_loop()
        self._hilo = threading.Thread(target=self._loop.run_forever,
                                      name="qvac-worker", daemon=True)
        self._hilo.start()
        self._arrancado = False
        self._candado_arranque = threading.Lock()
        self.ocr = None
        self.transport = None
        self.modelo_texto = None
        self.info = {}

    def ejecutar(self, corrutina):
        return asyncio.run_coroutine_threadsafe(corrutina, self._loop).result()

    def asegurar_arranque(self):
        with self._candado_arranque:
            if not self._arrancado:
                self.ejecutar(self._arrancar())
                self._arrancado = True

    async def _arrancar(self):
        t0 = time.time()
        self.ocr = MotorOCR()
        await self.ocr.__aenter__()
        self.transport = self.ocr.transport

        src = os.environ.get("QVAC_MODEL_TEXT")
        elegido = None
        if not src:
            filtro = os.environ.get("QVAC_MODEL_TEXT_NAME", MODELO_TEXTO_POR_DEFECTO)
            catalogo = [_dic(m) for m in
                        await q.model_registry_search(self.transport, addon="llm")]
            elegido = next(
                (d for d in catalogo
                 if filtro.lower() in f"{d.get('model_id') or ''} {d.get('name') or ''}".lower()),
                None)
            if elegido is None:
                raise RuntimeError(
                    f"No hay ningun modelo de texto que coincida con {filtro!r} en el "
                    f"registry. Listalos con: python scripts/setup_models.py --texto ''"
                )
            src = url_registry(elegido)

        self.modelo_texto = await q.load_model(
            self.transport, model_src=src, model_type="llamacpp-completion",
            model_config={})
        self.info = {
            "ocr": self.ocr.info,
            "texto_src": src,
            "texto_nombre": (elegido or {}).get("name"),
            "arranque_s": round(time.time() - t0, 2),
        }

    async def completar(self, sistema, usuario, generacion, json_estricto=False):
        run = q.completion(
            self.transport,
            model_id=self.modelo_texto,
            history=[{"role": "system", "content": sistema},
                     {"role": "user", "content": usuario}],
            generation_params=generacion,
            # json_object obliga al motor a emitir JSON sintacticamente valido.
            # No garantiza el esquema - de eso se encarga el validador del
            # orquestador - pero elimina de raiz el JSON roto, que es el modo de
            # fallo mas comun de un modelo de 2-4B cuantizado.
            response_format={"type": "json_object"} if json_estricto else None,
        )
        return await run.text()


def _verificar_valores(datos, texto_ocr):
    """Comprueba que cada valor extraido aparezca de verdad en el texto del OCR.

    No le pedimos al modelo que declare de donde saco cada dato: se lo verificamos
    nosotros contra el texto crudo. Un total que no aparece en el OCR es un total
    inventado, y eso hay que poder decirlo.
    """
    interesantes = ("supplier_tax_id", "invoice_number", "total_amount",
                    "subtotal", "tax_amount")
    salida = {}
    for campo in interesantes:
        valor = datos.get(campo)
        if valor in (None, ""):
            continue
        aguja = f"{valor:.2f}".rstrip("0").rstrip(".") if isinstance(valor, float) \
            else str(valor)
        ok, ratio = span_verificado(aguja, texto_ocr)
        salida[campo] = {"valor": aguja, "aparece_en_ocr": ok, "similitud": ratio}
    return salida


class QvacLLMClient(LLMClient):
    """Implementacion real de la interfaz. Un cliente por request; el worker es unico."""

    def __init__(self, filename: str = ""):
        self.filename = filename
        # Evidencia de la ultima extraccion: texto OCR, latencias y que valores se
        # pudieron verificar contra ese texto. La API puede adjuntarla a la traza.
        self.ultima_evidencia: dict | None = None

    # ---------------------------------------------------------------- Fase 2
    def extract_invoice(self, image_bytes: bytes, feedback: str | None = None) -> str:
        motor = _Motor.instancia()
        motor.asegurar_arranque()
        return motor.ejecutar(self._extraer(motor, image_bytes, feedback))

    async def _extraer(self, motor, image_bytes, feedback):
        ocr = await motor.ocr.leer_bytes(image_bytes)
        texto = (ocr.get("raw_text") or "").strip()

        if not texto:
            self.ultima_evidencia = {
                "archivo": self.filename, "ocr": ocr, "texto_ocr": "",
                "valores_verificados": {},
                "motivo": "el OCR no devolvio texto legible",
            }
            return SIN_LECTURA

        partes = ["TEXTO EXTRAIDO POR OCR DEL DOCUMENTO:", "---", texto, "---"]
        if feedback:
            partes += ["", feedback]
        partes.append("Devolve unicamente el objeto JSON del esquema.")

        t0 = time.time()
        crudo = await motor.completar(EXTRACTION_SYSTEM, "\n".join(partes),
                                      GEN_EXTRACCION, json_estricto=True)
        extraccion_s = round(time.time() - t0, 2)

        verificados = {}
        try:
            verificados = _verificar_valores(json.loads(crudo), texto)
        except (json.JSONDecodeError, AttributeError, TypeError):
            # Si no parsea, el orquestador lo va a rechazar y reintentar. No es
            # tarea de esta capa arreglarlo: la interfaz devuelve texto crudo.
            pass

        self.ultima_evidencia = {
            "archivo": self.filename,
            "texto_ocr": texto,
            "ocr": {k: v for k, v in ocr.items() if k != "raw_text"},
            "extraccion_s": extraccion_s,
            "valores_verificados": verificados,
            "reintento": bool(feedback),
        }
        return crudo

    # ---------------------------------------------------------------- Fase 4
    def reason_triage(self, prompt: str) -> str:
        motor = _Motor.instancia()
        motor.asegurar_arranque()
        texto = motor.ejecutar(
            motor.completar(TRIAGE_SYSTEM, prompt, GEN_TRIAJE))
        return (texto or "").strip()

    # -------------------------------------------------------------- Utilidad
    @staticmethod
    def info_motor() -> dict:
        """Modelos y latencia de arranque. Va al README y a `docs/environment`."""
        motor = _Motor.instancia()
        motor.asegurar_arranque()
        return motor.info
