import { useEffect, useRef, useState } from 'react'
import MessageBubble from './MessageBubble.jsx'

export default function ConversationPanel({ conversation, messages, userId, token, loading, typing, onOpen, onSend, onSendImage, onTyping, onBack, error }) {
  const [content, setContent] = useState('')
  const [sending, setSending] = useState(false)
  const endRef = useRef(null)
  const stopTimer = useRef(null)
  const fileInputRef = useRef(null)

  useEffect(() => endRef.current?.scrollIntoView({ behavior: 'smooth' }), [messages.length, conversation?.id])
  useEffect(() => () => window.clearTimeout(stopTimer.current), [])

  if (!conversation) {
    return <main className="no-conversation"><h2>Select a conversation</h2><p>Or start a new one from the sidebar.</p></main>
  }

  function updateContent(event) {
    setContent(event.target.value)
    onTyping(true)
    window.clearTimeout(stopTimer.current)
    stopTimer.current = window.setTimeout(() => onTyping(false), 1200)
  }

  async function submit(event) {
    event.preventDefault()
    const text = content.trim()
    if (!text || sending) return
    setContent('')
    onTyping(false)
    window.clearTimeout(stopTimer.current)
    setSending(true)
    try {
      await onSend(text)
    } catch {
      setContent(text)
    } finally {
      setSending(false)
    }
  }

  async function selectImage(event) {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file || sending) return
    if (file.size > 5 * 1024 * 1024) {
      window.alert('Image must be 5 MB or smaller.')
      return
    }
    setSending(true)
    try {
      await onSendImage(file)
    } catch {
      // The parent displays the API error above the conversation.
    } finally {
      setSending(false)
    }
  }

  return (
    <main className="chat-panel">
      <header className="chat-header">
        <button className="back-button" onClick={onBack} aria-label="Back to conversations">←</button>
        <div><h2>{conversation.other_user.username}</h2></div>
      </header>
      {error && <div className="chat-error" role="alert">{error}</div>}
      <section className="message-scroll">
        <div className="message-date">Open a message only when you are ready to read it.</div>
        {loading && <div className="loading-messages">Loading messages…</div>}
        {!loading && messages.length === 0 && <div className="first-message">No messages yet.</div>}
        {messages.map((message) => <MessageBubble key={message.id} message={message} mine={message.sender_id === userId} token={token} onOpen={onOpen} />)}
        {typing && <div className="typing-bubble"><i /><i /><i /></div>}
        <div ref={endRef} />
      </section>
      <form className="composer" onSubmit={submit}>
        <input ref={fileInputRef} className="file-input" type="file" accept="image/jpeg,image/png,image/gif,image/webp" onChange={selectImage} />
        <button className="attach-button" type="button" disabled={sending} onClick={() => fileInputRef.current?.click()} aria-label="Attach image">+</button>
        <textarea rows="1" maxLength="450" value={content} onChange={updateContent} onKeyDown={(event) => {
          if (event.key === 'Enter' && !event.shiftKey) submit(event)
        }} placeholder={`Message ${conversation.other_user.username}`} />
        <button className="send-button" disabled={!content.trim() || sending} aria-label="Send message">Send</button>
      </form>
    </main>
  )
}
