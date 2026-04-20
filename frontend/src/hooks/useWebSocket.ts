import { useEffect, useRef, useCallback } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import toast from 'react-hot-toast'
import { useStore } from '../store'

type Handler = (data: any) => void

export function useWebSocket() {
  const ws = useRef<WebSocket | null>(null)
  const handlers = useRef<Record<string, Handler[]>>({})
  const setWsConnected = useStore((s) => s.setWsConnected)
  const setLivePnl = useStore((s) => s.setLivePnl)
  const setEngineRunning = useStore((s) => s.setEngineRunning)
  const qc = useQueryClient()

  const on = useCallback((event: string, handler: Handler) => {
    if (!handlers.current[event]) handlers.current[event] = []
    handlers.current[event].push(handler)
    return () => {
      handlers.current[event] = handlers.current[event].filter((h) => h !== handler)
    }
  }, [])

  const send = useCallback((event: string, data: any) => {
    if (ws.current?.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify({ event, data }))
    }
  }, [])

  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const url = `${protocol}://${window.location.host}/ws`

    function connect() {
      const socket = new WebSocket(url)
      ws.current = socket

      socket.onopen = () => {
        setWsConnected(true)
        // Heartbeat
        const ping = setInterval(() => {
          if (socket.readyState === WebSocket.OPEN) socket.send('ping')
        }, 30_000)
        socket.addEventListener('close', () => clearInterval(ping))
      }

      socket.onmessage = (e) => {
        try {
          const { event, data } = JSON.parse(e.data)
          if (event === 'pong') return

          // Call registered handlers
          const hs = handlers.current[event] || []
          hs.forEach((h) => h(data))

          // Global reactions
          switch (event) {
            case 'trade.opened':
              toast.success(`📈 Trade opened: ${data.symbol} ${data.side?.toUpperCase()}`, { duration: 4000 })
              qc.invalidateQueries({ queryKey: ['positions'] })
              qc.invalidateQueries({ queryKey: ['trades'] })
              break
            case 'trade.closed':
              const pnl = data.net_pnl || 0
              const emoji = pnl >= 0 ? '✅' : '🔴'
              toast(`${emoji} Trade closed: ${data.symbol} ${pnl >= 0 ? '+' : ''}${pnl.toFixed(2)} USDT`, { duration: 5000 })
              qc.invalidateQueries({ queryKey: ['positions'] })
              qc.invalidateQueries({ queryKey: ['trades'] })
              qc.invalidateQueries({ queryKey: ['journal'] })
              break
            case 'order.filled':
              qc.invalidateQueries({ queryKey: ['orders'] })
              break
            case 'pnl.update':
              setLivePnl({ unrealized: data.unrealized ?? 0, today: data.today ?? 0 })
              break
            case 'ai.signal':
              qc.invalidateQueries({ queryKey: ['signals'] })
              break
            case 'balance.update':
              qc.invalidateQueries({ queryKey: ['balance'] })
              break
            case 'engine.status':
              if (data?.mode) {
                setEngineRunning(data.mode, data.status === 'started')
              }
              break
            case 'backtest.progress':
              qc.invalidateQueries({ queryKey: ['backtest-sessions'] })
              break
            case 'backtest.complete':
              toast.success(`Backtest complete: ${data.session_name}`, { duration: 6000 })
              qc.invalidateQueries({ queryKey: ['backtest-sessions'] })
              break
          }
        } catch {}
      }

      socket.onclose = () => {
        setWsConnected(false)
        // Reconnect after 3s
        setTimeout(connect, 3000)
      }

      socket.onerror = () => socket.close()
    }

    connect()
    return () => ws.current?.close()
  }, [])

  return { on, send }
}
