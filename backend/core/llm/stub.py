"""Clientes LLM falsos para desarrollar y testear sin QVAC.

StubLLMClient da respuestas deterministas segun el nombre del archivo, para que
la demo sea reproducible. FlakyLLMClient reproduce los modos de fallo tipicos de
un modelo de 1-4B, que es contra lo que se prueba el retry loop.
"""

import re

from backend.core.llm.base import LLMClient

# Cada fixture apunta a un caso del seed. La clave es un substring del nombre
# del archivo subido.
_FIXTURES: dict[str, str] = {
    # Coincide exacto con OC-101. Subtotal + IVA 13% cuadran.
    "match": """{
      "supplier_tax_id": "4820156023",
      "supplier_name": "Importadora Santa Cruz SRL",
      "invoice_number": "F-00731",
      "invoice_date": "2026-07-09",
      "subtotal": 3000.00,
      "tax_amount": 390.00,
      "total_amount": 3390.00,
      "currency": "BOB",
      "line_items": [
        {"description": "Resma papel bond A4", "quantity": 30, "unit_price": 45.00, "line_total": 1350.00},
        {"description": "Toner laser negro", "quantity": 6, "unit_price": 340.00, "line_total": 2040.00}
      ],
      "confidence": {"supplier_tax_id": 0.97, "total_amount": 0.95}
    }""",
    # EL CASO DEL MOCKUP: OC-113 autoriza 20 cajas a Bs 85; la factura cobra 24.
    "oriente": """{
      "supplier_tax_id": "1023874015",
      "supplier_name": "Distribuidora del Oriente",
      "invoice_number": "F-00842",
      "invoice_date": "2026-07-18",
      "subtotal": 1805.31,
      "tax_amount": 234.69,
      "total_amount": 2040.00,
      "currency": "BOB",
      "line_items": [
        {"description": "Aceite comestible caja x12", "quantity": 24, "unit_price": 85.00, "line_total": 2040.00}
      ],
      "confidence": {"supplier_tax_id": 0.96, "total_amount": 0.94}
    }""",
    # Suma de lineas descuadrada contra su propio total declarado (OC-104).
    "descuadre": """{
      "supplier_tax_id": "1029384756",
      "supplier_name": "Papelera Andina SA",
      "invoice_number": "F-00519",
      "invoice_date": "2026-07-12",
      "subtotal": 1100.44,
      "tax_amount": 143.06,
      "total_amount": 1243.50,
      "currency": "BOB",
      "line_items": [
        {"description": "Cuaderno empastado A5", "quantity": 45, "unit_price": 18.50, "line_total": 832.50},
        {"description": "Boligrafo azul caja x50", "quantity": 6, "unit_price": 68.50, "line_total": 380.00}
      ],
      "confidence": {"supplier_tax_id": 0.91, "total_amount": 0.88}
    }""",
    # Sobrecargo grande contra OC-107 (12600.00).
    "grande": """{
      "supplier_tax_id": "7788990011",
      "supplier_name": "Ferreteria El Constructor",
      "invoice_number": "F-01330",
      "invoice_date": "2026-07-18",
      "subtotal": 13805.31,
      "tax_amount": 1794.69,
      "total_amount": 15600.00,
      "currency": "BOB",
      "line_items": [
        {"description": "Taladro percutor 800W", "quantity": 12, "unit_price": 1300.00, "line_total": 15600.00}
      ],
      "confidence": {"supplier_tax_id": 0.94, "total_amount": 0.9}
    }""",
    # Multi-linea con una linea que NO figura en OC-118.
    "extra": """{
      "supplier_tax_id": "3344556677",
      "supplier_name": "Transportes Chuquisaca SRL",
      "invoice_number": "F-00988",
      "invoice_date": "2026-07-23",
      "subtotal": 5559.73,
      "tax_amount": 722.77,
      "total_amount": 6282.50,
      "currency": "BOB",
      "line_items": [
        {"description": "Flete Santa Cruz - La Paz", "quantity": 3, "unit_price": 1250.00, "line_total": 3750.00},
        {"description": "Flete La Paz - Oruro", "quantity": 2, "unit_price": 620.00, "line_total": 1240.00},
        {"description": "Seguro de carga", "quantity": 1, "unit_price": 692.50, "line_total": 692.50},
        {"description": "Gestion aduanera", "quantity": 1, "unit_price": 200.00, "line_total": 200.00},
        {"description": "Recargo por combustible", "quantity": 1, "unit_price": 400.00, "line_total": 400.00}
      ],
      "confidence": {"supplier_tax_id": 0.93, "total_amount": 0.9}
    }""",
    # IVA mal calculado contra OC-121: el desglose suma bien pero el 13% no da.
    "iva": """{
      "supplier_tax_id": "9911223344",
      "supplier_name": "Cafe Illimani SRL",
      "invoice_number": "F-00204",
      "invoice_date": "2026-07-25",
      "subtotal": 384.00,
      "tax_amount": 68.00,
      "total_amount": 452.00,
      "currency": "BOB",
      "line_items": [
        {"description": "Cafe en grano 1kg", "quantity": 8, "unit_price": 56.50, "line_total": 452.00}
      ],
      "confidence": {"supplier_tax_id": 0.9, "total_amount": 0.92}
    }""",
    # Cobra contra una OC cancelada (OC-125).
    "cancelada": """{
      "supplier_tax_id": "5566778899",
      "supplier_name": "Metalurgica Potosi SA",
      "invoice_number": "F-02210",
      "invoice_date": "2026-07-29",
      "subtotal": 16592.92,
      "tax_amount": 2157.08,
      "total_amount": 18750.00,
      "currency": "BOB",
      "line_items": [
        {"description": "Perfil de acero 6m", "quantity": 25, "unit_price": 750.00, "line_total": 18750.00}
      ],
      "confidence": {"supplier_tax_id": 0.96, "total_amount": 0.96}
    }""",
    # Subcobro contra OC-130 (6400.00).
    "subcobro": """{
      "supplier_tax_id": "2233445566",
      "supplier_name": "Servicios Integrales Beni SRL",
      "invoice_number": "F-00144",
      "invoice_date": "2026-08-07",
      "subtotal": 4247.79,
      "tax_amount": 552.21,
      "total_amount": 4800.00,
      "currency": "BOB",
      "line_items": [
        {"description": "Mantenimiento HVAC mensual", "quantity": 3, "unit_price": 1600.00, "line_total": 4800.00}
      ],
      "confidence": {"supplier_tax_id": 0.89, "total_amount": 0.93}
    }""",
    # Proveedor que no existe en el ERP.
    "desconocido": """{
      "supplier_tax_id": "6677889900",
      "supplier_name": "Comercial Yacuiba SRL",
      "invoice_number": "F-00032",
      "invoice_date": "2026-08-02",
      "subtotal": 648.85,
      "tax_amount": 84.35,
      "total_amount": 733.20,
      "currency": "BOB",
      "line_items": [],
      "confidence": {"supplier_tax_id": 0.72, "total_amount": 0.81}
    }""",
    # Documento ilegible: el modelo admite que no pudo leerlo.
    "ilegible": """{
      "supplier_tax_id": null,
      "supplier_name": null,
      "invoice_number": null,
      "invoice_date": null,
      "subtotal": null,
      "tax_amount": null,
      "total_amount": null,
      "currency": null,
      "line_items": [],
      "confidence": {"supplier_tax_id": 0.1, "total_amount": 0.05}
    }""",
}

_DEFAULT_FIXTURE = "match"


class StubLLMClient(LLMClient):
    """Respuestas deterministas elegidas por nombre de archivo.

    Subir "factura_oriente.jpg" da siempre el mismo resultado, asi la demo
    es reproducible y los tests no dependen de un modelo real.
    """

    def __init__(self, filename: str = "") -> None:
        self.filename = filename.lower()

    def _fixture_key(self) -> str:
        for key in _FIXTURES:
            if key in self.filename:
                return key
        return _DEFAULT_FIXTURE

    def extract_invoice(self, image_bytes: bytes, feedback: str | None = None) -> str:
        return _FIXTURES[self._fixture_key()]

    def reason_triage(self, prompt: str) -> str:
        """Redacta la nota a partir de lo que el prompt YA trae calculado.

        Igual que un modelo real: no recalcula nada, solo lee los hechos que le
        pasaron y los pone en prosa. Que sea determinista es lo que hace la
        demo reproducible.
        """
        cancelada = "CANCELADA" in prompt
        cantidad = _leer_check(prompt, "cantidad vs OC")
        diferencia = _leer_diferencia(prompt)

        if cancelada:
            return (
                "La orden de compra asociada figura cancelada. Rechazar la factura "
                "y escalar al responsable de compras."
            )

        # Caso del mockup: la discrepancia se explica por la cantidad, no por
        # el precio. Es la nota mas util para el operador.
        if cantidad and diferencia:
            unidades = _leer_exceso_unidades(cantidad)
            if unidades:
                return (
                    f"Se facturaron {unidades} unidades de mas. "
                    f"Diferencia de {diferencia} a favor del proveedor."
                )

        if "MAS de lo autorizado" in prompt:
            return (
                "Discrepancia detectada: el monto facturado supera al autorizado en "
                "la orden de compra. No aprobar el pago hasta que el proveedor "
                "justifique la diferencia por escrito."
            )
        if "MENOS de lo autorizado" in prompt:
            return (
                "La factura cobra menos de lo autorizado. Probablemente sea una "
                "entrega parcial. Verificar el remito antes de cerrar la orden."
            )
        if _leer_check(prompt, "suma de lineas"):
            return (
                "Las lineas de la factura no suman el total declarado. "
                "Devolver al proveedor para que emita una nota de correccion."
            )
        if _leer_check(prompt, "impuestos"):
            return (
                "El IVA declarado no corresponde al 13% del subtotal. "
                "Verificar con el proveedor antes de registrar el credito fiscal."
            )
        return (
            "Los montos coinciden con la orden de compra autorizada. "
            "Apto para aprobacion de pago."
        )


def _leer_check(prompt: str, etiqueta: str) -> str | None:
    """Devuelve el detalle de un check observado (ATENCION/FALLA), si lo hay."""
    for linea in prompt.splitlines():
        if etiqueta in linea and ("[ATENCION]" in linea or "[FALLA]" in linea):
            return linea.split(":", 1)[-1].strip()
    return None


def _leer_diferencia(prompt: str) -> str | None:
    for linea in prompt.splitlines():
        if "MAS de lo autorizado" in linea:
            return "Bs " + linea.split("cobra", 1)[1].split("MAS")[0].strip()
    return None


def _leer_exceso_unidades(detalle: str) -> str | None:
    """De 'Aceite ...: 24 vs 20 unidades' saca '4'."""
    m = re.search(r"(\d+(?:\.\d+)?)\s+vs\s+(\d+(?:\.\d+)?)", detalle)
    if not m:
        return None
    facturado, autorizado = float(m.group(1)), float(m.group(2))
    exceso = facturado - autorizado
    if exceso <= 0:
        return None
    return str(int(exceso)) if exceso == int(exceso) else str(exceso)


# Modos de fallo reales de un modelo pequenio. Ninguno es recuperable por la
# capa de rescate del orquestador (que si limpia fences y prosa alrededor):
# estos obligan a un reintento de verdad.
_FAILURE_MODES: list[str] = [
    # 1. Se queda sin tokens a mitad del JSON.
    '{"supplier_tax_id": "4820156023", "supplier_name": "Importadora Santa',
    # 2. Alucina un campo que nunca pedimos.
    '{"supplier_tax_id": "4820156023", "total_amount": 3390.00, '
    '"vendor_rating": "excelente", "line_items": [], "confidence": {}}',
    # 3. Ignora la instruccion de devolver JSON y contesta en prosa.
    "Claro! La factura corresponde a Importadora Santa Cruz por un total de "
    "3390 bolivianos. Que mas necesitas saber?",
    # 4. Devuelve el monto en palabras en vez de numero.
    '{"supplier_tax_id": "4820156023", "total_amount": "mil doscientos '
    'cincuenta", "line_items": [], "confidence": {}}',
    # 5. Devuelve el esquema en lugar de los datos.
    '{"supplier_tax_id": "string|null", "total_amount": "number|null", '
    '"line_items": [], "confidence": {}}',
]


class FlakyLLMClient(LLMClient):
    """Falla las primeras `fail_times` llamadas y despues acierta.

    Es lo que prueba que el self-correction loop funciona de verdad y no solo
    en el papel. Cada fallo usa un modo distinto, ciclando la lista.
    """

    def __init__(self, fail_times: int = 2, filename: str = "") -> None:
        self.fail_times = fail_times
        self.calls = 0
        self._good = StubLLMClient(filename)

    def extract_invoice(self, image_bytes: bytes, feedback: str | None = None) -> str:
        self.calls += 1
        if self.calls <= self.fail_times:
            return _FAILURE_MODES[(self.calls - 1) % len(_FAILURE_MODES)]
        return self._good.extract_invoice(image_bytes, feedback)

    def reason_triage(self, prompt: str) -> str:
        return self._good.reason_triage(prompt)
