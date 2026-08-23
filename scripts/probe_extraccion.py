"""Prueba el pipeline de inferencia completo sobre una imagen, SIN base de datos.

    python scripts/probe_extraccion.py data/receipts/R028.jpg

Corre exactamente lo que corre en produccion - `QvacLLMClient.extract_invoice` - y
muestra las tres capas por separado:

  1. el texto crudo del OCR      (etapa 1, ggml-ocr)
  2. el JSON crudo del modelo    (etapa 2, llamacpp-completion)
  3. la validacion contra `ExtractedInvoice` y que valores se pudieron verificar
     contra el texto del OCR

Sirve para separar culpas antes de meter MariaDB en la ecuacion: si el OCR trae
basura, no tiene sentido mirar el JSON; si el JSON no valida, no tiene sentido
mirar la conciliacion.
"""
import json
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from backend.core.llm.qvac import QvacLLMClient          # noqa: E402
from backend.core.schemas import ExtractedInvoice        # noqa: E402


def separador(titulo):
    print("\n" + titulo)
    print("-" * len(titulo))


def main():
    if len(sys.argv) < 2:
        print("Uso: python scripts/probe_extraccion.py <imagen> [imagen2 ...]")
        return 1

    cliente = QvacLLMClient()
    separador("MOTOR")
    print(json.dumps(QvacLLMClient.info_motor(), indent=2, ensure_ascii=False))

    for ruta in sys.argv[1:]:
        p = Path(ruta)
        if not p.exists():
            print(f"\n{ruta}: no existe")
            continue

        cliente.filename = p.name
        t0 = time.time()
        crudo = cliente.extract_invoice(p.read_bytes())
        total_s = round(time.time() - t0, 2)
        ev = cliente.ultima_evidencia or {}

        separador(f"{p.name}  ({total_s} s en total)")
        print("--- 1. TEXTO OCR (etapa 1) ---")
        print(ev.get("texto_ocr") or "(vacio)")
        print(f"\nmetricas OCR: {json.dumps(ev.get('ocr', {}), ensure_ascii=False)}")

        print("\n--- 2. JSON CRUDO DEL MODELO (etapa 2) ---")
        print(crudo)

        print("\n--- 3. VALIDACION ---")
        try:
            factura = ExtractedInvoice.model_validate(json.loads(crudo))
            print("esquema: VALIDO")
            print(f"  proveedor : {factura.supplier_name}")
            print(f"  NIT       : {factura.supplier_tax_id}")
            print(f"  numero    : {factura.invoice_number}")
            print(f"  fecha     : {factura.invoice_date}")
            print(f"  total     : {factura.total_amount} {factura.currency or ''}")
            print(f"  lineas    : {len(factura.line_items)}")
            print(f"  datos minimos para conciliar: {factura.has_minimum_data()}")
        except Exception as e:
            print(f"esquema: RECHAZADO -> {type(e).__name__}: {str(e)[:400]}")
            print("(en produccion esto dispara el reintento del orquestador)")

        print("\n--- VALORES VERIFICADOS CONTRA EL TEXTO DEL OCR ---")
        verificados = ev.get("valores_verificados") or {}
        if not verificados:
            print("(ninguno: sin texto OCR o sin JSON parseable)")
        for campo, d in verificados.items():
            marca = "OK      " if d["aparece_en_ocr"] else "INVENTADO"
            print(f"  [{marca}] {campo:18} {d['valor']:>14}   similitud {d['similitud']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
