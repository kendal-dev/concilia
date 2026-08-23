"""Probe OCR - resuelve el pipeline detector+reconocedor de QVAC y deja la receta escrita.

Uso:  python docs\\environment\\probe_ocr.py
Escribe consola + docs/environment/probe_ocr_out.txt + docs/environment/ocr_recipe.json

Hace, en orden:
  1. Introspeccion de LoadModelSrcRequestGgmlOcr y su modelConfig (claves JSON exactas).
  2. Lista TODOS los modelos addon=ocr del registry (busca el detector craft_*).
  3. Descarga el detector si falta.
  4. Prueba combinaciones de model_config hasta que load_model devuelva un model_id.
  5. Con el modelo cargado, corre ocr_stream sobre una imagen real y vuelca la
     estructura cruda del primer bloque (para saber como se llama el campo de texto).
  6. Guarda la receta ganadora en ocr_recipe.json.
"""
import asyncio
import json
import os
import sys
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

LOG = open(ROOT / "docs" / "environment" / "probe_ocr_out.txt", "w", encoding="utf-8")


def p(*a):
    s = " ".join(str(x) for x in a)
    print(s)
    LOG.write(s + "\n")
    LOG.flush()


def head(t):
    p("\n" + t)
    p("-" * len(t))


def show(cls, title=None, depth=0):
    if cls is None or not hasattr(cls, "model_fields"):
        return
    p(f"\n== {title or getattr(cls, '__name__', cls)} ==")
    for k, f in cls.model_fields.items():
        alias = f.alias or k
        req = "REQUERIDO" if f.is_required() else "opcional"
        p(f"  py:{k}  json:{alias}  {req}  ->  {f.annotation}")
    if depth == 0:
        for k, f in cls.model_fields.items():
            for sub in getattr(f.annotation, "__args__", ()) or (f.annotation,):
                if hasattr(sub, "model_fields") and getattr(sub, "__name__", "") not in ("NoneType",):
                    show(sub, f"anidado {cls.__name__}.{k} -> {sub.__name__}", depth + 1)


head("1. CLASES DE CARGA DE MODELO (nombres reales del SDK)")
for n in sorted(dir(gi)):
    if "Ocr" in n or n.startswith("LoadModel"):
        p("  ", n)

for name in ["LoadModelSrcRequestGgmlOcr", "OcrStreamResponseBlocksItem",
             "OcrStreamResponseStats", "OcrStreamRequestOptions"]:
    show(getattr(gi, name, None), name)


def campos_json(cls_name):
    cls = getattr(gi, cls_name, None)
    if cls is None:
        return []
    return [(f.alias or k) for k, f in cls.model_fields.items()]


CFG_CLS = None
for k, f in getattr(gi, "LoadModelSrcRequestGgmlOcr", type("X", (), {"model_fields": {}})).model_fields.items():
    if (f.alias or k) == "modelConfig":
        for sub in getattr(f.annotation, "__args__", ()) or (f.annotation,):
            if hasattr(sub, "model_fields"):
                CFG_CLS = sub
if CFG_CLS is not None:
    show(CFG_CLS, "modelConfig de ggml-ocr (CLAVES QUE ACEPTA)")
    CLAVES_CFG = [(f.alias or k) for k, f in CFG_CLS.model_fields.items()]
else:
    CLAVES_CFG = []
p("\nclaves modelConfig detectadas:", CLAVES_CFG)


async def main():
    client = q.Client(sdk_dir=os.environ.get("QVAC_SDK_DIR"),
                      bare_path=os.environ.get("QVAC_BARE_PATH"))
    async with client:
        tr = client._transport

        head("2. REGISTRY addon=ocr")
        modelos = await q.model_registry_search(tr, addon="ocr")
        catalogo = []
        for m in modelos:
            d = m.model_dump() if hasattr(m, "model_dump") else vars(m)
            catalogo.append(d)
            p(f"  name={d.get('name')!r:45} model_id={d.get('model_id')!r:40} "
              f"engine={d.get('engine')} size={d.get('expected_size')}")

        recon = os.environ.get("QVAC_MODEL_OCR") or "crnn_mobilenet_v3_small"
        det = next((d for d in catalogo if "craft" in str(d.get("name", "")).lower()), None)
        if det is None:
            p("\n!! No hay modelo 'craft' en addon=ocr. Buscando en todo el registry...")
            todos = await q.model_registry_list(tr)
            for m in todos:
                d = m.model_dump() if hasattr(m, "model_dump") else vars(m)
                if "craft" in str(d.get("name", "")).lower():
                    det = d
                    p("  encontrado en list():", d.get("name"), d.get("registry_path"))
                    break
        if det is None:
            p("\nFATAL: no encuentro el detector craft_mlt_25k en el registry.")
            return

        det_name = det.get("name")
        det_path = det.get("registry_path")
        p(f"\nDETECTOR: name={det_name}  registry_path={det_path}")
        p(f"RECONOCEDOR: {recon}")

        head("3. DESCARGA DEL DETECTOR")
        try:
            t0 = time.time()
            await q.download_asset(tr, DownloadAssetRequest(
                type="downloadAsset", asset_src=det_name, with_progress=False))
            p(f"  descarga OK en {time.time() - t0:.1f}s")
        except Exception as e:
            p(f"  descarga fallo (puede que ya este en cache): {type(e).__name__}: {e}")

        head("4. COMBINACIONES DE load_model")
        candidatos = []
        for clave in (CLAVES_CFG or ["detectorModelSrc"]):
            if "detector" in clave.lower():
                for val in (det_name, det_path):
                    if val:
                        candidatos.append({clave: val})
        if not candidatos:
            candidatos = [{"detectorModelSrc": det_name}, {"detectorModelSrc": det_path}]
        # variantes de model_src del reconocedor
        recon_vals = [recon]
        rec_entry = next((d for d in catalogo if d.get("name") == recon), None)
        if rec_entry and rec_entry.get("registry_path"):
            recon_vals.append(rec_entry["registry_path"])

        ganador = None
        for rv in recon_vals:
            for cfg in candidatos:
                etiqueta = f"model_src={rv!r} model_config={cfg}"
                try:
                    mid = await q.load_model(tr, model_src=rv, model_type="ggml-ocr",
                                             model_config=cfg)
                    p(f"  [OK]   {etiqueta}  ->  model_id={mid}")
                    ganador = {"model_src": rv, "model_type": "ggml-ocr",
                               "model_config": cfg, "model_id": mid}
                    break
                except Exception as e:
                    msg = str(e).splitlines()[0][:160]
                    p(f"  [FALLA] {etiqueta}  ->  {type(e).__name__}: {msg}")
            if ganador:
                break

        if not ganador:
            p("\nNinguna combinacion cargo. Pegar este log completo.")
            return

        head("5. OCR SOBRE IMAGEN REAL")
        img = None
        for cand in ["data/receipts/R001.jpg", "data/receipts/R001.jpeg", "dummy.jpg"]:
            if (ROOT / cand).exists():
                img = str((ROOT / cand).resolve())
                break
        if img is None:
            p("  sin imagen de prueba en data/receipts/. Saltando.")
        else:
            p(f"  imagen: {img}")
            req = OcrStreamRequest(
                type="ocrStream",
                model_id=ganador["model_id"],
                image=OcrStreamRequestImageFilePath(type="filePath", value=img),
                options=None,
            )
            t0 = time.time()
            n = 0
            texto = []
            async for chunk in q.ocr_stream(tr, req):
                n += 1
                if n == 1:
                    p("\n  --- PRIMER CHUNK CRUDO (estructura real) ---")
                    p("  ", json.dumps(chunk.model_dump(), ensure_ascii=False, default=str)[:1500])
                if getattr(chunk, "error", None):
                    p("  ERROR en stream:", chunk.error)
                    break
                for b in (getattr(chunk, "blocks", None) or []):
                    bd = b.model_dump() if hasattr(b, "model_dump") else vars(b)
                    if n <= 2:
                        p("   bloque:", json.dumps(bd, ensure_ascii=False, default=str)[:300])
                    for k in ("text", "value", "content", "label"):
                        if bd.get(k):
                            texto.append(str(bd[k]))
                            break
            dur = time.time() - t0
            p(f"\n  chunks={n}  latencia={dur:.2f}s")
            p("  --- TEXTO RECONSTRUIDO ---")
            p("  " + " ".join(texto)[:2000])
            ganador["latencia_s"] = round(dur, 2)
            ganador["chunks"] = n

        head("6. RECETA")
        ganador["detector_name"] = det_name
        ganador["detector_registry_path"] = det_path
        ganador.pop("model_id", None)
        (ROOT / "docs" / "environment" / "ocr_recipe.json").write_text(
            json.dumps(ganador, indent=2, ensure_ascii=False), encoding="utf-8")
        p(json.dumps(ganador, indent=2, ensure_ascii=False))
        p("\nGuardado en docs/environment/ocr_recipe.json")


try:
    asyncio.run(main())
except Exception as e:
    p(f"\nEXCEPCION GLOBAL: {type(e).__name__}: {e}")
    import traceback
    p(traceback.format_exc())
finally:
    LOG.close()
