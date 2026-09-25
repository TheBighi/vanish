import { useEffect, useRef, useState } from 'react'
import { API_BASE } from '../services/api.js'

function getSocketUrl(token) {
  const configured = import.meta.env.VITE_WS_URL
  const base = configured || `${API_BASE.replace(/^http/, 'ws')}/ws`
  const separator = base.includes('?') ? '&' : '?'
  return `${base}${separator}token=${encodeURIComponent(token)}`
}

export function useSocket(token, onEvent) {
  const [connectionState, setConnectionState] = useState('connecting')
  const socketRef = useRef(null)
  const eventHandlerRef = useRef(onEvent)
  eventHandlerRef.current = onEvent

  useEffect(() => {
    if (!token) {
      setConnectionState('offline')
      return undefined
    }

    let disposed = false
    let retryTimer
    let attempts = 0

    function connect() {
      if (disposed) return
      setConnectionState(attempts ? 'reconnecting' : 'connecting')
      const socket = new WebSocket(getSocketUrl(token))
      socketRef.current = socket

      socket.onopen = () => {
        attempts = 0
        setConnectionState('connected')
      }
      socket.onmessage = (event) => {
        try {
          eventHandlerRef.current(JSON.parse(event.data))
        } catch {
          // Ignore malformed server events without breaking the connection.
        }
      }
      socket.onerror = () => socket.close()
      socket.onclose = () => {
        if (socketRef.current === socket) socketRef.current = null
        if (disposed) return
        setConnectionState('reconnecting')
        const delay = Math.min(1000 * 2 ** attempts, 15000)
        attempts += 1
        retryTimer = window.setTimeout(connect, delay)
      }
    }

    connect()
    return () => {
      disposed = true
      window.clearTimeout(retryTimer)
      const socket = socketRef.current
      socketRef.current = null
      if (socket) socket.close()
    }
  }, [token])

  function send(type, data) {
    const socket = socketRef.current
    if (!socket || socket.readyState !== WebSocket.OPEN) return false
    socket.send(JSON.stringify({ type, data }))
    return true
  }

  return { connectionState, send }
}
