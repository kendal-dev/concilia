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
from confidence.detectors import valor_aparece, variantes_numero
from ocr.engine import MotorOCR, _dic, src_de_env, url_registry

# Modelo de texto por defecto. Se puede fijar otro con QVAC_MODEL_TEXT (ruta local o
# registry://) o elegir por nombre con QVAC_MODEL_TEXT_NAME.
MODELO_TEXTO_POR_DEFECTO = "Qwen3.5-4B-Q4_K_M"

# Qwen3.5 es un modelo de razonamiento: si se lo deja, abre un bloque <think>, se
# pone a analizar el ticket linea por linea y se queda sin presupuesto de tokens
# antes de emitir la primera llave del JSON. Pasa exactamente eso en la practica.
#
# `reasoning_budget: 0` lo apaga. Y no es una optimizacion: el prompt de extraccion
# dice textual "NO razones, NO calcules, NO completes lo que no ves". Un transcriptor
# que razona es justo lo que NO queremos - ahi es donde un modelo chico empieza a
# rellenar los huecos que no pudo leer.
_RAZONAMIENTO = int(os.environ.get("QVAC_REASONING_BUDGET", "0"))

# Extraccion: determinista. Un recibo no es una tarea creativa.
GEN_EXTRACCION = {"temp": 0.0, "predict": 768,
                  "reasoning_budget": _RAZONAMIENTO,
                  "remove_thinking_from_context": True}
# Triaje: una pizca de temperatura para que la nota no salga robotica.
GEN_TRIAJE = {"temp": 0.3, "predict": 320,
              "reasoning_budget": _RAZONAMIENTO,
              "remove_thinking_from_context": True}

# Respuesta vacia y honesta cuando el OCR no devolvio nada legible. El orquestador
# la valida sin problema y `has_minimum_data()` da False -> UNCERTAIN. Es exactamente
# el comportamiento que queremos: sin datos no se inventa un numero.
SIN_LECTURA = json.dumps({
    "supplier_tax_id": None, "supplier_name": None, "invoice_number": None,
    "invoice_date": None, "subtotal": None, "tax_amount": None,
    "total_amount": None, "currency": None, "line_items": [],
    "confidence": {},
})


def _json_suelto(crudo):
    """Recorta y parsea el JSON de la respuesta, o None. Misma regla que usa el
    orquestador (`_salvage_json`): desde la primera llave hasta la ultima."""
    if not crudo:
        return None
    i, j = crudo.find("{"), crudo.rfind("}")
    if i == -1 or j <= i:
        return None
    try:
        return json.loads(crudo[i:j + 1])
    except json.JSONDecodeError:
        return None


def _hay_datos_utiles(datos):
    """Sirve para reconciliar? Mismo criterio que `ExtractedInvoice.has_minimum_data`."""
    if not isinstance(datos, dict):
        return False
    return bool(datos.get("supplier_tax_id")) and datos.get("total_amount") is not None


def _bandera(clave):
    return os.environ.get(clave, "").strip().lower() in ("1", "true", "si", "yes", "on")


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

        # src_de_env descarta rutas locales inexistentes: una linea vieja del .env
        # apuntando a un .gguf que nunca se bajo no puede tumbar el arranque.
        src = src_de_env("QVAC_MODEL_TEXT")
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

        # `ctx_size` por defecto es 1024 tokens (verificado en el esquema
        # llamacpp-config del SDK). El prompt de extraccion mas el texto de un OCR
        # sucio lo pasa sin esfuerzo, y el motor responde ContextOverflowError. Se
        # sube, y se deja regulable: mas contexto es mas RAM, y en esta maquina el
        # detector CRAFT compite por la misma memoria.
        ctx = int(os.environ.get("QVAC_TEXT_CTX", "4096"))
        self.modelo_texto = await q.load_model(
            self.transport, model_src=src, model_type="llamacpp-completion",
            model_config={"ctx_size": ctx})
        self.info = {
            "ocr": self.ocr.info,
            "texto_src": src,
            "texto_nombre": (elegido or {}).get("name"),
            "ctx_size": ctx,
            "arranque_s": round(time.time() - t0, 2),
        }

    async def completar(self, sistema, usuario, generacion, json_estricto=False):
        run = q.completion(
            self.transport,
            model_id=self.modelo_texto,
            history=[{"role": "system", "content": sistema},
                     {"role": "user", "content": usuario}],
            generation_params=generacion,
            # Que el bloque <think> no termine mezclado con el JSON de salida.
            capture_thinking=False,
            # `response_format: json_object` hace que el motor arme una gramatica
            # GBNF para forzar JSON sintacticamente valido. Suena ideal, pero en
            # esta version revienta con "Unexpected empty grammar stack after
            # accepting piece", que es un fallo del motor y no del prompt. Queda
            # apagado por defecto y detras de QVAC_JSON_ESTRICTO por si una version
            # posterior lo arregla.
            #
            # No hace falta: el orquestador ya recorta el bloque entre la primera
            # llave y la ultima con `_salvage_json`, y si aun asi no valida, le
            # devuelve el error al modelo y reintenta. La fiabilidad esta puesta en
            # el bucle de correccion, no en confiar en que el modelo salga perfecto.
            response_format={"type": "json_object"} if json_estricto else None,
        )
        return await run.text()


NUMERICOS = ("total_amount", "subtotal", "tax_amount")
CAMPOS_VERIFICABLES = ("supplier_tax_id", "invoice_number") + NUMERICOS


def _verificar_valores(datos, texto_ocr):
    """Verifica contra el texto del OCR cada valor que el modelo dice haber leido.

    La logica vive en `confidence/detectors.py` - es un detector, no un detalle de
    este cliente - y desde aca solo se decide QUE campos se verifican.
    """
    salida = {}
    for campo in CAMPOS_VERIFICABLES:
        valor = datos.get(campo)
        if valor in (None, ""):
            continue
        ok, ratio = valor_aparece(valor, texto_ocr, es_numero=campo in NUMERICOS)
        impreso = (sorted(variantes_numero(valor))[0] if campo in NUMERICOS
                   else str(valor))
        salida[campo] = {"valor": impreso, "aparece_en_ocr": ok, "similitud": ratio}
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
        modo = os.environ.get("QVAC_OCR_ROTAR", "auto").strip().lower()
        if modo in ("1", "true", "si", "yes", "on"):
            ocr = await motor.ocr.leer_orientada(datos=image_bytes)
        else:
            ocr = await motor.ocr.leer_bytes(image_bytes)
        texto = (ocr.get("raw_text") or "").strip()

        if not texto:
            self.ultima_evidencia = {
                "archivo": self.filename, "ocr": ocr, "texto_ocr": "",
                "valores_verificados": {},
                "motivo": "el OCR no devolvio texto legible",
            }
            return SIN_LECTURA

        # Red de seguridad: un OCR que se dispara (una foto enorme, una pagina con
        # mucho ruido) puede desbordar el contexto igual. Se recorta y se declara
        # en la evidencia, en vez de dejar que el motor falle a mitad de la corrida.
        limite = int(os.environ.get("QVAC_OCR_MAX_CHARS", "6000"))
        recortado = len(texto) > limite
        if recortado:
            texto = texto[:limite]

        partes = ["TEXTO EXTRAIDO POR OCR DEL DOCUMENTO:", "---", texto, "---"]
        if feedback:
            partes += ["", feedback]
        partes.append("Devolve unicamente el objeto JSON del esquema.")

        t0 = time.time()
        crudo = await motor.completar(
            EXTRACTION_SYSTEM, "\n".join(partes), GEN_EXTRACCION,
            json_estricto=_bandera("QVAC_JSON_ESTRICTO"))
        extraccion_s = round(time.time() - t0, 2)
        datos = _json_suelto(crudo)

        # --- Escalada por rotacion --------------------------------------------
        # Una foto de factura girada 90 grados produce texto ilegible, y el sistema
        # responde UNCERTAIN correctamente: no puede leer, no inventa. Pero antes de
        # rendirse conviene descartar que el problema sea solo la orientacion.
        #
        # El barrido cuesta una pasada de OCR por angulo, asi que NO se corre de
        # entrada: se dispara solo cuando la primera lectura no dio ni NIT ni total,
        # que es la firma de una imagen mal orientada. En un documento derecho no
        # cuesta nada; en uno girado, lo rescata. Los angulos probados y el elegido
        # quedan en la evidencia.
        rotacion = None
        if (modo == "auto" and not _hay_datos_utiles(datos)
                and (ocr.get("raw_text") or "").strip()):
            ocr = await motor.ocr.leer_orientada(datos=image_bytes)
            texto2 = (ocr.get("raw_text") or "").strip()[:limite]
            rotacion = {"aplicada": ocr.get("rotacion_aplicada"),
                        "probadas": ocr.get("rotaciones_probadas")}
            if texto2 and texto2 != texto:
                texto = texto2
                partes = ["TEXTO EXTRAIDO POR OCR DEL DOCUMENTO:", "---", texto, "---"]
                if feedback:
                    partes += ["", feedback]
                partes.append("Devolve unicamente el objeto JSON del esquema.")
                t1 = time.time()
                crudo = await motor.completar(
                    EXTRACTION_SYSTEM, "\n".join(partes), GEN_EXTRACCION,
                    json_estricto=_bandera("QVAC_JSON_ESTRICTO"))
                extraccion_s = round(extraccion_s + time.time() - t1, 2)
                datos = _json_suelto(crudo)

        verificados = _verificar_valores(datos, texto) if datos else {}

        self.ultima_evidencia = {
            "rotacion": rotacion,
            "archivo": self.filename,
            "texto_ocr": texto,
            "ocr": {k: v for k, v in ocr.items() if k != "raw_text"},
            "extraccion_s": extraccion_s,
            "valores_verificados": verificados,
            "reintento": bool(feedback),
            "texto_recortado": recortado,
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
