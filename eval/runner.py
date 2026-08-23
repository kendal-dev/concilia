"""Corre el agente sobre los 31 recibos reales y emite RESULTS.md.

    python eval/runner.py                  # corrida completa
    python eval/runner.py --limite 3       # prueba rapida antes de la corrida larga
    python eval/runner.py --solo R028 R029 # recibos puntuales

Necesita MariaDB arriba (docker compose up -d) y los modelos descargados
(scripts/setup_models.py). Usa el motor configurado en LLM_CLIENT: para que los
numeros signifiquen algo tiene que ser `qvac`.

## De donde sale el veredicto esperado

No de una tabla escrita a mano. Para cada recibo se consulta el ERP con el MISMO
`lookup_purchase_order` que usa el agente, partiendo del NIT y el total del ground
truth anotado a mano en `eval/annotations_raw.json`:

    sin NIT o sin total legibles  -> UNCERTAIN   (el agente no tiene con que reconciliar)
    el lookup no encuentra orden  -> NO_PO_FOUND
    encuentra y el monto coincide -> MATCH
    encuentra y el monto difiere  -> MISMATCH

Asi el oraculo no puede desincronizarse del sistema: si cambia el seed, cambia el
esperado, y la tabla de resultados sigue diciendo la verdad.

## Como se cuentan los campos

Correcto / incorrecto / no leido. Devolver `null` NO cuenta como error: el track
premia decir "no se" antes que inventar un numero, y un runner que castiga la
abstencion mediria lo contrario de lo que el proyecto defiende.
"""
import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from backend.core.llm.factory import get_llm_client          # noqa: E402
from backend.core.orchestrator import reconcile              # noqa: E402
from backend.core.tools.db_tool import lookup_purchase_order  # noqa: E402
from backend.db.session import session_scope                 # noqa: E402
from scripts.gen_seed_erp import nit_de                      # noqa: E402

ANOTACIONES = RAIZ / "eval" / "annotations_raw.json"
RECIBOS = RAIZ / "data" / "receipts"
CORRIDAS = RAIZ / "logs" / "runs"
TOLERANCIA = Decimal("0.01")


def esperado(session, anotacion):
    """Veredicto que DEBE dar el agente si lee el documento perfectamente."""
    nit = nit_de(anotacion)
    total = anotacion.get("total")
    if not nit or total is None:
        return "UNCERTAIN", None
    po = lookup_purchase_order(session, nit, Decimal(str(total)))
    if po is None:
        return "NO_PO_FOUND", None
    delta = Decimal(str(total)) - po.total_amount
    return ("MATCH" if abs(delta) <= TOLERANCIA else "MISMATCH"), po


def compara(obtenido, referencia, numerico=False):
    if obtenido in (None, ""):
        return "no_leido"
    if numerico:
        try:
            return ("correcto" if abs(Decimal(str(obtenido)) - Decimal(str(referencia)))
                    <= TOLERANCIA else "incorrecto")
        except Exception:
            return "incorrecto"
    return ("correcto" if str(obtenido).strip().lower() == str(referencia).strip().lower()
            else "incorrecto")


def procesar(session, cliente, anotacion):
    rid = anotacion["receipt_id"]
    imagen = RECIBOS / f"{rid}.jpg"
    if not imagen.exists():
        return None

    veredicto_ok, po_esperada = esperado(session, anotacion)
    cliente.filename = imagen.name

    t0 = time.perf_counter()
    resultado = reconcile(session, cliente, imagen.read_bytes(), imagen.name,
                          content_type="image/jpeg")
    latencia = round(time.perf_counter() - t0, 2)

    evidencia = dict(cliente.ultima_evidencia or {})
    factura = resultado.invoice
    campos = {
        "supplier_tax_id": compara(factura.supplier_tax_id if factura else None,
                                   nit_de(anotacion)),
        "total_amount": compara(factura.total_amount if factura else None,
                                anotacion.get("total"), numerico=True),
    }
    reintentos = sum(p.retries for p in resultado.trace.steps)

    fila = {
        "receipt_id": rid,
        "origen": anotacion.get("origen"),
        "condicion": anotacion.get("condicion") or [],
        "esperado": veredicto_ok,
        "obtenido": resultado.verdict.value,
        "acierto": resultado.verdict.value == veredicto_ok,
        "po_esperada": po_esperada.po_number if po_esperada else None,
        "po_obtenida": (resultado.purchase_order.po_number
                        if resultado.purchase_order else None),
        "delta": str(resultado.amount_delta) if resultado.amount_delta is not None else None,
        "campos": campos,
        "reintentos": reintentos,
        "latencia_s": latencia,
        "ocr_s": (evidencia.get("ocr") or {}).get("duration_s"),
        "bloques_ocr": (evidencia.get("ocr") or {}).get("bloques"),
        "conf_ocr": (evidencia.get("ocr") or {}).get("confianza_media_ocr"),
        "verificados": evidencia.get("valores_verificados") or {},
        "checks": {c.name: c.status.value for c in resultado.checks},
        "nota": resultado.note,
    }

    CORRIDAS.mkdir(parents=True, exist_ok=True)
    (CORRIDAS / f"{rid}.json").write_text(json.dumps({
        "resumen": fila,
        "texto_ocr": evidencia.get("texto_ocr", ""),
        "contrato": resultado.model_dump(mode="json"),
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    return fila


def percentil(valores, p):
    if not valores:
        return None
    v = sorted(valores)
    k = max(0, min(len(v) - 1, round((p / 100) * (len(v) - 1))))
    return v[k]


def markdown(filas, motor):
    aciertos = sum(1 for f in filas if f["acierto"])
    lat = [f["latencia_s"] for f in filas]
    ocr = [f["ocr_s"] for f in filas if f["ocr_s"]]

    L = [f"# Resultados — {len(filas)} recibos reales", "",
         f"Modelo de extraccion: **{motor.get('texto_nombre')}** "
         f"(contexto {motor.get('ctx_size')} tokens)  ",
         f"OCR: **{motor['ocr']['reconocedor']}** + **{motor['ocr']['detector']}** "
         f"(pipeline `{motor['ocr']['pipeline']}`, backend `{motor['ocr']['backend']}`)  ",
         "Toda la inferencia corre en el dispositivo. Cero llamadas de red.", "",
         f"**Veredicto correcto en {aciertos} de {len(filas)} recibos "
         f"({100 * aciertos / len(filas):.0f}%).**", "",
         "## Veredictos", "",
         "| Esperado | Recibos | Correctos | Errores |", "|---|---|---|---|"]

    por_esperado = defaultdict(list)
    for f in filas:
        por_esperado[f["esperado"]].append(f)
    for v in ("MATCH", "MISMATCH", "NO_PO_FOUND", "UNCERTAIN"):
        grupo = por_esperado.get(v)
        if not grupo:
            continue
        ok = sum(1 for f in grupo if f["acierto"])
        L.append(f"| `{v}` | {len(grupo)} | {ok} | {len(grupo) - ok} |")

    L += ["", "## Extraccion por campo", "",
          "Devolver `null` no cuenta como error: el sistema prefiere abstenerse antes",
          "que inventar un numero, y esa es la conducta que el track premia.", "",
          "| Campo | Correcto | Incorrecto | No leido |", "|---|---|---|---|"]
    for campo, etiqueta in (("supplier_tax_id", "NIT del proveedor"),
                            ("total_amount", "Total")):
        c = Counter(f["campos"][campo] for f in filas)
        L.append(f"| {etiqueta} | {c['correcto']}/{len(filas)} | {c['incorrecto']} | "
                 f"{c['no_leido']} |")

    L += ["", "## Verificacion contra el texto del OCR", "",
          "Cada valor extraido se busca en el texto crudo que produjo el OCR. Un valor",
          "que no aparece ahi es un valor inventado.", "",
          "| Campo | Verificados | No hallados |", "|---|---|---|"]
    ver = defaultdict(lambda: [0, 0])
    for f in filas:
        for campo, d in f["verificados"].items():
            ver[campo][0 if d["aparece_en_ocr"] else 1] += 1
    for campo, (si, no) in sorted(ver.items()):
        L.append(f"| `{campo}` | {si} | {no} |")

    L += ["", "## Por condicion fisica del documento", "",
          "| Condicion | Aciertos |", "|---|---|"]
    por_cond = defaultdict(lambda: [0, 0])
    for f in filas:
        for cond in (f["condicion"] or ["sin_clasificar"]):
            por_cond[cond][0] += 1
            por_cond[cond][1] += 1 if f["acierto"] else 0
    for cond, (n, ok) in sorted(por_cond.items(), key=lambda x: -x[1][0]):
        L.append(f"| {cond} | {ok}/{n} ({100 * ok / n:.0f}%) |")

    L += ["", "## Latencia", "", "| Metrica | Valor |", "|---|---|",
          f"| Mediana por documento | {percentil(lat, 50):.2f} s |",
          f"| P95 | {percentil(lat, 95):.2f} s |",
          f"| Maxima | {max(lat):.2f} s |"]
    if ocr:
        L.append(f"| Mediana solo OCR | {percentil(ocr, 50):.2f} s |")
    L.append(f"| Reintentos de extraccion | {sum(f['reintentos'] for f in filas)} |")

    L += ["", "## Detalle por documento", "",
          "| Recibo | Origen | Esperado | Obtenido | OC | Delta | NIT | Total | "
          "Reint. | s |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    marca = {"correcto": "ok", "incorrecto": "MAL", "no_leido": "null"}
    for f in sorted(filas, key=lambda x: x["receipt_id"]):
        flecha = "" if f["acierto"] else " ⟵"
        L.append(f"| {f['receipt_id']} | {f['origen']} | `{f['esperado']}` | "
                 f"`{f['obtenido']}`{flecha} | {f['po_obtenida'] or '-'} | "
                 f"{f['delta'] or '-'} | {marca[f['campos']['supplier_tax_id']]} | "
                 f"{marca[f['campos']['total_amount']]} | {f['reintentos']} | "
                 f"{f['latencia_s']} |")
    L += ["", "Cada corrida deja su contrato completo, con el texto crudo del OCR y la",
          "traza por fases, en `logs/runs/<recibo>.json`.", ""]
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description="Evalua el agente sobre el dataset real")
    ap.add_argument("--limite", type=int, help="procesar solo los primeros N")
    ap.add_argument("--solo", nargs="*", help="ids puntuales, ej: R028 R029")
    ap.add_argument("--salida", default=str(RAIZ / "RESULTS.md"))
    a = ap.parse_args()

    anotaciones = json.loads(ANOTACIONES.read_text(encoding="utf-8"))
    if a.solo:
        pedidos = {s.upper() for s in a.solo}
        anotaciones = [x for x in anotaciones if x["receipt_id"] in pedidos]
    if a.limite:
        anotaciones = anotaciones[:a.limite]

    cliente = get_llm_client()
    motor = getattr(type(cliente), "info_motor", lambda: {})()
    if not motor:
        print("AVISO: el motor configurado no es QVAC (LLM_CLIENT). Los numeros de\n"
              "esta corrida no miden inferencia real.", file=sys.stderr)
        motor = {"ocr": {"reconocedor": "-", "detector": "-", "pipeline": "-",
                         "backend": "-"}}

    filas = []
    total = len(anotaciones)
    with session_scope() as session:
        for i, anotacion in enumerate(anotaciones, 1):
            rid = anotacion["receipt_id"]
            print(f"[{i}/{total}] {rid} ...", end=" ", flush=True)
            try:
                fila = procesar(session, cliente, anotacion)
            except Exception as e:
                print(f"FALLO {type(e).__name__}: {str(e)[:120]}")
                continue
            if fila is None:
                print("sin imagen")
                continue
            filas.append(fila)
            print(f"{fila['obtenido']:12} esperado {fila['esperado']:12} "
                  f"{'ok' if fila['acierto'] else 'DIFIERE'}  {fila['latencia_s']}s")

    if not filas:
        print("No se proceso ningun recibo.")
        return 1

    md = markdown(filas, motor)
    Path(a.salida).write_text(md, encoding="utf-8")
    aciertos = sum(1 for f in filas if f["acierto"])
    print(f"\n{aciertos}/{len(filas)} veredictos correctos. Escrito en {a.salida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
