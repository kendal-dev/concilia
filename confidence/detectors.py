"""Detectores de honestidad. El corazon del proyecto.

El track lo dice textual: *"an agent that flags uncertainty beats one that confidently
hallucinates a number"*. Este detector es como el sistema se entera de que no
sabe, antes de decir un numero.
"""
from difflib import SequenceMatcher


def normalizar_espacios(s: str) -> str:
    """Colapsa saltos de linea y espacios multiples, conserva tildes y mayusculas.

    El OCR corta lineas donde se le da la gana y mete espacios dobles. Comparar sin
    colapsar eso produce falsos negativos: un span correcto se marcaria inventado.
    """
    return " ".join((s or "").split())


UMBRAL_SPAN = 0.90


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


def variantes_numero(valor):
    """Todas las formas en que un mismo importe puede aparecer impreso.

    El modelo devuelve 33.9 y el ticket dice "RH 33,90": mismo numero, tres
    diferencias de escritura - coma decimal, cero final, y los espacios sueltos que
    el OCR intercala ("RM 33 ,92").
    """
    try:
        n = float(valor)
    except (TypeError, ValueError):
        return set()
    con_cero = f"{n:.2f}"
    sin_cero = con_cero.rstrip("0").rstrip(".")
    variantes = set()
    for base in (con_cero, sin_cero):
        variantes.add(base)
        variantes.add(base.replace(".", ","))
    return variantes


def valor_aparece(valor, texto_ocr, es_numero=False):
    """(aparece, similitud) de un valor extraido dentro del texto crudo del OCR.

    Es el detector de honestidad aplicado al reves: en vez de creerle al modelo
    cuando declara de donde saco un dato, se busca el dato en el texto. Si no esta,
    lo invento.

    Cuidado con lo que prueba: verifica PROCEDENCIA, no correccion. Un numero de
    factura leido de la linea de la direccion existe en el texto y aun asi es el
    campo equivocado. Esto descarta la alucinacion, no el error de interpretacion.
    """
    compacto = "".join((texto_ocr or "").split())
    if es_numero:
        variantes = variantes_numero(valor)
        if not variantes:
            return False, 0.0
        hallada = next((v for v in sorted(variantes) if v in compacto), None)
        if hallada:
            return True, 1.0
        return span_verificado(sorted(variantes)[0], texto_ocr)
    aguja = str(valor)
    ok, ratio = span_verificado(aguja, texto_ocr)
    if not ok and "".join(aguja.split()) in compacto:
        return True, 1.0
    return ok, ratio
