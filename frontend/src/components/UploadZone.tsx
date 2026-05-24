import { useRef, useState } from 'react'

interface UploadZoneProps {
  onUpload: (file: File) => Promise<void>
}

export default function UploadZone({ onUpload }: UploadZoneProps) {
  const [dragging, setDragging] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [message, setMessage] = useState<{ text: string; ok: boolean } | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const handle = async (file: File) => {
    setUploading(true)
    setMessage(null)
    try {
      await onUpload(file)
      setMessage({ text: `"${file.name}" published to network`, ok: true })
    } catch (err) {
      setMessage({ text: String(err), ok: false })
    } finally {
      setUploading(false)
    }
  }

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragging(false)
    const file = e.dataTransfer.files[0]
    if (file) handle(file)
  }

  const onFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) handle(file)
    e.target.value = ''
  }

  return (
    <div
      onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
      onClick={() => !uploading && inputRef.current?.click()}
      className={`relative flex flex-col items-center justify-center rounded-lg border-2 border-dashed p-8 transition-all cursor-pointer select-none ${
        dragging
          ? 'border-accent bg-blue-950/20'
          : 'border-border hover:border-accent-dim hover:bg-white/[0.02]'
      } ${uploading ? 'cursor-wait opacity-70' : ''}`}
    >
      <input
        ref={inputRef}
        type="file"
        className="hidden"
        onChange={onFileChange}
        disabled={uploading}
      />

      {uploading ? (
        <svg className="h-8 w-8 animate-spin text-accent mb-3" viewBox="0 0 24 24" fill="none">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
      ) : (
        <svg className={`h-8 w-8 mb-3 transition-colors ${dragging ? 'text-accent' : 'text-slate-600'}`}
          fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
            d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
        </svg>
      )}

      <p className={`text-sm font-medium ${dragging ? 'text-accent' : 'text-slate-400'}`}>
        {uploading ? 'Publishing…' : dragging ? 'Drop to publish' : 'Drop a file or click to browse'}
      </p>
      <p className="text-xs text-slate-600 mt-1">File will be shared with all peers automatically</p>

      {message && (
        <div className={`mt-3 text-xs px-3 py-1.5 rounded ${
          message.ok
            ? 'bg-green-950 text-green-400 border border-green-900'
            : 'bg-red-950 text-red-400 border border-red-900'
        }`}>
          {message.text}
        </div>
      )}
    </div>
  )
}
