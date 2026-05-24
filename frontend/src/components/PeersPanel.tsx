import type { Peer } from '../types'
import { formatRelativeTime } from '../types'

interface PeersPanelProps {
  peers: Peer[]
}

export default function PeersPanel({ peers }: PeersPanelProps) {
  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-sm font-semibold text-white uppercase tracking-wider">Peers</h2>
        <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
          peers.length > 0
            ? 'bg-blue-950 text-accent border border-accent-dim'
            : 'bg-zinc-900 text-slate-600 border border-zinc-800'
        }`}>
          {peers.length} online
        </span>
      </div>

      {peers.length === 0 ? (
        <div className="flex flex-col items-center py-6 text-slate-600">
          <svg className="h-8 w-8 mb-2 opacity-30" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1}
              d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z" />
          </svg>
          <p className="text-xs">No peers discovered yet</p>
          <p className="text-xs mt-0.5 opacity-60">Waiting for UDP broadcast…</p>
        </div>
      ) : (
        <ul className="space-y-2">
          {peers.map((peer) => (
            <li key={peer.peer_id} className="flex items-center justify-between rounded-md px-3 py-2 bg-black/40 border border-border">
              <div className="flex items-center gap-2 min-w-0">
                <span className="h-2 w-2 rounded-full bg-accent flex-shrink-0 animate-pulse" />
                <div className="min-w-0">
                  <p className="text-sm font-medium text-white truncate">{peer.peer_id}</p>
                  <p className="text-xs text-slate-500 font-mono">{peer.host}:{peer.port}</p>
                </div>
              </div>
              <span className="text-xs text-slate-600 flex-shrink-0 ml-2">
                {formatRelativeTime(peer.last_seen)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
