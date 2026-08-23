"""Introspeccion del SDK QVAC: firmas, campos pydantic y registry de modelos.
Diagnostico, no codigo de producto. Ejecutar: python docs/environment/probe.py"""
import os, inspect, asyncio
from dotenv import load_dotenv
import tetherto.qvac_sdk as q

load_dotenv()

def fields(name):
    try:
        c = getattr(q, name)
        print(f"\n== {name} ==")
        for k, v in c.model_fields.items():
            print(f"  {k}: {v.annotation}")
    except Exception as e:
        print(f"\n== {name} == ERROR: {e}")

print("== ModelType (valores exactos) ==")
try:
    print([(m.name, m.value) for m in q.ModelType])
except TypeError:
    print([m for m in dir(q.ModelType) if not m.startswith("_")])

for c in ("LoadModelRequest", "LoadModelResponse", "OcrStreamRequest",
          "OcrStreamResponse", "ModelRegistryListRequest",
          "ModelRegistrySearchRequest", "DownloadAssetRequest"):
    fields(c)

try:
    from tetherto.qvac_sdk._generated.models import _internal as gi
    for n in dir(gi):
        if n.startswith("OcrStreamRequest") and hasattr(getattr(gi, n), "model_fields"):
            print(f"\n== interno: {n} ==")
            for k, v in getattr(gi, n).model_fields.items():
                print(f"  {k}: {v.annotation}")
except Exception as e:
    print("internos:", e)

for fn in ("load_model", "ocr_stream", "model_registry_list",
           "model_registry_search", "download_asset", "get_model_info"):
    try:
        print(f"\n{fn}{inspect.signature(getattr(q, fn))}")
    except Exception as e:
        print(fn, "ERROR:", e)

async def registry():
    client = q.Client(sdk_dir=os.environ.get("QVAC_SDK_DIR"),
                      bare_path=os.environ.get("QVAC_BARE_PATH"))
    async with client:
        for maker in (lambda: q.model_registry_list(client.transport, q.ModelRegistryListRequest()),
                      lambda: q.model_registry_list(client.transport)):
            try:
                res = maker()
                if inspect.isawaitable(res):
                    res = await res
                print("\n== REGISTRY (modelos disponibles) ==")
                print(res)
                return
            except Exception as e:
                print(f"[intento fallido] {type(e).__name__}: {e}")

asyncio.run(registry())
