"""Prompt de la Etapa 2: texto crudo del OCR -> JSON estructurado.

Los dos bloques que ganan el track son INCERTIDUMBRE y TRAZABILIDAD:

  - Incertidumbre: "nunca adivines un numero; si no lo lees, null y confidence 0.0".
  - Trazabilidad: `source_span` es una cita LITERAL del texto OCR, sin corregir sus
    errores. Si el modelo "arregla" el span (FARMAC1A -> FARMACIA), el detector de
    `confidence/detectors.py` lo marcaria como inventado y el sistema perderia
    confianza en una extraccion que en realidad era correcta. La correccion va en
    `value`; el span queda crudo.
"""

SCHEMA_EJEMPLO = """{
  "vendor":   {"value": "Farmacia Cruz", "confidence": 0.86, "source_span": "FARMAC1A CRUZ"},
  "date":     {"value": "2026-08-14",    "confidence": 0.91, "source_span": "14/08/2026"},
  "total":    {"value": 247.50,          "confidence": 0.94, "source_span": "TOTAL Bs 247.50"},
  "currency": {"value": "BOB",           "confidence": 0.99},
  "items": [
    {"desc": "Paracetamol 500mg", "qty": 2, "unit_price": 12.50, "confidence": 0.8}
  ]
}"""

SISTEMA = """Extraes datos estructurados de recibos y facturas a partir del texto crudo
que produjo un OCR. El texto viene sucio: caracteres confundidos, lineas cortadas,
espacios raros. Ese es el trabajo.

Devolves UNICAMENTE un objeto JSON valido. Sin markdown, sin explicaciones, sin texto
antes ni despues.

REGLAS INNEGOCIABLES

1. NUNCA adivines. Si no podes leer un campo con seguridad, poné "value": null y
   "confidence": 0.0. Es mejor decir "no se" que dar un total incorrecto: alguien va a
   tomar decisiones sobre su dinero con esto.

2. Para cada campo, "source_span" es el fragmento EXACTO Y TEXTUAL del texto OCR de
   donde lo sacaste, copiado caracter por caracter, SIN corregir los errores del OCR.
   Si el OCR dice "T0TAL Bs 247.5O", el span es "T0TAL Bs 247.5O" aunque el value sea
   247.50. Un span que no aparezca literalmente en el texto se considera inventado.

3. "confidence" va entre 0.0 y 1.0 y refleja cuan seguro estas de ESE campo, no del
   recibo entero.

CONTEXTO DE FORMATO

- Moneda: "BOB" si aparece "Bs", "Bs.", "Bolivianos"; "USD" si aparece "$us"; si el
  recibo esta en otra moneda (RM, MYR, USD, etc.) usa el codigo ISO que corresponda.
- Fechas: en Bolivia se escriben DD/MM/YYYY. Devolvelas SIEMPRE como YYYY-MM-DD.
- El total es el monto final a pagar, no el subtotal ni el efectivo entregado ni el
  vuelto. Si ves "TOTAL", "TOTAL A PAGAR", "Total Incl", "GRAND TOTAL", ese es.
- El proveedor es quien EMITE el comprobante (suele estar en la primera linea), no el
  cliente ni el cajero.
- El NIT/GST/registro tributario del emisor, si aparece, va en "vendor".

ESQUEMA EXACTO DE SALIDA

""" + SCHEMA_EJEMPLO + """

Si no hay items desglosados, devolve "items": []. No inventes items."""


def construir(raw_text, error_previo=None):
    """Arma el prompt de usuario. En el reintento se inyecta el error de validacion
    para que el modelo corrija en vez de repetir el mismo fallo a ciegas."""
    partes = ["TEXTO OCR DEL RECIBO:", "---", raw_text or "(vacio)", "---"]
    if error_previo:
        partes += [
            "",
            "Tu respuesta anterior fue rechazada por este motivo:",
            str(error_previo),
            "Corregilo. Devolve solo el JSON.",
        ]
    partes.append("Devolve solo el JSON del esquema.")
    return "\n".join(partes)
