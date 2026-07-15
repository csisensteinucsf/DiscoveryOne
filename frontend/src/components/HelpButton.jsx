import { useEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import Modal from './Modal.jsx'
import { useAuth } from '../auth.jsx'

const isRequestorRole = (role) => role === 'requestor'
const isTechRole = (role) => role === 'tech'

const cleanPath = (rawPath) => {
  const normalized = (rawPath || '/').replace(/\\/g, '/')
  if (normalized.length > 1 && normalized.endsWith('/')) {
    return normalized.slice(0, -1)
  }
  return normalized
}

const parseCaseIdFromPath = (pathname) => {
  const match = cleanPath(pathname).match(/^\/cases\/(\d+)/i)
  if (!match) return null
  const value = Number(match[1])
  if (!Number.isFinite(value) || value <= 0) return null
  return value
}

const getHelpAnchor = (pathname, search, role) => {
  const path = cleanPath(pathname)
  const params = new URLSearchParams(search || '')
  const type = (params.get('type') || '').toLowerCase()
  const isTech = isTechRole(role)
  const isRequestor = isRequestorRole(role)

  if (['/login', '/register', '/setup'].includes(path)) return '#access'

  if (path === '/system') return isTech ? '#tech-system' : '#system'

  if (path === '/' || path === '/cases') return isTech ? '#tech-cases' : '#cases'

  if (path.startsWith('/cases/') && path !== '/cases') {
    return isTech ? '#tech-case-detail' : '#case-detail'
  }

  if (path === '/requests') {
    if (isTech) return '#tech-unavailable-pages'
    if (type === 'new_case') return '#new-case-request'
    if (type === 'custodian') return '#custodian-update-request'
    if (type === 'search') return '#search-request'
    if (type === 'close_case') return '#close-case-request'
    return '#requests'
  }

  if (path === '/dashboards') return isTech ? '#tech-unavailable-pages' : '#dashboards'
  if (path === '/reports') return isTech ? '#tech-unavailable-pages' : '#reports'

  if (path === '/logs') {
    if (isTech) return '#tech-unavailable-pages'
    if (isRequestor) return '#logs'
    return '#help-overview'
  }

  if (path === '/custodians' || path.startsWith('/custodians/')) {
    return isTech ? '#tech-unavailable-pages' : '#help-overview'
  }

  if (path === '/help') {
    if (isTech) return '#tech-overview'
    return '#help-overview'
  }

  return isTech ? '#tech-overview' : '#help-overview'
}

const initialAssistantMessage = {
  role: 'assistant',
  content: 'How can I help you?',
  citations: [],
}

export default function HelpButton() {
  const { pathname, search } = useLocation()
  const navigate = useNavigate()
  const { user } = useAuth()
  const role = user?.role || (user?.is_admin ? 'sys_admin' : 'analyst')
  const anchor = useMemo(() => getHelpAnchor(pathname, search, role), [pathname, search, role])
  const caseId = useMemo(() => parseCaseIdFromPath(pathname), [pathname])

  const [showHelpMenu, setShowHelpMenu] = useState(false)
  const [showAssistantModal, setShowAssistantModal] = useState(false)
  const [chatInput, setChatInput] = useState('')
  const [chatBusy, setChatBusy] = useState(false)
  const [assistantTyping, setAssistantTyping] = useState(false)
  const [chatMessages, setChatMessages] = useState([initialAssistantMessage])

  const helpBadgeRef = useRef(null)
  const helpMenuRef = useRef(null)
  const threadRef = useRef(null)
  const chatInputRef = useRef(null)

  useEffect(() => {
    if (!showHelpMenu) return undefined

    const onPointerDown = (event) => {
      const target = event?.target
      if (!target) return
      const inMenu = helpMenuRef.current && helpMenuRef.current.contains(target)
      const inBadge = helpBadgeRef.current && helpBadgeRef.current.contains(target)
      if (!inMenu && !inBadge) {
        setShowHelpMenu(false)
      }
    }

    const onKeyDown = (event) => {
      if (event.key === 'Escape') setShowHelpMenu(false)
    }

    document.addEventListener('mousedown', onPointerDown)
    document.addEventListener('touchstart', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('mousedown', onPointerDown)
      document.removeEventListener('touchstart', onPointerDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [showHelpMenu])

  useEffect(() => {
    const el = threadRef.current
    if (!el) return
    el.scrollTop = el.scrollHeight
  }, [chatMessages, assistantTyping, showAssistantModal])

  const openHelpPage = () => {
    setShowHelpMenu(false)
    navigate(`/help${anchor}`)
  }

  const openAssistant = () => {
    setShowHelpMenu(false)
    setShowAssistantModal(true)
    setChatMessages((prev) => (Array.isArray(prev) && prev.length ? prev : [initialAssistantMessage]))
  }

  const closeAssistant = () => {
    if (chatBusy) return
    setShowAssistantModal(false)
  }

  const handleChatInputChange = (event) => {
    const value = event?.target?.value ?? ''
    setChatInput(value)
    const el = event?.target
    if (!el) return
    el.style.height = '38px'
    const next = Math.min(el.scrollHeight || 38, 140)
    el.style.height = `${Math.max(next, 38)}px`
  }
  const sendChat = async () => {
    const text = String(chatInput || '').trim()
    if (!text || chatBusy) return

    const userMsg = { role: 'user', content: text, citations: [] }
    const history = [...chatMessages, userMsg].map((item) => ({
      role: item.role === 'assistant' ? 'assistant' : 'user',
      content: String(item.content || ''),
    }))

    setChatMessages((prev) => [...prev, userMsg])
    setChatInput('')
    if (chatInputRef.current) chatInputRef.current.style.height = '38px'
    setChatBusy(true)
    setAssistantTyping(true)

    try {
      const res = await fetch('/api/ai/help_chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          message: text,
          history,
          context: {
            pathname,
            search,
            case_id: caseId,
            help_anchor: anchor,
          },
        }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        throw new Error(data?.detail || 'AI assistant request failed')
      }

      const answer = String(data?.answer || '').trim() || 'I could not produce an answer for that request.'
      const citations = Array.isArray(data?.citations) ? data.citations.filter(Boolean).slice(0, 8) : []
      const clarifyingQuestion = String(data?.clarifying_question || '').trim()
      const responseText = clarifyingQuestion ? `${answer}\n\nClarifying question: ${clarifyingQuestion}` : answer

      setChatMessages((prev) => [
        ...prev,
        { role: 'assistant', content: responseText, citations },
      ])
    } catch (err) {
      console.error(err)
      setChatMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: err?.message || 'AI assistant is unavailable right now.',
          citations: ['assistant_error'],
        },
      ])
    } finally {
      setAssistantTyping(false)
      setChatBusy(false)
    }
  }

  return (
    <>
      <button
        ref={helpBadgeRef}
        type="button"
        className="help-badge"
        aria-label="Open help options"
        onClick={() => setShowHelpMenu((prev) => !prev)}
      >
        ?
      </button>

      {showHelpMenu && (
        <div ref={helpMenuRef} className="help-popover" role="menu" aria-label="Help options">
          <button type="button" className="help-popover__option" onClick={openHelpPage}>
            Help Page
          </button>
          <button type="button" className="help-popover__option" onClick={openAssistant}>
            AI Assistant
          </button>
        </div>
      )}

      <Modal
        open={showAssistantModal}
        onClose={closeAssistant}
        title="DiscoveryOne AI Assistant"
        width={980}
        dismissOnBackdrop={!chatBusy}
        bodyStyle={{ padding: 0 }}
      >
        <div className="ai-assistant-shell">
          <div className="ai-assistant-banner">
            <div className="ai-assistant-banner__left">
              <div className="ai-assistant-avatar">AI</div>
            </div>
            <button
              type="button"
              className="ai-assistant-close"
              onClick={closeAssistant}
              disabled={chatBusy}
              aria-label="Close assistant"
              title="Close"
            >
              x
            </button>
          </div>

          <div ref={threadRef} className="ai-chat-thread">
            {chatMessages.map((msg, idx) => {
              const isUser = msg.role === 'user'
              return (
                <div key={`${msg.role}-${idx}`} className={`ai-chat-row ${isUser ? 'is-user' : 'is-assistant'}`}>
                  <div className={`ai-chat-bubble ${isUser ? 'is-user' : 'is-assistant'}`}>
                    <div className="ai-chat-text">{msg.content}</div>

                  </div>
                </div>
              )
            })}

            {assistantTyping && (
              <div className="ai-chat-row is-assistant">
                <div className="ai-chat-bubble is-assistant ai-chat-typing">
                  <span className="ai-typing-dots">
                    <span className="ai-dot ai-dot-1">.</span>
                    <span className="ai-dot ai-dot-2">.</span>
                    <span className="ai-dot ai-dot-3">.</span>
                  </span>
                </div>
              </div>
            )}
          </div>

          <div className="ai-chat-compose">
            <textarea
              ref={chatInputRef}
              className="ai-chat-input"
              rows={1}
              value={chatInput}
              onChange={handleChatInputChange}
              placeholder="Ask anything about DiscoveryOne..."
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  if (!chatBusy && String(chatInput || '').trim()) sendChat()
                }
              }}
            />
            <button
              className="ai-chat-send"
              type="button"
              onClick={sendChat}
              disabled={chatBusy || !String(chatInput || '').trim()}
            >
              {chatBusy ? 'Waiting' : 'Send'}
            </button>
          </div>
        </div>
      </Modal>
    </>
  )
}



