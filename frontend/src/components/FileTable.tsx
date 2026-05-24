import type { NetworkFile } from '../types'
import { getFileStatus, formatBytes, truncateHash } from '../types'

interface FileTableProps {
  files: NetworkFile[]
  downloading: Set<string>
  onDownload: (hash: string) => void
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
  const copy = () => {
    navigator.clipboard.writeText(text).catch(() => {})
  }
  return (
    <button
      onClick={copy}
      title={text}
      className="ml-1 text-slate-600 hover:text-accent transition-colors"
    >
      <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
          d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
      </svg>
    </button>
  )
}

export default function FileTable({ files, downloading, onDownload }: FileTableProps) {
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

            return (
              <tr key={file.file_hash} className="hover:bg-white/[0.02] transition-colors group">
                <td className="py-3 pl-4">
                  <StatusBadge file={file} />
                </td>
                <td className="py-3 max-w-[200px]">
                  <span className="truncate block text-white font-medium" title={file.name}>
                    {file.name}
                  </span>
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
                <td className="py-3 pr-4 text-right">
                  {status === 'Downloaded' ? (
                    <span className="text-xs text-slate-600">—</span>
                  ) : (
                    <button
                      onClick={() => onDownload(file.file_hash)}
                      disabled={!canDownload || isDownloading}
                      className={`inline-flex items-center gap-1.5 rounded px-3 py-1.5 text-xs font-medium transition-colors ${
                        canDownload && !isDownloading
                          ? 'bg-accent hover:bg-accent-hover text-white'
                          : 'bg-zinc-800 text-slate-600 cursor-not-allowed'
                      }`}
                    >
                      {isDownloading ? (
                        <>
                          <svg className="h-3 w-3 animate-spin" viewBox="0 0 24 24" fill="none">
                            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                          </svg>
                          Downloading
                        </>
                      ) : (
                        <>
                          <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                              d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                          </svg>
                          {status === 'Unavailable' ? 'No peers' : 'Download'}
                        </>
                      )}
                    </button>
                  )}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
