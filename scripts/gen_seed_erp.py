"""Agrega al ERP las ordenes de compra que corresponden al dataset real de 31 recibos.

    python scripts/gen_seed_erp.py

Es ADITIVO: conserva intacto el seed original (OC-101 a OC-135, ids 1-9), del que
dependen los tests del backend y el recorrido con el motor `stub`. Las ordenes del
dataset arrancan en el id 100 y en OC-200, asi que no hay colision posible.

Regenera el bloque cada vez que corre, asi que se puede ejecutar N veces sin duplicar.
Despues:  docker compose down -v && docker compose up -d

## Como se decide el veredicto esperado

El motor busca la orden por `supplier_tax_id`. Entonces:

  MATCH        se siembra una orden con el NIT del recibo y su total exacto
  MISMATCH     misma cosa, pero con el total alterado (transposicion, IVA 13%,
               decimal corrido) -> el delta lo calcula Python y la nota la redacta
               el modelo
  NO_PO_FOUND  no se siembra ninguna orden con ese NIT

## Una limitacion que se declara, no se disimula

Las cuatro facturas bolivianas (R028-R031) NO imprimen el NIT del emisor: el unico
NIT en el papel es el del cliente, y el del proveedor viaja dentro del codigo QR, que
el OCR no lee. Se siembra la orden contra el NIT que SI es legible, y queda anotado
en `docs/limitations.md`. Inventar un NIT que no esta en la imagen seria exactamente
la clase de trampa que este proyecto dice no hacer.
"""
import json
import re
import unicodedata
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
ANOTACIONES = RAIZ / "eval" / "annotations_raw.json"
SEED = RAIZ / "db" / "seed.sql"

MARCA_INICIO = "-- === DATASET CONCILIA (generado por scripts/gen_seed_erp.py) ==="
MARCA_FIN = "-- === FIN DATASET CONCILIA ==="

# Mismo reparto que eval/dataset_map.md, traducido a los veredictos del backend.
# R016 sale del grupo MATCH a proposito: comparte NIT con R015, que tiene que dar
# NO_PO_FOUND. Si se sembrara la orden de R016, el lookup por NIT tambien la
# encontraria para R015 y el caso "sin orden" desapareceria del dataset.
MATCH = ["R002", "R003", "R006", "R011", "R012", "R019", "R020", "R021",
         "R023", "R027", "R028"]
MISMATCH = {
    "R008": ("transposicion", 121.46),
    "R009": ("iva_13", 30.06),
    "R014": ("decimal_corrido", 3.27),
    "R017": ("transposicion", 68.00),
    "R018": ("iva_13", 61.59),
    "R022": ("decimal_corrido", 551.00),
    "R024": ("transposicion", 135.35),
    "R029": ("transposicion", 1360.20),
}
NO_PO = ["R015", "R016", "R025", "R026", "R030", "R031"]
TOLERANTES = ["R005", "R007", "R010", "R013"]   # par exacto; si el OCR falla -> UNCERTAIN

# NIT que el OCR puede leer de verdad en cada recibo. Para los bolivianos es el del
# cliente (ver el docstring); para el resto, el registro tributario del emisor.
NIT_CLIENTE_BOLIVIA = "5900398"


def esc(s):
    return str(s).replace("\\", "\\\\").replace("'", "''")


def ascii_plano(s):
    s = unicodedata.normalize("NFKD", str(s))
    return "".join(c for c in s if not unicodedata.combining(c))


def nit_de(reg):
    if reg["origen"] == "boliviano_real":
        return NIT_CLIENTE_BOLIVIA
    nit = (reg.get("nit") or "").strip()
    return nit or None


def veredicto_esperado(reg, ordenes):
    """Simula `db_tool.lookup_purchase_order` para saber que DEBE pasar con cada recibo.

    No se puede decidir el veredicto esperado a mano: el backend busca por NIT, y
    varios recibos comparten proveedor (TEO HENG aparece cinco veces, las cuatro
    facturas de Monopol comparten el mismo NIT legible). Si dos recibos del mismo
    proveedor caen en grupos distintos, la orden sembrada para uno la encuentra
    tambien el otro. Reproducir aqui la misma regla de desempate del backend -
    la orden de monto mas cercano, empate al id menor - es la unica forma de que
    el oraculo de la evaluacion no mienta.
    """
    nit = nit_de(reg)
    total = reg.get("total")
    if not nit or total is None:
        return "UNCERTAIN", None, "sin NIT o sin total legible en la imagen"
    candidatas = [o for o in ordenes if o["nit"] == nit]
    if not candidatas:
        return "NO_PO_FOUND", None, f"ninguna orden con el NIT {nit}"
    elegida = min(candidatas, key=lambda o: (abs(o["total"] - total), o["id"]))
    delta = round(total - elegida["total"], 2)
    if abs(delta) < 0.01:
        return "MATCH", elegida, "coincide con la orden sembrada"
    return "MISMATCH", elegida, f"delta {delta:+.2f} contra {elegida['po']}"


def _escribir_mapa(por_id, ordenes, sin_nit):
    filas, conteo = [], {}
    for rid in sorted(por_id):
        reg = por_id[rid]
        veredicto, orden, motivo = veredicto_esperado(reg, ordenes)
        conteo[veredicto] = conteo.get(veredicto, 0) + 1
        filas.append((rid, reg, veredicto, orden, motivo))

    M = ["# dataset_map_erp.md - oraculo de la evaluacion contra el ERP", "",
         "Generado por `scripts/gen_seed_erp.py`. **No se escribe a mano**: el veredicto",
         "esperado se obtiene simulando el mismo `lookup_purchase_order` del backend",
         "(busqueda por NIT, desempate por monto mas cercano). Decidirlo de memoria",
         "produciria expectativas falsas, porque varios recibos comparten proveedor.", "",
         "## Procedencia", "",
         "- 4 facturas bolivianas reales (Pinturas Monopol Ltda., Santa Cruz).",
         "- 27 tickets del corpus publico SROIE (comercios de Malasia, en MYR).",
         "  Aportan la suciedad real que el track exige: termicos descoloridos, sombras",
         "  de escaneo, sellos superpuestos, arrugas y anotaciones manuscritas.", "",
         "## Distribucion esperada", "",
         "| Veredicto | Recibos |", "|---|---|"]
    for v in ("MATCH", "MISMATCH", "NO_PO_FOUND", "UNCERTAIN"):
        if v in conteo:
            M.append(f"| `{v}` | {conteo[v]} |")
    M += ["", f"Total: {len(filas)} recibos, {len(ordenes)} ordenes sembradas.", "",
          "## Detalle", "",
          "| Recibo | Proveedor | NIT legible | Total factura | Orden | Total orden | "
          "Esperado | Por que |",
          "|---|---|---|---|---|---|---|---|"]
    for rid, reg, veredicto, orden, motivo in filas:
        M.append(
            f"| {rid} | {ascii_plano(reg['vendor'])} | {nit_de(reg) or '-'} | "
            f"{reg['total'] if reg['total'] is not None else '-'} | "
            f"{orden['po'] if orden else '-'} | "
            f"{('%.2f' % orden['total']) if orden else '-'} | "
            f"`{veredicto}` | {motivo} |")
    if sin_nit:
        M += ["", f"Sin orden sembrada por no tener NIT legible: {', '.join(sin_nit)}. "
                  "Inventar un NIT que no esta en la imagen seria la clase de trampa "
                  "que este proyecto dice no hacer."]
    M.append("")
    (RAIZ / "eval" / "dataset_map_erp.md").write_text("\n".join(M), encoding="utf-8")
    return conteo


def main():
    datos = json.loads(ANOTACIONES.read_text(encoding="utf-8"))
    por_id = {d["receipt_id"]: d for d in datos}

    ordenes, lineas, sin_nit, omitidos = [], [], [], []
    po_id, numero = 100, 200

    for rid in MATCH + TOLERANTES + list(MISMATCH):
        reg = por_id[rid]
        nit = nit_de(reg)
        if not nit:
            # Sin NIT legible no hay contra que buscar. Se omite y se declara:
            # sembrar una orden con un NIT inventado seria hacer trampa.
            sin_nit.append(rid)
            continue
        if rid in MISMATCH:
            tipo, total = MISMATCH[rid]
            nota = f"{rid} - total alterado ({tipo}); factura cobra {reg['total']:.2f}"
        else:
            total, tipo = reg["total"], "exacto"
            nota = f"{rid} - par exacto"
        ordenes.append({
            "id": po_id, "po": f"OC-{numero}", "nit": nit,
            "proveedor": ascii_plano(reg["vendor"])[:160],
            "moneda": reg["currency"] or "BOB", "total": round(total, 2),
            "estado": "OPEN", "fecha": reg["date"] or "2026-01-01", "nota": nota,
        })
        lineas.append({
            "po_id": po_id,
            "desc": f"Compra segun comprobante {rid}",
            "cantidad": 1.0, "precio": round(total, 2), "total": round(total, 2),
        })
        po_id += 1
        numero += 1

    for rid in NO_PO:
        omitidos.append(f"{rid} ({por_id[rid]['vendor']})")

    L = [MARCA_INICIO,
         "-- No editar a mano: regenerar con scripts/gen_seed_erp.py.",
         f"-- {len(ordenes)} ordenes contra los recibos reales de data/receipts/.",
         f"-- Sin orden a proposito (NO_PO_FOUND esperado): {', '.join(omitidos)}."]
    if sin_nit:
        L.append(f"-- Omitidos por no tener NIT legible en la imagen: {', '.join(sin_nit)}.")
    L += ["",
          "INSERT INTO purchase_orders",
          "    (id, po_number, supplier_tax_id, supplier_name, currency, total_amount, "
          "status, issued_at) VALUES"]
    for i, o in enumerate(ordenes):
        # El separador va ANTES del comentario: un `-- ...` se come todo lo que
        # venga despues en la linea, coma incluida.
        fin = ";" if i == len(ordenes) - 1 else ","
        L.append(f"    ({o['id']}, '{o['po']}', '{esc(o['nit'])}', "
                 f"'{esc(o['proveedor'])}', '{o['moneda']}', {o['total']:.2f}, "
                 f"'{o['estado']}', '{o['fecha']}'){fin}  -- {o['nota']}")
    L += ["",
          "INSERT INTO po_line_items (po_id, description, quantity, unit_price, "
          "line_total) VALUES"]
    filas = [f"    ({x['po_id']}, '{esc(x['desc'])}', {x['cantidad']:.3f}, "
             f"{x['precio']:.2f}, {x['total']:.2f})" for x in lineas]
    L.append(",\n".join(filas) + ";")
    L += ["", MARCA_FIN, ""]
    bloque = "\n".join(L)

    _escribir_mapa(por_id, ordenes, sin_nit)

    actual = SEED.read_text(encoding="utf-8")
    patron = re.compile(re.escape(MARCA_INICIO) + r".*?" + re.escape(MARCA_FIN) + r"\n?",
                        re.S)
    nuevo = (patron.sub(bloque, actual) if MARCA_INICIO in actual
             else actual.rstrip() + "\n\n" + bloque)
    SEED.write_text(nuevo, encoding="utf-8")

    print(f"ordenes agregadas : {len(ordenes)}  (ids 100-{po_id - 1})")
    print(f"sin orden a proposito (NO_PO_FOUND): {len(NO_PO)}")
    if sin_nit:
        print(f"omitidos por falta de NIT legible: {', '.join(sin_nit)}")
    print(f"escrito en {SEED}")
    print("\nAplicar:  docker compose down -v && docker compose up -d")


if __name__ == "__main__":
    main()
