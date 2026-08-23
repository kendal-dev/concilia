import {
  ArrowUp,
  Bot,
  FileSearch,
  FileText,
  LoaderCircle,
  Paperclip,
  ShieldCheck,
  Sparkles,
  UserRound,
  X,
} from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'
import { type FormEvent, useEffect, useRef, useState } from 'react'

import type { ReconciliationView } from '../api/types'
import { formatMoney, verdictMeta } from '../lib/format'

interface ChatEntry {
  id: string
  role: 'assistant' | 'user'
  content: string
  attachment?: string
  result?: ReconciliationView
}

interface OperationsChatProps {
  file: File | null
  latest: ReconciliationView | null
  isAnalyzing: boolean
  error?: string
  onSelectFile: (file: File | null) => void
  onAnalyze: () => void
  onOpenResult: () => void
}

const QUICK_PROMPTS = [
  'Conciliar una factura',
  '¿Qué discrepancias detectas?',
  'Revisar casos pendientes',
]

function assistantReply(prompt: string): string {
  const normalized = prompt.toLocaleLowerCase('es')
  if (normalized.includes('discrep') || normalized.includes('diferencia')) {
    return 'Adjunta una factura para contrastar importes, proveedor, moneda y líneas contra la orden de compra. Te devolveré una explicación breve y la evidencia de cada validación.'
  }
  if (normalized.includes('riesgo') || normalized.includes('crédito')) {
    return 'El flujo de riesgo post-trigger está definido en la hoja de ruta: reunir documentos, resumir exposición, preparar una nota y proponer el siguiente responsable.'
  }
  if (normalized.includes('pago') || normalized.includes('transacci')) {
    return 'El análisis de pagos está planificado para priorizar anomalías, duplicados y cambios relevantes. Hoy el flujo ejecutable es la conciliación documental de facturas.'
  }
  return 'Puedo iniciar una conciliación real desde aquí. Adjunta un PDF, una fotografía o un escaneo de factura y presiona enviar para ejecutar el análisis local.'
}

export function OperationsChat({
  file,
  latest,
  isAnalyzing,
  error,
  onSelectFile,
  onAnalyze,
  onOpenResult,
}: OperationsChatProps) {
  const [draft, setDraft] = useState('')
  const [entries, setEntries] = useState<ChatEntry[]>([
    {
      id: 'welcome',
      role: 'assistant',
      content: 'Hola, soy tu agente local de operaciones. Puedo leer una factura, contrastarla con la orden de compra y explicarte qué requiere atención.',
    },
  ])
  const inputRef = useRef<HTMLInputElement>(null)
  const listRef = useRef<HTMLDivElement>(null)
  const lastResultId = useRef<number | null>(null)

  useEffect(() => {
    if (!latest || lastResultId.current === latest.id) return
    lastResultId.current = latest.id
    setEntries((current) => [
      ...current,
      {
        id: `result-${latest.id}`,
        role: 'assistant',
        content: latest.note || verdictMeta[latest.verdict].description,
        result: latest,
      },
    ])
  }, [latest])

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: 'smooth' })
  }, [entries, isAnalyzing])

  function sendPrompt(prompt: string) {
    const value = prompt.trim()
    if (!value) return
    setEntries((current) => [
      ...current,
      { id: `user-${Date.now()}`, role: 'user', content: value },
      { id: `assistant-${Date.now() + 1}`, role: 'assistant', content: assistantReply(value) },
    ])
    setDraft('')
  }

  function submit(event: FormEvent) {
    event.preventDefault()
    if (isAnalyzing) return
    if (file) {
      setEntries((current) => [
        ...current,
        {
          id: `file-${Date.now()}`,
          role: 'user',
          content: draft.trim() || 'Analiza esta factura y señala lo que requiere atención.',
          attachment: file.name,
        },
      ])
      setDraft('')
      onAnalyze()
      return
    }
    sendPrompt(draft)
  }

  return (
    <section className="assistant-workspace" aria-label="Asistente de operaciones">
      <div className="assistant-intro">
        <div>
          <span className="section-kicker">AGENTE DE CONCILIACIÓN</span>
          <h1>¿Qué operación revisamos hoy?</h1>
          <p>Conversaciones claras, evidencia verificable y decisiones siempre bajo control humano.</p>
        </div>
        <div className="privacy-pill"><ShieldCheck size={15} /> Los documentos permanecen en este equipo</div>
      </div>

      <div className="chat-surface">
        <div className="chat-thread" ref={listRef} aria-live="polite">
          {entries.map((entry) => (
            <motion.article
              key={entry.id}
              className={`chat-message ${entry.role}`}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
            >
              <div className="message-avatar">
                {entry.role === 'assistant' ? <Bot size={17} /> : <UserRound size={16} />}
              </div>
              <div className="message-body">
                <span className="message-author">{entry.role === 'assistant' ? 'Concilia' : 'Tú'}</span>
                <p>{entry.content}</p>
                {entry.attachment && (
                  <div className="message-attachment"><FileText size={16} /><span>{entry.attachment}</span></div>
                )}
                {entry.result && (
                  <button type="button" className={`chat-result tone-${verdictMeta[entry.result.verdict].tone}`} onClick={onOpenResult}>
                    <span className="result-symbol"><FileSearch size={19} /></span>
                    <span>
                      <small>ANÁLISIS COMPLETADO</small>
                      <strong>{verdictMeta[entry.result.verdict].label}</strong>
                      <em>Diferencia: {formatMoney(entry.result.amountDelta, entry.result.invoice?.currency ?? 'BOB')}</em>
                    </span>
                    <span className="result-open">Ver evidencia</span>
                  </button>
                )}
              </div>
            </motion.article>
          ))}

          {isAnalyzing && (
            <motion.article className="chat-message assistant" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
              <div className="message-avatar"><Bot size={17} /></div>
              <div className="message-body">
                <span className="message-author">Concilia</span>
                <div className="thinking-line"><LoaderCircle size={15} className="spin" /> Leyendo el documento y verificando evidencias…</div>
              </div>
            </motion.article>
          )}
        </div>

        <div className="chat-bottom">
          {entries.length === 1 && (
            <div className="quick-prompts">
              {QUICK_PROMPTS.map((prompt) => (
                <button
                  type="button"
                  key={prompt}
                  onClick={() => sendPrompt(prompt)}
                >
                  <Sparkles size={13} /> {prompt}
                </button>
              ))}
            </div>
          )}

          <AnimatePresence>
            {file && (
              <motion.div className="composer-file" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
                <FileText size={15} />
                <span>{file.name}</span>
                <button type="button" onClick={() => onSelectFile(null)} aria-label="Quitar archivo"><X size={14} /></button>
              </motion.div>
            )}
          </AnimatePresence>

          <form className="chat-composer" onSubmit={submit}>
            <label className="attach-button" title="Adjuntar factura">
              <Paperclip size={19} />
              <input
                ref={inputRef}
                type="file"
                accept="image/jpeg,image/png,image/webp,application/pdf"
                onChange={(event) => onSelectFile(event.target.files?.[0] ?? null)}
                disabled={isAnalyzing}
              />
            </label>
            <input
              type="text"
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              placeholder={file ? 'Añade una instrucción para el análisis…' : 'Pregunta o adjunta una factura…'}
              disabled={isAnalyzing}
            />
            <button className="send-button" type="submit" disabled={isAnalyzing || (!draft.trim() && !file)} aria-label="Enviar">
              {isAnalyzing ? <LoaderCircle size={18} className="spin" /> : <ArrowUp size={19} />}
            </button>
          </form>
          {error && <p className="composer-error">{error}</p>}
          <p className="composer-note">Concilia puede equivocarse. Verifica la evidencia antes de decidir.</p>
        </div>
      </div>
    </section>
  )
}
