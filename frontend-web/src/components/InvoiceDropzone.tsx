import { FileText, LoaderCircle, Upload, X } from 'lucide-react'
import { motion } from 'motion/react'
import { useDropzone } from 'react-dropzone'

interface InvoiceDropzoneProps {
  file: File | null
  isAnalyzing: boolean
  error?: string
  onSelect: (file: File) => void
  onClear: () => void
  onAnalyze: () => void
}

const ACCEPTED_FILES = {
  'image/jpeg': ['.jpg', '.jpeg'],
  'image/png': ['.png'],
  'image/webp': ['.webp'],
  'application/pdf': ['.pdf'],
}

function humanSize(bytes: number): string {
  return `${(bytes / 1024 / 1024).toFixed(bytes >= 1024 * 1024 ? 1 : 2)} MB`
}

export function InvoiceDropzone({ file, isAnalyzing, error, onSelect, onClear, onAnalyze }: InvoiceDropzoneProps) {
  const { getRootProps, getInputProps, isDragActive, open, fileRejections } = useDropzone({
    accept: ACCEPTED_FILES,
    maxSize: 10 * 1024 * 1024,
    maxFiles: 1,
    multiple: false,
    noClick: true,
    onDropAccepted: ([selected]) => {
      if (selected) onSelect(selected)
    },
  })

  const rejection = fileRejections.at(0)
  const rejectionMessage = rejection
    ? rejection.errors.some((item) => item.code === 'file-too-large')
      ? 'El archivo supera el límite de 10 MB.'
      : 'Selecciona una imagen JPG, PNG, WEBP o un PDF.'
    : error

  return (
    <section className="upload-card" aria-labelledby="upload-title">
      <div className="section-kicker">NUEVA CONCILIACIÓN</div>
      <div className="upload-heading">
        <div>
          <h2 id="upload-title">Trae la factura a la mesa de revisión.</h2>
          <p>El documento se procesa localmente y se contrasta con la orden autorizada.</p>
        </div>
      </div>

      <div {...getRootProps()} className={`dropzone ${isDragActive ? 'is-dragging' : ''} ${file ? 'has-file' : ''}`}>
        <input {...getInputProps()} />
        {file ? (
          <div className="file-ready">
            <div className="file-icon"><FileText size={22} strokeWidth={1.65} /></div>
            <div className="file-name">
              <strong>{file.name}</strong>
              <span>{humanSize(file.size)} · Listo para analizar</span>
            </div>
            {!isAnalyzing && (
              <button className="icon-button" type="button" onClick={onClear} aria-label="Quitar archivo">
                <X size={18} />
              </button>
            )}
          </div>
        ) : (
          <>
            <div className="upload-icon"><Upload size={26} strokeWidth={1.45} /></div>
            <strong>{isDragActive ? 'Suelta el documento aquí' : 'Arrastra una factura aquí'}</strong>
            <span>JPG, PNG, WEBP o PDF · hasta 10 MB</span>
            <button type="button" className="text-button" onClick={open}>Seleccionar archivo</button>
          </>
        )}
      </div>

      {rejectionMessage && <p className="form-error" role="alert">{rejectionMessage}</p>}

      <div className="upload-actions">
        {file && !isAnalyzing && (
          <button type="button" className="secondary-button" onClick={open}>Cambiar archivo</button>
        )}
        <motion.button
          type="button"
          className="primary-button analyze-button"
          disabled={!file || isAnalyzing}
          onClick={onAnalyze}
          whileHover={!file || isAnalyzing ? undefined : { y: -2 }}
          whileTap={!file || isAnalyzing ? undefined : { scale: 0.98 }}
        >
          {isAnalyzing ? <LoaderCircle size={18} className="spin" /> : <FileText size={18} />}
          {isAnalyzing ? 'Analizando documento' : 'Analizar documento'}
        </motion.button>
      </div>

      {isAnalyzing && <p className="processing-note">Esto puede tardar unos segundos. Mantén esta ventana abierta.</p>}
    </section>
  )
}
