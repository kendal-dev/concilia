"""Etapa 1 - OCR local con el SDK nativo de QVAC.

    python ocr/engine.py data/receipts/R028.jpg

## Como se resuelve un modelo (leido del codigo del SDK, no supuesto)

`server/rpc/handlers/load-model/resolve.js` acepta cuatro formas de `modelSrc`:

    registry://<source>/<path>   descarga del registry P2P y cachea
    http(s)://...                descarga por HTTP
    pear://<key>/<path>          hyperdrive
    cualquier cosa con / o \\     ruta de archivo local
    un nombre suelto             busca en la cache local; si no esta, falla con
                                 "Available models: ..."

Los cuatro intentos previos fallaron porque pasabamos el nombre suelto
(`crnn_mobilenet_v3_small`) o el `registry_path` pelado, y ninguno de los dos es una
forma valida: el primero exige que el archivo YA este en cache, y el segundo se
interpreta como ruta de disco. La forma correcta es `registry://s3/<registry_path>`,
que es literalmente lo que el motor pedia cuando dijo "Use a hyperdrive or registry
source". Aqui se construye desde el propio registry, asi que la fecha del path no
queda hardcodeada.

## El pipeline OCR son DOS modelos

El addon `@qvac/ocr-ggml` recibe `pathDetector` y `pathRecognizer`, y trae dos familias
que no se mezclan:

    easyocr  CRAFT (craft_mlt_25k) + CRNN gen-2 (latin_g2)     <- por defecto, usa langList
    doctr    DBNet (db_mobilenet_v3_large) + crnn_mobilenet_v3_small

`latin_g2` cubre espanol; por eso easyocr es la ruta principal para recibos bolivianos.
"""
import asyncio
import base64
import json
import os
import statistics
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
import tetherto.qvac_sdk as q
from tetherto.qvac_sdk._generated.models._internal import (
    OcrStreamRequest,
    OcrStreamRequestImageBase64,
    OcrStreamRequestImageFilePath,
    OcrStreamRequestOptions,
)

RAIZ = Path(__file__).resolve().parents[1]
load_dotenv(RAIZ / ".env")

FAMILIAS = {
    "easyocr": {"reconocedor": "latin_g2", "detector": "craft_mlt_25k"},
    "doctr": {"reconocedor": "crnn_mobilenet_v3_small", "detector": "db_mobilenet_v3_large"},
}
UMBRAL_CONFIANZA_BLOQUE = 0.5


def _num_env(clave):
    valor = os.environ.get(clave, "").strip()
    if not valor:
        return None
    try:
        return float(valor)
    except ValueError:
        return None


def _bool_env(clave):
    valor = os.environ.get(clave, "").strip().lower()
    if valor in ("1", "true", "si", "yes", "on"):
        return True
    if valor in ("0", "false", "no", "off"):
        return False
    return None


def _transporte(client):
    """El SDK 0.17.1 expone el transporte como .transport o ._transport segun build."""
    return getattr(client, "transport", None) or client._transport


def _dic(m):
    return m.model_dump() if hasattr(m, "model_dump") else vars(m)


ESQUEMAS = ("registry://", "http://", "https://", "pear://")


def src_de_env(clave):
    """Lee un modelSrc del .env, pero descarta las rutas locales que no existen.

    Una linea vieja del .env apuntando a un .gguf que nunca se descargo pisa la
    resolucion automatica y produce un "Failed to locate model file" que parece un
    bug del pipeline y no lo es. Si el valor trae esquema (registry://, http://,
    pear://) se respeta tal cual; si es una ruta y el archivo no esta, se ignora y
    se cae al registry avisando por consola.
    """
    valor = (os.environ.get(clave) or "").strip()
    if not valor or valor.upper() == "PENDIENTE":
        return None
    if valor.startswith(ESQUEMAS):
        return valor
    if Path(valor).exists():
        return valor
    print(f"[aviso] {clave}={valor} no existe en disco; se ignora y se resuelve "
          f"desde el registry.", file=sys.stderr)
    return None


def url_registry(entrada):
    """De una entrada del registry al modelSrc que el resolver entiende."""
    fuente = entrada.get("registry_source") or "s3"
    return f"registry://{fuente}/{entrada['registry_path']}"


class MotorOCR:
    """Un cliente, una carga de modelo, muchas imagenes.

    Cargar el par detector+reconocedor cuesta segundos; hacerlo por imagen en una
    corrida de 31 recibos multiplicaria la latencia sin motivo. Por eso el motor es
    un context manager y `main.py --batch` lo abre una sola vez.
    """

    def __init__(self, pipeline=None, idiomas=None, backend=None):
        self.pipeline = pipeline or os.environ.get("QVAC_OCR_PIPELINE", "easyocr")
        if self.pipeline not in FAMILIAS:
            raise ValueError(f"pipeline invalido: {self.pipeline}. Use easyocr o doctr.")
        self.idiomas = idiomas or [s.strip() for s in
                                   os.environ.get("QVAC_OCR_LANGS", "es,en").split(",")
                                   if s.strip()]
        self.backend = backend or os.environ.get("QVAC_OCR_BACKEND", "cpu")
        # Perillas del addon easyocr, regulables por .env porque calibrarlas contra
        # el dataset real es parte del trabajo.
        #
        # magRatio y canvasSize NO usan el default del addon (1.5 y 2560) a
        # proposito. CRAFT es completamente convolucional: con canvas 2560 las
        # activaciones intermedias son enormes, y cuando el modelo de texto de la
        # etapa 2 ya ocupa memoria, ggml no consigue el buffer y falla con
        # "ggml_gallocr_alloc_graph failed". Con 1280 y 1.0 el grafo entra comodo
        # Y ADEMAS el OCR pasa de 52 s a 8 s por recibo, sin perder calidad
        # apreciable en tickets de ~1000 px de alto. Si alguien corre esto en una
        # maquina holgada y quiere el default original, son dos lineas del .env.
        self.mag_ratio = _num_env("QVAC_OCR_MAG_RATIO") or 1.0
        self.canvas_size = _num_env("QVAC_OCR_CANVAS") or 1280
        self.low_conf = _num_env("QVAC_OCR_LOW_CONF")              # addon: 0.4
        self.contrast_retry = _bool_env("QVAC_OCR_CONTRAST_RETRY")  # addon: False
        self.hilos = _num_env("QVAC_OCR_THREADS")                  # addon: auto
        self.client = None
        self.transport = None
        self.model_id = None
        self.info = {}

    async def __aenter__(self):
        self.client = q.Client(sdk_dir=os.environ.get("QVAC_SDK_DIR"),
                               bare_path=os.environ.get("QVAC_BARE_PATH"))
        await self.client.__aenter__()
        self.transport = _transporte(self.client)

        familia = FAMILIAS[self.pipeline]
        catalogo = {d["name"]: d for d in
                    (_dic(m) for m in
                     await q.model_registry_search(self.transport, addon="ocr"))}

        # .env puede fijar un modelSrc explicito (ruta local o registry://);
        # si no, se arma desde el registry para no hardcodear la fecha del path.
        src_recon = src_de_env("QVAC_MODEL_OCR") or url_registry(
            catalogo[familia["reconocedor"]])
        src_det = src_de_env("QVAC_MODEL_OCR_DETECTOR") or url_registry(
            catalogo[familia["detector"]])

        config = {
            "detectorModelSrc": src_det,
            "pipelineType": self.pipeline,
            "backendDevice": self.backend,
        }
        if self.hilos is not None:
            config["nThreads"] = self.hilos
        if self.pipeline == "easyocr":
            config["langList"] = self.idiomas   # doctr es agnostico al idioma
            for clave, valor in (("magRatio", self.mag_ratio),
                                 ("canvasSize", self.canvas_size),
                                 ("lowConfidenceThreshold", self.low_conf),
                                 ("contrastRetry", self.contrast_retry)):
                if valor is not None:
                    config[clave] = valor

        t0 = time.time()
        self.model_id = await q.load_model(self.transport, model_src=src_recon,
                                           model_type="ggml-ocr", model_config=config)
        self.info = {
            "pipeline": self.pipeline,
            "reconocedor": familia["reconocedor"],
            "detector": familia["detector"],
            "model_src": src_recon,
            "detector_src": src_det,
            "backend": self.backend,
            "idiomas": self.idiomas if self.pipeline == "easyocr" else None,
            "carga_s": round(time.time() - t0, 2),
        }
        return self

    async def __aexit__(self, *exc):
        if self.client is not None:
            await self.client.__aexit__(*exc)
        return False

    async def leer(self, ruta_imagen, paragraph=None):
        """Devuelve el bloque `ocr` del contrato.

        OJO con `options`: el SDK serializa con `model_dump(exclude_unset=True)`, asi
        que un `options=None` pasado explicitamente SI viaja por el cable, como
        `"options": null`. Del otro lado el schema es zod `ocrOptionsSchema.optional()`,
        y `.optional()` en zod acepta `undefined` pero RECHAZA `null`. Ese es todo el
        misterio del "RPCError: Invalid input": no era la ruta, ni el modelo, ni el
        pipeline. Era un null donde tenia que no haber nada. Por eso el campo se omite
        salvo que haya algo real que mandar.
        """
        ruta = str(Path(ruta_imagen).resolve())
        imagen = OcrStreamRequestImageFilePath(type="filePath", value=ruta)
        return await self._ocr(imagen, paragraph)

    async def leer_bytes(self, datos, paragraph=None):
        """Igual que `leer`, pero desde bytes en memoria.

        La API sube la factura como `UploadFile`; escribirla a disco solo para que
        el OCR la lea seria un rodeo. El SDK acepta base64 y se encarga del temporal.
        """
        imagen = OcrStreamRequestImageBase64(
            type="base64", value=base64.b64encode(datos).decode("ascii"))
        return await self._ocr(imagen, paragraph)

    async def leer_orientada(self, ruta_imagen=None, datos=None, angulos=None,
                             paragraph=None):
        """Prueba varias rotaciones y se queda con la mejor lectura.

        Las fotos de factura salen giradas 90 grados y no traen EXIF de orientacion,
        asi que no hay forma de saber la correcta sin mirar. El addon tiene
        `defaultRotationAngles`, pero solo reintenta las cajas que quedaron por debajo
        de `lowConfidenceThreshold`: si el reconocedor lee basura CON confianza, nunca
        se dispara.

        Aca la decision se toma con el resultado en la mano: se corre el OCR en cada
        angulo y gana el que produce mas texto con mas confianza. Cuesta una pasada por
        angulo, y por eso es opcional. El angulo elegido y los descartados quedan en el
        resultado: la decision es auditable, no magia.
        """
        from io import BytesIO
        from PIL import Image

        if angulos is None:
            crudo = os.environ.get("QVAC_OCR_ANGULOS", "0,90,180,270")
            angulos = [int(a) for a in crudo.split(",") if a.strip()]

        if datos is None and ruta_imagen is None:
            raise ValueError("leer_orientada necesita ruta_imagen o datos")
        original = Image.open(BytesIO(datos) if datos is not None else ruta_imagen)
        mejor_puntaje, mejor = None, None
        candidatos = []
        for angulo in angulos:
            if angulo % 360 == 0:
                res = (await self.leer_bytes(datos, paragraph=paragraph)
                       if datos is not None
                       else await self.leer(ruta_imagen, paragraph=paragraph))
            else:
                buffer = BytesIO()
                original.rotate(-angulo, expand=True).save(buffer, format="PNG")
                res = await self.leer_bytes(buffer.getvalue(), paragraph=paragraph)
            confianza = res.get("confianza_media_ocr") or 0.0
            caracteres = len(res.get("raw_text") or "")
            # La confianza al cuadrado castiga las lecturas "seguras" de basura, que
            # es justo lo que produce una imagen girada.
            puntaje = (confianza ** 2) * caracteres
            candidatos.append({"angulo": angulo, "confianza": round(confianza, 3),
                               "caracteres": caracteres, "puntaje": round(puntaje, 1)})
            if mejor_puntaje is None or puntaje > mejor_puntaje:
                mejor_puntaje, mejor = puntaje, (angulo, res)

        angulo, res = mejor
        res["rotacion_aplicada"] = angulo
        res["rotaciones_probadas"] = candidatos
        if angulo % 360 != 0:
            res.setdefault("quality_flags", []).append(f"rotada_{angulo}")
        return res

    async def _ocr(self, imagen, paragraph=None):
        t0 = time.time()
        campos = {
            "type": "ocrStream",
            "model_id": self.model_id,
            "image": imagen,
        }
        if paragraph is not None:
            campos["options"] = OcrStreamRequestOptions(paragraph=paragraph)
        req = OcrStreamRequest(**campos)
        lineas, confianzas, error = [], [], None
        try:
            async for chunk in q.ocr_stream(self.transport, req):
                if getattr(chunk, "error", None):
                    error = chunk.error
                    break
                for b in (getattr(chunk, "blocks", None) or []):
                    texto = getattr(b, "text", "") or ""
                    if texto.strip():
                        lineas.append(texto)
                    c = getattr(b, "confidence", None)
                    if isinstance(c, (int, float)):
                        confianzas.append(float(c))
        except Exception as e:
            error = f"{type(e).__name__}: {e}"

        raw = "\n".join(lineas)
        flags = []
        if error:
            flags.append("ocr_error")
        if not raw.strip():
            flags.append("partial_read")
        elif len(lineas) < 3:
            flags.append("pocas_lineas")
        if confianzas:
            media = statistics.fmean(confianzas)
            if media < UMBRAL_CONFIANZA_BLOQUE:
                flags.append("baja_confianza_ocr")
        else:
            media = None

        return {
            "raw_text": raw,
            "engine": f"qvac-ggml-ocr/{self.pipeline}",
            "route": "ocr",
            "duration_s": round(time.time() - t0, 2),
            "quality_flags": flags,
            "bloques": len(lineas),
            "confianza_media_ocr": round(media, 3) if media is not None else None,
            "error": error,
        }


async def leer_muchas(rutas, rotar=False, **kwargs):
    """Una sola carga de modelo para toda la corrida."""
    async with MotorOCR(**kwargs) as motor:
        salida = []
        for r in rutas:
            salida.append(await (motor.leer_orientada(r) if rotar else motor.leer(r)))
        return motor.info, salida


def run_ocr(ruta_imagen, **kwargs):
    """Atajo sincronico de una sola imagen. Para lotes usar `leer_muchas`:
    esto abre y cierra el worker, y recarga el modelo, en cada llamada."""
    async def _uno():
        async with MotorOCR(**kwargs) as motor:
            return await motor.leer(ruta_imagen)
    return asyncio.run(_uno())


if __name__ == "__main__":
    argumentos = [a for a in sys.argv[1:] if a != "--rotar"]
    rotar = "--rotar" in sys.argv
    if not argumentos:
        print("Uso: python ocr/engine.py [--rotar] <imagen> [imagen2 ...]")
        raise SystemExit(1)
    info, resultados = asyncio.run(leer_muchas(argumentos, rotar=rotar))
    print(json.dumps({"motor": info, "resultados": resultados},
                     indent=2, ensure_ascii=False))
