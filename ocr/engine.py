import os, time, json, base64
import tetherto.qvac_sdk as qvac
from dotenv import load_dotenv

load_dotenv()
# Tomamos el nombre del modelo de tu archivo .env
MODEL_OCR = os.getenv("QVAC_MODEL_OCR", "modelo-no-configurado")

def _b64(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()

def run_ocr(image_path: str) -> dict:
    t0 = time.time()
    try:
        client = qvac.Client()
        
        # Inyectamos los parámetros exactos que descubrimos en la introspección
        request = qvac.OcrStreamRequest(
            modelId=MODEL_OCR,
            image={"base64": _b64(image_path)}
        )
        
        response = client.ocr_stream(request)
        
        raw_text = ""
        # Iteramos el stream nativo
        for chunk in response:
            if hasattr(chunk, 'text'):
                raw_text += chunk.text
            elif isinstance(chunk, dict) and 'text' in chunk:
                raw_text += chunk['text']
            else:
                raw_text += str(chunk)
            
        return {
            "raw_text": raw_text.strip(), 
            "engine": MODEL_OCR, 
            "route": "ocr",
            "duration_s": round(time.time() - t0, 2), 
            "quality_flags": []
        }
    except Exception as e:
        print(f"\n[!] Error nativo SDK: {e}")
        return {"raw_text": "", "engine": "qvac-native-ocr", "route": "ocr", "duration_s": round(time.time() - t0, 2), "quality_flags": ["sdk_error"]}

if __name__ == "__main__":
    import sys
    print(json.dumps(run_ocr(sys.argv[1]), indent=2, ensure_ascii=False))