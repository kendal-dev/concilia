"""Tests del orquestador con un stub de DB en memoria.

No requieren MariaDB corriendo: lo que se prueba aca es la logica de fiabilidad,
no el SQL. El SQL se prueba en test_db_tool.py contra la base real.
"""

import json
from decimal import Decimal

import pytest

from backend.core import orchestrator
from backend.core.llm.stub import FlakyLLMClient, StubLLMClient
from backend.core.orchestrator import _parse_extraction, _salvage_json, reconcile
from backend.core.schemas import (
    CheckStatus,
    LineItem,
    PurchaseOrderRecord,
    Verdict,
)

IMG = b"bytes-de-imagen-de-prueba"


# ---------------------------------------------------------------------
# Dobles de prueba
# ---------------------------------------------------------------------

class FakeSession:
    """Sesion inerte: el orquestador solo la pasa al db_tool y al repositorio,
    que estan parcheados en estos tests."""


@pytest.fixture
def erp(monkeypatch):
    """Parchea la capa de datos y expone lo que se persistio."""
    saved: dict = {}

    catalogo = {
        "4820156023": PurchaseOrderRecord(
            id=1,
            po_number="OC-101",
            supplier_tax_id="4820156023",
            supplier_name="Importadora Santa Cruz SRL",
            currency="BOB",
            total_amount=Decimal("3390.00"),
            status="OPEN",
            issued_at="2026-07-02",
            line_items=[
                LineItem(description="Resma papel bond A4", quantity=Decimal("30"),
                         unit_price=Decimal("45.00"), line_total=Decimal("1350.00")),
                LineItem(description="Toner laser negro", quantity=Decimal("6"),
                         unit_price=Decimal("340.00"), line_total=Decimal("2040.00")),
            ],
        ),
        "1023874015": PurchaseOrderRecord(
            id=4,
            po_number="OC-113",
            supplier_tax_id="1023874015",
            supplier_name="Distribuidora del Oriente",
            currency="BOB",
            total_amount=Decimal("1700.00"),
            status="OPEN",
            issued_at="2026-07-15",
            line_items=[
                LineItem(description="Aceite comestible caja x12", quantity=Decimal("20"),
                         unit_price=Decimal("85.00"), line_total=Decimal("1700.00")),
            ],
        ),
        "5566778899": PurchaseOrderRecord(
            id=7,
            po_number="OC-125",
            supplier_tax_id="5566778899",
            supplier_name="Metalurgica Potosi SA",
            currency="BOB",
            total_amount=Decimal("18750.00"),
            status="CANCELLED",
            issued_at="2026-07-24",
        ),
    }

    monkeypatch.setattr(
        orchestrator, "lookup_purchase_order",
        lambda session, tax_id, total=None: catalogo.get(tax_id),
    )
    monkeypatch.setattr(
        orchestrator, "save_invoice",
        lambda session, filename, invoice: saved.update(invoice=invoice) or 101,
    )
    monkeypatch.setattr(
        orchestrator, "save_reconciliation",
        lambda session, **kw: saved.update(kw) or 202,
    )
    # El documento no se escribe a disco en los tests del orquestador.
    monkeypatch.setattr(
        orchestrator, "store_document",
        lambda invoice_id, data, filename: f"storage/documents/{invoice_id}.jpg",
    )
    monkeypatch.setattr(
        orchestrator, "attach_document",
        lambda session, invoice_id, path, content_type: saved.update(document_path=path),
    )
    return saved


def run(llm, filename: str, max_retries: int = 3):
    return reconcile(FakeSession(), llm, IMG, filename, max_retries=max_retries)


# ---------------------------------------------------------------------
# Capa de rescate de JSON
# ---------------------------------------------------------------------

def test_salvage_extrae_json_de_un_bloque_de_codigo():
    raw = 'Aca tenes:\n```json\n{"total_amount": 10}\n```\nEspero que sirva!'
    assert _salvage_json(raw) == '{"total_amount": 10}'


def test_salvage_extrae_json_rodeado_de_prosa():
    raw = 'Claro! {"supplier_tax_id": "30-1"} listo.'
    assert _salvage_json(raw) == '{"supplier_tax_id": "30-1"}'


def test_salvage_devuelve_none_si_no_hay_objeto():
    assert _salvage_json("No pude leer el documento, lo siento.") is None


def test_ruido_de_formato_no_gasta_un_reintento():
    """Un fence de markdown es ruido de formato, no un error de contenido."""
    invoice = _parse_extraction('```json\n{"total_amount": 1250.00}\n```')
    assert invoice.total_amount == Decimal("1250.00")


def test_los_montos_se_parsean_como_decimal_no_float():
    invoice = _parse_extraction('{"total_amount": 0.1}')
    assert isinstance(invoice.total_amount, Decimal)
    assert invoice.total_amount == Decimal("0.1")


def test_campo_alucinado_es_rechazado():
    with pytest.raises(Exception):
        _parse_extraction('{"total_amount": 10, "vendor_rating": "excelente"}')


# ---------------------------------------------------------------------
# Veredictos
# ---------------------------------------------------------------------

def test_match_exacto(erp):
    result = run(StubLLMClient("factura_match.jpg"), "factura_match.jpg")
    assert result.verdict is Verdict.MATCH
    assert result.amount_delta == Decimal("0.00")


def test_match_con_checks_limpios_se_auto_aprueba(erp):
    result = run(StubLLMClient("factura_match.jpg"), "factura_match.jpg")
    assert result.auto_approved
    assert result.ui_state == "auto-aprobada"
    assert all(c.status is CheckStatus.PASS for c in result.checks)


def test_la_auto_aprobacion_exige_match_y_checks_limpios(erp):
    """MATCH por si solo no alcanza: un check en WARN bloquea el pago."""
    result = run(StubLLMClient("factura_cancelada.jpg"), "factura_cancelada.jpg")
    assert result.amount_delta == Decimal("0.00")   # los montos coinciden
    assert not result.auto_approved                 # pero la OC esta cancelada
    assert result.ui_state == "a revisar"


def test_sobrecargo_da_mismatch_con_delta_positivo(erp):
    """El caso del mockup: 24 cajas facturadas contra 20 autorizadas."""
    result = run(StubLLMClient("factura_oriente.jpg"), "factura_oriente.jpg")
    assert result.verdict is Verdict.MISMATCH
    # Bs 2040.00 facturados contra Bs 1700.00 autorizados.
    assert result.amount_delta == Decimal("340.00")
    assert isinstance(result.amount_delta, Decimal)
    assert not result.auto_approved


def test_la_nota_del_mockup_explica_la_cantidad_no_solo_el_monto(erp):
    """Un operador necesita saber POR QUE difiere, no solo cuanto."""
    result = run(StubLLMClient("factura_oriente.jpg"), "factura_oriente.jpg")
    assert "4 unidades de mas" in result.note
    assert "340" in result.note


def test_proveedor_sin_orden_no_llama_al_modelo_de_razonamiento(erp):
    """Sin datos que comparar, pedirle una opinion al modelo es invitarlo a
    confabular. El veredicto lo decide Python."""
    result = run(StubLLMClient("factura_desconocido.jpg"), "factura_desconocido.jpg")
    assert result.verdict is Verdict.NO_PO_FOUND
    assert result.amount_delta is None
    assert not any(s.phase.value == "reasoning" for s in result.trace.steps)


def test_orden_cancelada_nunca_es_match(erp):
    """Los montos coinciden, pero cobrar contra una PO cancelada es un problema."""
    result = run(StubLLMClient("factura_cancelada.jpg"), "factura_cancelada.jpg")
    assert result.amount_delta == Decimal("0.00")
    assert result.verdict is Verdict.MISMATCH


def test_documento_ilegible_da_uncertain_no_un_numero_inventado(erp):
    result = run(StubLLMClient("factura_ilegible.jpg"), "factura_ilegible.jpg")
    assert result.verdict is Verdict.UNCERTAIN
    assert result.amount_delta is None
    assert "revision manual" in result.note.lower()


# ---------------------------------------------------------------------
# Self-correction loop
# ---------------------------------------------------------------------

def test_se_recupera_de_dos_respuestas_rotas(erp):
    llm = FlakyLLMClient(fail_times=2, filename="factura_match.jpg")
    result = run(llm, "factura_match.jpg")

    assert result.verdict is Verdict.MATCH
    assert llm.calls == 3
    extraccion = next(s for s in result.trace.steps if s.phase.value == "extraction")
    assert extraccion.retries == 2


def test_agotar_los_reintentos_da_uncertain_sin_excepcion(erp):
    llm = FlakyLLMClient(fail_times=5, filename="factura_match.jpg")
    result = run(llm, "factura_match.jpg", max_retries=3)

    assert result.verdict is Verdict.UNCERTAIN
    assert llm.calls == 3
    extraccion = next(s for s in result.trace.steps if s.phase.value == "extraction")
    assert extraccion.retries == 3
    assert extraccion.error


def test_el_error_de_validacion_se_reinyecta_en_el_reintento(erp):
    """El modelo tiene que recibir que estuvo mal, no solo que reintente."""
    recibidos: list[str | None] = []

    class Espia(FlakyLLMClient):
        def extract_invoice(self, image_bytes, feedback=None):
            recibidos.append(feedback)
            return super().extract_invoice(image_bytes, feedback)

    run(Espia(fail_times=1, filename="factura_match.jpg"), "factura_match.jpg")

    assert recibidos[0] is None
    assert recibidos[1] is not None
    assert "rechazada" in recibidos[1]


# ---------------------------------------------------------------------
# Traza de auditoria
# ---------------------------------------------------------------------

def test_la_traza_registra_todas_las_fases(erp):
    result = run(StubLLMClient("factura_oriente.jpg"), "factura_oriente.jpg")
    fases = [s.phase.value for s in result.trace.steps]
    assert fases == ["extraction", "lookup", "verification", "reasoning", "persist"]


def test_la_traza_se_persiste_junto_al_dictamen(erp):
    run(StubLLMClient("factura_match.jpg"), "factura_match.jpg")
    assert erp["verdict"] is Verdict.MATCH
    assert erp["po_id"] == 1
    assert erp["trace"].steps
    assert erp["checks"]
    assert erp["auto_approved"] is True


def test_el_documento_original_se_guarda_como_evidencia(erp):
    run(StubLLMClient("factura_match.jpg"), "factura_match.jpg")
    assert erp["document_path"] == "storage/documents/101.jpg"


def test_los_checks_llegan_al_prompt_de_razonamiento(erp):
    """El modelo debe recibir los hechos ya verificados, no deducirlos."""
    result = run(StubLLMClient("factura_oriente.jpg"), "factura_oriente.jpg")
    razonamiento = next(s for s in result.trace.steps if s.phase.value == "reasoning")
    assert "VERIFICACIONES YA EJECUTADAS" in razonamiento.input
    assert "cantidad vs OC" in razonamiento.input

# ---------------------------------------------------------------------
# Evidencia de la etapa 1 en la traza
# ---------------------------------------------------------------------

class ConEvidencia(StubLLMClient):
    """Cliente de prueba que si expone `ultima_evidencia`, como hace QvacLLMClient.

    Sirve para probar el puente sin arrastrar el SDK ni cargar un modelo: lo que
    se verifica es que el orquestador adjunta la evidencia a la traza, no como la
    produce el cliente real.
    """

    def __init__(self, filename: str = "", texto: str = "TOTAL Bs 3390.00") -> None:
        super().__init__(filename)
        self.ultima_evidencia = {
            "texto_ocr": texto,
            "valores_verificados": {
                "total_amount": {"valor": "3390.00", "aparece_en_ocr": True,
                                 "similitud": 1.0},
                "supplier_tax_id": {"valor": "4820156023", "aparece_en_ocr": False,
                                    "similitud": 0.41},
            },
            "ocr": {"engine": "qvac-ggml-ocr/easyocr", "duration_s": 9.8,
                    "bloques": 14, "quality_flags": []},
            "rotacion": None,
        }


def test_sin_evidencia_la_traza_queda_igual_que_antes(erp):
    """Los motores deterministas no producen evidencia y no deben romper nada."""
    result = run(StubLLMClient("factura_match.jpg"), "factura_match.jpg")
    extraccion = next(s for s in result.trace.steps if s.phase.value == "extraction")
    assert extraccion.input is None


def test_el_texto_del_ocr_llega_a_la_traza(erp):
    """El pipeline de dos etapas solo vale si el texto intermedio es visible."""
    result = run(ConEvidencia("factura_match.jpg"), "factura_match.jpg")
    extraccion = next(s for s in result.trace.steps if s.phase.value == "extraction")
    assert extraccion.input["texto_ocr"] == "TOTAL Bs 3390.00"
    assert extraccion.input["ocr"]["engine"] == "qvac-ggml-ocr/easyocr"


def test_la_procedencia_de_cada_valor_llega_a_la_traza(erp):
    """Un valor que no aparece en el texto del OCR fue inventado, y hay que verlo."""
    result = run(ConEvidencia("factura_match.jpg"), "factura_match.jpg")
    verificados = next(
        s for s in result.trace.steps if s.phase.value == "extraction"
    ).input["valores_verificados"]

    assert verificados["total_amount"]["aparece_en_ocr"] is True
    assert verificados["supplier_tax_id"]["aparece_en_ocr"] is False


def test_la_evidencia_tambien_se_adjunta_cuando_la_extraccion_falla(erp):
    """Es cuando mas se necesita: muestra QUE leyo el OCR si el modelo no pudo."""

    class SiempreRota(ConEvidencia):
        def extract_invoice(self, image_bytes, feedback=None):
            return "no soy JSON"

    result = run(SiempreRota("factura_match.jpg"), "factura_match.jpg", max_retries=2)

    assert result.verdict is Verdict.UNCERTAIN
    extraccion = next(s for s in result.trace.steps if s.phase.value == "extraction")
    assert extraccion.error
    assert extraccion.input["texto_ocr"] == "TOTAL Bs 3390.00"


def test_la_evidencia_sobrevive_la_serializacion_de_la_traza(erp):
    """La traza va a una columna JSON; si la evidencia no serializa, se pierde."""
    run(ConEvidencia("factura_match.jpg"), "factura_match.jpg")
    traza = json.loads(erp["trace"].model_dump_json())
    extraccion = next(s for s in traza["steps"] if s["phase"] == "extraction")
    assert extraccion["input"]["texto_ocr"] == "TOTAL Bs 3390.00"
