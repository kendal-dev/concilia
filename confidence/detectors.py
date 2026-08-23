"""Detectores de honestidad. El corazon del proyecto.

El track lo dice textual: *"an agent that flags uncertainty beats one that confidently
hallucinates a number"*. Estos dos detectores son como el sistema se entera de que no
sabe, antes de decir un numero.
"""
from difflib import SequenceMatcher

from reconcile.text import normalizar_espacios

UMBRAL_SPAN = 0.90
TOLERANCIA_ARITMETICA = 1.0


def span_verificado(span, raw_text, umbral=UMBRAL_SPAN):
    """El modelo dice que saco el total de "TOTAL Bs 247.00". ?Ese fragmento existe
    de verdad en el texto del OCR?  Si no existe, lo invento.

    NO se compara por substring literal: el OCR mete saltos de linea, espacios dobles
    y mayusculas variables, y una comparacion estricta marcaria como "inventadas"
    extracciones correctas. Se compara sobre texto con espacios colapsados, y si la
    contencion falla se hace una ventana deslizante con SequenceMatcher.
    """
    span_n = normalizar_espacios(span).lower()
    text_n = normalizar_espacios(raw_text).lower()
    if not span_n:
        return False, 0.0
    if not text_n:
        return False, 0.0
    if span_n in text_n:
        return True, 1.0
    n = len(span_n)
    paso = max(1, n // 4)
    mejor = 0.0
    for i in range(0, max(1, len(text_n) - n + 1), paso):
        r = SequenceMatcher(None, span_n, text_n[i:i + n]).ratio()
        if r > mejor:
            mejor = r
            if mejor >= 0.995:
                break
    return mejor >= umbral, round(mejor, 3)


def coherencia_aritmetica(items, total, tolerancia=TOLERANCIA_ARITMETICA):
    """Suma(qty * unit_price) contra el total declarado.

    Devuelve (estado, delta) con estado en {"ok", "desvia", "no_aplica"}.
    Un recibo sin items desglosados (taxi, mercado) NO se penaliza: castigarlo seria
    inventar incertidumbre donde no la hay.
    """
    if total is None:
        return "no_aplica", None
    if not items:
        return "no_aplica", None
    suma = 0.0
    usados = 0
    for it in items:
        q = _num(it.get("qty"))
        pu = _num(it.get("unit_price"))
        if q is None or pu is None:
            continue
        suma += q * pu
        usados += 1
    if usados == 0:
        return "no_aplica", None
    delta = round(suma - float(total), 2)
    return ("ok" if abs(delta) <= tolerancia else "desvia"), delta


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
