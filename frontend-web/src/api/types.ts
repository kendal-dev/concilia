export type DecimalString = string

export type Verdict = 'MATCH' | 'MISMATCH' | 'NO_PO_FOUND' | 'UNCERTAIN'
export type HumanDecision = 'PENDING' | 'APPROVED' | 'ESCALATED'
export type CheckStatus = 'PASS' | 'WARN' | 'FAIL' | 'SKIPPED'
export type Phase = 'extraction' | 'lookup' | 'verification' | 'reasoning' | 'persist'

export interface Health {
  status: 'ok' | 'degraded'
  db: 'connected' | 'unreachable'
  // Estos campos existen en la API temporalmente, pero nunca se exponen en la UI.
  llm_client: string
  test_clients: string[]
}

export interface Stats {
  procesadas: number
  auto_aprobadas: number
  a_revisar: number
  pendientes: number
  escaladas: number
}

export interface ExtractedLineItem {
  description: string
  quantity: DecimalString | null
  unit_price: DecimalString | null
  line_total: DecimalString | null
}

export interface LineItem {
  description: string
  quantity: DecimalString
  unit_price: DecimalString
  line_total: DecimalString
}

export interface Invoice {
  supplier_tax_id: string | null
  supplier_name: string | null
  invoice_number: string | null
  invoice_date: string | null
  subtotal: DecimalString | null
  tax_amount: DecimalString | null
  total_amount: DecimalString | null
  currency: string | null
  line_items: ExtractedLineItem[]
  confidence: Record<string, number>
}

export interface PurchaseOrder {
  id: number
  po_number: string
  supplier_tax_id: string
  supplier_name: string
  currency: string
  total_amount: DecimalString
  status: string
  issued_at: string
  line_items: LineItem[]
}

export interface Check {
  name: string
  label: string
  status: CheckStatus
  detail: string
  expected: string | null
  actual: string | null
}

export interface TraceStep {
  phase: Phase
  summary: string
  duration_ms: number
  retries: number
  error: string | null
}

export interface AgentTrace {
  steps: TraceStep[]
  started_at: string
}

export interface ReconcileResult {
  verdict: Verdict
  auto_approved: boolean
  checks: Check[]
  note: string
  invoice: Invoice | null
  purchase_order: PurchaseOrder | null
  amount_delta: DecimalString | null
  trace: AgentTrace
  invoice_id: number | null
  reconciliation_id: number | null
  human_decision: HumanDecision
}

export interface ReconciliationRow {
  id: number
  verdict: Verdict
  auto_approved: 0 | 1 | boolean
  amount_delta: DecimalString | null
  note: string | null
  checks: Check[] | null
  trace: AgentTrace | null
  human_decision: HumanDecision
  decided_by: string | null
  decided_at: string | null
  created_at: string
  invoice_id: number
  source_filename: string
  supplier_tax_id: string | null
  invoice_number: string | null
  subtotal: DecimalString | null
  tax_amount: DecimalString | null
  invoice_total: DecimalString | null
  raw_extraction: Invoice | null
  document_path: string | null
  content_type: string | null
  po_id: number | null
  po_number: string | null
  supplier_name: string | null
  po_status: string | null
  currency: string | null
  po_total: DecimalString | null
}

export interface ReconciliationDetail extends ReconciliationRow {
  po_line_items: LineItem[]
}

export interface DecisionResponse {
  id: number
  human_decision: Exclude<HumanDecision, 'PENDING'>
}

export interface ReconciliationView {
  id: number
  verdict: Verdict
  autoApproved: boolean
  humanDecision: HumanDecision
  amountDelta: DecimalString | null
  note: string
  invoice: Invoice | null
  purchaseOrder: PurchaseOrder | null
  checks: Check[]
  trace: AgentTrace
  sourceFilename: string
  hasDocument: boolean
  createdAt?: string
}

export function fromReconcile(result: ReconcileResult): ReconciliationView {
  return {
    id: result.reconciliation_id ?? result.invoice_id ?? 0,
    verdict: result.verdict,
    autoApproved: result.auto_approved,
    humanDecision: result.human_decision,
    amountDelta: result.amount_delta,
    note: result.note,
    invoice: result.invoice,
    purchaseOrder: result.purchase_order,
    checks: result.checks,
    trace: result.trace,
    sourceFilename: result.invoice?.invoice_number ?? 'Factura procesada',
    hasDocument: result.reconciliation_id !== null,
  }
}

export function fromDetail(detail: ReconciliationDetail): ReconciliationView {
  const purchaseOrder = detail.po_number
    ? {
        id: detail.po_id ?? 0,
        po_number: detail.po_number,
        supplier_tax_id: detail.supplier_tax_id ?? '',
        supplier_name: detail.supplier_name ?? 'Proveedor no identificado',
        currency: detail.currency ?? 'BOB',
        total_amount: detail.po_total ?? '0',
        status: detail.po_status ?? 'OPEN',
        issued_at: '',
        line_items: detail.po_line_items ?? [],
      }
    : null

  return {
    id: detail.id,
    verdict: detail.verdict,
    autoApproved: Boolean(detail.auto_approved),
    humanDecision: detail.human_decision,
    amountDelta: detail.amount_delta,
    note: detail.note ?? '',
    invoice: detail.raw_extraction,
    purchaseOrder,
    checks: detail.checks ?? [],
    trace: detail.trace ?? { steps: [], started_at: detail.created_at },
    sourceFilename: detail.source_filename,
    hasDocument: Boolean(detail.document_path),
    createdAt: detail.created_at,
  }
}
