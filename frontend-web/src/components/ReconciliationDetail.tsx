import {
  ArrowUpRight,
  CheckCircle2,
  CircleAlert,
  CircleX,
  Eye,
  FileSearch,
  Landmark,
  MinusCircle,
  ScrollText,
  ShieldCheck,
} from 'lucide-react'
import { motion } from 'motion/react'

import { api } from '../api/client'
import type { CheckStatus, ReconciliationView, Verdict } from '../api/types'
import { checkMeta, decisionLabel, formatDate, formatMoney, formatQuantity, phaseLabel, verdictMeta } from '../lib/format'

interface ReconciliationDetailProps {
  reconciliation: ReconciliationView
  onDecision: (decision: 'APPROVED' | 'ESCALATED') => void
  decisionPending: boolean
}

function VerdictIcon({ verdict }: { verdict: Verdict }) {
  if (verdict === 'MATCH') return <CheckCircle2 aria-hidden="true" />
  if (verdict === 'MISMATCH') return <CircleX aria-hidden="true" />
  if (verdict === 'NO_PO_FOUND') return <FileSearch aria-hidden="true" />
  return <CircleAlert aria-hidden="true" />
}

function CheckIcon({ status }: { status: CheckStatus }) {
  if (status === 'PASS') return <CheckCircle2 aria-hidden="true" />
  if (status === 'FAIL') return <CircleX aria-hidden="true" />
  if (status === 'WARN') return <CircleAlert aria-hidden="true" />
  return <MinusCircle aria-hidden="true" />
}

function DataList({ side, lines, currency }: {
  side: 'factura' | 'orden'
  lines: Array<{ description: string; quantity: string | null; unit_price: string | null; line_total: string | null }>
  currency: string
}) {
  const isInvoice = side === 'factura'
  return (
    <div className="line-list">
      <div className="line-list-title">
        <span>{isInvoice ? 'Documento recibido' : 'Orden autorizada'}</span>
        <strong>{lines.length} línea{lines.length === 1 ? '' : 's'}</strong>
      </div>
      {lines.length === 0 ? (
        <p className="line-empty">No hay líneas disponibles.</p>
      ) : lines.map((line, index) => (
        <div className="invoice-line" key={`${side}-${index}-${line.description}`}>
          <strong>{line.description || 'Descripción no disponible'}</strong>
          <div>
            <span>{formatQuantity(line.quantity)} unid.</span>
            <span>× {formatMoney(line.unit_price, currency)}</span>
            <b>{formatMoney(line.line_total, currency)}</b>
          </div>
        </div>
      ))}
    </div>
  )
}

function FactCell({ label, value }: { label: string; value: string }) {
  return (
    <div className="fact-cell">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  )
}

export function ReconciliationDetail({ reconciliation, onDecision, decisionPending }: ReconciliationDetailProps) {
  const { invoice, purchaseOrder, verdict, autoApproved, humanDecision, amountDelta } = reconciliation
  const meta = verdictMeta[verdict]
  const currency = purchaseOrder?.currency ?? invoice?.currency ?? 'BOB'
  const hasDelta = amountDelta !== null && amountDelta !== undefined
  const deltaLabel = !hasDelta ? 'No evaluable' : amountDelta === '0' || amountDelta === '0.00' ? 'Sin diferencia' : formatMoney(amountDelta, currency)

  return (
    <section className="result-section" aria-labelledby="result-title">
      <div className="section-heading">
        <div>
          <div className="section-kicker">DICTAMEN DE CONCILIACIÓN</div>
          <h2 id="result-title">La evidencia, antes de la decisión.</h2>
        </div>
        <span className={`decision-state ${humanDecision.toLowerCase()}`}>{decisionLabel(humanDecision, autoApproved)}</span>
      </div>

      <motion.article
        className={`verdict-card tone-${meta.tone}`}
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.36, ease: 'easeOut' }}
      >
        <div className="verdict-topline">
          <div className="verdict-icon"><VerdictIcon verdict={verdict} /></div>
          <div>
            <span className="eyebrow">{meta.label}</span>
            <h3>{invoice?.invoice_number ?? reconciliation.sourceFilename}</h3>
            <p>{invoice?.supplier_name ?? purchaseOrder?.supplier_name ?? 'Proveedor no identificado'}</p>
          </div>
          <div className="delta-block">
            <span>Diferencia</span>
            <strong>{deltaLabel}</strong>
          </div>
        </div>
        <p className="verdict-description">{meta.description}</p>

        <div className="fact-grid">
          <FactCell label="Orden de compra" value={purchaseOrder?.po_number ?? 'Sin orden asociada'} />
          <FactCell label="Total factura" value={formatMoney(invoice?.total_amount, currency)} />
          <FactCell label="Total autorizado" value={formatMoney(purchaseOrder?.total_amount, currency)} />
          <FactCell label="NIT" value={invoice?.supplier_tax_id ?? purchaseOrder?.supplier_tax_id ?? '—'} />
        </div>

        <div className="conclusion">
          <span>Conclusión</span>
          <p>{reconciliation.note || 'No se registró una nota para esta conciliación.'}</p>
        </div>

        {humanDecision === 'PENDING' ? (
          <div className="decision-actions">
            <motion.button
              type="button"
              className="primary-button"
              disabled={decisionPending}
              onClick={() => onDecision('APPROVED')}
              whileHover={decisionPending ? undefined : { y: -2 }}
              whileTap={decisionPending ? undefined : { scale: 0.98 }}
            >
              <ShieldCheck size={18} /> Aprobar factura
            </motion.button>
            <button type="button" className="danger-button" disabled={decisionPending} onClick={() => onDecision('ESCALATED')}>
              <Landmark size={18} /> Escalar a compras
            </button>
            {reconciliation.hasDocument && (
              <a className="secondary-button document-link" href={api.documentUrl(reconciliation.id)} target="_blank" rel="noreferrer">
                <Eye size={18} /> Ver documento <ArrowUpRight size={15} />
              </a>
            )}
          </div>
        ) : (
          <div className="completed-decision">
            <CheckCircle2 size={18} /> {decisionLabel(humanDecision, autoApproved)}
            {reconciliation.hasDocument && (
              <a href={api.documentUrl(reconciliation.id)} target="_blank" rel="noreferrer">Abrir evidencia <ArrowUpRight size={14} /></a>
            )}
          </div>
        )}
      </motion.article>

      <div className="detail-grid">
        <article className="content-panel comparison-panel">
          <div className="panel-heading">
            <div>
              <span className="panel-kicker">EVIDENCIA DE IMPORTES</span>
              <h3>Comparación detallada</h3>
            </div>
            <FileSearch size={20} aria-hidden="true" />
          </div>
          <div className="line-columns">
            <DataList side="factura" lines={invoice?.line_items ?? []} currency={currency} />
            <DataList side="orden" lines={purchaseOrder?.line_items ?? []} currency={currency} />
          </div>
        </article>

        <article className="content-panel checks-panel">
          <div className="panel-heading">
            <div>
              <span className="panel-kicker">REGLAS DETERMINISTAS</span>
              <h3>Validaciones aplicadas</h3>
            </div>
            <ShieldCheck size={20} aria-hidden="true" />
          </div>
          <div className="checks-list">
            {reconciliation.checks.length === 0 ? <p className="line-empty">No hay validaciones disponibles.</p> : reconciliation.checks.map((check) => {
              const checkInfo = checkMeta[check.status]
              return (
                <details className={`check-row tone-${checkInfo.tone}`} key={check.name}>
                  <summary>
                    <span className="check-icon"><CheckIcon status={check.status} /></span>
                    <span>{check.label}</span>
                    <small>{checkInfo.label}</small>
                  </summary>
                  <p>{check.detail}</p>
                </details>
              )
            })}
          </div>
        </article>
      </div>

      <details className="audit-panel">
        <summary><ScrollText size={18} /> Auditoría y trazabilidad <span>Ver detalle</span></summary>
        <div className="audit-content">
          {reconciliation.createdAt && <p className="audit-date">Registrada el {formatDate(reconciliation.createdAt)}</p>}
          {reconciliation.trace.steps.length === 0 ? <p className="line-empty">No hay trazabilidad disponible.</p> : reconciliation.trace.steps.map((step, index) => (
            <div className="audit-step" key={`${step.phase}-${index}`}>
              <span>{String(index + 1).padStart(2, '0')}</span>
              <div>
                <strong>{phaseLabel[step.phase] ?? step.phase}</strong>
                <p>{step.summary}</p>
              </div>
              <small>{step.duration_ms ? `${step.duration_ms} ms` : ''}</small>
            </div>
          ))}
        </div>
      </details>
    </section>
  )
}
