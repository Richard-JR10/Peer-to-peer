import { useState, useRef, useEffect } from 'react'
import type { Message, Peer } from '../types'
import { formatRelativeTime } from '../types'

interface MessagingPanelProps {
  peers: Peer[]
  messages: Message[]
  myPeerId: string
  onSend: (to_peer_id: string, text: string) => Promise<void>
}

export default function MessagingPanel({ peers, messages, onSend }: MessagingPanelProps) {
  const [selectedPeer, setSelectedPeer] = useState('')
  const [text, setText] = useState('')
  const [sending, setSending] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  const conversation = messages.filter(m =>
    (m.direction === 'received' && m.from_peer === selectedPeer) ||
    (m.direction === 'sent' && m.to_peer === selectedPeer)
  )

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [conversation.length])

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
    <div className="rounded-lg border border-border bg-card flex flex-col" style={{ height: '380px' }}>
      {/* Header with peer selector */}
      <div className="flex items-center gap-2 border-b border-border px-4 py-3">
        <h2 className="text-sm font-semibold text-white uppercase tracking-wider shrink-0">Chat</h2>
        <select
          value={selectedPeer}
          onChange={e => setSelectedPeer(e.target.value)}
          className="flex-1 rounded bg-surface border border-border px-2 py-1 text-xs text-white focus:outline-none focus:border-accent"
        >
          <option value="">Select peer…</option>
          {peers.map(p => (
            <option key={p.peer_id} value={p.peer_id}>{p.peer_id}</option>
          ))}
        </select>
      </div>

      {/* Message thread */}
      <div className="flex-1 overflow-y-auto px-3 py-2 space-y-2">
        {!selectedPeer ? (
          <p className="text-xs text-slate-600 italic text-center mt-8">Select a peer to start chatting</p>
        ) : conversation.length === 0 ? (
          <p className="text-xs text-slate-600 italic text-center mt-8">No messages yet</p>
        ) : (
          conversation.map((m, i) => {
            const isSent = m.direction === 'sent'
            return (
              <div key={i} className={`flex flex-col ${isSent ? 'items-end' : 'items-start'}`}>
                {!isSent && (
                  <span className="text-[10px] text-slate-500 mb-0.5 ml-1">{m.from_peer}</span>
                )}
                <div className={`max-w-[80%] px-3 py-1.5 rounded-lg text-xs break-words ${
                  isSent
                    ? 'bg-accent text-white rounded-br-sm'
                    : 'bg-surface border border-border text-slate-300 rounded-bl-sm'
                }`}>
                  {m.text}
                </div>
                <span className="text-[10px] text-slate-600 mt-0.5 mx-1">
                  {formatRelativeTime(m.timestamp)}
                </span>
              </div>
            )
          })
        )}
        <div ref={bottomRef} />
      </div>

      {/* Compose bar */}
      <div className="border-t border-border px-3 py-2 flex gap-2">
        <input
          value={text}
          onChange={e => setText(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && handleSend()}
          placeholder={selectedPeer ? `Message ${selectedPeer}…` : 'Select a peer first…'}
          disabled={!selectedPeer}
          className="flex-1 rounded bg-surface border border-border px-2 py-1.5 text-xs text-white placeholder-slate-600 focus:outline-none focus:border-accent disabled:opacity-40"
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
  )
}
