"""Diagnostico: firmas y campos del SDK QVAC. No es codigo de producto."""
import inspect, asyncio, json
import tetherto.qvac_sdk as q

print("=== Client ===")
print(inspect.signature(q.Client))

for cls in ("ModelRegistryListRequest", "ModelRegistrySearchRequest",
            "LoadModelRequest", "OcrStreamRequest", "OcrStreamResponse"):
    c = getattr(q, cls)
    print(f"\n=== {cls} ===")
    try:
        print({k: str(v.annotation) for k, v in c.model_fields.items()})
    except Exception as e:
        print("sin model_fields:", e)

for fn in ("model_registry_list", "model_registry_search", "load_model", "ocr_stream"):
    print(f"\n=== {fn} ===", inspect.signature(getattr(q, fn)))

print("\n=== ModelType ===")
print([m for m in dir(q.ModelType) if not m.startswith("_")])

print("\n=== Intento de listar registry ===")
try:
    client = q.Client()
    req = q.ModelRegistryListRequest()
    res = q.model_registry_list(client, req)
    if inspect.iscoroutine(res):
        res = asyncio.run(res)
    print(res)
except Exception as e:
    print(f"[fallo controlado] {type(e).__name__}: {e}")