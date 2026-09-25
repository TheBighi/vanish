const TOKEN_KEY = 'vanish_access_token'
const USER_KEY = 'vanish_user'

export function getSession() {
  try {
    const token = localStorage.getItem(TOKEN_KEY)
    const user = JSON.parse(localStorage.getItem(USER_KEY) || 'null')
    return token ? { token, user } : null
  } catch {
    clearSession()
    return null
  }
}

export function saveSession(payload) {
  localStorage.setItem(TOKEN_KEY, payload.access_token)
  localStorage.setItem(USER_KEY, JSON.stringify(payload.user))
  return { token: payload.access_token, user: payload.user }
}

export function updateStoredUser(user) {
  localStorage.setItem(USER_KEY, JSON.stringify(user))
}

export function clearSession() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
}
