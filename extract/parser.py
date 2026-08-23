"""Parser tolerante de la salida del modelo + validacion de esquema.

Un 4B cuantizado envuelve el JSON en markdown, agrega preambulo, usa comillas simples
o deja comas finales. Cada reparacion se REGISTRA en `parser_repairs` y viaja en el
contrato: es un dato de fiabilidad del modelo, no un detalle interno.
"""
import json
import re

CAMPOS = ("vendor", "date", "total", "currency")
FECHA_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class ErrorValidacion(ValueError):
    pass


def parsear(texto):
    """Devuelve (dict, reparaciones). Lanza ErrorValidacion si no hay JSON recuperable."""
    reparaciones = []
    if not texto or not texto.strip():
        raise ErrorValidacion("el modelo devolvio texto vacio")

    s = texto.strip()
    try:
        return json.loads(s), reparaciones
    except json.JSONDecodeError:
        pass

    if "```" in s:
        s = re.sub(r"```[a-zA-Z]*", "", s).replace("```", "")
        reparaciones.append("fences_markdown")

    i, j = s.find("{"), s.rfind("}")
    if i == -1 or j == -1 or j < i:
        raise ErrorValidacion("no hay un objeto JSON en la respuesta")
    if i > 0 or j < len(s) - 1:
        reparaciones.append("preambulo_recortado")
    s = s[i:j + 1]

    for intento in ("directo", "comas_finales", "comillas_simples"):
        if intento == "comas_finales":
            nuevo = re.sub(r",\s*([}\]])", r"\1", s)
            if nuevo == s:
                continue
            s = nuevo
            reparaciones.append("comas_finales")
        elif intento == "comillas_simples":
            nuevo = re.sub(r"'([^'\"]*)'(\s*[:,}\]])", r'"\1"\2', s)
            if nuevo == s:
                continue
            s = nuevo
            reparaciones.append("comillas_simples")
        try:
            return json.loads(s), reparaciones
        except json.JSONDecodeError:
            continue

    raise ErrorValidacion("JSON irrecuperable tras las reparaciones")


def validar(d):
    """Normaliza al esquema del contrato y valida tipos. Lanza ErrorValidacion.

    Deliberadamente minima y explicita: solo lo que romperia la conciliacion aguas
    abajo. Validar de mas aqui es rechazar extracciones utiles.
    """
    if not isinstance(d, dict):
        raise ErrorValidacion("la raiz no es un objeto")

    salida = {}
    for campo in CAMPOS:
        c = d.get(campo)
        if c is None:
            salida[campo] = {"value": None, "confidence": 0.0, "source_span": ""}
            continue
        if not isinstance(c, dict):
            c = {"value": c, "confidence": 0.0, "source_span": ""}
        conf = c.get("confidence", 0.0)
        try:
            conf = float(conf)
        except (TypeError, ValueError):
            conf = 0.0
        if not 0.0 <= conf <= 1.0:
            raise ErrorValidacion(f"'{campo}.confidence' fuera de [0,1]: {conf}")
        salida[campo] = {
            "value": c.get("value"),
            "confidence": round(conf, 3),
            "source_span": str(c.get("source_span") or ""),
        }

    total = salida["total"]["value"]
    if total is not None:
        monto = a_monto(total)
        if monto is None:
            raise ErrorValidacion(f"'total.value' no es numero ni null: {total!r}")
        salida["total"]["value"] = monto

    fecha = salida["date"]["value"]
    if fecha is not None:
        fecha = str(fecha).strip()
        if not FECHA_ISO.match(fecha):
            raise ErrorValidacion(f"'date.value' no esta en YYYY-MM-DD: {fecha!r}")
        salida["date"]["value"] = fecha

    items = []
    for it in (d.get("items") or []):
        if not isinstance(it, dict):
            continue
        items.append({
            "desc": str(it.get("desc") or ""),
            "qty": _num(it.get("qty")),
            "unit_price": _num(it.get("unit_price")),
            "confidence": _num(it.get("confidence")) or 0.0,
        })
    salida["items"] = items
    salida["parser_repairs"] = []
    return salida


def a_monto(v):
    """Convierte a float lo que el modelo devuelva como monto, o None.

    "1234,50" es mil doscientos treinta y cuatro con cincuenta, no ciento veintitres mil.
    Y "1,234.50" es lo mismo con la convencion inversa. La regla: cuando aparecen los
    dos separadores, el ULTIMO es el decimal; cuando aparece uno solo, es decimal si
    deja exactamente dos digitos al final, y separador de miles en cualquier otro caso.
    """
    if isinstance(v, (int, float)):
        return round(float(v), 2)
    s = re.sub(r"[^\d,.\-]", "", str(v or "")).strip()
    if not s or s in ("-", ".", ","):
        return None
    if "," in s and "." in s:
        decimal = "," if s.rfind(",") > s.rfind(".") else "."
        miles = "." if decimal == "," else ","
        s = s.replace(miles, "").replace(decimal, ".")
    elif "," in s:
        s = s.replace(",", "." if re.search(r",\d{2}$", s) else "")
    elif re.search(r"\.\d{3}$", s) and s.count(".") == 1:
        s = s.replace(".", "")   # "1.500" en formato boliviano son mil quinientos
    try:
        return round(float(s), 2)
    except ValueError:
        return None


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
