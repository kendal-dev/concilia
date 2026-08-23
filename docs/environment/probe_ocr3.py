"""Probe OCR v3 - decisivo. Dos hipotesis, las dos verificables en una corrida.

    python docs\\environment\\probe_ocr3.py

Por que existe: en el v2 trunque los mensajes de error a ~110 caracteres, y el dato
que necesitabamos estaba justo despues del corte. El error dice:

    Model with ID "crnn_mobilenet_v3_small.gguf". Available models: acestep-...gguf, ...

Esa lista viene ordenada alfabeticamente y quedo cortada en la "a". El ID que el motor
espera puede estar ahi con otro formato. Este script imprime la lista COMPLETA.

Hipotesis A: el ID correcto esta en esa lista y solo hay que escribirlo igual.
Hipotesis B: los modelos no estan realmente en disco. `download_asset` devolvio
"OK (0.0s)" para un archivo de 83 MB, lo cual es sospechoso, y el preflight no
encontro ningun .gguf. En ese caso hay que ver que devuelve DownloadAssetResponse
y donde deja el archivo.

Tambien prueba la forma de OBJETO de `detectorModelSrc` (campos verificados en el v2:
src REQUERIDO, name, modelId, registryPath, registrySource, blobCoreKey, blobIndex,
engine, expectedSize, sha256Checksum, addon), que es lo que el motor pedia cuando dijo
"Use a hyperdrive or registry source".
"""
import asyncio
import json
import os
import re
import time
from pathlib import Path

from dotenv import load_dotenv
import tetherto.qvac_sdk as q
from tetherto.qvac_sdk._generated.models._internal import (
    DownloadAssetRequest,
    OcrStreamRequest,
    OcrStreamRequestImageFilePath,
)

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
LOG = open(ROOT / "docs" / "environment" / "probe_ocr3_out.txt", "w", encoding="utf-8")


def p(*a):
    s = " ".join(str(x) for x in a)
    print(s)
    LOG.write(s + "\n")
    LOG.flush()


def head(t):
    p("\n" + t)
    p("-" * len(t))


def dic(m):
    return m.model_dump() if hasattr(m, "model_dump") else vars(m)


head("0. .gguf EN DISCO (busqueda amplia, incluye node_modules y AppData)")
SKIP = {".git", "__pycache__", "Windows", "Program Files", "Program Files (x86)"}
raices = [ROOT, Path.home() / "AppData" / "Local", Path.home() / "AppData" / "Roaming",
          Path.home() / ".qvac", Path.home() / ".cache"]
encontrados = []
for base in raices:
    if not base.exists():
        continue
    base_n = len(base.parts)
    for dirpath, dirnames, filenames in os.walk(base):
        if len(Path(dirpath).parts) - base_n > 6:
            dirnames[:] = []
            continue
        dirnames[:] = [d for d in dirnames if d not in SKIP]
        for f in filenames:
            if f.endswith(".gguf"):
                fp = Path(dirpath) / f
                encontrados.append(fp)
                p(f"  {fp}  ({fp.stat().st_size / 1e6:.1f} MB)")
if not encontrados:
    p("  NINGUNO. Los modelos no estan en disco -> hipotesis B confirmada.")


async def main():
    client = q.Client(sdk_dir=os.environ.get("QVAC_SDK_DIR"),
                      bare_path=os.environ.get("QVAC_BARE_PATH"))
    async with client:
        tr = getattr(client, "transport", None) or client._transport

        catalogo = {d["name"]: d for d in
                    (dic(m) for m in await q.model_registry_search(tr, addon="ocr"))}
        p("\ncatalogo ocr:", list(catalogo))

        head("1. DESCARGA CON RESPUESTA COMPLETA")
        for nombre in ("craft_mlt_25k", "latin_g2"):
            for kwargs in ({"with_progress": True}, {"with_progress": True, "seed": True}):
                try:
                    t0 = time.time()
                    resp = await q.download_asset(tr, DownloadAssetRequest(
                        type="downloadAsset", asset_src=nombre, **kwargs))
                    p(f"  {nombre} {kwargs}: {time.time() - t0:.1f}s")
                    p(f"    respuesta: {json.dumps(dic(resp), ensure_ascii=False, default=str)[:800]}")
                    break
                except Exception as e:
                    p(f"  {nombre} {kwargs}: {type(e).__name__}: {str(e)[:300]}")

        head("2. LISTA COMPLETA DE 'Available models'")
        disponibles = []
        try:
            await q.load_model(tr, model_src="__inexistente__", model_type="ggml-ocr",
                               model_config={"detectorModelSrc": "__inexistente__"})
        except Exception as e:
            texto = str(e)
            p(f"  (mensaje completo, {len(texto)} caracteres)")
            m = re.search(r"Available models:\s*(.+)", texto, re.S)
            if m:
                disponibles = [x.strip() for x in m.group(1).replace("\n", " ").split(",")
                               if x.strip()]
                p(f"  total disponibles: {len(disponibles)}")
                claves = ("ocr", "craft", "crnn", "latin", "db_mobile", "mobilenet",
                          "easy", "doctr")
                coinciden = [x for x in disponibles
                             if any(k in x.lower() for k in claves)]
                p(f"  COINCIDEN CON OCR ({len(coinciden)}): {coinciden}")
                p("  primeros 40 del total: " + ", ".join(disponibles[:40]))
                p("  ultimos 20 del total: " + ", ".join(disponibles[-20:]))
            else:
                p("  no pude extraer la lista. Mensaje crudo:")
                p("  " + texto[:3000])

        head("3. MATRIZ FINAL")

        def descriptor(nombre):
            """detectorModelSrc en forma de OBJETO, armado desde el registry."""
            d = catalogo.get(nombre, {})
            obj = {"src": d.get("registry_path") or d.get("model_id") or nombre}
            for origen, destino in (("name", "name"), ("model_id", "modelId"),
                                    ("registry_path", "registryPath"),
                                    ("registry_source", "registrySource"),
                                    ("blob_core_key", "blobCoreKey"),
                                    ("engine", "engine"),
                                    ("expected_size", "expectedSize"),
                                    ("sha256_checksum", "sha256Checksum")):
                v = d.get(origen)
                if v is not None:
                    obj[destino] = str(v) if destino in ("engine",) else v
            obj["addon"] = "ocr"
            return obj

        def candidatos_src(nombre):
            d = catalogo.get(nombre, {})
            out = []
            # lo que aparezca en la lista real de disponibles gana
            for x in disponibles:
                if nombre.lower() in x.lower():
                    out.append(x)
            for v in (d.get("model_id"), d.get("name"), d.get("registry_path")):
                if v and v not in out:
                    out.append(v)
            for fp in encontrados:
                if nombre.lower() in fp.name.lower():
                    out.append(str(fp))
            return out

        parejas = [("latin_g2", "craft_mlt_25k", "easyocr"),
                   ("crnn_mobilenet_v3_small", "db_mobilenet_v3_large", "doctr")]
        ganador = None
        for recon, det, pipe in parejas:
            dets = [descriptor(det)] + candidatos_src(det)
            for src in candidatos_src(recon):
                for dsrc in dets:
                    cfg = {"detectorModelSrc": dsrc, "pipelineType": pipe,
                           "langList": ["es", "en"]}
                    corta = dsrc if isinstance(dsrc, str) else f"<objeto src={dsrc['src']}>"
                    try:
                        mid = await q.load_model(tr, model_src=src, model_type="ggml-ocr",
                                                 model_config=cfg)
                        p(f"  [OK]    src={src!r} det={corta} pipe={pipe}  ->  {mid}")
                        ganador = {"model_src": src, "model_type": "ggml-ocr",
                                   "model_config": cfg, "_model_id": mid,
                                   "reconocedor": recon, "detector": det}
                        break
                    except Exception as e:
                        p(f"  [falla] src={src!r} det={corta} pipe={pipe}")
                        p(f"          {str(e).splitlines()[0][:400]}")
                if ganador:
                    break
            if ganador:
                break

        if not ganador:
            p("\nNinguna combinacion cargo. El log tiene la lista completa de IDs validos.")
            return

        head("4. OCR SOBRE RECIBOS REALES")
        corridas = []
        for nombre in ("R028.jpg", "R002.jpg", "R001.jpg"):
            img = ROOT / "data" / "receipts" / nombre
            if not img.exists():
                continue
            req = OcrStreamRequest(
                type="ocrStream", model_id=ganador["_model_id"],
                image=OcrStreamRequestImageFilePath(type="filePath", value=str(img)),
                options=None)
            t0, n, bloques = time.time(), 0, []
            try:
                async for chunk in q.ocr_stream(tr, req):
                    n += 1
                    if n == 1:
                        p(f"\n  --- {nombre}: primer chunk crudo ---")
                        p("  " + json.dumps(dic(chunk), ensure_ascii=False,
                                            default=str)[:900])
                    if getattr(chunk, "error", None):
                        p(f"  ERROR: {chunk.error}")
                        break
                    for b in (getattr(chunk, "blocks", None) or []):
                        bloques.append(getattr(b, "text", "") or "")
            except Exception as e:
                p(f"  {nombre}: {type(e).__name__}: {str(e)[:300]}")
                continue
            dur = time.time() - t0
            p(f"\n  {nombre}: {len(bloques)} bloques en {dur:.2f}s")
            p("  " + "\n".join(bloques)[:1200].replace("\n", "\n  "))
            corridas.append({"imagen": nombre, "bloques": len(bloques),
                             "latencia_s": round(dur, 2)})

        head("5. RECETA")
        salida = {k: v for k, v in ganador.items() if not k.startswith("_")}
        salida["corridas"] = corridas
        (ROOT / "docs" / "environment" / "ocr_recipe.json").write_text(
            json.dumps(salida, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        p(json.dumps(salida, indent=2, ensure_ascii=False, default=str))


try:
    asyncio.run(main())
except Exception as e:
    import traceback
    p(f"\nEXCEPCION GLOBAL: {type(e).__name__}: {e}")
    p(traceback.format_exc())
finally:
    LOG.close()
