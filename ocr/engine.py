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


def _transporte(client):
    """El SDK 0.17.1 expone el transporte como .transport o ._transport segun build."""
    return getattr(client, "transport", None) or client._transport


def _dic(m):
    return m.model_dump() if hasattr(m, "model_dump") else vars(m)


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
        src_recon = os.environ.get("QVAC_MODEL_OCR") or url_registry(
            catalogo[familia["reconocedor"]])
        src_det = os.environ.get("QVAC_MODEL_OCR_DETECTOR") or url_registry(
            catalogo[familia["detector"]])

        config = {
            "detectorModelSrc": src_det,
            "pipelineType": self.pipeline,
            "backendDevice": self.backend,
        }
        if self.pipeline == "easyocr":
            config["langList"] = self.idiomas   # doctr es agnostico al idioma

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


async def leer_muchas(rutas, **kwargs):
    """Una sola carga de modelo para toda la corrida."""
    async with MotorOCR(**kwargs) as motor:
        return motor.info, [await motor.leer(r) for r in rutas]


def run_ocr(ruta_imagen, **kwargs):
    """Atajo sincronico de una sola imagen. Para lotes usar `leer_muchas`:
    esto abre y cierra el worker, y recarga el modelo, en cada llamada."""
    async def _uno():
        async with MotorOCR(**kwargs) as motor:
            return await motor.leer(ruta_imagen)
    return asyncio.run(_uno())


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python ocr/engine.py <imagen> [imagen2 ...]")
        raise SystemExit(1)
    info, resultados = asyncio.run(leer_muchas(sys.argv[1:]))
    print(json.dumps({"motor": info, "resultados": resultados},
                     indent=2, ensure_ascii=False))
