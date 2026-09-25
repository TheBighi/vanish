import { useCallback, useEffect, useRef, useState } from 'react'
import ConversationPanel from '../components/ConversationPanel.jsx'
import SearchDialog from '../components/SearchDialog.jsx'
import Sidebar from '../components/Sidebar.jsx'
import { useSocket } from '../hooks/useSocket.js'
import { api, ApiError } from '../services/api.js'

function normalizeMessage(message, userId) {
  const expired = message.expires_at && new Date(message.expires_at).getTime() <= Date.now()
  const unopenedIncoming = message.recipient_id === userId && !message.opened_at
  return { ...message, content: expired || unopenedIncoming ? null : message.content, status: expired ? 'expired' : message.status }
}

function upsertMessage(list = [], incoming) {
  const index = list.findIndex((message) => message.id === incoming.id)
  if (index < 0) return [...list, incoming].sort((a, b) => new Date(a.created_at) - new Date(b.created_at))
  const next = [...list]
  const existing = next[index]
  const hasExpired = incoming.status === 'expired' || (incoming.expires_at && new Date(incoming.expires_at).getTime() <= Date.now())
  const content = incoming.content == null && existing.content && !hasExpired ? existing.content : incoming.content
  next[index] = { ...existing, ...incoming, content }
  return next
}

export default function ChatPage({ session, onLogout }) {
  const { token, user } = session
  const [conversations, setConversations] = useState([])
  const [activeId, setActiveId] = useState(null)
  const [messages, setMessages] = useState({})
  const [loadingConversationId, setLoadingConversationId] = useState(null)
  const [searchOpen, setSearchOpen] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(true)
  const [typingByConversation, setTypingByConversation] = useState({})
  const [error, setError] = useState('')
  const activeIdRef = useRef(activeId)
  activeIdRef.current = activeId

  const handleSocketEvent = useCallback((event) => {
    const { type, data = {} } = event
    if (type === 'message:expired' && data.message_id) {
      setMessages((current) => Object.fromEntries(
        Object.entries(current).map(([conversationId, items]) => [
          conversationId,
          items.map((message) => message.id === data.message_id
            ? { ...message, content: null, status: 'expired' }
            : message),
        ]),
      ))
      return
    }
    if (type?.startsWith('message:') && data.message) {
      const incoming = normalizeMessage(data.message, user.id)
      setMessages((current) => ({ ...current, [incoming.conversation_id]: upsertMessage(current[incoming.conversation_id], incoming) }))
      setConversations((current) => current.map((conversation) => {
        if (conversation.id !== incoming.conversation_id) return conversation
        const isNewIncoming = type === 'message:new' && incoming.sender_id !== user.id
        return { ...conversation, last_message_at: incoming.created_at, unread_count: isNewIncoming ? (conversation.unread_count || 0) + 1 : conversation.unread_count }
      }))
      if (type === 'message:new') {
        api.conversations(token).then(setConversations).catch(() => {})
      }
      return
    }
    if (type === 'typing:start' || type === 'typing:stop') {
      if (data.user_id !== user.id) setTypingByConversation((current) => ({ ...current, [data.conversation_id]: type === 'typing:start' }))
      return
    }
  }, [token, user.id])

  const { connectionState, send } = useSocket(token, handleSocketEvent)

  useEffect(() => {
    api.conversations(token).then(setConversations).catch((requestError) => {
      if (requestError instanceof ApiError && requestError.status === 401) onLogout()
      else setError(requestError.message)
    })
  }, [token, onLogout])

  useEffect(() => {
    const timers = []
    Object.values(messages).flat().forEach((message) => {
      if (!message.expires_at || message.status === 'expired') return
      const delay = new Date(message.expires_at).getTime() - Date.now()
      if (delay <= 0) {
        setMessages((current) => ({ ...current, [message.conversation_id]: (current[message.conversation_id] || []).map((item) => item.id === message.id ? { ...item, content: null, status: 'expired' } : item) }))
      } else {
        timers.push(window.setTimeout(() => {
          setMessages((current) => ({ ...current, [message.conversation_id]: (current[message.conversation_id] || []).map((item) => item.id === message.id ? { ...item, content: null, status: 'expired' } : item) }))
        }, delay))
      }
    })
    return () => timers.forEach(window.clearTimeout)
  }, [messages])

  async function selectConversation(id) {
    setActiveId(id)
    setMobileOpen(false)
    setError('')
    if (messages[id]) return
    setLoadingConversationId(id)
    try {
      const result = await api.messages(token, id)
      setMessages((current) => ({ ...current, [id]: result.map((message) => normalizeMessage(message, user.id)) }))
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setLoadingConversationId((current) => current === id ? null : current)
    }
  }

  async function startConversation(username) {
    setError('')
    try {
      const conversation = await api.startConversation(token, username)
      setConversations((current) => {
        return current.some((item) => item.id === conversation.id) ? current : [conversation, ...current]
      })
      setSearchOpen(false)
      await selectConversation(conversation.id)
    } catch (requestError) {
      setError(requestError.message)
      throw requestError
    }
  }

  async function openMessage(messageId) {
    const conversationId = activeIdRef.current
    setMessages((current) => ({ ...current, [conversationId]: current[conversationId].map((item) => item.id === messageId ? { ...item, opening: true } : item) }))
    try {
      const opened = normalizeMessage(await api.openMessage(token, messageId), user.id)
      setMessages((current) => ({ ...current, [conversationId]: upsertMessage(current[conversationId], { ...opened, opening: false }) }))
      setConversations((current) => current.map((conversation) => conversation.id === conversationId
        ? { ...conversation, unread_count: Math.max(0, (conversation.unread_count || 0) - 1) }
        : conversation))
    } catch (requestError) {
      setMessages((current) => ({ ...current, [conversationId]: current[conversationId].map((item) => item.id === messageId ? { ...item, opening: false } : item) }))
      setError(requestError.message)
    }
  }

  async function sendMessage(content) {
    setError('')
    try {
      const sent = normalizeMessage(await api.sendMessage(token, activeId, content), user.id)
      setMessages((current) => ({ ...current, [activeId]: upsertMessage(current[activeId], sent) }))
    } catch (requestError) {
      setError(requestError.message)
      throw requestError
    }
  }

  async function sendImage(file) {
    setError('')
    try {
      const sent = normalizeMessage(await api.sendImage(token, activeId, file), user.id)
      setMessages((current) => ({ ...current, [activeId]: upsertMessage(current[activeId], sent) }))
    } catch (requestError) {
      setError(requestError.message)
      throw requestError
    }
  }

  const activeConversation = conversations.find((conversation) => conversation.id === activeId)
  return (
    <div className="app-shell">
      <Sidebar conversations={conversations} activeId={activeId} onSelect={selectConversation} onNew={() => setSearchOpen(true)} user={user} onLogout={onLogout} connectionState={connectionState} mobileOpen={mobileOpen} />
      <ConversationPanel conversation={activeConversation} messages={messages[activeId] || []} userId={user.id} token={token} loading={loadingConversationId === activeId} typing={typingByConversation[activeId]} onOpen={openMessage} onSend={sendMessage} onSendImage={sendImage} onTyping={(isTyping) => send(isTyping ? 'typing:start' : 'typing:stop', { conversation_id: activeId })} onBack={() => setMobileOpen(true)} error={error} />
      {searchOpen && <SearchDialog onClose={() => setSearchOpen(false)} onStart={startConversation} />}
    </div>
  )
}
