import { ChevronRight, Inbox, Search, SlidersHorizontal } from 'lucide-react'
import { useMemo, useState } from 'react'

import type { ReconciliationRow } from '../api/types'
import { decisionLabel, formatDate, formatMoney, verdictMeta } from '../lib/format'

interface ReviewsPanelProps {
  rows: ReconciliationRow[]
  isLoading: boolean
  selectedId: number | null
  onSelect: (id: number) => void
}

type Filter = 'ALL' | 'PENDING' | 'APPROVED' | 'ESCALATED'

const filters: Array<{ value: Filter; label: string }> = [
  { value: 'PENDING', label: 'Pendientes' },
  { value: 'APPROVED', label: 'Aprobadas' },
  { value: 'ESCALATED', label: 'Escaladas' },
  { value: 'ALL', label: 'Todas' },
]

export function ReviewsPanel({ rows, isLoading, selectedId, onSelect }: ReviewsPanelProps) {
  const [filter, setFilter] = useState<Filter>('PENDING')
  const [search, setSearch] = useState('')

  const filtered = useMemo(() => {
    const needle = search.trim().toLocaleLowerCase()
    return rows.filter((row) => {
      const matchesState = filter === 'ALL' || row.human_decision === filter
      const matchesSearch = !needle || [row.invoice_number, row.source_filename, row.supplier_name, row.po_number]
        .filter(Boolean)
        .some((value) => value?.toLocaleLowerCase().includes(needle))
      return matchesState && matchesSearch
    })
  }, [filter, rows, search])

  return (
    <section className="reviews-section" aria-labelledby="reviews-title">
      <div className="section-heading">
        <div>
          <div className="section-kicker">MESA DE DECISIONES</div>
          <h1 id="reviews-title">Revisiones que necesitan contexto.</h1>
          <p>Abre cualquier caso para contrastar el documento, la orden y las validaciones aplicadas.</p>
        </div>
      </div>

      <div className="review-toolbar">
        <label className="search-field">
          <Search size={18} aria-hidden="true" />
          <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Buscar factura o proveedor" />
        </label>
        <div className="filter-group" aria-label="Filtrar revisiones">
          <SlidersHorizontal size={17} aria-hidden="true" />
          {filters.map((item) => (
            <button
              type="button"
              key={item.value}
              className={filter === item.value ? 'is-active' : ''}
              onClick={() => setFilter(item.value)}
            >
              {item.label}
            </button>
          ))}
        </div>
      </div>

      <div className="review-table-wrap">
        <table className="review-table">
          <thead>
            <tr>
              <th>Factura</th>
              <th>Proveedor</th>
              <th>Orden</th>
              <th>Diferencia</th>
              <th>Estado</th>
              <th>Fecha</th>
              <th aria-label="Abrir caso" />
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr><td colSpan={7} className="table-message">Cargando revisiones…</td></tr>
            ) : filtered.length === 0 ? (
              <tr>
                <td colSpan={7} className="table-message empty-message">
                  <Inbox size={21} aria-hidden="true" />
                  No hay facturas que coincidan con este filtro.
                </td>
              </tr>
            ) : filtered.map((row) => {
              const meta = verdictMeta[row.verdict]
              return (
                <tr className={selectedId === row.id ? 'is-selected' : ''} key={row.id}>
                  <td><strong>{row.invoice_number ?? row.source_filename}</strong></td>
                  <td>{row.supplier_name ?? 'Proveedor no identificado'}</td>
                  <td>{row.po_number ?? 'Sin orden'}</td>
                  <td className={row.amount_delta && row.amount_delta !== '0.00' && row.amount_delta !== '0' ? 'delta-cell' : ''}>
                    {formatMoney(row.amount_delta, row.currency ?? 'BOB')}
                  </td>
                  <td><span className={`table-status tone-${meta.tone}`}>{decisionLabel(row.human_decision, Boolean(row.auto_approved))}</span></td>
                  <td>{formatDate(row.created_at)}</td>
                  <td>
                    <button type="button" className="open-case" onClick={() => onSelect(row.id)} aria-label={`Abrir ${row.invoice_number ?? row.source_filename}`}>
                      <ChevronRight size={18} />
                    </button>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </section>
  )
}
