import type {
  HealthResponse,
  NetworkFile,
  Peer,
  LocalFiles,
  UploadResult,
  DownloadResult,
  Message,
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

export const postDownload = (file_hash: string, file_password?: string): Promise<DownloadResult> =>
  apiFetch('/download', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ file_hash, ...(file_password ? { file_password } : {}) }),
  })

export const deleteFile = (file_hash: string): Promise<{ ok: boolean }> =>
  apiFetch('/delete', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ file_hash }),
  })

export const getMessages = (): Promise<{ messages: Message[] }> =>
  apiFetch('/messages')

export const sendMessage = (to_peer_id: string, text: string): Promise<{ ok: boolean }> =>
  apiFetch('/send_message', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ to_peer_id, text }),
  })

export function postUpload(
  file: File,
  onProgress?: (pct: number) => void,
  allowedPeers?: string[],
  filePassword?: string
): Promise<UploadResult> {
  return new Promise((resolve, reject) => {
    const params = new URLSearchParams({ name: file.name })
    if (allowedPeers?.length) params.set('allowed_peers', allowedPeers.join(','))
    if (filePassword) params.set('file_password', filePassword)
    const xhr = new XMLHttpRequest()
    xhr.open('POST', `${BASE}/upload?${params.toString()}`)
    xhr.setRequestHeader('Content-Type', 'application/octet-stream')
    if (onProgress) {
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) onProgress(Math.round((e.loaded / e.total) * 100))
      }
    }
    xhr.onload = () => {
      try {
        const data = JSON.parse(xhr.responseText)
        if (xhr.status >= 200 && xhr.status < 300) resolve(data)
        else reject(new Error(data.error ?? xhr.statusText))
      } catch { reject(new Error(xhr.statusText)) }
    }
    xhr.onerror = () => reject(new Error('Upload failed'))
    xhr.send(file)
  })
}
