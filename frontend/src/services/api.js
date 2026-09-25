export const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function request(path, { token, responseType, ...options } = {}) {
  const headers = new Headers(options.headers)
  if (options.body && !(options.body instanceof FormData)) headers.set('Content-Type', 'application/json')
  if (token) headers.set('Authorization', `Bearer ${token}`)

  let response
  try {
    response = await fetch(`${API_BASE}${path}`, { ...options, headers })
  } catch {
    throw new ApiError('Cannot reach the server. Check your connection.', 0)
  }

  if (!response.ok) {
    let detail
    try {
      const body = await response.json()
      detail = body.detail || body.message
    } catch {
      detail = null
    }
    if (Array.isArray(detail)) detail = detail.map((item) => item.msg).join(', ')
    throw new ApiError(detail || `Request failed (${response.status})`, response.status)
  }

  if (response.status === 204) return null
  if (responseType === 'blob') return response.blob()
  return response.json()
}

export const api = {
  register: (credentials) => request('/auth/register', { method: 'POST', body: JSON.stringify(credentials) }),
  login: (credentials) => request('/auth/login', { method: 'POST', body: JSON.stringify(credentials) }),
  me: (token) => request('/users/me', { token }),
  conversations: (token) => request('/conversations', { token }),
  startConversation: (token, username) => request('/conversations', {
    token,
    method: 'POST',
    body: JSON.stringify({ username }),
  }),
  messages: (token, conversationId) => request(`/conversations/${conversationId}/messages`, { token }),
  sendMessage: (token, conversationId, content) => request('/messages', {
    token,
    method: 'POST',
    body: JSON.stringify({ conversation_id: conversationId, content }),
  }),
  sendImage: (token, conversationId, file) => {
    const body = new FormData()
    body.append('conversation_id', conversationId)
    body.append('file', file)
    return request('/messages/image', { token, method: 'POST', body })
  },
  messageAttachment: (token, messageId) => request(`/messages/${messageId}/attachment`, { token, responseType: 'blob' }),
  openMessage: (token, messageId) => request(`/messages/${messageId}/open`, { token, method: 'POST' }),
}
