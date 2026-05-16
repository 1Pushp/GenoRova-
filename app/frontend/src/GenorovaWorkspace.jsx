import { useEffect, useRef, useState } from 'react'
import GenorovaLogo from './components/GenorovaLogo'

/* -- Colors (match landing page) -- */
const C = {
  bg: '#FFFFFF',
  sidebar: '#F0F4FF',
  border: '#E0E8FF',
  blue: '#0F2D6E',
  blue2: '#1A4BAD',
  cyan: '#00CFFF',
  grey: '#6B7FAB',
  lgrey: '#F7F9FF',
  white: '#FFFFFF',
  msgUser: '#EEF2FF',
  msgAI: '#FFFFFF',
}

/* -- Demo prompts -- */
const DEMOS = [
  'Generate 10 DPP-4 inhibitors under 450 daltons',
  'Suggest 3D prompt for DPP4 docking',
  'Show me antibacterial candidates with high QED score',
  'Find drug-like molecules similar to Sitagliptin',
  'Generate 5 molecules for diabetes research',
  'What is the ADMET profile of aspirin?',
]

const RAW_API_BASE = import.meta.env.VITE_API_BASE_URL || window.location.origin
const API_BASE = RAW_API_BASE.replace(/\/$/, '')
const CHAT_ENDPOINT = `${API_BASE}/api/chat`
const CHAT_TIMEOUT_MS = 120000
const CHAT_TIMEOUT_MESSAGE =
  'Request took too long. Render free instance/model may still be warming up. Please retry.'

/* -- API helpers -- */
async function getUser() {
  try {
    const r = await fetch('/auth/me', { credentials: 'include' })
    if (!r.ok) return null
    const data = await r.json()
    return data.user || data
  } catch {
    return null
  }
}

async function logout() {
  await fetch('/auth/logout', { method: 'POST', credentials: 'include' })
  window.location.reload()
}

async function sendMessage(message, sessionId) {
  const controller = new AbortController()
  const timeout = setTimeout(() => {
    console.warn('[Chat] aborting request after timeout', {
      endpoint: CHAT_ENDPOINT,
      timeoutMs: CHAT_TIMEOUT_MS,
    })
    controller.abort(CHAT_TIMEOUT_MESSAGE)
  }, CHAT_TIMEOUT_MS)

  const body = {
    message,
    session_id: sessionId ?? null,
    mode: 'chat',
  }

  sendMessage.lastEndpoint = CHAT_ENDPOINT
  sendMessage.lastStatusCode = null
  sendMessage.lastError = null

  try {
    console.log('[Chat] CHAT_ENDPOINT', CHAT_ENDPOINT)
    console.log('[Chat] endpoint called', CHAT_ENDPOINT)
    console.log('[Chat] sending body', body)

    const r = await fetch(CHAT_ENDPOINT, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: controller.signal,
    })

    sendMessage.lastStatusCode = r.status
    console.log('[Chat] status code', r.status)

    const text = await r.text()
    console.log('[Chat] raw response text', text)
    let payload = {}

    try {
      payload = text ? JSON.parse(text) : {}
    } catch {
      payload = { reply: text }
    }

    console.log('[Chat] response JSON', payload)

    if (!r.ok) {
      throw Object.assign(
        new Error(
          payload?.detail ||
            payload?.reply ||
            payload?.error ||
            `Chat request failed with status ${r.status}`,
        ),
        { response: r, data: payload, statusCode: r.status, endpoint: CHAT_ENDPOINT },
      )
    }

    return payload
  } catch (err) {
    const abortReason = controller.signal.reason || err?.message || 'No abort reason provided'
    const isAbort = err?.name === 'AbortError' || controller.signal.aborted
    if (isAbort) {
      console.warn('[Chat] abort reason', abortReason)
    }
    const friendlyError = isAbort ? CHAT_TIMEOUT_MESSAGE : String(err?.message || err)
    sendMessage.lastError = friendlyError
    console.error('[Chat] fetch failed', err)
    if (isAbort) {
      throw Object.assign(new Error(CHAT_TIMEOUT_MESSAGE), {
        name: 'AbortError',
        endpoint: CHAT_ENDPOINT,
        abortReason,
        isAbort: true,
      })
    }
    throw err
  } finally {
    clearTimeout(timeout)
  }
}

async function getSessions() {
  try {
    const r = await fetch('/api/chat/sessions', { credentials: 'include' })
    if (!r.ok) return []
    const d = await r.json()
    return Array.isArray(d) ? d : d.sessions || []
  } catch {
    return []
  }
}

function valueFrom(obj, keys, fallback = '') {
  for (const key of keys) {
    const value = obj?.[key]
    if (value !== undefined && value !== null && value !== '') return value
  }
  return fallback
}

function extractMolecules(data) {
  if (!data || typeof data !== 'object') return []
  if (Array.isArray(data.molecules) && data.molecules.length > 0) {
    return data.molecules
  }
  if (Array.isArray(data.generated_candidates) && data.generated_candidates.length > 0) {
    return data.generated_candidates
  }
  if (Array.isArray(data.comparison?.molecules) && data.comparison.molecules.length > 0) {
    return data.comparison.molecules
  }
  if (data.candidate?.smiles) {
    return [data.candidate]
  }
  return []
}

function errorText(value, fallback = 'Request failed') {
  if (!value) return fallback
  if (typeof value === 'string') return value
  if (Array.isArray(value)) return value.map((item) => errorText(item, '')).filter(Boolean).join('; ') || fallback
  if (typeof value === 'object') {
    return value.message || value.detail || value.error || JSON.stringify(value)
  }
  return String(value)
}

function makeMessageId(offset = 0) {
  return globalThis.crypto?.randomUUID?.() || String(Date.now() + offset)
}

/* -- Format AI response into readable text -- */
function formatResponse(data) {
  if (typeof data === 'string') return data

  const parts = []

  const primaryReply = data.reply || data.summary || data.message
  if (primaryReply) parts.push(primaryReply)

  if (data.generated_candidates?.length > 0) {
    parts.push(`\n**Generated ${data.generated_candidates.length} candidates:**`)
    data.generated_candidates.slice(0, 5).forEach((mol, i) => {
      const smiles = valueFrom(mol, ['smiles', 'SMILES'])
      const score = valueFrom(mol, [
        'composite_score',
        'clinical_score',
        'score',
      ])
      const grade = valueFrom(mol, ['grade', 'recommendation'])
      const qed = valueFrom(mol, ['QED', 'qed', 'qed_score'])
      const mw = valueFrom(mol, [
        'mol_weight',
        'MW',
        'mw',
        'molecular_weight',
      ])
      const shownSmiles =
        smiles.length > 45 ? `${smiles.slice(0, 45)}...` : smiles

      parts.push(
        `\n${i + 1}. **${shownSmiles}**\n` +
          `   Score: ${score} · Grade: ${grade} · QED: ${qed} · MW: ${mw} Da`,
      )
    })
  }

  if (data.candidate) {
    const c = data.candidate
    const smiles = valueFrom(c, ['smiles', 'SMILES'])
    if (smiles) {
      parts.push(
        `\n**Top Candidate:**\n${smiles}\n` +
          `Score: ${valueFrom(c, ['composite_score', 'clinical_score', 'score'])} · ` +
          `Grade: ${valueFrom(c, ['grade', 'recommendation'])} · ` +
          `QED: ${valueFrom(c, ['QED', 'qed', 'qed_score'])}`,
      )
    }
  }

  if (data.limitations?.length > 0) {
    parts.push(`\n**Important:** ${data.limitations[0]}`)
  }

  if (data.next_steps?.length > 0) {
    parts.push(`\n**Next steps:** ${data.next_steps[0]}`)
  }

  return (
    parts.join('\n').trim() ||
    data.message ||
    'I processed your request. Could you be more specific?'
  )
}

function contentFromStoredMessage(message) {
  if (typeof message.content === 'string') return message.content
  if (message.payload) return formatResponse(message.payload)
  if (message.content) return formatResponse(message.content)
  return ''
}

function MoleculeCards({ molecules }) {
  if (!molecules?.length) return null

  return (
    <div
      style={{
        marginTop: 12,
        display: 'grid',
        gap: 10,
      }}
    >
      {molecules.slice(0, 5).map((molecule, index) => {
        const smiles = valueFrom(molecule, ['smiles', 'SMILES'], 'Unknown SMILES')
        const score = valueFrom(molecule, ['score', 'clinical_score', 'composite_score', 'rank_score'], 'n/a')
        const qed = valueFrom(molecule, ['qed_score', 'QED', 'qed'], 'n/a')
        const mw = valueFrom(molecule, ['molecular_weight', 'mol_weight', 'MW', 'mw'], 'n/a')
        const grade = valueFrom(molecule, ['grade', 'recommendation', 'rank_label'], '')

        return (
          <div
            key={`${smiles}-${index}`}
            style={{
              border: `1px solid ${C.border}`,
              borderRadius: 12,
              background: C.lgrey,
              padding: 12,
            }}
          >
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                gap: 10,
                alignItems: 'center',
                marginBottom: 8,
              }}
            >
              <div style={{ fontSize: 12, fontWeight: 700, color: C.blue2 }}>
                Molecule {index + 1}
              </div>
              {grade && (
                <div
                  style={{
                    fontSize: 11,
                    color: C.blue,
                    background: C.white,
                    border: `1px solid ${C.border}`,
                    borderRadius: 999,
                    padding: '2px 8px',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {grade}
                </div>
              )}
            </div>
            {molecule.molecule_svg ? (
              <div
                style={{
                  background: C.white,
                  border: `1px solid ${C.border}`,
                  borderRadius: 10,
                  marginBottom: 8,
                  overflow: 'hidden',
                  maxHeight: 180,
                }}
                dangerouslySetInnerHTML={{ __html: molecule.molecule_svg }}
              />
            ) : null}
            <div
              style={{
                fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
                fontSize: 12,
                color: C.blue,
                wordBreak: 'break-all',
                lineHeight: 1.5,
              }}
            >
              {smiles}
            </div>
            <div
              style={{
                display: 'flex',
                flexWrap: 'wrap',
                gap: 6,
                marginTop: 8,
                color: C.grey,
                fontSize: 11,
              }}
            >
              <span>Score: {score}</span>
              <span>QED: {qed}</span>
              <span>MW: {mw}</span>
            </div>
          </div>
        )
      })}
    </div>
  )
}

/* -- Message bubble -- */
function Message({ msg }) {
  const isUser = msg.role === 'user'
  const isTyping = msg.typing || msg.loading

  return (
    <div
      style={{
        display: 'flex',
        justifyContent: isUser ? 'flex-end' : 'flex-start',
        marginBottom: 16,
        gap: 10,
        alignItems: 'flex-start',
      }}
    >
      {!isUser && (
        <div
          style={{
            width: 32,
            height: 32,
            borderRadius: '50%',
            flexShrink: 0,
            background: `linear-gradient(135deg, ${C.blue2}, ${C.cyan})`,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <GenorovaLogo size={18} showText={false} />
        </div>
      )}

      <div
        style={{
          maxWidth: '72%',
          background: isUser ? C.msgUser : C.msgAI,
          border: `1px solid ${isUser ? '#C7D8FF' : C.border}`,
          borderRadius: isUser ? '18px 18px 4px 18px' : '4px 18px 18px 18px',
          padding: '12px 16px',
          boxShadow: '0 1px 4px rgba(15,45,110,0.06)',
        }}
      >
        {isTyping ? (
          <div
            style={{
              display: 'flex',
              gap: 8,
              alignItems: 'center',
              color: C.grey,
              fontSize: 13,
              lineHeight: 1.5,
              minWidth: 150,
            }}
          >
            <span>Genorova is thinking</span>
            <span
              aria-label="Genorova is thinking"
              style={{
                display: 'inline-flex',
                gap: 5,
                alignItems: 'center',
              }}
            >
            {[0, 1, 2].map((i) => (
              <div
                key={i}
                style={{
                  width: 6,
                  height: 6,
                  borderRadius: '50%',
                  background: C.blue2,
                  opacity: 0.4,
                  animation: `pulse 1.2s ease-in-out ${i * 0.2}s infinite`,
                }}
              />
            ))}
            </span>
          </div>
        ) : (
          <div
            style={{
              color: msg.error ? '#991B1B' : C.blue,
              fontSize: 14,
              lineHeight: 1.7,
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
            }}
          >
            {msg.content.split('**').map((part, i) =>
              i % 2 === 1 ? <strong key={i}>{part}</strong> : <span key={i}>{part}</span>,
            )}
          </div>
        )}
        {!isTyping && msg.error && (
          <div
            style={{
              marginTop: 10,
              border: '1px solid #FCA5A5',
              background: '#FEF2F2',
              color: '#991B1B',
              borderRadius: 10,
              padding: '8px 10px',
              fontSize: 12,
              lineHeight: 1.5,
            }}
          >
            Backend request failed. Check the browser console for endpoint, status code,
            response JSON, and error details.
          </div>
        )}
        {!isTyping && !isUser && <MoleculeCards molecules={msg.molecules} />}
        {!isTyping && msg.source && (
          <div
            style={{
              marginTop: 6,
              fontSize: 10,
              color: C.grey,
              display: 'flex',
              alignItems: 'center',
              gap: 4,
            }}
          >
            <span
              style={{
                background: 'rgba(0,207,255,0.1)',
                border: '1px solid rgba(0,207,255,0.3)',
                color: C.blue2,
                padding: '1px 7px',
                borderRadius: 8,
                fontSize: 10,
                fontWeight: 600,
              }}
            >
              {msg.source}
            </span>
          </div>
        )}
      </div>

      {isUser && (
        <div
          style={{
            width: 32,
            height: 32,
            borderRadius: '50%',
            flexShrink: 0,
            background: C.blue2,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: C.white,
            fontSize: 13,
            fontWeight: 700,
          }}
        >
          {msg.userName?.[0]?.toUpperCase() || 'U'}
        </div>
      )}
    </div>
  )
}

/* -- Main Workspace -- */
export default function GenorovaWorkspace() {
  const [user, setUser] = useState(null)
  const [sessions, setSessions] = useState([])
  const [sessionId, setSessionId] = useState(null)
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [lastError, setLastError] = useState(null)
  const [chatDebug, setChatDebug] = useState({
    lastEndpoint: CHAT_ENDPOINT,
    lastStatusCode: null,
    lastError: null,
  })
  const [sidebarOpen, setSidebar] = useState(true)
  const bottomRef = useRef(null)

  /* Load user + sessions on mount */
  useEffect(() => {
    getUser().then((u) => {
      setUser(u)
      if (!u) window.location.href = '/'
    })
    getSessions().then(setSessions)
  }, [])

  /* Auto scroll to bottom */
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  /* Start new chat */
  const newChat = () => {
    setSessionId(null)
    setMessages([])
    setInput('')
    setLastError(null)
  }

  /* Load existing session */
  const loadSession = async (sid) => {
    setSessionId(sid)
    setMessages([])
    try {
      const r = await fetch(`/api/chat/sessions/${sid}`, {
        credentials: 'include',
      })
      if (r.ok) {
        const d = await r.json()
        const session = d.session || d
        const history = session.messages || d.messages || d.history || []
        setMessages(
          history.map((m) => ({
            role: m.role,
            content: contentFromStoredMessage(m),
            payload: m.payload || null,
            molecules: extractMolecules(m.payload || m.content),
            source: m.payload?.source || m.payload?.program_context?.model || null,
            userName: user?.name || user?.email,
          })),
        )
      }
    } catch {
      setMessages([])
    }
  }

  /* Send message */
  const send = async (overrideText) => {
    const text = String(typeof overrideText === 'string' ? overrideText : input).trim()
    if (!text || loading) return

    const typingId = 'assistant-typing'
    const userMessage = {
      id: makeMessageId(),
      role: 'user',
      content: text,
      userName: user?.name || user?.email || 'You',
    }
    const typingMessage = {
      id: typingId,
      role: 'assistant',
      content: '',
      typing: true,
    }

    setMessages((prev) => [...prev, userMessage, typingMessage])
    setInput('')
    setLoading(true)
    setLastError(null)
    setChatDebug({
      lastEndpoint: CHAT_ENDPOINT,
      lastStatusCode: null,
      lastError: null,
    })

    try {
      console.log('[Chat] submit message', text)

      const payload = await sendMessage(text, sessionId)

      console.log('[Chat] response payload', payload)

      const reply =
        payload?.reply ||
        payload?.message ||
        payload?.response ||
        payload?.answer ||
        'No response returned from GenorovaAI.'

      const assistantMessage = {
        id: makeMessageId(1),
        role: 'assistant',
        content: reply,
        intent: payload?.intent || 'general',
        molecules: payload?.molecules || extractMolecules(payload),
        metadata: payload?.metadata || {},
        payload,
      }

      setMessages((prev) => [
        ...prev.filter((message) => message.id !== typingId),
        assistantMessage,
      ])

      if (payload?.metadata?.session_id) {
        setSessionId(payload.metadata.session_id)
        getSessions().then(setSessions)
      } else if (payload?.session_id && !sessionId) {
        setSessionId(payload.session_id)
        getSessions().then(setSessions)
      }

      setChatDebug({
        lastEndpoint: sendMessage.lastEndpoint || CHAT_ENDPOINT,
        lastStatusCode: sendMessage.lastStatusCode ?? null,
        lastError: null,
      })
    } catch (e) {
      console.error('[Chat] error', e)
      const errorMsg =
        e?.isAbort || e?.name === 'AbortError'
          ? CHAT_TIMEOUT_MESSAGE
          : 'Backend request failed. Please check login/session, API endpoint, or Render deployment logs.'

      setLastError(errorMsg)
      setChatDebug({
        lastEndpoint: e.endpoint || sendMessage.lastEndpoint || CHAT_ENDPOINT,
        lastStatusCode: e.statusCode || sendMessage.lastStatusCode || null,
        lastError: String(e?.message || e),
      })
      setMessages((prev) => [
        ...prev.filter((message) => message.id !== typingId),
        {
          id: makeMessageId(2),
          role: 'assistant',
          content: errorMsg,
          intent: 'error',
          molecules: [],
          metadata: { error: String(e?.message || e) },
          error: true,
        },
      ])
    } finally {
      setLoading(false)
      setChatDebug((prev) => ({
        ...prev,
        lastEndpoint: prev.lastEndpoint || CHAT_ENDPOINT,
      }))
    }
  }

  const firstName = user?.name?.split(' ')[0] || user?.email?.split('@')[0] || 'Researcher'

  return (
    <>
      <style>{`
        @keyframes pulse {
          0%,100% { opacity:0.3; transform:scale(0.8) }
          50% { opacity:1; transform:scale(1.1) }
        }
        * { box-sizing: border-box; margin: 0; padding: 0 }
        body { background: ${C.white} }
        textarea:focus, input:focus { outline: none }
        ::-webkit-scrollbar { width: 5px }
        ::-webkit-scrollbar-thumb {
          background: ${C.border}; border-radius: 4px
        }
      `}</style>

      <div
        style={{
          display: 'flex',
          height: '100vh',
          fontFamily: '"Inter","SF Pro",system-ui,sans-serif',
          background: C.white,
          color: C.blue,
          overflow: 'hidden',
        }}
      >
        {/* -- SIDEBAR -- */}
        <div
          style={{
            width: sidebarOpen ? 260 : 0,
            minWidth: sidebarOpen ? 260 : 0,
            background: C.sidebar,
            borderRight: `1px solid ${C.border}`,
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden',
            transition: 'width 0.25s ease, min-width 0.25s ease',
          }}
        >
          <div
            style={{
              padding: '16px 14px',
              borderBottom: `1px solid ${C.border}`,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
            }}
          >
            <GenorovaLogo size={28} showText={true} />
          </div>

          <div style={{ padding: '12px 12px 6px' }}>
            <button
              type="button"
              onClick={newChat}
              style={{
                width: '100%',
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                padding: '9px 14px',
                borderRadius: 10,
                background: C.blue2,
                color: C.white,
                border: 'none',
                cursor: 'pointer',
                fontSize: 13,
                fontWeight: 600,
                boxShadow: '0 2px 8px rgba(26,75,173,0.2)',
              }}
            >
              <span style={{ fontSize: 16 }}>+</span>
              New Chat
            </button>
          </div>

          <div
            style={{
              flex: 1,
              overflowY: 'auto',
              padding: '6px 12px',
            }}
          >
            {sessions.length > 0 && (
              <div
                style={{
                  color: C.grey,
                  fontSize: 11,
                  fontWeight: 600,
                  letterSpacing: '0.06em',
                  padding: '8px 4px 6px',
                  textTransform: 'uppercase',
                }}
              >
                Recent
              </div>
            )}
            {sessions.map((s) => {
              const sid = s.id || s.session_id
              return (
                  <button
                  type="button"
                  key={sid}
                  onClick={() => loadSession(sid)}
                  style={{
                    width: '100%',
                    textAlign: 'left',
                    padding: '9px 10px',
                    borderRadius: 8,
                    background: sessionId === sid ? C.border : 'transparent',
                    border: 'none',
                    cursor: 'pointer',
                    fontSize: 13,
                    color: C.blue,
                    marginBottom: 2,
                    display: 'block',
                    whiteSpace: 'nowrap',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    transition: 'background 0.15s',
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.background = C.border
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.background =
                      sessionId === sid ? C.border : 'transparent'
                  }}
                >
                  💬 {s.title || s.first_message || `Chat ${(sid || '').slice(0, 8)}`}
                </button>
              )
            })}
            {sessions.length === 0 && (
              <div
                style={{
                  color: C.grey,
                  fontSize: 12,
                  textAlign: 'center',
                  padding: '24px 8px',
                  lineHeight: 1.6,
                }}
              >
                Your conversations will appear here
              </div>
            )}
          </div>

          <div
            style={{
              padding: 12,
              borderTop: `1px solid ${C.border}`,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: 8,
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <div
                style={{
                  width: 32,
                  height: 32,
                  borderRadius: '50%',
                  background: C.blue2,
                  color: C.white,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: 13,
                  fontWeight: 700,
                  flexShrink: 0,
                }}
              >
                {firstName[0]?.toUpperCase()}
              </div>
              <div style={{ overflow: 'hidden' }}>
                <div
                  style={{
                    fontSize: 13,
                    fontWeight: 600,
                    color: C.blue,
                    whiteSpace: 'nowrap',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    maxWidth: 140,
                  }}
                >
                  {firstName}
                </div>
                <div
                  style={{
                    fontSize: 10,
                    color: C.grey,
                    whiteSpace: 'nowrap',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    maxWidth: 140,
                  }}
                >
                  {user?.email}
                </div>
              </div>
            </div>
            <button
              type="button"
              onClick={logout}
              title="Log out"
              style={{
                background: 'transparent',
                border: 'none',
                cursor: 'pointer',
                color: C.grey,
                fontSize: 16,
                padding: 4,
                borderRadius: 6,
                flexShrink: 0,
              }}
            >
              ↩
            </button>
          </div>
        </div>

        {/* -- MAIN AREA -- */}
        <div
          style={{
            flex: 1,
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden',
            background: C.white,
          }}
        >
          <div
            style={{
              padding: '12px 20px',
              borderBottom: `1px solid ${C.border}`,
              display: 'flex',
              alignItems: 'center',
              gap: 12,
              background: C.white,
              boxShadow: '0 1px 4px rgba(15,45,110,0.04)',
            }}
          >
            <button
              type="button"
              onClick={() => setSidebar((o) => !o)}
              style={{
                background: 'transparent',
                border: 'none',
                cursor: 'pointer',
                color: C.grey,
                fontSize: 18,
                padding: '4px 6px',
                borderRadius: 6,
                lineHeight: 1,
              }}
            >
              ☰
            </button>
            <div
              style={{
                fontSize: 14,
                fontWeight: 600,
                color: C.blue2,
              }}
            >
              Genorova AI
            </div>
            <div
              style={{
                marginLeft: 'auto',
                display: 'flex',
                alignItems: 'center',
                gap: 6,
              }}
            >
              <div
                style={{
                  background: 'rgba(0,207,255,0.1)',
                  border: '1px solid rgba(0,207,255,0.3)',
                  color: C.blue2,
                  padding: '3px 10px',
                  borderRadius: 12,
                  fontSize: 11,
                  fontWeight: 600,
                }}
              >
                CVAE v1.0 · SNN 0.611
              </div>
            </div>
          </div>

          <div
            style={{
              flex: 1,
              overflowY: 'auto',
              padding: '24px 20px',
            }}
          >
            {messages.length === 0 ? (
              <div
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  justifyContent: 'center',
                  minHeight: '60vh',
                  textAlign: 'center',
                  padding: '0 24px',
                }}
              >
                <GenorovaLogo size={52} showText={true} />
                <h2
                  style={{
                    marginTop: 20,
                    fontSize: 22,
                    fontWeight: 700,
                    color: C.blue,
                  }}
                >
                  Hello, {firstName} 👋
                </h2>
                <p
                  style={{
                    color: C.grey,
                    fontSize: 14,
                    marginTop: 8,
                    marginBottom: 32,
                    maxWidth: 420,
                    lineHeight: 1.6,
                  }}
                >
                  Ask me to generate drug-like molecules, score compounds, or explore
                  chemical space. Try one of these:
                </p>

                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
                    gap: 10,
                    width: '100%',
                    maxWidth: 680,
                  }}
                >
                  {DEMOS.map((d) => (
                    <button
                      type="button"
                      key={d}
                      onClick={() => send(d)}
                      style={{
                        background: C.lgrey,
                        border: `1px solid ${C.border}`,
                        borderRadius: 12,
                        padding: '12px 14px',
                        textAlign: 'left',
                        cursor: 'pointer',
                        fontSize: 13,
                        color: C.blue,
                        lineHeight: 1.45,
                        transition: 'all 0.15s',
                      }}
                      onMouseEnter={(e) => {
                        e.currentTarget.style.background = C.msgUser
                        e.currentTarget.style.borderColor = '#C7D8FF'
                      }}
                      onMouseLeave={(e) => {
                        e.currentTarget.style.background = C.lgrey
                        e.currentTarget.style.borderColor = C.border
                      }}
                    >
                      {d}
                    </button>
                  ))}
                </div>

                <p
                  style={{
                    marginTop: 28,
                    fontSize: 11,
                    color: C.grey,
                    maxWidth: 440,
                    lineHeight: 1.6,
                  }}
                >
                  Genorova AI generates computational candidates only. All results require
                  wet-lab validation.
                </p>
              </div>
            ) : (
              <div style={{ maxWidth: 760, margin: '0 auto', width: '100%' }}>
                {messages.map((msg, i) => (
                  <Message key={i} msg={msg} />
                ))}
                <div ref={bottomRef} />
              </div>
            )}
          </div>

          <div
            style={{
              padding: '12px 20px 20px',
              background: C.white,
              borderTop: `1px solid ${C.border}`,
            }}
          >
            {lastError && (
              <div
                style={{
                  maxWidth: 760,
                  margin: '0 auto 10px',
                  border: '1px solid #FCA5A5',
                  background: '#FEF2F2',
                  color: '#991B1B',
                  borderRadius: 12,
                  padding: '10px 12px',
                  fontSize: 13,
                  lineHeight: 1.5,
                }}
              >
                Chat request failed: {lastError}
              </div>
            )}
            <div
              style={{
                maxWidth: 760,
                margin: '0 auto',
                display: 'flex',
                gap: 10,
                alignItems: 'flex-end',
                background: C.lgrey,
                border: `1.5px solid ${C.border}`,
                borderRadius: 14,
                padding: '10px 14px',
                boxShadow: '0 2px 12px rgba(15,45,110,0.06)',
                transition: 'border-color 0.2s',
              }}
            >
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault()
                    send()
                  }
                }}
                placeholder="Ask Genorova to generate molecules, score compounds..."
                rows={1}
                style={{
                  flex: 1,
                  background: 'transparent',
                  border: 'none',
                  resize: 'none',
                  fontSize: 14,
                  color: C.blue,
                  lineHeight: 1.5,
                  maxHeight: 120,
                  overflowY: 'auto',
                  fontFamily: 'inherit',
                }}
              />
              <button
                type="button"
                onClick={send}
                disabled={loading || !input.trim()}
                style={{
                  width: 36,
                  height: 36,
                  borderRadius: 10,
                  background:
                    loading || !input.trim()
                      ? C.border
                      : `linear-gradient(135deg, ${C.blue2}, #2563EB)`,
                  border: 'none',
                  cursor: loading || !input.trim() ? 'not-allowed' : 'pointer',
                  color: C.white,
                  fontSize: 16,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  flexShrink: 0,
                  transition: 'all 0.2s',
                  boxShadow:
                    loading || !input.trim()
                      ? 'none'
                      : '0 2px 8px rgba(26,75,173,0.3)',
                }}
              >
                ↑
              </button>
            </div>
            <div
              style={{
                textAlign: 'center',
                marginTop: 8,
                fontSize: 11,
                color: C.grey,
              }}
            >
              Genorova generates computational candidates only · Shift+Enter for new line
            </div>
          </div>
        </div>
      </div>
    </>
  )
}
