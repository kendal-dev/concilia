import * as Dialog from '@radix-ui/react-dialog'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Activity,
  Bot,
  CheckCircle2,
  CircleAlert,
  FileText,
  History,
  Landmark,
  LoaderCircle,
  ShieldCheck,
  X,
} from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'
import { lazy, Suspense, useEffect, useMemo, useState } from 'react'

import { api, ApiError } from './api/client'
import { fromDetail, fromReconcile, type ReconciliationView } from './api/types'
import emblem from './assets/brand/concilia-emblem.png'
import { InvoiceDropzone } from './components/InvoiceDropzone'
import { OperationsChat } from './components/OperationsChat'
import { ReconciliationDetail } from './components/ReconciliationDetail'
import { ReviewsPanel } from './components/ReviewsPanel'
import './App.css'

type Page = 'assistant' | 'reconcile' | 'reviews'
type Confirmation = { id: number; decision: 'APPROVED' | 'ESCALATED' } | null

const EMPTY_STATS = { procesadas: 0, auto_aprobadas: 0, a_revisar: 0, pendientes: 0, escaladas: 0 }
const SealScene = lazy(() => import('./components/SealScene').then((module) => ({ default: module.SealScene })))

function readableError(error: unknown): string | undefined {
  if (!error) return undefined
  if (error instanceof ApiError) return error.message
  return 'Ocurrió un error inesperado. Intenta nuevamente.'
}

function StatCard({ label, value, icon: Icon, tone = 'default' }: {
  label: string
  value: number
  icon: typeof Activity
  tone?: 'default' | 'success' | 'warning' | 'danger'
}) {
  return (
    <motion.article className={`stat-card tone-${tone}`} whileHover={{ y: -3 }} transition={{ duration: 0.18 }}>
      <div className="stat-icon"><Icon size={18} strokeWidth={1.7} /></div>
      <div><strong>{value}</strong><span>{label}</span></div>
    </motion.article>
  )
}

function App() {
  const queryClient = useQueryClient()
  const [page, setPage] = useState<Page>('assistant')
  const [file, setFile] = useState<File | null>(null)
  const [latest, setLatest] = useState<ReconciliationView | null>(null)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [confirmation, setConfirmation] = useState<Confirmation>(null)

  const health = useQuery({ queryKey: ['health'], queryFn: api.health, refetchInterval: 20_000, retry: 1 })
  const stats = useQuery({ queryKey: ['stats'], queryFn: api.stats, refetchInterval: 20_000, retry: 1 })
  const reviews = useQuery({ queryKey: ['reconciliations'], queryFn: api.reconciliations, retry: 1 })
  const reviewDetail = useQuery({
    queryKey: ['reconciliation', selectedId],
    queryFn: () => api.reconciliation(selectedId as number),
    enabled: selectedId !== null,
  })

  const upload = useMutation({
    mutationFn: api.reconcile,
    onSuccess: (result) => {
      setLatest(fromReconcile(result))
      queryClient.invalidateQueries({ queryKey: ['stats'] })
      queryClient.invalidateQueries({ queryKey: ['reconciliations'] })
    },
  })

  const decision = useMutation({
    mutationFn: ({ id, action }: { id: number; action: 'APPROVED' | 'ESCALATED' }) => api.decision(id, action),
    onSuccess: (response) => {
      setLatest((current) => current?.id === response.id ? { ...current, humanDecision: response.human_decision } : current)
      queryClient.invalidateQueries({ queryKey: ['stats'] })
      queryClient.invalidateQueries({ queryKey: ['reconciliations'] })
      queryClient.invalidateQueries({ queryKey: ['reconciliation', response.id] })
      setConfirmation(null)
    },
  })

  const currentReview = useMemo(
    () => reviewDetail.data ? fromDetail(reviewDetail.data) : null,
    [reviewDetail.data],
  )
  const currentStats = stats.data ?? EMPTY_STATS
  const healthIsReady = health.data?.status === 'ok' && health.data.db === 'connected'
  const uploadError = readableError(upload.error)
  const decisionError = readableError(decision.error)
  const sealPhase = upload.isPending ? 'analyzing' : latest?.verdict ?? 'idle'

  useEffect(() => {
    window.scrollTo({ top: 0, behavior: 'instant' })
  }, [page])

  function selectFile(nextFile: File | null) {
    setFile(nextFile)
    setLatest(null)
    upload.reset()
  }

  function analyze() {
    if (file) upload.mutate(file)
  }

  function openReview(id: number) {
    setSelectedId(id)
    setPage('reviews')
  }

  function confirmDecision() {
    if (!confirmation) return
    decision.mutate({ id: confirmation.id, action: confirmation.decision })
  }

  function openLatestResult() {
    window.requestAnimationFrame(() => document.querySelector('#assistant-result')?.scrollIntoView({ behavior: 'smooth' }))
  }

  const pageTitle = {
    assistant: ['Agente operativo', 'Asistente local'],
    reconcile: ['Flujo activo', 'Conciliación de facturas'],
    reviews: ['Control humano', 'Revisiones'],
  }[page]

  return (
    <div className="app-shell">
      <aside className="app-sidebar">
        <button className="brand sidebar-brand" type="button" onClick={() => setPage('assistant')} aria-label="Ir al asistente Concilia">
          <span className="brand-mark"><img src={emblem} alt="" /></span>
          <span>CONCILIA</span>
        </button>

        <button type="button" className="new-operation" onClick={() => setPage('assistant')}>
          <Bot size={17} /> Nueva conversación <span>+</span>
        </button>

        <nav className="sidebar-nav" aria-label="Navegación principal">
          <span className="sidebar-label">ESPACIO DE TRABAJO</span>
          <button type="button" className={page === 'assistant' ? 'is-active' : ''} onClick={() => setPage('assistant')}>
            <Bot size={17} /> Asistente
          </button>
          <button type="button" className={page === 'reconcile' ? 'is-active' : ''} onClick={() => setPage('reconcile')}>
            <FileText size={17} /> Conciliar factura
          </button>
          <button type="button" className={page === 'reviews' ? 'is-active' : ''} onClick={() => setPage('reviews')}>
            <History size={17} /> Revisiones
          </button>
        </nav>

        <div className={`sidebar-connection ${healthIsReady ? 'is-ready' : 'is-offline'}`}>
          {health.isLoading ? <LoaderCircle size={15} className="spin" /> : healthIsReady ? <Activity size={15} /> : <CircleAlert size={15} />}
          <span><strong>{healthIsReady ? 'Sistema operativo' : 'Servicio no disponible'}</strong><small>{healthIsReady ? 'Procesamiento en este equipo' : 'Revisa el servicio local'}</small></span>
        </div>
      </aside>

      <div className="workspace-frame">
      <header className="topbar">
        <div className="workspace-title"><span>{pageTitle[0]}</span><strong>{pageTitle[1]}</strong></div>
        <div className={`connection-status ${healthIsReady ? 'is-ready' : 'is-offline'}`} title={healthIsReady ? 'Servicio local disponible' : 'No se puede alcanzar el servicio local'}>
          {health.isLoading ? <LoaderCircle size={15} className="spin" /> : healthIsReady ? <Activity size={15} /> : <CircleAlert size={15} />}
          <span>{healthIsReady ? 'Procesamiento local' : 'Servicio no disponible'}</span>
        </div>
      </header>

      <main>
        <AnimatePresence mode="wait">
          {page === 'assistant' ? (
            <motion.div key="assistant" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
              <OperationsChat
                file={file}
                latest={latest}
                isAnalyzing={upload.isPending}
                error={uploadError}
                onSelectFile={selectFile}
                onAnalyze={analyze}
                onOpenResult={openLatestResult}
              />
              {latest && (
                <motion.div id="assistant-result" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}>
                  <ReconciliationDetail
                    reconciliation={latest}
                    decisionPending={decision.isPending}
                    onDecision={(action) => setConfirmation({ id: latest.id, decision: action })}
                  />
                </motion.div>
              )}
            </motion.div>
          ) : page === 'reconcile' ? (
            <motion.div key="reconcile" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
              <section className="hero-grid">
                <div className="hero-copy">
                  <div className="section-kicker">RECONCILIACIÓN LOCAL</div>
                  <h1>Una decisión clara<br />para cada factura.</h1>
                  <p>Contrasta cada documento con la orden autorizada, sin que la información salga de este equipo.</p>
                  <div className="hero-trust">
                    <ShieldCheck size={18} />
                    <span>Validaciones trazables y evidencia lista para revisar.</span>
                  </div>
                </div>
                <div className="hero-seal-wrap">
                  <div className="seal-orbit orbit-one" />
                  <div className="seal-orbit orbit-two" />
                  <Suspense fallback={<div className="seal-fallback" aria-hidden="true"><img src={emblem} alt="" /></div>}>
                    <SealScene phase={sealPhase} />
                  </Suspense>
                  <span className="seal-caption">Sello de conciliación</span>
                </div>
              </section>

              <section className="stats-row" aria-label="Resumen operativo">
                <StatCard label="Pendientes" value={currentStats.pendientes} icon={CircleAlert} tone="warning" />
                <StatCard label="Conformes" value={currentStats.auto_aprobadas} icon={CheckCircle2} tone="success" />
                <StatCard label="Escaladas" value={currentStats.escaladas} icon={Landmark} tone="danger" />
                <StatCard label="Procesadas" value={currentStats.procesadas} icon={FileText} />
              </section>

              <InvoiceDropzone
                file={file}
                isAnalyzing={upload.isPending}
                error={uploadError}
                onSelect={selectFile}
                onClear={() => selectFile(null)}
                onAnalyze={analyze}
              />

              <AnimatePresence>
                {latest && (
                  <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }}>
                    <ReconciliationDetail
                      reconciliation={latest}
                      decisionPending={decision.isPending}
                      onDecision={(action) => setConfirmation({ id: latest.id, decision: action })}
                    />
                  </motion.div>
                )}
              </AnimatePresence>
            </motion.div>
          ) : (
            <motion.div key="reviews" initial={{ opacity: 0, x: 12 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -12 }}>
              <ReviewsPanel
                rows={reviews.data ?? []}
                isLoading={reviews.isLoading}
                selectedId={selectedId}
                onSelect={openReview}
              />
              {reviewDetail.isError && <p className="form-error review-error">{readableError(reviewDetail.error)}</p>}
              {currentReview && (
                <ReconciliationDetail
                  reconciliation={currentReview}
                  decisionPending={decision.isPending}
                  onDecision={(action) => setConfirmation({ id: currentReview.id, decision: action })}
                />
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </main>

      <footer className="app-footer">
        <span>CONCILIA · Reconciliación documental</span>
        <span>La decisión siempre queda en manos del operador.</span>
      </footer>
      </div>

      <Dialog.Root open={confirmation !== null} onOpenChange={(open) => !open && !decision.isPending && setConfirmation(null)}>
        <Dialog.Portal>
          <Dialog.Overlay className="dialog-overlay" />
          <Dialog.Content className="decision-dialog" aria-describedby="decision-description">
            <button type="button" className="dialog-close" onClick={() => setConfirmation(null)} disabled={decision.isPending} aria-label="Cerrar">
              <X size={18} />
            </button>
            <div className={`dialog-emblem ${confirmation?.decision === 'ESCALATED' ? 'is-danger' : ''}`}>
              {confirmation?.decision === 'APPROVED' ? <ShieldCheck size={25} /> : <Landmark size={25} />}
            </div>
            <Dialog.Title>{confirmation?.decision === 'APPROVED' ? '¿Aprobar esta factura?' : '¿Escalar a compras?'}</Dialog.Title>
            <Dialog.Description id="decision-description">
              {confirmation?.decision === 'APPROVED'
                ? 'La aprobación quedará registrada como una decisión del operador.'
                : 'El caso quedará marcado para revisión por el área de compras.'}
            </Dialog.Description>
            {decisionError && <p className="form-error">{decisionError}</p>}
            <div className="dialog-actions">
              <button type="button" className="secondary-button" disabled={decision.isPending} onClick={() => setConfirmation(null)}>Cancelar</button>
              <button type="button" className={confirmation?.decision === 'APPROVED' ? 'primary-button' : 'danger-button'} disabled={decision.isPending} onClick={confirmDecision}>
                {decision.isPending && <LoaderCircle size={17} className="spin" />}
                {confirmation?.decision === 'APPROVED' ? 'Confirmar aprobación' : 'Confirmar escalamiento'}
              </button>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </div>
  )
}

export default App
