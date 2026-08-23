"""Descarga los modelos QVAC que CONCILIA necesita, desde un clone limpio.

    python scripts/setup_models.py             # baja el par de OCR (easyocr)
    python scripts/setup_models.py --doctr     # baja tambien el par docTR
    python scripts/setup_models.py --listar    # solo muestra el catalogo
    python scripts/setup_models.py --texto qwen3  # baja un modelo de texto (etapa 2)

Por que existe: el CLI `@qvac/cli` 0.11.0 NO tiene `qvac models pull` (sus comandos son
bundle, doctor, verify, openai, serve). La descarga se hace por el SDK.

Dos cosas que costaron horas y quedan documentadas aqui:

1. `download_asset` NO lanza excepcion cuando falla. El handler devuelve
   `{success: false, error: ...}`. Si no se revisa `success`, una descarga fallida
   parece exitosa - y despues `load_model` falla con "Available models: ..." sin que
   se entienda por que. Este script revisa `success` en cada descarga.

2. El identificador tiene que ser `registry://<source>/<registry_path>`. Un nombre
   suelto solo funciona si el archivo ya esta en la cache local.
"""
import argparse
import asyncio
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
import tetherto.qvac_sdk as q
from tetherto.qvac_sdk._generated.models._internal import DownloadAssetRequest

RAIZ = Path(__file__).resolve().parents[1]
load_dotenv(RAIZ / ".env")

PARES = {
    "easyocr": ("latin_g2", "craft_mlt_25k"),
    "doctr": ("crnn_mobilenet_v3_small", "db_mobilenet_v3_large"),
}


def transporte(client):
    return getattr(client, "transport", None) or client._transport


def dic(m):
    return m.model_dump() if hasattr(m, "model_dump") else vars(m)


def url_registry(d):
    return f"registry://{d.get('registry_source') or 's3'}/{d['registry_path']}"


async def descargar(tr, etiqueta, src):
    print(f"  {etiqueta}\n    {src}", flush=True)
    t0 = time.time()
    resp = dic(await q.download_asset(tr, DownloadAssetRequest(
        type="downloadAsset", asset_src=src, with_progress=True)))
    if not resp.get("success", False):
        print(f"    FALLO tras {time.time() - t0:.0f}s: {resp.get('error')}", flush=True)
        return False
    print(f"    OK en {time.time() - t0:.0f}s", flush=True)
    return True


async def main(a):
    if not os.environ.get("QVAC_SDK_DIR") or not os.environ.get("QVAC_BARE_PATH"):
        print("Falta configuracion. Copia .env.example a .env y ajusta QVAC_SDK_DIR y\n"
              "QVAC_BARE_PATH (los crea `npm install` en la raiz del proyecto).")
        return 1

    client = q.Client(sdk_dir=os.environ["QVAC_SDK_DIR"],
                      bare_path=os.environ["QVAC_BARE_PATH"])
    async with client:
        tr = transporte(client)
        ocr = {d["name"]: d for d in (dic(m) for m in
                                      await q.model_registry_search(tr, addon="ocr"))}
        print(f"\nModelos OCR en el registry ({len(ocr)}):")
        for n, d in ocr.items():
            print(f"  {n:30} {d['expected_size'] / 1e6:8.1f} MB   {url_registry(d)}")

        if a.texto is not None:
            texto = [dic(m) for m in await q.model_registry_search(tr, addon="llm")]
            filtro = (a.texto or "").lower()
            elegibles = [d for d in texto if filtro in str(d.get("name", "")).lower()]
            print(f"\nModelos de texto que coinciden con {filtro!r} "
                  f"({len(elegibles)} de {len(texto)}):")
            for d in elegibles[:40]:
                print(f"  {d['name']:45} {d.get('quantization') or '-':10} "
                      f"{(d.get('expected_size') or 0) / 1e9:5.2f} GB")

        if a.listar:
            return 0

        familias = [] if a.saltar_ocr else ["easyocr"] + (["doctr"] if a.doctr else [])
        ok = True
        for familia in familias:
            recon, det = PARES[familia]
            print(f"\nPar {familia}:")
            for etiqueta, nombre in (("detector", det), ("reconocedor", recon)):
                if nombre not in ocr:
                    print(f"  {etiqueta} {nombre}: no esta en el registry")
                    ok = False
                    continue
                ok &= await descargar(tr, f"{etiqueta} {nombre}",
                                      url_registry(ocr[nombre]))

        if a.texto and a.descargar_texto:
            texto = [dic(m) for m in await q.model_registry_search(tr, addon="llm")]
            elegido = next((d for d in texto
                            if a.texto.lower() in str(d.get("name", "")).lower()), None)
            if elegido:
                print(f"\nModelo de texto {elegido['name']}:")
                ok &= await descargar(tr, elegido["name"], url_registry(elegido))
            else:
                print(f"\nNingun modelo de texto coincide con {a.texto!r}")
                ok = False

        print("\n" + "=" * 66)
        if ok:
            recon, det = PARES["easyocr"]
            print("Listo. El .env no necesita los IDs: ocr/engine.py los resuelve del")
            print("registry en cada arranque. Si queres fijarlos igual:")
            print(f"  QVAC_MODEL_OCR={url_registry(ocr[recon])}")
            print(f"  QVAC_MODEL_OCR_DETECTOR={url_registry(ocr[det])}")
        else:
            print("Alguna descarga fallo. Revisa el detalle de arriba y reintenta:")
            print("  el registry es P2P, y una corrida fallida suele resolverse sola")
            print("  al segundo intento.")
        print("=" * 66)
    return 0 if ok else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Descarga los modelos QVAC de CONCILIA")
    ap.add_argument("--listar", action="store_true", help="solo listar, no descargar")
    ap.add_argument("--doctr", action="store_true", help="tambien el par docTR")
    ap.add_argument("--texto", nargs="?", const="", default=None,
                    help="filtra modelos de texto del registry (etapa 2)")
    ap.add_argument("--descargar-texto", action="store_true",
                    help="ademas de listarlo, descarga el primero que coincida")
    ap.add_argument("--saltar-ocr", action="store_true",
                    help="no toca el par de OCR (util si ya esta en cache)")
    sys.exit(asyncio.run(main(ap.parse_args())))
