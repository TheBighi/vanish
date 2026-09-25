import { useEffect, useState } from 'react'
import AuthPage from './pages/AuthPage.jsx'
import ChatPage from './pages/ChatPage.jsx'
import { api, ApiError } from './services/api.js'
import { clearSession, getSession, saveSession, updateStoredUser } from './services/auth.js'

export default function App() {
  const [session, setSession] = useState(getSession)
  const [checking, setChecking] = useState(Boolean(session?.token && !session?.user))

  useEffect(() => {
    if (!session?.token || session.user) return
    api.me(session.token)
      .then((user) => {
        updateStoredUser(user)
        setSession((current) => ({ ...current, user }))
      })
      .catch((error) => {
        if (error instanceof ApiError && error.status === 401) {
          clearSession()
          setSession(null)
        }
      })
      .finally(() => setChecking(false))
  }, [session?.token, session?.user])

  function handleAuthenticated(payload) {
    setSession(saveSession(payload))
  }

  function logout() {
    clearSession()
    setSession(null)
  }

  if (checking) return <div className="boot-screen"><span className="brand-mark">V</span></div>
  if (!session?.token || !session.user) return <AuthPage onAuthenticated={handleAuthenticated} />
  return <ChatPage session={session} onLogout={logout} />
}
