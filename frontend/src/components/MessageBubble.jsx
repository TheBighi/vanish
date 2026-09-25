import { useEffect, useState } from 'react'
import { api } from '../services/api.js'

function formatTime(value) {
  return new Date(value).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

function senderStatus(message) {
  if (message.status === 'expired') return 'Expired'
  if (message.opened_at) return 'Opened'
  if (message.delivered_at || message.status === 'delivered') return 'Delivered'
  return message.status === 'sending' ? 'Sending…' : 'Sent'
}

export default function MessageBubble({ message, mine, token, onOpen }) {
  const [remaining, setRemaining] = useState(null)
  const [imageUrl, setImageUrl] = useState(null)
  const [imageError, setImageError] = useState(false)
  const openedAndVisible = !mine && message.opened_at && message.status === 'opened' && message.expires_at

  useEffect(() => {
    if (!openedAndVisible) {
      setRemaining(null)
      return undefined
    }
    function update() {
      setRemaining(Math.max(0, new Date(message.expires_at).getTime() - Date.now()))
    }
    update()
    const timer = window.setInterval(update, 100)
    return () => window.clearInterval(timer)
  }, [openedAndVisible, message.expires_at])

  useEffect(() => {
    const canLoad = message.kind === 'image' && message.status !== 'expired' && (mine || message.opened_at)
    if (!canLoad) {
      setImageUrl(null)
      setImageError(false)
      return undefined
    }
    let disposed = false
    let objectUrl
    setImageError(false)
    api.messageAttachment(token, message.id)
      .then((blob) => {
        if (disposed) return
        objectUrl = URL.createObjectURL(blob)
        setImageUrl(objectUrl)
      })
      .catch(() => !disposed && setImageError(true))
    return () => {
      disposed = true
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [message.id, message.kind, message.opened_at, message.status, mine, token])

  if (!mine && !message.opened_at && message.status !== 'expired') {
    return (
      <div className="message-line incoming">
        <button className="sealed-message" onClick={() => onOpen(message.id)} disabled={message.opening}>
          <span><strong>{message.opening ? 'Opening…' : 'New message'}</strong><small>Click to view</small></span>
        </button>
        <time>{formatTime(message.created_at)}</time>
      </div>
    )
  }

  if (message.status === 'expired') {
    return <div className={`message-line ${mine ? 'outgoing' : 'incoming'}`}><div className="expired-message">Message disappeared</div></div>
  }

  const duration = Math.max(1, (message.display_seconds || 10) * 1000)
  const progress = remaining === null ? 1 : Math.min(1, remaining / duration)
  return (
    <div className={`message-line ${mine ? 'outgoing' : 'incoming'}`}>
      {message.kind === 'image'
        ? <div className="image-message">{imageUrl ? <img src={imageUrl} alt={message.attachment_name || 'Disappearing image'} /> : <span>{imageError ? 'Image unavailable' : 'Loading image…'}</span>}</div>
        : <div className="message-bubble">{message.content}</div>}
      <div className="message-info">
        <time>{formatTime(message.created_at)}</time>
        {mine && <span>{senderStatus(message)}</span>}
        {openedAndVisible && <span className="countdown">{Math.ceil((remaining || 0) / 1000)}s</span>}
      </div>
      {openedAndVisible && <div className="expiry-track"><span style={{ transform: `scaleX(${progress})` }} /></div>}
    </div>
  )
}
