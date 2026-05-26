import axios from 'axios'
import type {
  HealthResponse,
  NetworkFile,
  Peer,
  LocalFiles,
  UploadResult,
  DownloadResult,
  Message,
} from './types'

const api = axios.create({ baseURL: '/api' })

// Unwrap axios error bodies into plain Error so callers get a readable message.
api.interceptors.response.use(
  res => res,
  err => {
    const message = err.response?.data?.error ?? err.message
    return Promise.reject(new Error(message))
  }
)

export const getHealth = (): Promise<HealthResponse> =>
  api.get('/health').then(r => r.data)

export const getFiles = (): Promise<{ files: NetworkFile[] }> =>
  api.get('/files').then(r => r.data)

export const getPeers = (): Promise<{ peers: Peer[] }> =>
  api.get('/peers').then(r => r.data)

export const getLocal = (): Promise<LocalFiles> =>
  api.get('/local').then(r => r.data)

export const getMessages = (): Promise<{ messages: Message[] }> =>
  api.get('/messages').then(r => r.data)

export const postDownload = (file_hash: string, file_password?: string): Promise<DownloadResult> =>
  api.post('/download', { file_hash, ...(file_password ? { file_password } : {}) }).then(r => r.data)

export const deleteFile = (file_hash: string): Promise<{ ok: boolean }> =>
  api.post('/delete', { file_hash }).then(r => r.data)

export const sendMessage = (to_peer_id: string, text: string): Promise<{ ok: boolean }> =>
  api.post('/send_message', { to_peer_id, text }).then(r => r.data)

export const stopSharing = (file_hash: string): Promise<{ ok: boolean }> =>
  api.post('/stop_sharing', { file_hash }).then(r => r.data)

export const resumeSharing = (file_hash: string): Promise<{ ok: boolean }> =>
  api.post('/resume_sharing', { file_hash }).then(r => r.data)

export const openLocal = (file_hash: string): Promise<{ ok: boolean }> =>
  api.post('/open_local', { file_hash }).then(r => r.data)

export async function postUpload(
  file: File,
  onProgress?: (pct: number) => void,
  allowedPeers?: string[],
  filePassword?: string
): Promise<UploadResult> {
  const params = new URLSearchParams({ name: file.name })
  if (allowedPeers?.length) params.set('allowed_peers', allowedPeers.join(','))
  if (filePassword) params.set('file_password', filePassword)

  const res = await api.post<UploadResult>(`/upload?${params}`, file, {
    headers: { 'Content-Type': 'application/octet-stream' },
    onUploadProgress: e => {
      if (onProgress && e.total) onProgress(Math.round((e.loaded / e.total) * 100))
    },
  })
  return res.data
}
