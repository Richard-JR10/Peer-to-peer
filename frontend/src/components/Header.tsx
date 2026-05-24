interface HeaderProps {
  peerId: string
  connected: boolean
  peerCount: number
  fileCount: number
}

export default function Header({ peerId, connected, peerCount, fileCount }: HeaderProps) {
  return (
    <header className="border-b border-border bg-card px-6 py-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <div className="h-7 w-7 rounded bg-accent flex items-center justify-center">
              <svg className="h-4 w-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M8.684 13.342C8.886 12.938 9 12.482 9 12c0-.482-.114-.938-.316-1.342m0 2.684a3 3 0 110-2.684m0 2.684l6.632 3.316m-6.632-6l6.632-3.316m0 0a3 3 0 105.367-2.684 3 3 0 00-5.367 2.684zm0 9.316a3 3 0 105.368 2.684 3 3 0 00-5.368-2.684z" />
              </svg>
            </div>
            <span className="text-lg font-semibold tracking-wide text-white">PDC P2P</span>
          </div>

          <div className="h-4 w-px bg-border" />

          <div className="flex items-center gap-2 text-sm text-slate-400">
            <span className="text-slate-500">Node</span>
            <span className="font-mono text-white">{peerId || '—'}</span>
          </div>
        </div>

        <div className="flex items-center gap-4">
          <div className="flex items-center gap-3 text-sm text-slate-400">
            <span>
              <span className="text-white font-medium">{peerCount}</span> peer{peerCount !== 1 ? 's' : ''}
            </span>
            <span>
              <span className="text-white font-medium">{fileCount}</span> file{fileCount !== 1 ? 's' : ''}
            </span>
          </div>

          <div className={`flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium ${
            connected
              ? 'bg-blue-950 text-accent border border-accent-dim'
              : 'bg-red-950 text-red-400 border border-red-900'
          }`}>
            <span className={`h-1.5 w-1.5 rounded-full ${
              connected ? 'bg-accent animate-pulse' : 'bg-red-400'
            }`} />
            {connected ? 'Connected' : 'Offline'}
          </div>
        </div>
      </div>
    </header>
  )
}
