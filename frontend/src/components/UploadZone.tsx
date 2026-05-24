import { useRef, useState } from 'react'
import type { Peer } from '../types'

interface UploadZoneProps {
  peers: Peer[]
  onUpload: (file: File, onProgress?: (pct: number) => void, allowedPeers?: string[], filePassword?: string) => Promise<void>
}

export default function UploadZone({ peers, onUpload }: UploadZoneProps) {
  const [dragging, setDragging] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [uploadPct, setUploadPct] = useState(0)
  const [message, setMessage] = useState<{ text: string; ok: boolean } | null>(null)
  const [selectedPeers, setSelectedPeers] = useState<string[]>([])
  const [filePassword, setFilePassword] = useState('')
  const [showControls, setShowControls] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const togglePeer = (peerId: string) => {
    setSelectedPeers(prev =>
      prev.includes(peerId) ? prev.filter(p => p !== peerId) : [...prev, peerId]
    )
  }

  const handle = async (file: File) => {
    setUploading(true)
    setUploadPct(0)
    setMessage(null)
    try {
      await onUpload(
        file,
        (pct) => setUploadPct(pct),
        selectedPeers.length ? selectedPeers : undefined,
        filePassword || undefined,
      )
      setMessage({ text: `"${file.name}" published to network`, ok: true })
    } catch (err) {
      setMessage({ text: String(err), ok: false })
    } finally {
      setUploading(false)
      setUploadPct(0)
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
    <div className="space-y-2">
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
          {uploading ? `Publishing… ${uploadPct}%` : dragging ? 'Drop to publish' : 'Drop a file or click to browse'}
        </p>
        <p className="text-xs text-slate-600 mt-1">
          {selectedPeers.length > 0
            ? `Restricted to: ${selectedPeers.join(', ')}`
            : filePassword
            ? 'Password protected · shared with all peers'
            : 'File will be shared with all peers automatically'}
        </p>

        {uploading && (
          <div className="mt-3 w-full max-w-xs">
            <div className="h-1.5 rounded bg-slate-800 overflow-hidden">
              <div
                className="h-full bg-accent transition-all duration-200"
                style={{ width: `${uploadPct}%` }}
              />
            </div>
          </div>
        )}

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

      {/* Access controls toggle */}
      <button
        onClick={() => setShowControls(v => !v)}
        className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-300 transition-colors px-1"
      >
        <svg className={`h-3 w-3 transition-transform ${showControls ? 'rotate-90' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
        </svg>
        Access controls
        {(selectedPeers.length > 0 || filePassword) && (
          <span className="ml-1 rounded-full bg-accent px-1.5 py-0.5 text-[10px] text-white">
            {[selectedPeers.length > 0 && 'restricted', filePassword && 'password'].filter(Boolean).join(' · ')}
          </span>
        )}
      </button>

      {showControls && (
        <div className="rounded-lg border border-border bg-card px-4 py-3 space-y-3">
          {/* Peer restriction */}
          <div>
            <p className="text-xs text-slate-400 font-medium mb-1.5">Restrict to peers <span className="text-slate-600 font-normal">(leave empty = public)</span></p>
            {peers.length === 0 ? (
              <p className="text-xs text-slate-600 italic">No peers discovered yet</p>
            ) : (
              <div className="flex flex-wrap gap-2">
                {peers.map(p => (
                  <label key={p.peer_id} className="flex items-center gap-1.5 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={selectedPeers.includes(p.peer_id)}
                      onChange={() => togglePeer(p.peer_id)}
                      className="accent-accent"
                    />
                    <span className="text-xs text-slate-300">{p.peer_id}</span>
                  </label>
                ))}
              </div>
            )}
          </div>

          {/* File password */}
          <div>
            <p className="text-xs text-slate-400 font-medium mb-1.5">File password <span className="text-slate-600 font-normal">(optional — encrypts content)</span></p>
            <div className="flex items-center gap-2">
              <input
                type="password"
                value={filePassword}
                onChange={e => setFilePassword(e.target.value)}
                placeholder="Leave empty for no encryption…"
                className="flex-1 rounded bg-surface border border-border px-2 py-1.5 text-xs text-white placeholder-slate-600 focus:outline-none focus:border-accent"
              />
              {filePassword && (
                <button onClick={() => setFilePassword('')} className="text-slate-600 hover:text-slate-400 text-xs">Clear</button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
