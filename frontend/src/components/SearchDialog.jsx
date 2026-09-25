import { useEffect, useRef, useState } from 'react'

export default function SearchDialog({ onClose, onStart }) {
  const [username, setUsername] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const inputRef = useRef(null)

  useEffect(() => inputRef.current?.focus(), [])

  async function submit(event) {
    event.preventDefault()
    const exactUsername = username.trim()
    if (!exactUsername || submitting) return
    setSubmitting(true)
    setError('')
    try {
      await onStart(exactUsername)
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="dialog-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <section className="search-dialog" role="dialog" aria-modal="true" aria-labelledby="search-title">
        <header><h2 id="search-title">New conversation</h2><button className="icon-button" onClick={onClose} aria-label="Close">×</button></header>
        <form className="username-form" onSubmit={submit}>
          <div className="search-field"><input ref={inputRef} value={username} onChange={(event) => setUsername(event.target.value)} maxLength="32" placeholder="Exact username" /></div>
          <p className="search-hint">No suggestions are shown. Enter the username exactly.</p>
          {error && <p className="form-error">{error}</p>}
          <button className="primary-button" disabled={!username.trim() || submitting}>{submitting ? 'Starting…' : 'Start conversation'}</button>
        </form>
      </section>
    </div>
  )
}
