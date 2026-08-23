"""Vista de auditoria en terminal. Reemplaza al frontend a proposito.

El track evalua el agente, no la UI. Y lo que el track SI exige - *"it shows its
reasoning so a human can audit it"* - es exactamente esta pantalla: el texto crudo del
OCR con el `source_span` resaltado encima, al lado de lo que el modelo extrajo y de lo
que dice el libro.

Todo lo que se imprime sale del contrato JSON. La vista es una proyeccion, sin logica
propia: si algo no esta en el contrato, no se muestra.
"""
from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

COLOR = {
    "MATCH": "green",
    "MISMATCH": "yellow",
    "NO_MATCH": "yellow",
    "UNCERTAIN": "cyan",   # nunca rojo: no es un error, es el sistema funcionando
}
ICONO = {"MATCH": "OK", "MISMATCH": "!", "NO_MATCH": "!", "UNCERTAIN": "?"}


def _v(campo):
    return campo.get("value") if isinstance(campo, dict) else campo


def _c(campo):
    return campo.get("confidence") if isinstance(campo, dict) else None


def _resaltar(raw_text, spans):
    """Texto del OCR con los source_span sobre fondo cian."""
    t = Text(raw_text or "(sin texto)")
    bajo = (raw_text or "").lower()
    for s in spans:
        if not s:
            continue
        i = bajo.find(s.lower())
        if i >= 0:
            t.stylize("black on cyan", i, i + len(s))
    return t


def render(contrato, console=None):
    console = console or Console()
    ocr = contrato.get("ocr", {})
    ext = contrato.get("extracted", {})
    rec = contrato.get("reconciliation", {})
    det = contrato.get("confidence_detail", {})
    veredicto = rec.get("verdict", "UNCERTAIN")
    color = COLOR.get(veredicto, "white")

    # --- panel 1: imagen ---
    t1 = Table.grid(padding=(0, 1))
    t1.add_row("archivo", contrato.get("source_image", "-"))
    t1.add_row("ruta", ocr.get("route", "-"))
    t1.add_row("motor", ocr.get("engine", "-"))
    t1.add_row("ocr", f"{ocr.get('duration_s', 0)} s")
    flags = ocr.get("quality_flags") or []
    t1.add_row("flags", ", ".join(flags) if flags else "ninguno")

    # --- panel 2: texto OCR con spans resaltados ---
    spans = [(_span(ext, c)) for c in ("vendor", "date", "total")]
    p2 = _resaltar(ocr.get("raw_text", ""), spans)

    # --- panel 3: extraido ---
    t3 = Table.grid(padding=(0, 1))
    for campo, etiqueta in (("vendor", "proveedor"), ("date", "fecha"),
                            ("total", "total"), ("currency", "moneda")):
        val = _v(ext.get(campo))
        conf = _c(ext.get(campo))
        marca = ""
        est = det.get("spans", {}).get(campo, {}).get("verificado")
        if est is True:
            marca = "[green]span ok[/green]"
        elif est is False:
            marca = "[red]span INVENTADO[/red]"
        t3.add_row(etiqueta,
                   f"[bold]{val if val is not None else '-'}[/bold]",
                   f"({conf:.2f})" if isinstance(conf, (int, float)) else "",
                   marca)
    items = ext.get("items") or []
    if items:
        t3.add_row("items", str(len(items)), "", "")
    rep = ext.get("parser_repairs") or []
    if rep:
        t3.add_row("reparaciones", ", ".join(rep), "", "")

    # --- panel 4: libro ---
    reg = rec.get("matched_record") or rec.get("_registro")
    t4 = Table.grid(padding=(0, 1))
    if reg:
        t4.add_row("registro", f"#{reg['id']}")
        t4.add_row("proveedor", str(reg.get("proveedor", "-")))
        t4.add_row("fecha", str(reg.get("fecha", "-")))
        t4.add_row("monto", f"[bold]{float(reg['monto']):.2f}[/bold]")
        t4.add_row("estrategia", str(rec.get("match_strategy")))
        if rec.get("delta") is not None:
            t4.add_row("delta", f"{rec['delta']:+.2f}")
    else:
        t4.add_row("registro", "sin coincidencia en el libro")

    console.print(Panel(Group(
        Panel(t1, title="IMAGEN", border_style="dim"),
        Panel(p2, title="TEXTO OCR (span resaltado)", border_style="dim"),
        Panel(t3, title="EXTRAIDO", border_style="dim"),
        Panel(t4, title="LIBRO (MariaDB)", border_style="dim"),
    ), title=f"[bold]{contrato.get('receipt_id', '?')}[/bold]", border_style=color))

    conf = contrato.get("confidence_overall", 0.0)
    console.print(f"[bold {color}]{ICONO.get(veredicto, '?')}  {veredicto}[/bold {color}]"
                  f"  ·  confianza {conf:.2f}"
                  f"  ·  {contrato.get('latency_s', 0)} s")
    console.print(f"    {rec.get('explanation', '')}")
    for veto in det.get("vetos", []):
        console.print(f"    [dim]veto:[/dim] {veto}")
    if rec.get("human_review_required"):
        console.print("    [bold]requiere revision humana[/bold]")
    console.print()


def tabla_resumen(filas, console=None, titulo="Resumen"):
    """filas: dicts con veredicto/n/confianza_media, o receipt_id/veredicto/..."""
    console = console or Console()
    if not filas:
        console.print("[dim]sin datos[/dim]")
        return
    t = Table(title=titulo, header_style="bold")
    for k in filas[0].keys():
        t.add_column(str(k))
    for f in filas:
        vals = []
        for k, v in f.items():
            s = "-" if v is None else str(v)
            if k.lower().startswith("vered"):
                s = f"[{COLOR.get(str(v), 'white')}]{s}[/{COLOR.get(str(v), 'white')}]"
            vals.append(s)
        t.add_row(*vals)
    console.print(t)


def _span(ext, campo):
    c = ext.get(campo)
    return c.get("source_span") if isinstance(c, dict) else None
