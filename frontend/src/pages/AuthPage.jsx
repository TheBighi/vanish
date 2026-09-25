import { useState } from 'react'
import { api } from '../services/api.js'

export default function AuthPage({ onAuthenticated }) {
  const [mode, setMode] = useState('login')
  const [form, setForm] = useState({ username: '', password: '' })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function submit(event) {
    event.preventDefault()
    if (!form.username.trim() || !form.password) return
    setError('')
    setLoading(true)
    try {
      const credentials = { username: form.username.trim(), password: form.password }
      const payload = mode === 'login' ? await api.login(credentials) : await api.register(credentials)
      onAuthenticated(payload)
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setLoading(false)
    }
  }

  function switchMode(nextMode) {
    setMode(nextMode)
    setError('')
  }

  return (
    <main className="auth-page">
      <section className="auth-panel">
        <form className="auth-card" onSubmit={submit}>
          <div className="wordmark">vanish</div>
          <div>
            <h1>{mode === 'login' ? 'Sign in' : 'Create account'}</h1>
            <p className="auth-description">Messages disappear after they are opened.</p>
          </div>
          <div className="auth-tabs" role="tablist">
            <button type="button" className={mode === 'login' ? 'active' : ''} onClick={() => switchMode('login')}>Sign in</button>
            <button type="button" className={mode === 'register' ? 'active' : ''} onClick={() => switchMode('register')}>Create account</button>
          </div>
          <label>
            <span>Username</span>
            <input autoComplete="username" maxLength="32" value={form.username} onChange={(event) => setForm({ ...form, username: event.target.value })} placeholder="your_alias" autoFocus />
          </label>
          <label>
            <span>Password</span>
            <input type="password" autoComplete={mode === 'login' ? 'current-password' : 'new-password'} minLength="6" value={form.password} onChange={(event) => setForm({ ...form, password: event.target.value })} placeholder="••••••••" />
          </label>
          {error && <div className="form-error" role="alert">{error}</div>}
          <button className="primary-button" disabled={loading}>
            {loading ? 'Please wait…' : mode === 'login' ? 'Sign in' : 'Create account'}
          </button>
          <p className="privacy-note">End-to-end encryption is not implemented.</p>
        </form>
      </section>
    </main>
  )
}
