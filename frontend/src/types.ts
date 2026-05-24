export interface HealthResponse {
  status: string
  peer_id: string
  mode: string
  known_peers: number
  known_files: number
}

export interface ChunkMeta {
  index: number
  hash: string
  size: number
}

export interface PeerOwnership {
  peer_id: string
  chunks: number[]
  last_seen: number
}

export interface NetworkFile {
  file_hash: string
  name: string
  size: number
  chunk_size: number
  chunks: ChunkMeta[]
  peers: Record<string, PeerOwnership>
  local_chunks: number
}

export interface Peer {
  peer_id: string
  host: string
  port: number
  last_seen: number
  digest: string
}

export interface LocalFiles {
  shared: string[]
  downloads: string[]
  chunks: string[]
}

export interface UploadResult {
  file_hash: string
  name: string
  size: number
  chunks: number
}

export interface DownloadResult {
  file_hash: string
  saved_to: string
  chunks: number[]
}

export interface Message {
  from_peer: string
  text: string
  timestamp: number
}

export type FileStatus = 'Downloaded' | 'Partial' | 'Available' | 'Unavailable'

export function getFileStatus(file: NetworkFile): FileStatus {
  if (file.chunks.length > 0 && file.local_chunks === file.chunks.length) return 'Downloaded'
  if (file.local_chunks > 0) return 'Partial'
  if (Object.keys(file.peers).length > 0) return 'Available'
  return 'Unavailable'
}

export function formatBytes(bytes: number): string {
  if (bytes >= 1_073_741_824) return (bytes / 1_073_741_824).toFixed(2) + ' GB'
  if (bytes >= 1_048_576) return (bytes / 1_048_576).toFixed(2) + ' MB'
  if (bytes >= 1_024) return (bytes / 1_024).toFixed(1) + ' KB'
  return bytes + ' B'
}

export function formatRelativeTime(unixSeconds: number): string {
  const diff = Math.floor(Date.now() / 1000) - unixSeconds
  if (diff < 60) return `${diff}s ago`
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  return `${Math.floor(diff / 3600)}h ago`
}

export function truncateHash(hash: string): string {
  if (hash.length <= 20) return hash
  return hash.slice(0, 10) + '…' + hash.slice(-8)
}
