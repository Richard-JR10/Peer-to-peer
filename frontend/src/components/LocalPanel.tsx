import type { LocalFiles } from '../types'

interface LocalPanelProps {
  local: LocalFiles | null
}

function basename(path: string): string {
  return path.replace(/\\/g, '/').split('/').pop() ?? path
}

function FileList({ paths, emptyText }: { paths: string[]; emptyText: string }) {
  if (paths.length === 0) {
    return <p className="text-xs text-slate-600 italic">{emptyText}</p>
  }
  return (
    <ul className="space-y-1">
      {paths.map((p) => (
        <li key={p} className="text-xs text-slate-300 font-mono truncate" title={p}>
          {basename(p)}
        </li>
      ))}
    </ul>
  )
}

export default function LocalPanel({ local }: LocalPanelProps) {
  if (!local) {
    return (
      <div className="rounded-lg border border-border bg-card p-4">
        <h2 className="text-sm font-semibold text-white uppercase tracking-wider mb-4">Local Files</h2>
        <p className="text-xs text-slate-600">Loading…</p>
      </div>
    )
  }

  return (
    <div className="rounded-lg border border-border bg-card p-4 space-y-4">
      <h2 className="text-sm font-semibold text-white uppercase tracking-wider">Local Files</h2>

      <div>
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs text-slate-500 uppercase tracking-wide">Shared</span>
          <span className="text-xs text-slate-600">{local.shared.length}</span>
        </div>
        <FileList paths={local.shared} emptyText="No files in shared folder" />
      </div>

      <div className="border-t border-border pt-3">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs text-slate-500 uppercase tracking-wide">Downloads</span>
          <span className="text-xs text-slate-600">{local.downloads.length}</span>
        </div>
        <FileList paths={local.downloads} emptyText="No downloaded files" />
      </div>

      <div className="border-t border-border pt-3">
        <div className="flex items-center justify-between">
          <span className="text-xs text-slate-500 uppercase tracking-wide">Chunk cache</span>
          <span className={`text-xs font-medium tabular-nums ${
            local.chunks.length > 0 ? 'text-accent' : 'text-slate-600'
          }`}>
            {local.chunks.length} chunk{local.chunks.length !== 1 ? 's' : ''}
          </span>
        </div>
      </div>
    </div>
  )
}
