import { useState, useCallback } from 'react'
import { getHealth, getFiles, getPeers, getLocal, postDownload, postUpload } from './api'
import { usePolling } from './hooks/usePolling'
import type { HealthResponse, NetworkFile, Peer, LocalFiles } from './types'
import Header from './components/Header'
import FileTable from './components/FileTable'
import UploadZone from './components/UploadZone'
import PeersPanel from './components/PeersPanel'
import LocalPanel from './components/LocalPanel'

export default function App() {
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [files, setFiles] = useState<NetworkFile[]>([])
  const [peers, setPeers] = useState<Peer[]>([])
  const [local, setLocal] = useState<LocalFiles | null>(null)
  const [downloading, setDownloading] = useState<Set<string>>(new Set())
  const [toast, setToast] = useState<{ text: string; ok: boolean } | null>(null)

  const showToast = (text: string, ok: boolean) => {
    setToast({ text, ok })
    setTimeout(() => setToast(null), 4000)
  }

  const fetchHealth = useCallback(async () => {
    try {
      const h = await getHealth()
      setHealth(h)
    } catch {
      setHealth(null)
    }
  }, [])

  const fetchAll = useCallback(async () => {
    try {
      const [filesRes, peersRes, localRes] = await Promise.all([
        getFiles(),
        getPeers(),
        getLocal(),
      ])
      setFiles(filesRes.files)
      setPeers(peersRes.peers)
      setLocal(localRes)
    } catch {
      // peer.py not reachable — keep stale data
    }
  }, [])

  usePolling(fetchHealth, 2000)
  usePolling(fetchAll, 3000)

  const handleDownload = async (hash: string) => {
    setDownloading((prev) => new Set([...prev, hash]))
    try {
      const result = await postDownload(hash)
      showToast(`Saved to ${result.saved_to.split(/[\\/]/).pop()}`, true)
      await fetchAll()
    } catch (err) {
      showToast(String(err), false)
    } finally {
      setDownloading((prev) => {
        const next = new Set(prev)
        next.delete(hash)
        return next
      })
    }
  }

  const handleUpload = async (file: File) => {
    await postUpload(file)
    await fetchAll()
  }

  const connected = health?.status === 'ok'

  return (
    <div className="min-h-screen bg-black flex flex-col">
      <Header
        peerId={health?.peer_id ?? ''}
        connected={connected}
        peerCount={peers.length}
        fileCount={files.length}
      />

      <main className="flex-1 p-6">
        <div className="mx-auto max-w-7xl grid grid-cols-1 xl:grid-cols-[1fr_300px] gap-6">

          {/* Left column */}
          <div className="flex flex-col gap-6">
            {/* Network files */}
            <div className="rounded-lg border border-border bg-card">
              <div className="flex items-center justify-between border-b border-border px-4 py-3">
                <h2 className="text-sm font-semibold text-white uppercase tracking-wider">
                  Network Files
                </h2>
                <span className="text-xs text-slate-600">{files.length} total</span>
              </div>
              <div className="p-1">
                <FileTable
                  files={files}
                  downloading={downloading}
                  onDownload={handleDownload}
                />
              </div>
            </div>

            {/* Upload zone */}
            <UploadZone onUpload={handleUpload} />
          </div>

          {/* Right column */}
          <div className="flex flex-col gap-6">
            <PeersPanel peers={peers} />
            <LocalPanel local={local} />
          </div>
        </div>
      </main>

      {/* Toast */}
      {toast && (
        <div className={`fixed bottom-6 right-6 flex items-center gap-2 rounded-lg border px-4 py-3 text-sm shadow-lg transition-all ${
          toast.ok
            ? 'bg-card border-green-900 text-green-400'
            : 'bg-card border-red-900 text-red-400'
        }`}>
          {toast.ok ? (
            <svg className="h-4 w-4 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
          ) : (
            <svg className="h-4 w-4 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          )}
          {toast.text}
        </div>
      )}
    </div>
  )
}
