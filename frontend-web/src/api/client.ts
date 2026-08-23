import type {
  DecisionResponse,
  Health,
  ReconcileResult,
  ReconciliationDetail,
  ReconciliationRow,
  Stats,
} from './types'

// En el navegador Vite redirige /api al backend. En el binario Tauri no hay
// servidor Vite, por lo que se usa directamente el servicio local.
const isDesktop = typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window
const API_ROOT = import.meta.env.VITE_API_BASE_URL ?? (isDesktop ? 'http://127.0.0.1:8123' : '/api')

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

function errorMessage(payload: unknown): string {
  if (typeof payload === 'object' && payload !== null && 'detail' in payload) {
    const detail = (payload as { detail: unknown }).detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) return 'Hay datos incompletos o inválidos en la solicitud.'
  }
  return 'No fue posible completar la solicitud.'
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API_ROOT}${path}`, init)
  } catch {
    throw new ApiError(0, 'No se pudo conectar con el servicio local.')
  }

  if (!response.ok) {
    let payload: unknown = null
    try {
      payload = await response.json()
    } catch {
      // El detalle no siempre es JSON (por ejemplo, ante un proxy caído).
    }
    throw new ApiError(response.status, errorMessage(payload))
  }

  return response.json() as Promise<T>
}

export const api = {
  health: () => request<Health>('/health'),
  stats: () => request<Stats>('/stats'),
  reconciliations: () => request<ReconciliationRow[]>('/reconciliations?limit=50'),
  reconciliation: (id: number) => request<ReconciliationDetail>(`/reconciliations/${id}`),
  documentUrl: (id: number) => `${API_ROOT}/reconciliations/${id}/document`,
  async reconcile(file: File): Promise<ReconcileResult> {
    const body = new FormData()
    body.append('file', file)

    const controller = new AbortController()
    const timeout = window.setTimeout(() => controller.abort(), 120_000)
    try {
      return await request<ReconcileResult>('/reconcile', {
        method: 'POST',
        body,
        signal: controller.signal,
      })
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') {
        throw new ApiError(408, 'El análisis tardó demasiado. Intenta nuevamente.')
      }
      throw error
    } finally {
      window.clearTimeout(timeout)
    }
  },
  decision: (id: number, decision: 'APPROVED' | 'ESCALATED') =>
    request<DecisionResponse>(`/reconciliations/${id}/decision`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ decision, decided_by: 'operador' }),
    }),
}
