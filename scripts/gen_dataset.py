"""Genera eval/ground_truth.json, eval/dataset_map.md y db/seed.sql desde eval/annotations_raw.json.

    python scripts/gen_dataset.py

annotations_raw.json es la anotacion manual (ground truth crudo) de los 31 recibos.
Los tres archivos generados deben moverse SIEMPRE juntos: el runner de evaluacion usa
dataset_map.md como oraculo y el seed tiene que coincidir con el, o los numeros divergen.
Tras regenerar el seed:  docker compose down -v && docker compose up -d
"""
import json
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GT = json.loads((ROOT / "eval" / "annotations_raw.json").read_text(encoding="utf-8"))


def normalizar(s):
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.split())


def esc(s):
    return s.replace("\\", "\\\\").replace("'", "''")


# ---------- roles ----------
MATCH = ["R002", "R003", "R005", "R006", "R011", "R012", "R013", "R016",
         "R019", "R020", "R021", "R023", "R027", "R028"]
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
NO_MATCH = ["R015", "R025", "R026", "R030", "R031"]
UNCERTAIN_TOL = ["R001", "R004", "R007", "R010"]

por_id = {g["receipt_id"]: g for g in GT}
assert len(MATCH) + len(MISMATCH) + len(NO_MATCH) + len(UNCERTAIN_TOL) == len(GT), "reparto incompleto"

CATEGORIA = {
    "ferreteria": ["HARDWARE", "MACHINERY", "D.I.Y", "KHOO", "AIK HUAT", "MONOPOL",
                   "FERRETERIA"],
    "papeleria": ["STATIONERY", "TEO HENG"],
    "alimentos": ["RESTORAN", "ROASTED", "ASIA MART", "SPEED MART", "GERBANG",
                  "FUYI", "PANADERIA"],
    "combustible": ["SHELL", "MOTOR"],
}


def categoria(vendor):
    v = vendor.upper()
    for cat, claves in CATEGORIA.items():
        if any(k in v for k in claves):
            return cat
    return "varios"


# ---------- proveedores ----------
vendors = []
for g in GT:
    if g["vendor"] not in vendors:
        vendors.append(g["vendor"])
EXTRA = ["Distribuidora El Trompillo", "Ferreteria San Martin", "Panaderia La Espiga"]
for e in EXTRA:
    vendors.append(e)
prov_id = {v: i + 1 for i, v in enumerate(vendors)}
nit_de = {}
for g in GT:
    if g.get("nit") and g["vendor"] not in nit_de:
        nit_de[g["vendor"]] = g["nit"]

# ---------- gastos ----------
gastos = []  # (proveedor, fecha, monto, categoria, descripcion, receipt_ref)


def add(vendor, fecha, monto, desc, ref=None):
    gastos.append({"vendor": vendor, "fecha": fecha, "monto": round(monto, 2),
                   "categoria": categoria(vendor), "descripcion": desc, "ref": ref})


for rid in MATCH + UNCERTAIN_TOL:
    g = por_id[rid]
    add(g["vendor"], g["date"], g["total"], f"Compra segun comprobante {rid}", rid)

for rid, (tipo, monto_alt) in MISMATCH.items():
    g = por_id[rid]
    add(g["vendor"], g["date"], monto_alt,
        f"Compra segun comprobante {rid} (libro con {tipo})", rid)

# duplicados: mismo proveedor/fecha/monto que dos registros existentes
for rid in ("R003", "R020"):
    g = por_id[rid]
    add(g["vendor"], g["date"], g["total"], f"Cargo repetido del comprobante {rid}", None)

# ruido: gastos legitimos sin recibo
RUIDO = [
    ("TEO HENG STATIONERY & BOOKS", "2018-01-30", 62.40, "Resma papel bond"),
    ("TEO HENG STATIONERY & BOOKS", "2018-02-20", 19.80, "Marcadores permanentes"),
    ("MR D.I.Y. (JOHOR) SDN BHD", "2019-01-28", 45.60, "Focos LED de repuesto"),
    ("ASIA MART", "2017-12-30", 88.15, "Abarrotes fin de mes"),
    ("SAM SAM TRADING CO", "2018-01-05", 22.30, "Pegamento y cinta"),
    ("HOME MASTER HARDWARE & ELECTRICAL", "2018-01-09", 74.25, "Cable dos hilos"),
    ("99 SPEED MART S/B", "2018-02-02", 13.75, "Insumos de limpieza"),
    ("Distribuidora El Trompillo", "2026-03-04", 1240.00, "Pintura latex 20L"),
    ("Distribuidora El Trompillo", "2026-06-18", 430.50, "Solvente y brochas"),
    ("Ferreteria San Martin", "2026-04-09", 275.00, "Herramienta menor"),
    ("Ferreteria San Martin", "2026-07-02", 918.60, "Andamio alquilado"),
    ("Panaderia La Espiga", "2026-05-15", 85.00, "Refrigerio de obra"),
    ("Pinturas Monopol Ltda.", "2026-03-27", 512.40, "Compra sin comprobante archivado"),
    ("Pinturas Monopol Ltda.", "2026-08-05", 1105.00, "Pedido a cuenta"),
]
for v, f, m, d in RUIDO:
    add(v, f, m, d)

# ---------- ground_truth.json ----------
gt_final = []
for g in GT:
    rid = g["receipt_id"]
    if rid in MATCH:
        esperado, nota = "MATCH", "par exacto en el libro"
    elif rid in MISMATCH:
        esperado, nota = "MISMATCH", f"libro alterado por {MISMATCH[rid][0]}"
    elif rid in NO_MATCH:
        esperado, nota = "NO_MATCH", "sin registro en el libro"
    else:
        esperado, nota = "MATCH|UNCERTAIN", "calidad degradada: UNCERTAIN tambien es acierto"
    gt_final.append({
        "receipt_id": rid,
        "source_image": f"data/receipts/{rid}.jpg",
        "vendor": g["vendor"],
        "nit": g["nit"],
        "date": g["date"],
        "total": g["total"],
        "currency": g["currency"],
        "n_items": g["n_items"],
        "doc_type": g["doc_type"],
        "condicion": g["condicion"],
        "legible_humano": g["legible_humano"],
        "origen": g["origen"],
        "veredicto_esperado": esperado,
        "nota_evaluacion": nota,
        "notas_anotador": g["notas"],
    })
(ROOT / "eval" / "ground_truth.json").write_text(
    json.dumps(gt_final, indent=2, ensure_ascii=False), encoding="utf-8")

# ---------- seed.sql ----------
L = []
L.append("-- seed.sql - libro de gastos esperados de CONCILIA")
L.append("-- GENERADO por scripts/gen_dataset.py desde eval/ground_truth.json + eval/dataset_map.md")
L.append("-- No editar a mano: regenerar. El seed y el ground truth deben moverse juntos.")
L.append("")
L.append("INSERT INTO proveedores (id, nombre, nombre_norm, nit) VALUES")
filas = []
for v in vendors:
    filas.append(f"  ({prov_id[v]}, '{esc(v)}', '{esc(normalizar(v))}', "
                 + (f"'{esc(nit_de[v])}')" if v in nit_de else "NULL)"))
L.append(",\n".join(filas) + ";")
L.append("")
L.append("INSERT INTO gastos_esperados (proveedor_id, fecha, monto, categoria, descripcion) VALUES")
filas = []
for g in gastos:
    filas.append(f"  ({prov_id[g['vendor']]}, '{g['fecha']}', {g['monto']:.2f}, "
                 f"'{g['categoria']}', '{esc(g['descripcion'])}')")
L.append(",\n".join(filas) + ";")
L.append("")
(ROOT / "db" / "seed.sql").write_text("\n".join(L), encoding="utf-8")

# ---------- dataset_map.md ----------
M = []
M.append("# dataset_map.md - contrato entre el dataset y el libro de gastos")
M.append("")
M.append("Fuente unica de verdad para el runner de evaluacion (`eval/runner.py`).")
M.append("Generado por `scripts/gen_dataset.py`. Si cambia el dataset, se regenera todo junto:")
M.append("`ground_truth.json`, `seed.sql` y esta tabla.")
M.append("")
M.append("## Procedencia del dataset")
M.append("")
n_bo = sum(1 for g in GT if g["origen"] == "boliviano_real")
M.append(f"- **{n_bo} facturas bolivianas reales** (Pinturas Monopol Ltda., Santa Cruz, Bs, fotos giradas 90 grados).")
M.append(f"- **{len(GT) - n_bo} tickets del corpus publico SROIE** (recibos escaneados de comercios de Malasia, en MYR).")
M.append("  Aportan suciedad real: termicos descoloridos, sombras de escaneo, sellos superpuestos,")
M.append("  arrugas y anotaciones manuscritas. **Esta procedencia se declara en el README y en")
M.append("  `docs/limitations.md`** - el sistema no afirma haberlos recolectado en Bolivia.")
M.append("")
M.append("## Reparto de veredictos")
M.append("")
M.append("| Recibos | Cantidad | Veredicto esperado | Como se planta |")
M.append("|---|---|---|---|")
M.append(f"| {', '.join(MATCH)} | {len(MATCH)} | `MATCH` | par exacto proveedor+fecha+monto |")
M.append(f"| {', '.join(MISMATCH)} | {len(MISMATCH)} | `MISMATCH` | monto alterado en el libro |")
M.append(f"| {', '.join(NO_MATCH)} | {len(NO_MATCH)} | `NO_MATCH` | sin registro en el libro |")
M.append(f"| {', '.join(UNCERTAIN_TOL)} | {len(UNCERTAIN_TOL)} | `MATCH` o `UNCERTAIN` | par exacto, pero imagen degradada: si el OCR no lee, `UNCERTAIN` cuenta como acierto |")
M.append("")
M.append(f"Total: {len(GT)} recibos. Libro (`gastos_esperados`): {len(gastos)} registros, "
         f"{len(vendors)} proveedores.")
M.append("")
M.append("## Alteraciones plantadas en los MISMATCH")
M.append("")
M.append("| Recibo | Real | Libro | Patron | Explicacion que debe generar |")
M.append("|---|---|---|---|---|")
EXPL = {
    "transposicion": "digitos transpuestos",
    "iva_13": "diferencia de ~13% (IVA no registrado)",
    "decimal_corrido": "corrimiento de decimal (~10x)",
}
for rid, (tipo, alt) in MISMATCH.items():
    real = por_id[rid]["total"]
    M.append(f"| {rid} | {real:.2f} | {alt:.2f} | `{tipo}` | {EXPL[tipo]} |")
M.append("")
M.append("## Casos extra plantados en el libro")
M.append("")
M.append("- **2 duplicados**: copia exacta (proveedor+fecha+monto) de los registros de R003 y R020")
M.append("  -> debe dispararse la deteccion de cargo duplicado.")
M.append(f"- **{len(RUIDO)} registros de ruido**: gastos legitimos sin recibo asociado. Evitan que")
M.append("  `NO_MATCH` sea trivial y obligan al fuzzy de proveedor a discriminar de verdad.")
M.append("")
M.append("## Tabla completa recibo -> esperado")
M.append("")
M.append("| Recibo | Proveedor | Fecha | Total | Moneda | Condicion | Origen | Esperado |")
M.append("|---|---|---|---|---|---|---|---|")
for g in gt_final:
    M.append(f"| {g['receipt_id']} | {g['vendor']} | {g['date']} | {g['total']:.2f} | "
             f"{g['currency']} | {', '.join(g['condicion'])} | {g['origen']} | "
             f"`{g['veredicto_esperado']}` |")
M.append("")
(ROOT / "eval" / "dataset_map.md").write_text("\n".join(M), encoding="utf-8")

print("recibos:", len(GT))
print("proveedores:", len(vendors))
print("gastos_esperados:", len(gastos))
print("MATCH", len(MATCH), "MISMATCH", len(MISMATCH), "NO_MATCH", len(NO_MATCH), "UNC", len(UNCERTAIN_TOL))
