import type { CheckStatus, HumanDecision, Verdict } from '../api/types'

export function formatMoney(value: string | null | undefined, currency = 'BOB'): string {
  if (value === null || value === undefined || value === '') return '—'

  const source = String(value).trim()
  const negative = source.startsWith('-')
  const unsigned = negative || source.startsWith('+') ? source.slice(1) : source
  const [integerRaw = '0', fractionRaw = ''] = unsigned.split('.')
  const integer = integerRaw.replace(/^0+(?=\d)/, '') || '0'
  const grouped = integer.replace(/\B(?=(\d{3})+(?!\d))/g, '.')
  const fraction = `${fractionRaw}00`.slice(0, 2)
  const symbol = currency === 'BOB' ? 'Bs' : currency
  return `${symbol} ${negative ? '−' : ''}${grouped},${fraction}`
}

export function formatQuantity(value: string | null | undefined): string {
  if (value === null || value === undefined || value === '') return '—'
  const [integer, fraction = ''] = String(value).split('.')
  const trimmed = fraction.replace(/0+$/, '')
  return trimmed ? `${integer},${trimmed}` : integer
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('es-BO', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  }).format(date)
}

export const verdictMeta: Record<Verdict, { label: string; tone: string; description: string }> = {
  MATCH: {
    label: 'Sin diferencias',
    tone: 'success',
    description: 'Los importes y las validaciones coinciden con la orden autorizada.',
  },
  MISMATCH: {
    label: 'Diferencia detectada',
    tone: 'danger',
    description: 'La factura requiere una decisión antes de continuar.',
  },
  NO_PO_FOUND: {
    label: 'Sin orden asociada',
    tone: 'warning',
    description: 'No se encontró una orden de compra para contrastar esta factura.',
  },
  UNCERTAIN: {
    label: 'Lectura incompleta',
    tone: 'warning',
    description: 'Faltan datos confiables para emitir una conciliación definitiva.',
  },
}

export const checkMeta: Record<CheckStatus, { label: string; tone: string }> = {
  PASS: { label: 'Conforme', tone: 'success' },
  WARN: { label: 'Observación', tone: 'warning' },
  FAIL: { label: 'No conforme', tone: 'danger' },
  SKIPPED: { label: 'No evaluable', tone: 'neutral' },
}

export function decisionLabel(decision: HumanDecision, autoApproved: boolean): string {
  if (decision === 'APPROVED') return 'Aprobada por el operador'
  if (decision === 'ESCALATED') return 'Escalada a compras'
  return autoApproved ? 'Cumple los criterios automáticos' : 'Pendiente de decisión'
}

export const phaseLabel: Record<string, string> = {
  extraction: 'Lectura del documento',
  lookup: 'Consulta de orden',
  verification: 'Validaciones aplicadas',
  reasoning: 'Preparación del dictamen',
  persist: 'Registro de conciliación',
}
