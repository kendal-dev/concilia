"""Probe OCR v2 - encuentra la combinacion exacta que carga el pipeline ggml-ocr.

    python docs\\environment\\probe_ocr2.py

Que aprendimos del probe v1 (todo verificado, nada supuesto):
  - `modelSrc` y `detectorModelSrc` se resuelven por ID de modelo, no por nombre ni por
    registry_path: el error listaba "Available models: acestep-...gguf, ...", todos con
    extension. El ID correcto es el campo `model_id` del registry (con .gguf).
  - El registry tiene CUATRO modelos ocr, de dos familias distintas:
      easyocr  -> detector craft_mlt_25k        + reconocedor latin_g2
      doctr    -> detector db_mobilenet_v3_large + reconocedor crnn_mobilenet_v3_small
    Mezclarlos es lo que producia "easyocr pipeline expects craft_mlt_25k.gguf":
    se pedia el reconocedor de doctr con el detector de easyocr.
  - `modelConfig.pipelineType` es un enum: aqui se imprimen sus valores reales.

El script descarga los cuatro modelos y prueba la matriz hasta que uno cargue.
"""
import asyncio
import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv
import tetherto.qvac_sdk as q
from tetherto.qvac_sdk._generated.models import _internal as gi
from tetherto.qvac_sdk._generated.models._internal import (
    DownloadAssetRequest,
    OcrStreamRequest,
    OcrStreamRequestImageFilePath,
)

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
LOG = open(ROOT / "docs" / "environment" / "probe_ocr2_out.txt", "w", encoding="utf-8")


def p(*a):
    s = " ".join(str(x) for x in a)
    print(s)
    LOG.write(s + "\n")
    LOG.flush()


def head(t):
    p("\n" + t)
    p("-" * len(t))


def valores_enum(nombre):
    c = getattr(gi, nombre, None)
    if c is None:
        return []
    try:
        return [m.value for m in c]
    except TypeError:
        return [v for k, v in vars(c).items() if isinstance(v, str) and not k.startswith("_")]


head("1. ENUMS DEL modelConfig")
PIPELINES = valores_enum("LoadModelSrcRequestGgmlOcrModelConfigPipelineType")
BACKENDS = valores_enum("LoadModelSrcRequestGgmlOcrModelConfigBackendDevice")
p("pipelineType:", PIPELINES)
p("backendDevice:", BACKENDS)


def dic(m):
    return m.model_dump() if hasattr(m, "model_dump") else vars(m)


async def main():
    client = q.Client(sdk_dir=os.environ.get("QVAC_SDK_DIR"),
                      bare_path=os.environ.get("QVAC_BARE_PATH"))
    async with client:
        tr = getattr(client, "transport", None) or client._transport

        head("2. CATALOGO OCR")
        modelos = [dic(m) for m in await q.model_registry_search(tr, addon="ocr")]
        por_nombre = {}
        for d in modelos:
            por_nombre[d["name"]] = d
            p(f"  {d['name']:32} id={d['model_id']:34} path={d.get('registry_path')}")

        head("3. DESCARGA DE LOS CUATRO")
        for nombre in por_nombre:
            try:
                t0 = time.time()
                await q.download_asset(tr, DownloadAssetRequest(
                    type="downloadAsset", asset_src=nombre, with_progress=False))
                p(f"  {nombre}: OK ({time.time() - t0:.1f}s)")
            except Exception as e:
                p(f"  {nombre}: {type(e).__name__}: {str(e)[:120]}")

        head("4. MATRIZ DE CARGA")

        def ids(nombre):
            """Devuelve los identificadores plausibles de un modelo, en orden de apuesta."""
            d = por_nombre.get(nombre, {})
            out = []
            for v in (d.get("model_id"), d.get("name"), d.get("registry_path")):
                if v and v not in out:
                    out.append(v)
            return out

        # pares coherentes primero: reconocedor y detector de la MISMA familia
        parejas = [
            ("latin_g2", "craft_mlt_25k", "easyocr"),
            ("crnn_mobilenet_v3_small", "db_mobilenet_v3_large", "doctr"),
            ("crnn_mobilenet_v3_small", "craft_mlt_25k", None),
            ("latin_g2", "db_mobilenet_v3_large", None),
        ]
        # pipelineType candidato: el sugerido por la familia si existe en el enum
        def pipes(sugerido):
            cands = []
            if sugerido:
                for v in PIPELINES:
                    if sugerido in str(v).lower():
                        cands.append(v)
            cands.append(None)
            for v in PIPELINES:
                if v not in cands:
                    cands.append(v)
            return cands

        ganador = None
        for recon, det, familia in parejas:
            if recon not in por_nombre or det not in por_nombre:
                continue
            for src in ids(recon):
                for dsrc in ids(det):
                    for pt in pipes(familia):
                        cfg = {"detectorModelSrc": dsrc}
                        if pt:
                            cfg["pipelineType"] = pt
                        etiqueta = f"src={src!r} det={dsrc!r} pipe={pt!r}"
                        try:
                            mid = await q.load_model(tr, model_src=src,
                                                     model_type="ggml-ocr",
                                                     model_config=cfg)
                            p(f"  [OK]    {etiqueta}  ->  model_id={mid}")
                            ganador = {"model_src": src, "model_type": "ggml-ocr",
                                       "model_config": cfg, "_model_id": mid,
                                       "reconocedor": recon, "detector": det}
                            break
                        except Exception as e:
                            p(f"  [falla] {etiqueta}  ->  {str(e).splitlines()[0][:110]}")
                    if ganador:
                        break
                if ganador:
                    break
            if ganador:
                break

        if not ganador:
            p("\nNinguna combinacion cargo. Pegar este log completo.")
            return

        head("5. OCR SOBRE RECIBOS REALES")
        recetas = []
        for nombre in ("R028.jpg", "R002.jpg", "R001.jpg"):
            img = ROOT / "data" / "receipts" / nombre
            if not img.exists():
                continue
            req = OcrStreamRequest(
                type="ocrStream",
                model_id=ganador["_model_id"],
                image=OcrStreamRequestImageFilePath(type="filePath", value=str(img)),
                options=None,
            )
            t0, n, bloques = time.time(), 0, []
            try:
                async for chunk in q.ocr_stream(tr, req):
                    n += 1
                    if n == 1:
                        p(f"\n  --- {nombre}: primer chunk crudo ---")
                        p("  " + json.dumps(chunk.model_dump(), ensure_ascii=False,
                                            default=str)[:900])
                    if getattr(chunk, "error", None):
                        p(f"  ERROR: {chunk.error}")
                        break
                    for b in (getattr(chunk, "blocks", None) or []):
                        bloques.append(getattr(b, "text", "") or "")
            except Exception as e:
                p(f"  {nombre}: EXCEPCION {type(e).__name__}: {str(e)[:200]}")
                continue
            dur = time.time() - t0
            texto = "\n".join(bloques)
            p(f"\n  {nombre}: {len(bloques)} bloques, {dur:.2f}s")
            p("  --- TEXTO ---")
            p("  " + texto[:1200].replace("\n", "\n  "))
            recetas.append({"imagen": nombre, "bloques": len(bloques),
                            "latencia_s": round(dur, 2)})

        head("6. RECETA")
        salida = {k: v for k, v in ganador.items() if not k.startswith("_")}
        salida["corridas"] = recetas
        (ROOT / "docs" / "environment" / "ocr_recipe.json").write_text(
            json.dumps(salida, indent=2, ensure_ascii=False), encoding="utf-8")
        p(json.dumps(salida, indent=2, ensure_ascii=False))
        p("\nGuardado en docs/environment/ocr_recipe.json")


try:
    asyncio.run(main())
except Exception as e:
    import traceback
    p(f"\nEXCEPCION GLOBAL: {type(e).__name__}: {e}")
    p(traceback.format_exc())
finally:
    LOG.close()
