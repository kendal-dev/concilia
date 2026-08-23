"""Calculo de `confidence_overall` y decision final del veredicto.

Promedio ponderado + VETOS. Los detectores criticos no promedian: imponen techo.
Un `source_span` inventado en el campo `total` no puede quedar diluido por buenas
senales en los demas campos - es justo el caso que el track quiere que se atrape.

Vetos (techo de confianza):
  span inventado en `total`      -> 0.40
  aritmetica que no cierra       -> 0.55
  ruta multimodal (sin OCR que verificar) -> 0.70
  2+ flags severos de calidad    -> 0.50

Y el umbral: por debajo de CONFIDENCE_THRESHOLD (0.6 por defecto, en .env) el
veredicto se fuerza a UNCERTAIN, diga lo que diga el modelo.
"""
import os

from .detectors import coherencia_aritmetica, span_verificado

FLAGS_SEVEROS = {"blurry", "faded_thermal", "partial_read", "overexposed"}

PESOS = {
    "calidad_imagen": 0.20,
    "confianza_modelo": 0.30,
    "spans": 0.25,
    "cascada": 0.25,
}

CONF_ESTRATEGIA = {
    "exact": 1.00,
    "fuzzy_vendor": 0.85,
    "vendor_date": 0.75,
    "date_amount": 0.70,
    "amount_only": 0.50,
    None: 0.30,
}


def _v(campo):
    return campo.get("value") if isinstance(campo, dict) else campo


def evaluar(contrato, umbral=None):
    """Muta y devuelve el contrato: escribe `confidence_overall`, el veredicto final,
    `human_review_required` y el bloque de auditoria `confidence_detail`."""
    if umbral is None:
        umbral = float(os.environ.get("CONFIDENCE_THRESHOLD", "0.6"))

    ocr = contrato.get("ocr", {})
    ext = contrato.get("extracted", {})
    rec = contrato.setdefault("reconciliation", {})
    raw = ocr.get("raw_text", "") or ""

    # --- senal 1: calidad de imagen ---
    flags = ocr.get("quality_flags", []) or []
    severos = [f for f in flags if f in FLAGS_SEVEROS]
    calidad = max(0.0, 1.0 - 0.25 * len(flags) - 0.15 * len(severos))

    # --- senal 2: confianza declarada por el modelo, campo por campo ---
    confs = []
    for campo in ("vendor", "date", "total"):
        c = ext.get(campo)
        if isinstance(c, dict) and isinstance(c.get("confidence"), (int, float)):
            confs.append(float(c["confidence"]))
    conf_modelo = sum(confs) / len(confs) if confs else 0.3

    # --- senal 3: spans verificables ---
    ruta_multimodal = ocr.get("route") == "multimodal_fallback"
    spans = {}
    verificados = []
    for campo in ("vendor", "date", "total"):
        c = ext.get(campo)
        span = c.get("source_span") if isinstance(c, dict) else None
        if ruta_multimodal or not raw:
            spans[campo] = {"verificado": None, "ratio": None,
                            "motivo": "sin texto OCR contra el cual verificar"}
            continue
        ok, ratio = span_verificado(span or "", raw)
        spans[campo] = {"verificado": ok, "ratio": ratio}
        verificados.append(1.0 if ok else 0.0)
    señal_spans = sum(verificados) / len(verificados) if verificados else 0.5

    # --- senal 4: nivel de la cascada del matcher ---
    cascada = CONF_ESTRATEGIA.get(rec.get("match_strategy"), 0.30)

    # --- senal auxiliar: aritmetica ---
    items = ext.get("items") or []
    estado_arit, delta_arit = coherencia_aritmetica(items, _v(ext.get("total")))

    base = (PESOS["calidad_imagen"] * calidad
            + PESOS["confianza_modelo"] * conf_modelo
            + PESOS["spans"] * señal_spans
            + PESOS["cascada"] * cascada)

    # --- vetos ---
    vetos = []
    techo = 1.0
    if spans.get("total", {}).get("verificado") is False:
        techo = min(techo, 0.40)
        vetos.append("source_span de 'total' no existe en el texto OCR")
    if estado_arit == "desvia":
        techo = min(techo, 0.55)
        vetos.append(f"la suma de items difiere del total en {delta_arit}")
    if ruta_multimodal:
        techo = min(techo, 0.70)
        vetos.append("ruta multimodal: no hay texto OCR para verificar spans")
    if len(severos) >= 2:
        techo = min(techo, 0.50)
        vetos.append(f"calidad de imagen: {', '.join(severos)}")
    if _v(ext.get("total")) is None:
        techo = min(techo, 0.30)
        vetos.append("el modelo no pudo leer el total")

    confianza = round(min(base, techo), 3)

    # --- decision ---
    forzado = confianza < umbral
    if forzado:
        rec["verdict"] = "UNCERTAIN"
    rec["human_review_required"] = bool(
        forzado or estado_arit == "desvia" or rec.get("verdict") == "MISMATCH")

    contrato["confidence_overall"] = confianza
    contrato["confidence_detail"] = {
        "umbral": umbral,
        "señales": {
            "calidad_imagen": round(calidad, 3),
            "confianza_modelo": round(conf_modelo, 3),
            "spans_verificados": round(señal_spans, 3),
            "nivel_cascada": cascada,
        },
        "spans": spans,
        "aritmetica": {"estado": estado_arit, "delta": delta_arit},
        "vetos": vetos,
        "techo_aplicado": techo,
        "base_ponderada": round(base, 3),
        "veredicto_forzado_a_uncertain": forzado,
    }
    return contrato
