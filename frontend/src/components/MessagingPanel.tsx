import { useState } from 'react'
import type { Message, Peer } from '../types'
import { formatRelativeTime } from '../types'

interface MessagingPanelProps {
  peers: Peer[]
  messages: Message[]
  onSend: (to_peer_id: string, text: string) => Promise<void>
}

export default function MessagingPanel({ peers, messages, onSend }: MessagingPanelProps) {
  const [selectedPeer, setSelectedPeer] = useState('')
  const [text, setText] = useState('')
  const [sending, setSending] = useState(false)

  const handleSend = async () => {
    if (!selectedPeer || !text.trim()) return
    setSending(true)
    try {
      await onSend(selectedPeer, text.trim())
      setText('')
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="rounded-lg border border-border bg-card p-4 space-y-3">
      <h2 className="text-sm font-semibold text-white uppercase tracking-wider">Messages</h2>

      <div className="space-y-2 max-h-48 overflow-y-auto">
        {messages.length === 0 ? (
          <p className="text-xs text-slate-600 italic">No messages yet</p>
        ) : (
          [...messages].reverse().map((m, i) => (
            <div key={i} className="rounded bg-surface border border-border px-3 py-2">
              <div className="flex justify-between items-center mb-0.5">
                <span className="text-xs font-medium text-accent">{m.from_peer}</span>
                <span className="text-xs text-slate-600">{formatRelativeTime(m.timestamp)}</span>
              </div>
              <p className="text-xs text-slate-300 break-words">{m.text}</p>
            </div>
          ))
        )}
      </div>

      <div className="space-y-2 border-t border-border pt-3">
        <select
          value={selectedPeer}
          onChange={e => setSelectedPeer(e.target.value)}
          className="w-full rounded bg-surface border border-border px-2 py-1.5 text-xs text-white focus:outline-none focus:border-accent"
        >
          <option value="">Select peer…</option>
          {peers.map(p => (
            <option key={p.peer_id} value={p.peer_id}>{p.peer_id}</option>
          ))}
        </select>
        <div className="flex gap-2">
          <input
            value={text}
            onChange={e => setText(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleSend()}
            placeholder="Type a message…"
            className="flex-1 rounded bg-surface border border-border px-2 py-1.5 text-xs text-white placeholder-slate-600 focus:outline-none focus:border-accent"
          />
          <button
            onClick={handleSend}
            disabled={!selectedPeer || !text.trim() || sending}
            className="rounded px-3 py-1.5 text-xs font-medium bg-accent hover:bg-accent-hover text-white disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            Send
          </button>
        </div>
      </div>
    </div>
  )
}
