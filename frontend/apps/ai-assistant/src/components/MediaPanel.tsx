// Media panel for HospitalGPT: STT (mic), TTS (speak), OCR (upload image).

import { useRef, useState } from 'react'

import { aiApi } from '../lib/client'

export function MediaPanel() {
  const [micText, setMicText] = useState<string | null>(null)
  const [micBusy, setMicBusy] = useState(false)
  const [ttsBusy, setTtsBusy] = useState(false)
  const [ocrText, setOcrText] = useState<string | null>(null)
  const [ocrBusy, setOcrBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const ocrInputRef = useRef<HTMLInputElement | null>(null)

  const recordMic = async () => {
    setMicBusy(true)
    setError(null)
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const recorder = new MediaRecorder(stream)
      const chunks: Blob[] = []
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunks.push(e.data)
      }
      recorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop())
        const blob = new Blob(chunks, { type: 'audio/webm' })
        const result = await aiApi.stt(blob)
        setMicText(result.text)
        setMicBusy(false)
      }
      recorder.start()
      setTimeout(() => void recorder.stop(), 4000)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Mic unavailable')
      setMicBusy(false)
    }
  }

  const speak = async (text: string | null) => {
    const phrase = text?.trim()
    if (!phrase || ttsBusy) return
    setTtsBusy(true)
    setError(null)
    try {
      const out = await aiApi.tts(phrase)
      const bytes = atob(out.audio_base64)
      const array = new Uint8Array(bytes.length)
      for (let i = 0; i < bytes.length; i++) array[i] = bytes.charCodeAt(i)
      const url = URL.createObjectURL(new Blob([array], { type: out.mime }))
      const audio = new Audio(url)
      audio.onended = () => URL.revokeObjectURL(url)
      await audio.play()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'TTS failed')
    } finally {
      setTtsBusy(false)
    }
  }

  const runOcr = async (file: File) => {
    setOcrBusy(true)
    setError(null)
    try {
      const result = await aiApi.ocr(file)
      setOcrText(result.text)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'OCR failed')
    } finally {
      setOcrBusy(false)
    }
  }

  return (
    <div className="media-panel">
      <section className="media-card">
        <h3>Speech-to-Text</h3>
        <p>Record a 4-second dictation; the local STT facade returns a transcript.</p>
        <button onClick={() => void recordMic()} disabled={micBusy}>
          {micBusy ? 'Recording…' : 'Record'}
        </button>
        {micText && (
          <textarea readOnly value={micText} rows={4} aria-label="transcript" />
        )}
      </section>

      <section className="media-card">
        <h3>Text-to-Speech</h3>
        <p>Send the latest assistant answer to the local TTS facade (offline WAV).</p>
        <button onClick={() => void speak(micText)} disabled={ttsBusy}>
          {ttsBusy ? 'Speaking…' : 'Speak'}
        </button>
      </section>

      <section className="media-card">
        <h3>OCR</h3>
        <p>Upload an image containing text; the local OCR facade extracts it.</p>
        <input
          ref={ocrInputRef}
          type="file"
          accept="image/*"
          onChange={(e) => {
            const file = e.target.files?.[0]
            if (file) void runOcr(file)
          }}
        />
        {ocrBusy && <p>Extracting…</p>}
        {ocrText && <textarea readOnly value={ocrText} rows={4} aria-label="ocr text" />}
      </section>

      {error && <div className="error">{error}</div>}
    </div>
  )
}