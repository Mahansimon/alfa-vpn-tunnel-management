import { useEffect, useRef, useState } from 'react'
import { LiveSocket } from '@/lib/ws'

export interface LiveMetric {
  id: string
  status?: string
  cpu_percent?: number
  ram_percent?: number
  disk_percent?: number
  rx_rate?: number
  tx_rate?: number
  load_1?: number
  uptime_seconds?: number
  health_score?: number
}

/** اشتراک در متریک‌های زنده سرورها (WebSocket) */
export function useLiveMetrics(enabled = true) {
  const [metrics, setMetrics] = useState<Record<string, LiveMetric>>({})
  const [connected, setConnected] = useState(false)
  const [lastUpdate, setLastUpdate] = useState<number | null>(null)

  useEffect(() => {
    if (!enabled) return
    const socket = new LiveSocket('metrics', (event, data) => {
      if (event === 'socket.open') setConnected(true)
      if (event === 'socket.close') setConnected(false)
      if (event === 'metrics.tick') {
        const payload = data as { servers?: LiveMetric[] }
        if (!payload?.servers) return
        setMetrics((prev) => {
          const next = { ...prev }
          for (const item of payload.servers ?? []) next[item.id] = { ...next[item.id], ...item }
          return next
        })
        setLastUpdate(Date.now())
      }
      if (event === 'servers.health') {
        const payload = data as { servers?: LiveMetric[] }
        setMetrics((prev) => {
          const next = { ...prev }
          for (const item of payload.servers ?? []) next[item.id] = { ...next[item.id], ...item }
          return next
        })
      }
    })
    socket.connect()
    return () => socket.close()
  }, [enabled])

  return { metrics, connected, lastUpdate }
}

/** اشتراک در یک موضوع دلخواه با callback */
export function useLiveTopic(topic: string, handler: (event: string, data: unknown) => void, enabled = true) {
  const ref = useRef(handler)
  ref.current = handler
  const [connected, setConnected] = useState(false)

  useEffect(() => {
    if (!enabled) return
    const socket = new LiveSocket(topic, (event, data) => {
      if (event === 'socket.open') setConnected(true)
      if (event === 'socket.close') setConnected(false)
      ref.current(event, data)
    })
    socket.connect()
    return () => socket.close()
  }, [topic, enabled])

  return connected
}

export function useDebouncedValue<T>(value: T, delay = 300) {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(timer)
  }, [value, delay])
  return debounced
}
