import { useState } from 'react'
import type { NetworkFile } from '../types'
import { getFileStatus, formatBytes, truncateHash } from '../types'

interface FileTableProps {
  files: NetworkFile[]
  downloading: Set<string>
  onDownload: (hash: string, password?: string) => void
  onDelete: (hash: string) => void
  peerId: string
}

function StatusBadge({ file }: { file: NetworkFile }) {
  const status = getFileStatus(file)
  const base = 'inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium'

  if (status === 'Downloaded') {
    return <span className={`${base} bg-green-950 text-green-400 border border-green-900`}>Downloaded</span>
  }
  if (status === 'Partial') {
    return (
      <span className={`${base} bg-yellow-950 text-yellow-400 border border-yellow-900`}>
        Partial {file.local_chunks}/{file.chunks.length}
      </span>
    )
  }
  if (status === 'Available') {
    return <span className={`${base} bg-blue-950 text-accent border border-accent-dim`}>Available</span>
  }
  return <span className={`${base} bg-zinc-900 text-slate-500 border border-zinc-800`}>Unavailable</span>
}

function CopyButton({ text }: { text: string }) {
  const copy = () => { navigator.clipboard.writeText(text).catch(() => {}) }
  return (
    <button onClick={copy} title={text} className="ml-1 text-slate-600 hover:text-accent transition-colors">
      <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
          d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
      </svg>
    </button>
  )
}

function ChunkMap({ file, peerId }: { file: NetworkFile; peerId: string }) {
  return (
    <div className="px-4 pb-4 pt-1">
      <p className="text-xs text-slate-500 mb-2">Chunk distribution across peers</p>
      <div className="flex flex-wrap gap-1">
        {file.chunks.map(chunk => {
          const isLocal = file.peers[peerId]?.chunks.includes(chunk.index)
          const hasPeer = Object.values(file.peers).some(p => p.chunks.includes(chunk.index))
          return (
            <div
              key={chunk.index}
              title={`Chunk ${chunk.index} · ${formatBytes(chunk.size)}`}
              className={`w-6 h-6 rounded text-[9px] flex items-center justify-center font-mono select-none
                ${isLocal
                  ? 'bg-green-800 text-green-100'
                  : hasPeer
                  ? 'bg-accent/30 text-blue-300'
                  : 'bg-slate-800 text-slate-600'}`}
            >
              {chunk.index}
            </div>
          )
        })}
      </div>
      <div className="flex gap-4 mt-2 text-xs text-slate-600">
        <span><span className="inline-block w-2.5 h-2.5 rounded bg-green-800 mr-1 align-middle" />Local</span>
        <span><span className="inline-block w-2.5 h-2.5 rounded bg-accent/30 mr-1 align-middle" />Peer</span>
        <span><span className="inline-block w-2.5 h-2.5 rounded bg-slate-800 mr-1 align-middle" />Missing</span>
      </div>
    </div>
  )
}

export default function FileTable({ files, downloading, onDownload, onDelete, peerId }: FileTableProps) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [filePasswords, setFilePasswords] = useState<Record<string, string>>({})

  const toggleExpand = (hash: string) => {
    setExpanded(prev => {
      const next = new Set(prev)
      next.has(hash) ? next.delete(hash) : next.add(hash)
      return next
    })
  }

  if (files.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-slate-600">
        <svg className="h-12 w-12 mb-3 opacity-30" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1}
            d="M5 8h14M5 8a2 2 0 110-4h14a2 2 0 110 4M5 8v10a2 2 0 002 2h10a2 2 0 002-2V8m-9 4h4" />
        </svg>
        <p className="text-sm">No files on the network yet</p>
        <p className="text-xs mt-1">Upload a file to get started</p>
      </div>
    )
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-border text-xs text-slate-500 uppercase tracking-wider">
            <th className="pb-3 pl-4 text-left font-medium">Status</th>
            <th className="pb-3 text-left font-medium">Name</th>
            <th className="pb-3 text-right font-medium">Size</th>
            <th className="pb-3 text-center font-medium">Chunks</th>
            <th className="pb-3 text-center font-medium">Peers</th>
            <th className="pb-3 text-left font-medium">Hash</th>
            <th className="pb-3 pr-4 text-right font-medium">Action</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {files.map((file) => {
            const status = getFileStatus(file)
            const isDownloading = downloading.has(file.file_hash)
            const canDownload = status !== 'Downloaded' && status !== 'Unavailable'
            const peerCount = Object.keys(file.peers).length
            const isExpanded = expanded.has(file.file_hash)
            const progress = file.chunks.length > 0
              ? Math.round((file.local_chunks / file.chunks.length) * 100)
              : 0

            return (
              <>
                <tr
                  key={file.file_hash}
                  onClick={() => toggleExpand(file.file_hash)}
                  className="hover:bg-white/[0.02] transition-colors cursor-pointer"
                >
                  <td className="py-3 pl-4">
                    <StatusBadge file={file} />
                  </td>
                  <td className="py-3 max-w-[200px]">
                    <div className="flex items-center gap-1">
                      <span className="truncate text-white font-medium" title={file.name}>
                        {file.name}
                      </span>
                      {file.password_protected && (
                        <span title="Password protected">
                          <svg className="h-3 w-3 shrink-0 text-yellow-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                          </svg>
                        </span>
                      )}
                      {file.allowed_peers.length > 0 && (
                        <span title={`Restricted to: ${file.allowed_peers.join(', ')}`}>
                          <svg className="h-3 w-3 shrink-0 text-accent" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z" />
                          </svg>
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="py-3 text-right text-slate-400 tabular-nums">
                    {formatBytes(file.size)}
                  </td>
                  <td className="py-3 text-center text-slate-400 tabular-nums">
                    {file.chunks.length}
                  </td>
                  <td className="py-3 text-center">
                    <span className={`tabular-nums ${peerCount > 0 ? 'text-accent' : 'text-slate-600'}`}>
                      {peerCount}
                    </span>
                  </td>
                  <td className="py-3">
                    <div className="flex items-center gap-1">
                      <span className="font-mono text-xs text-slate-500">
                        {truncateHash(file.file_hash)}
                      </span>
                      <CopyButton text={file.file_hash} />
                    </div>
                  </td>
                  <td className="py-3 pr-4" onClick={e => e.stopPropagation()}>
                    <div className="flex items-center justify-end gap-2">
                      {/* Delete button — only for files this peer has locally */}
                      {file.local_chunks > 0 && (
                        <button
                          onClick={() => onDelete(file.file_hash)}
                          title="Remove file"
                          className="p-1.5 rounded text-slate-600 hover:text-red-400 hover:bg-red-900/20 transition-colors"
                        >
                          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                              d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                          </svg>
                        </button>
                      )}

                      {/* Download button / progress bar */}
                      {isDownloading ? (
                        <div className="w-28">
                          <div className="flex justify-between text-xs text-slate-500 mb-1">
                            <span>Downloading</span>
                            <span>{file.local_chunks}/{file.chunks.length}</span>
                          </div>
                          <div className="h-1.5 rounded bg-slate-800 overflow-hidden">
                            <div
                              className="h-full bg-accent transition-all duration-300"
                              style={{ width: `${progress}%` }}
                            />
                          </div>
                        </div>
                      ) : status === 'Downloaded' ? (
                        <span className="text-xs text-slate-600">—</span>
                      ) : (
                        <div className="flex items-center gap-1.5">
                          {file.password_protected && (
                            <input
                              type="password"
                              placeholder="Password…"
                              value={filePasswords[file.file_hash] ?? ''}
                              onChange={e => setFilePasswords(p => ({ ...p, [file.file_hash]: e.target.value }))}
                              onKeyDown={e => {
                                if (e.key === 'Enter' && canDownload && filePasswords[file.file_hash]?.trim())
                                  onDownload(file.file_hash, filePasswords[file.file_hash])
                              }}
                              className="w-24 rounded bg-surface border border-border px-2 py-1.5 text-xs text-white placeholder-slate-600 focus:outline-none focus:border-accent"
                            />
                          )}
                          <button
                            onClick={() => onDownload(file.file_hash, filePasswords[file.file_hash])}
                            disabled={!canDownload || (file.password_protected && !filePasswords[file.file_hash]?.trim())}
                            className={`inline-flex items-center gap-1.5 rounded px-3 py-1.5 text-xs font-medium transition-colors ${
                              canDownload && (!file.password_protected || filePasswords[file.file_hash]?.trim())
                                ? 'bg-accent hover:bg-accent-hover text-white'
                                : 'bg-zinc-800 text-slate-600 cursor-not-allowed'
                            }`}
                          >
                            <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                                d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                            </svg>
                            {status === 'Unavailable' ? 'No peers' : 'Download'}
                          </button>
                        </div>
                      )}
                    </div>
                  </td>
                </tr>

                {/* Chunk availability map — expands on row click */}
                {isExpanded && (
                  <tr key={`${file.file_hash}-map`} className="bg-white/[0.01]">
                    <td colSpan={7}>
                      <ChunkMap file={file} peerId={peerId} />
                    </td>
                  </tr>
                )}
              </>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
