function initials(name = '') {
  return name.slice(0, 2).toUpperCase()
}

function timeLabel(value) {
  if (!value) return ''
  const date = new Date(value)
  const today = new Date()
  if (date.toDateString() === today.toDateString()) return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  return date.toLocaleDateString([], { month: 'short', day: 'numeric' })
}

export default function Sidebar({ conversations, activeId, onSelect, onNew, user, onLogout, connectionState, mobileOpen }) {
  return (
    <aside className={`sidebar ${mobileOpen ? 'mobile-open' : ''}`}>
      <header className="sidebar-header">
        <div className="wordmark">vanish</div>
        <button className="icon-button" onClick={onNew} aria-label="Start a conversation">+</button>
      </header>
      <div className="conversation-heading">
        <span>Messages</span>
        <span>{conversations.length}</span>
      </div>
      <nav className="conversation-list" aria-label="Conversations">
        {conversations.length === 0 && (
          <div className="empty-list"><p>No conversations yet.</p><button onClick={onNew}>Find someone</button></div>
        )}
        {conversations.map((conversation) => (
          <button key={conversation.id} className={`conversation-row ${activeId === conversation.id ? 'active' : ''}`} onClick={() => onSelect(conversation.id)}>
            <div className="avatar">{initials(conversation.other_user?.username)}</div>
            <div className="conversation-copy">
              <strong>{conversation.other_user?.username}</strong>
              <span>{conversation.unread_count ? 'Unopened message' : 'Private conversation'}</span>
            </div>
            <div className="conversation-meta">
              <time>{timeLabel(conversation.last_message_at || conversation.created_at)}</time>
              {conversation.unread_count > 0 && <b>{conversation.unread_count}</b>}
            </div>
          </button>
        ))}
      </nav>
      <footer className="account-bar">
        <div className="avatar small">{initials(user.username)}</div>
        <div><strong>{user.username}</strong>{connectionState !== 'connected' && <span className="connection">Reconnecting</span>}</div>
        <button className="text-button" onClick={onLogout}>Sign out</button>
      </footer>
    </aside>
  )
}
