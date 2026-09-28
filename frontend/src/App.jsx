import { useEffect, useState } from 'react'
import AuthPage from './pages/AuthPage.jsx'
import ChatPage from './pages/ChatPage.jsx'
import { api, ApiError } from './services/api.js'
import { clearSession, getSession, saveSession, updateStoredUser } from './services/auth.js'
import { generateIdentity, storeIdentity } from './services/messageCrypto.js'

export default function App() {
  const [session, setSession] = useState(getSession)
  const [checking, setChecking] = useState(Boolean(session?.token))

  useEffect(() => {
    if (!session?.token) return
    api.me(session.token)
      .then(async (user) => {
        if (!user.public_key) {
          const identity = await generateIdentity()
          user = await api.setEncryptionKey(session.token, identity.publicKey)
          await storeIdentity(user.id, identity)
        }
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
  }, [session?.token])

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
