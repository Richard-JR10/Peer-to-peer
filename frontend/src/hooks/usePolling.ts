import { useEffect, useRef } from 'react'

export function usePolling(callback: () => Promise<void>, intervalMs: number): void {
  const savedCallback = useRef(callback)

  useEffect(() => {
    savedCallback.current = callback
  }, [callback])

  useEffect(() => {
    let cancelled = false

    const run = () => {
      if (!cancelled) savedCallback.current().catch(() => {})
    }

    run()
    const id = setInterval(run, intervalMs)
    return () => {
      cancelled = true
      clearInterval(id)
    }
  }, [intervalMs])
}
