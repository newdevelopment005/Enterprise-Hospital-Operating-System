// HospitalGPT assistant app shell: login, status, model picker, chat and media tabs.

import { useCallback, useEffect, useState } from 'react'

import { ChatPanel } from './components/ChatPanel'
import { MediaPanel } from './components/MediaPanel'
import { AuthError, clearToken, getValidToken, login } from './lib/auth'
import { aiApi } from './lib/client'
import type { AiModel, AiStatus } from './lib/types'

type Tab = 'chat' | 'media'

export default function App() {
  const [authenticated, setAuthenticated] = useState(false)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [loginBusy, setLoginBusy] = useState(false)
  const [status, setStatus] = useState<AiStatus | null>(null)
  const [models, setModels] = useState<AiModel[]>([])
  const [modelKey, setModelKey] = useState('llama-3.1-8b')
  const [useRag, setUseRag] = useState(true)
  const [tab, setTab] = useState<Tab>('chat')
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setError(null)
    try {
      await getValidToken()
      setAuthenticated(true)
      const [st, ms] = await Promise.all([aiApi.status(), aiApi.listModels()])
      setStatus(st)
      setModels(ms.items)
      if (ms.items.length > 0) setModelKey(ms.items[0].model_key)
    } catch (err) {
      if (err instanceof AuthError) {
        setAuthenticated(false)
      } else {
        setError(err instanceof Error ? err.message : 'Unable to reach ai-service')
      }
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const submitLogin = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault()
      if (!username.trim() || loginBusy) return
      setLoginBusy(true)
      setError(null)
      try {
        await login(username.trim(), password)
        setAuthenticated(true)
        setPassword('')
        await load()
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Login failed')
      } finally {
        setLoginBusy(false)
      }
    },
    [username, password, loginBusy, load],
  )

  const signOut = () => {
    clearToken()
    setAuthenticated(false)
    setStatus(null)
    setModels([])
    setError(null)
  }

  if (!authenticated) {
    return (
      <div className="shell">
        <header className="app-header">
          <div>
            <h1>HospitalGPT</h1>
            <p>Local-only hospital AI · sign in to continue</p>
          </div>
        </header>
        <form className="login" onSubmit={submitLogin}>
          <h2>Sign in</h2>
          <p className="login-hint">
            Use a Keycloak <code>ehos</code> realm account (e.g. <code>admin</code>) to continue.
          </p>
          <label>
            Username
            <input
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
              autoFocus
            />
          </label>
          <label>
            Password
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
            />
          </label>
          {error && <div className="error">{error}</div>}
          <button type="submit" disabled={loginBusy || !username.trim() || !password}>
            {loginBusy ? 'Signing in…' : 'Sign in'}
          </button>
        </form>
      </div>
    )
  }

  return (
    <div className="shell">
      <header className="app-header">
        <div>
          <h1>HospitalGPT</h1>
          <p>Local-only hospital AI · no cloud · grounded in approved knowledge</p>
        </div>
        <nav className="tabs">
          <button className={tab === 'chat' ? 'active' : ''} onClick={() => setTab('chat')}>
            Chat
          </button>
          <button className={tab === 'media' ? 'active' : ''} onClick={() => setTab('media')}>
            Voice / OCR
          </button>
          <button className="ghost" onClick={signOut}>
            Sign out
          </button>
        </nav>
      </header>

      {error && <div className="error banner">{error}</div>}

      {tab === 'chat' ? (
        <ChatPanel
          models={models}
          status={status}
          modelKey={modelKey}
          setModelKey={setModelKey}
          useRag={useRag}
          setUseRag={setUseRag}
        />
      ) : (
        <MediaPanel />
      )}
    </div>
  )
}