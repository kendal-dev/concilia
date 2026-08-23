"""Runner de evaluacion: compara los contratos de una corrida contra el ground truth
y emite el markdown de RESULTS.md. Nadie llena esas tablas a mano.

    python eval/runner.py                      # lee logs/runs/*.json
    python eval/runner.py --salida RESULTS.md

Oraculo: `eval/ground_truth.json` (campo `veredicto_esperado`, generado desde
`eval/dataset_map.md` por scripts/gen_dataset.py).

Convencion de la evaluacion, declarada aqui para que sea auditable:
  - Un campo cuenta CORRECTO si coincide con el ground truth; UNCERTAIN si el sistema
    devolvio null; INCORRECTO si devolvio un valor distinto. Devolver null NO se
    computa como error: el track premia decir "no se" antes que inventar.
  - Un veredicto esperado "MATCH|UNCERTAIN" acepta cualquiera de los dos.
"""
import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


def cargar_contratos(directorio):
    contratos = {}
    for p in sorted(Path(directorio).rglob("*.json")):
        try:
            c = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if isinstance(c, dict) and c.get("receipt_id"):
            contratos[c["receipt_id"]] = c
    return contratos


def _v(campo):
    return campo.get("value") if isinstance(campo, dict) else campo


def comparar_campo(obtenido, esperado, tolerancia=None):
    if obtenido is None:
        return "uncertain"
    if tolerancia is not None:
        try:
            return "correcto" if abs(float(obtenido) - float(esperado)) <= tolerancia \
                else "incorrecto"
        except (TypeError, ValueError):
            return "incorrecto"
    a = str(obtenido).strip().lower()
    b = str(esperado).strip().lower()
    return "correcto" if a == b else "incorrecto"


def evaluar(gt, contratos):
    campos = {"vendor": Counter(), "date": Counter(), "total": Counter()}
    veredictos = defaultdict(Counter)
    por_condicion = defaultdict(Counter)
    latencias = []
    faltantes = []
    detalle = []

    for g in gt:
        rid = g["receipt_id"]
        c = contratos.get(rid)
        if not c:
            faltantes.append(rid)
            continue
        ext = c.get("extracted", {})
        res = {
            "vendor": comparar_campo(_v(ext.get("vendor")), g["vendor"]),
            "date": comparar_campo(_v(ext.get("date")), g["date"]),
            "total": comparar_campo(_v(ext.get("total")), g["total"], tolerancia=0.01),
        }
        for k, v in res.items():
            campos[k][v] += 1

        esperado = g["veredicto_esperado"]
        obtenido = c.get("reconciliation", {}).get("verdict")
        acierto = obtenido in esperado.split("|")
        veredictos[esperado]["total"] += 1
        veredictos[esperado]["ok" if acierto else "error"] += 1

        for cond in (g.get("condicion") or ["sin_clasificar"]):
            por_condicion[cond]["total"] += 1
            por_condicion[cond]["ok" if acierto else "error"] += 1

        if isinstance(c.get("latency_s"), (int, float)):
            latencias.append(float(c["latency_s"]))

        detalle.append({
            "receipt_id": rid, "esperado": esperado, "obtenido": obtenido,
            "acierto": acierto, "confianza": c.get("confidence_overall"),
            "campos": res, "origen": g.get("origen"),
        })

    return {"campos": campos, "veredictos": veredictos, "por_condicion": por_condicion,
            "latencias": sorted(latencias), "faltantes": faltantes, "detalle": detalle}


def percentil(valores, p):
    if not valores:
        return None
    k = max(0, min(len(valores) - 1, int(round((p / 100) * (len(valores) - 1)))))
    return valores[k]


def markdown(r, n_total, modelo="(modelo)"):
    L = [f"# Resultados - {n_total} recibos reales · {modelo}", ""]
    if r["faltantes"]:
        L += [f"> Sin contrato en esta corrida: {', '.join(r['faltantes'])}", ""]

    L += ["## Extraccion por campo", "",
          "| Campo | Correcto | Incorrecto | UNCERTAIN |", "|---|---|---|---|"]
    etiquetas = {"vendor": "Proveedor", "date": "Fecha", "total": "Total"}
    for k, c in r["campos"].items():
        n = sum(c.values())
        L.append(f"| {etiquetas[k]} | {c['correcto']}/{n} | {c['incorrecto']} | "
                 f"{c['uncertain']} |")

    L += ["", "## Conciliacion (veredicto esperado segun dataset_map.md)", "",
          "| Veredicto esperado | Correctos | Errores |", "|---|---|---|"]
    for esperado, c in sorted(r["veredictos"].items()):
        L.append(f"| {esperado} ({c['total']}) | {c['ok']}/{c['total']} | {c['error']} |")

    L += ["", "## Por condicion fisica del recibo", "",
          "| Condicion | Aciertos |", "|---|---|"]
    for cond, c in sorted(r["por_condicion"].items(), key=lambda x: -x[1]["total"]):
        pct = 100 * c["ok"] / c["total"] if c["total"] else 0
        L.append(f"| {cond} | {c['ok']}/{c['total']} ({pct:.0f}%) |")

    lat = r["latencias"]
    L += ["", "## Latencia", "", "| Metrica | Valor |", "|---|---|"]
    if lat:
        L.append(f"| Mediana por recibo | {percentil(lat, 50):.2f} s |")
        L.append(f"| P95 | {percentil(lat, 95):.2f} s |")
        L.append(f"| Maxima | {lat[-1]:.2f} s |")
    else:
        L.append("| - | sin datos |")

    L += ["", "## Detalle por recibo", "",
          "| Recibo | Origen | Esperado | Obtenido | Confianza | Proveedor | Fecha | Total |",
          "|---|---|---|---|---|---|---|---|"]
    for d in r["detalle"]:
        marca = "" if d["acierto"] else " ⟵"
        conf = f"{d['confianza']:.2f}" if isinstance(d["confianza"], (int, float)) else "-"
        L.append(f"| {d['receipt_id']} | {d['origen']} | `{d['esperado']}` | "
                 f"`{d['obtenido']}`{marca} | {conf} | {d['campos']['vendor']} | "
                 f"{d['campos']['date']} | {d['campos']['total']} |")
    L += ["", "> Un `UNCERTAIN` en un recibo ilegible no es un fallo: es el sistema "
          "funcionando. La convencion de conteo esta declarada en `eval/runner.py`.", ""]
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description="Evalua una corrida contra el ground truth")
    ap.add_argument("--runs", default=str(RAIZ / "logs" / "runs"))
    ap.add_argument("--gt", default=str(RAIZ / "eval" / "ground_truth.json"))
    ap.add_argument("--salida", default=str(RAIZ / "RESULTS.md"))
    ap.add_argument("--modelo", default="crnn_mobilenet_v3_small + Qwen3.5-4B Q4_K_M")
    a = ap.parse_args()

    gt = json.loads(Path(a.gt).read_text(encoding="utf-8"))
    contratos = cargar_contratos(a.runs)
    if not contratos:
        print(f"No hay contratos en {a.runs}. Corre primero: python main.py --batch "
              f"data/receipts/")
        return 1
    r = evaluar(gt, contratos)
    md = markdown(r, len(gt), a.modelo)
    Path(a.salida).write_text(md, encoding="utf-8")
    print(md)
    print(f"\nEscrito en {a.salida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
