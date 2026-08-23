"""Genera la tabla de permalinks del README apuntando al commit actual.

    python scripts/permalinks.py            # actualiza README.md
    python scripts/permalinks.py --mostrar  # solo imprime la tabla

Por que un script y no escribirlos a mano: el jurado mira primero los permalinks a
las lineas donde ocurre la inferencia, y un enlace a `main` o a una linea corrida por
un commit posterior lo manda a codigo que no es el que se describe. Aca los numeros
de linea se buscan por su marcador en el archivo y el hash sale de `git rev-parse`,
asi que la tabla no puede quedar desfasada: se regenera antes del freeze y listo.
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
INICIO = "<!-- PERMALINKS -->"
FIN = "<!-- /PERMALINKS -->"

# (etiqueta, archivo, patron que identifica la linea, cuantas lineas resaltar)
PUNTOS = [
    ("Carga del par OCR (detector + reconocedor)", "ocr/engine.py",
     r"self\.model_id = await q\.load_model", 3),
    ("Inferencia OCR sobre la imagen", "ocr/engine.py",
     r"async for chunk in q\.ocr_stream", 6),
    ("Barrido de rotacion", "ocr/engine.py",
     r"async def leer_orientada", 12),
    ("Cliente QVAC: interfaz del orquestador", "backend/core/llm/qvac.py",
     r"def extract_invoice", 5),
    ("Pipeline de dos etapas (OCR -> texto -> JSON)", "backend/core/llm/qvac.py",
     r"async def _extraer", 14),
    ("Carga del modelo de texto", "backend/core/llm/qvac.py",
     r"self\.modelo_texto = await q\.load_model", 4),
    ("Generacion (llamacpp-completion)", "backend/core/llm/qvac.py",
     r"async def completar", 8),
    ("Seleccion del motor real", "backend/core/llm/factory.py",
     r'if kind == "qvac"', 6),
    ("Verificacion de valores contra el texto OCR", "confidence/detectors.py",
     r"def valor_aparece", 10),
    ("Descarga de modelos desde el registry", "scripts/setup_models.py",
     r"async def descargar", 8),
]


def repo_url():
    url = subprocess.check_output(["git", "config", "--get", "remote.origin.url"],
                                  cwd=RAIZ, text=True).strip()
    url = re.sub(r"\.git$", "", url)
    return re.sub(r"^git@github\.com:", "https://github.com/", url)


def commit():
    return subprocess.check_output(["git", "rev-parse", "HEAD"],
                                   cwd=RAIZ, text=True).strip()


def linea_de(archivo, patron):
    ruta = RAIZ / archivo
    if not ruta.exists():
        return None
    for i, linea in enumerate(ruta.read_text(encoding="utf-8").splitlines(), 1):
        if re.search(patron, linea):
            return i
    return None


def tabla():
    base, sha = repo_url(), commit()
    faltantes = []
    filas = ["| Que | Donde |", "|---|---|"]
    for etiqueta, archivo, patron, span in PUNTOS:
        n = linea_de(archivo, patron)
        if n is None:
            faltantes.append(f"{archivo} :: {patron}")
            continue
        ancla = f"#L{n}-L{n + span}" if span else f"#L{n}"
        filas.append(f"| {etiqueta} | [`{archivo}:{n}`]({base}/blob/{sha}/{archivo}{ancla}) |")
    return "\n".join(filas), sha, faltantes


def main():
    ap = argparse.ArgumentParser(description="Regenera los permalinks del README")
    ap.add_argument("--mostrar", action="store_true", help="no escribe, solo imprime")
    a = ap.parse_args()

    md, sha, faltantes = tabla()
    if faltantes:
        print("No encontre estos marcadores (el codigo cambio?):", file=sys.stderr)
        for f in faltantes:
            print("  ", f, file=sys.stderr)

    bloque = f"{INICIO}\n\n{md}\n\n_Enlaces fijados al commit `{sha[:10]}`._\n\n{FIN}"
    if a.mostrar:
        print(bloque)
        return 0

    readme = RAIZ / "README.md"
    texto = readme.read_text(encoding="utf-8")
    if INICIO not in texto or FIN not in texto:
        print(f"README.md no tiene los marcadores {INICIO} / {FIN}", file=sys.stderr)
        return 1
    nuevo = re.sub(re.escape(INICIO) + r".*?" + re.escape(FIN), bloque, texto, flags=re.S)
    readme.write_text(nuevo, encoding="utf-8")
    print(f"Permalinks actualizados al commit {sha[:10]}.")
    print("IMPORTANTE: commitea y pushea el README DESPUES de correr esto, y si\n"
          "haces mas commits al codigo, volve a correrlo antes de enviar.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
