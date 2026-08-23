import os, sys, json, time, asyncio
from dotenv import load_dotenv
import tetherto.qvac_sdk as q

load_dotenv()

async def _run_ocr_async(image_path: str) -> dict:
    start_time = time.time()
    
    try:
        client = q.Client(
            sdk_dir=os.environ.get("QVAC_SDK_DIR"),
            bare_path=os.environ.get("QVAC_BARE_PATH")
        )
    except Exception as e:
        return _fail(start_time, f"Fallo al iniciar Client: {e}")

    model_name = os.environ.get("QVAC_MODEL_OCR")
    if not model_name or model_name == "PENDIENTE":
        return _fail(start_time, "QVAC_MODEL_OCR PENDIENTE. Configura tu .env")

    raw_text = ""
    error_flag = None

    try:
        async with client:
            model_req = q.load_model(
                client.transport,
                model_name=model_name,
                model_type="ggml_ocr"
            )
            model_id = await model_req if asyncio.iscoroutine(model_req) else model_req

            req = q.OcrStreamRequest(
                type="ocrStream",
                model_id=model_id,
                image={"path": image_path}
            )

            async for chunk in q.ocr_stream(client.transport, req):
                if getattr(chunk, "error", None):
                    error_flag = chunk.error
                    break
                blocks = getattr(chunk, "blocks", [])
                if blocks:
                    for block in blocks:
                        if hasattr(block, 'text') and block.text:
                            raw_text += block.text + "\n"
    except Exception as e:
        error_flag = str(e)

    flags = []
    if error_flag:
        flags.append(f"stream_error: {error_flag}")

    return {
        "raw_text": raw_text.strip(),
        "engine": "qvac-native-ocr",
        "route": "ocr",
        "duration_s": round(time.time() - start_time, 2),
        "quality_flags": flags
    }

def _fail(start_time: float, reason: str) -> dict:
    return {
        "raw_text": "",
        "engine": "qvac-native-ocr",
        "route": "ocr",
        "duration_s": round(time.time() - start_time, 2),
        "quality_flags": [reason]
    }

def run_ocr(image_path: str) -> dict:
    return asyncio.run(_run_ocr_async(image_path))

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Uso: python ocr/engine.py <ruta_imagen>"}))
        sys.exit(1)
    print(json.dumps(run_ocr(sys.argv[1]), indent=2))