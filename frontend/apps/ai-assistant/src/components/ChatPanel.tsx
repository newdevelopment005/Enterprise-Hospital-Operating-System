// Chat panel for HospitalGPT: messages, RAG source citations, controls.

import { useCallback, useEffect, useRef, useState } from 'react'

import { aiApi } from '../lib/client'
import type { AiModel, AiStatus, ChatIn, Message } from '../lib/types'

const USER_ID = 'clinic-user-1'

interface Props {
  models: AiModel[]
  status: AiStatus | null
  modelKey: string
  setModelKey: (key: string) => void
  useRag: boolean
  setUseRag: (v: boolean) => void
}

export function ChatPanel({ models, status, modelKey, setModelKey, useRag, setUseRag }: Props) {
  const [conversationId, setConversationId] = useState<string | null>(null)
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [lastRequestId, setLastRequestId] = useState<string | null>(null)
  const [rating, setRating] = useState<number | null>(null)
  const [feedbackSent, setFeedbackSent] = useState(false)
  const bottomRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, busy])

  const send = useCallback(async () => {
    const text = input.trim()
    if (!text || busy) return
    setBusy(true)
    setError(null)
    setFeedbackSent(false)
    setRating(null)
    const payload: ChatIn = { message: text, user_id: USER_ID, model_key: modelKey, use_rag: useRag }
    if (conversationId) payload.conversation_id = conversationId
    try {
      const result = await aiApi.chat(payload)
      setConversationId(result.conversation_id)
      setLastRequestId(result.request_id)
      const history = await aiApi.listMessages(result.conversation_id)
      setMessages(history.items)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Chat failed')
    } finally {
      setBusy(false)
      setInput('')
    }
  }, [busy, input, modelKey, useRag, conversationId])

  const startNew = useCallback(async () => {
    setConversationId(null)
    setMessages([])
    setLastRequestId(null)
    setFeedbackSent(false)
    setRating(null)
    setError(null)
  }, [])

  const recordFeedback = useCallback(
    async (value: number) => {
      if (!lastRequestId || feedbackSent) return
      setRating(value)
      setFeedbackSent(true)
      try {
        await aiApi.sendFeedback({ ai_request_id: lastRequestId, user_id: USER_ID, rating: value, accepted: value >= 4 })
      } catch {
        setFeedbackSent(false)
      }
    },
    [lastRequestId, feedbackSent],
  )

  const lastAssistant = [...messages].reverse().find((m) => m.role === 'ASSISTANT')

  return (
    <div className="chat-panel">
      <header className="chat-header">
        <div>
          <strong>HospitalGPT</strong>
          <span className="badge-meta">
            {status ? `${status.inference_adapter} · offline` : 'offline local'}
          </span>
        </div>
        <div className="chat-controls">
          <label className="control">
            Model
            <select value={modelKey} onChange={(e) => setModelKey(e.target.value)}>
              {models.map((m) => (
                <option key={m.model_key} value={m.model_key}>
                  {m.base_name} {m.version}
                  {m.load_status === 'LOADED' ? ' ●' : ''}
                </option>
              ))}
            </select>
          </label>
          <label className="control check">
            <input type="checkbox" checked={useRag} onChange={(e) => setUseRag(e.target.checked)} />
            RAG
          </label>
          <button className="ghost" onClick={startNew} disabled={busy}>
            New chat
          </button>
        </div>
      </header>

      <main className="messages">
        {messages.length === 0 && (
          <div className="empty">
            <p>Local-only clinical assistant. Ask about guidelines, policies, medications or lab ranges.</p>
          </div>
        )}
        {messages.map((m) => (
          <div key={m.id} className={`message ${m.role === 'USER' ? 'user' : 'assistant'}`}>
            <div className="message-role">{m.role === 'USER' ? 'You' : 'HospitalGPT'}</div>
            <div className="message-body">
              <pre className="answer">{m.content}</pre>
              {m.role === 'ASSISTANT' && m.sources?.items && m.sources.items.length > 0 && (
                <details className="sources">
                  <summary>Sources ({m.sources.items.length})</summary>
                  <ul>
                    {m.sources.items.map((s, i) => (
                      <li key={i}>
                        <span className="doc-type">{s.doc_type}</span> {s.document_title} ·{' '}
                        <span className="score">{s.score.toFixed(3)}</span>
                      </li>
                    ))}
                  </ul>
                </details>
              )}
            </div>
          </div>
        ))}
        {busy && (
          <div className="message assistant">
            <div className="message-role">HospitalGPT</div>
            <div className="message-body">
              <span className="typing">Thinking…</span>
            </div>
          </div>
        )}
        {error && <div className="error">{error}</div>}
        <div ref={bottomRef} />
      </main>

      {lastAssistant && lastRequestId && (
        <div className="feedback-row">
          <span>Was this helpful?</span>
          {[1, 2, 3, 4, 5].map((n) => (
            <button
              key={n}
              className={`star ${rating === n ? 'on' : ''}`}
              onClick={() => void recordFeedback(n)}
              disabled={feedbackSent}
            >
              {n}
            </button>
          ))}
          {feedbackSent && <span className="feedback-done">Feedback recorded ✓</span>}
        </div>
      )}

      <footer className="composer">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') void send()
          }}
          placeholder="Ask about hospital knowledge…"
          disabled={busy}
        />
        <button onClick={() => void send()} disabled={busy || !input.trim()}>
          Send
        </button>
      </footer>
    </div>
  )
}