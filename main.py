"""CONCILIA - CLI.

    python main.py --receipt data/receipts/R001.jpg     un recibo, pipeline completo
    python main.py --batch   data/receipts/             todo el dataset
    python main.py --from-json eval/fixtures/match.json  sin inferencia (fixtures/tests)
    python main.py --report                              resumen desde MariaDB

`--report` sale de consultas SQL sobre los contratos guardados en la tabla
`conciliaciones` (JSON_EXTRACT), no de archivos sueltos: es lo que justifica MariaDB
en el stack y no un adorno.
"""
import argparse
import json
import sys
from pathlib import Path

from rich.console import Console

from db.connection import get_connection
from pipeline import conciliar, nuevo_contrato, serializable
from reconcile.repository import Repositorio
from report import terminal

RAIZ = Path(__file__).resolve().parent
LOGS = RAIZ / "logs" / "runs"
console = Console()


def _guardar_disco(contrato):
    d = LOGS / contrato["receipt_id"]
    d.mkdir(parents=True, exist_ok=True)
    (d / "contract.json").write_text(
        json.dumps(serializable(contrato), indent=2, ensure_ascii=False, default=str),
        encoding="utf-8")
    raw = contrato.get("ocr", {}).get("raw_text")
    if raw:
        (d / "ocr.txt").write_text(raw, encoding="utf-8")


def procesar_imagen(ruta, repo, guardar=True):
    """OCR (etapa 1) -> extraccion estructurada (etapa 2) -> conciliacion."""
    from ocr.engine import run_ocr           # import diferido: solo esta ruta usa el SDK
    from extract.structurer import extraer

    ruta = Path(ruta)
    contrato = nuevo_contrato(ruta.stem, str(ruta).replace("\\", "/"))
    contrato["ocr"] = run_ocr(str(ruta))
    contrato["extracted"] = extraer(contrato["ocr"].get("raw_text", ""))
    conciliar(contrato, repo, guardar=guardar)
    if guardar:
        _guardar_disco(contrato)
    return contrato


def main():
    ap = argparse.ArgumentParser(description="CONCILIA - conciliacion local de facturas")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--receipt", help="una imagen de recibo")
    g.add_argument("--batch", help="carpeta con recibos")
    g.add_argument("--from-json", dest="from_json",
                   help="contrato ya extraido (salta OCR e inferencia)")
    g.add_argument("--report", action="store_true", help="resumen desde MariaDB")
    ap.add_argument("--no-guardar", action="store_true",
                    help="no escribe en MariaDB ni en logs/runs")
    a = ap.parse_args()

    conn = get_connection()
    repo = Repositorio(conn)
    guardar = not a.no_guardar

    if a.report:
        terminal.tabla_resumen(repo.resumen_veredictos(), console,
                               "Veredictos (JSON_EXTRACT sobre conciliaciones)")
        terminal.tabla_resumen(repo.listar_conciliaciones(30), console,
                               "Ultimas conciliaciones")
        return 0

    if a.from_json:
        contrato = json.loads(Path(a.from_json).read_text(encoding="utf-8"))
        conciliar(contrato, repo, guardar=guardar)
        terminal.render(contrato, console)
        return 0

    if a.receipt:
        terminal.render(procesar_imagen(a.receipt, repo, guardar), console)
        return 0

    carpeta = Path(a.batch)
    imagenes = sorted(p for p in carpeta.iterdir()
                      if p.suffix.lower() in (".jpg", ".jpeg", ".png"))
    if not imagenes:
        console.print(f"[yellow]Sin imagenes en {carpeta}[/yellow]")
        return 1
    console.print(f"Procesando {len(imagenes)} recibos de {carpeta}\n")
    resumen = []
    for i, p in enumerate(imagenes, 1):
        console.print(f"[dim]({i}/{len(imagenes)})[/dim] {p.name}")
        try:
            c = procesar_imagen(p, repo, guardar)
        except Exception as e:
            console.print(f"  [red]fallo:[/red] {type(e).__name__}: {e}")
            continue
        terminal.render(c, console)
        resumen.append({"recibo": c["receipt_id"],
                        "veredicto": c["reconciliation"].get("verdict"),
                        "confianza": c.get("confidence_overall"),
                        "explicacion": (c["reconciliation"].get("explanation") or "")[:60]})
    terminal.tabla_resumen(resumen, console, "Corrida completa")
    return 0


if __name__ == "__main__":
    sys.exit(main())
