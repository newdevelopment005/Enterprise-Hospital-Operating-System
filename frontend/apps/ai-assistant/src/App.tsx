// HospitalGPT assistant app shell: status, model picker, chat and media tabs.

import { useEffect, useState } from 'react'

import { ChatPanel } from './components/ChatPanel'
import { MediaPanel } from './components/MediaPanel'
import { aiApi } from './lib/client'
import type { AiModel, AiStatus } from './lib/types'

type Tab = 'chat' | 'media'

export default function App() {
  const [status, setStatus] = useState<AiStatus | null>(null)
  const [models, setModels] = useState<AiModel[]>([])
  const [modelKey, setModelKey] = useState('llama-3.1-8b')
  const [useRag, setUseRag] = useState(true)
  const [tab, setTab] = useState<Tab>('chat')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const load = async () => {
      try {
        const [st, ms] = await Promise.all([aiApi.status(), aiApi.listModels()])
        setStatus(st)
        setModels(ms.items)
        if (ms.items.length > 0) setModelKey(ms.items[0].model_key)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Unable to reach ai-service')
      }
    }
    void load()
  }, [])

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