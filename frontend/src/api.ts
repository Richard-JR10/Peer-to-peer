import type {
  HealthResponse,
  NetworkFile,
  Peer,
  LocalFiles,
  UploadResult,
  DownloadResult,
} from './types'

const BASE = '/api'

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(BASE + path, init)
  if (!res.ok) {
    const body = await res.json().catch(() => ({ error: res.statusText }))
    throw new Error((body as { error?: string }).error ?? res.statusText)
  }
  return res.json() as Promise<T>
}

export const getHealth = (): Promise<HealthResponse> =>
  apiFetch('/health')

export const getFiles = (): Promise<{ files: NetworkFile[] }> =>
  apiFetch('/files')

export const getPeers = (): Promise<{ peers: Peer[] }> =>
  apiFetch('/peers')

export const getLocal = (): Promise<LocalFiles> =>
  apiFetch('/local')

export const postDownload = (file_hash: string): Promise<DownloadResult> =>
  apiFetch('/download', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ file_hash }),
  })

export const postUpload = (file: File): Promise<UploadResult> => {
  const params = new URLSearchParams({ name: file.name })
  return apiFetch(`/upload?${params}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/octet-stream' },
    body: file,
  })
}
