// Queues panel: create queues, join the current patient, call-next, serve.

import { FormEvent, useState } from 'react'
import { queuesApi } from '../lib/client'
import type { Queue, QueueBoard, QueueEntry } from '../lib/types'
import { PanelShell, fmt, useLoad } from './Panels'

const QUEUE_TYPES = ['OUTPATIENT', 'EMERGENCY', 'LAB', 'PHARMACY', 'ADMISSION', 'RADIOLOGY']

export function QueuesPanel({ patientId }: { patientId: string }) {
  const [selectedId, setSelectedId] = useState('')
  const { data: queues, error: listError, reload: reloadQueues } = useLoad(() => queuesApi.list())
  const boardLoader = async (): Promise<QueueBoard | null> =>
    selectedId ? queuesApi.board(selectedId) : null
  const { data: board, error: boardError, reload: reloadBoard } = useLoad(boardLoader)

  const [newType, setNewType] = useState('OUTPATIENT')
  const [priority, setPriority] = useState('0')
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const run = async (fn: () => Promise<string | void>) => {
    setError(null)
    try {
      const msg = await fn()
      if (msg) setMessage(msg)
      await Promise.all([reloadQueues(), reloadBoard()])
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Action failed')
    }
  }

  const createQueue = (e: FormEvent) => {
    e.preventDefault()
    void run(async () => {
      await queuesApi.create(newType)
      return `Queue created (${newType})`
    })
  }

  const joinCurrentPatient = () =>
    run(async () => {
      const entry = await queuesApi.join(selectedId, patientId, Number(priority) || 0)
      return `Joined with ticket ${entry.ticket_number}`
    })

  if (!queues || queues.total === 0) {
    return (
      <PanelShell title="Queues" error={listError}>
        <p className="muted">No active queues yet. Create one to start taking tickets.</p>
        <QueueForm newType={newType} setNewType={setNewType} onSubmit={createQueue} />
      </PanelShell>
    )
  }

  return (
    <PanelShell
      title="Queues"
      error={listError ?? boardError ?? error}
      addForm={<QueueForm newType={newType} setNewType={setNewType} onSubmit={createQueue} />}
    >
      <div className="stack">
        <label>
          Queue
          <select value={selectedId || queues.queues[0]?.id || ''} onChange={(e) => setSelectedId(e.target.value)}>
            {queues.queues.map((q: Queue) => (
              <option key={q.id} value={q.id}>{q.name ?? q.queue_type}</option>
            ))}
          </select>
        </label>

        {board && (
          <>
            <div className="grid">
              <div className="card">
                <h4>Now serving</h4>
                <p className="mono">{board.now_serving?.ticket_number ?? '—'}</p>
                {board.now_serving && (
                  <>
                    <button onClick={() => void run(async () => { await queuesApi.start(board.now_serving!.id) })}>Start</button>{' '}
                    <button onClick={() => void run(async () => { await queuesApi.complete(board.now_serving!.id) })}>Complete</button>{' '}
                    <button onClick={() => void run(async () => { await queuesApi.cancel(board.now_serving!.id) })}>Cancel</button>
                  </>
                )}
              </div>
              <div className="card">
                <h4>Waiting</h4>
                <p className="mono">{board.waiting.length}</p>
              </div>
              <div className="card">
                <h4>Completed</h4>
                <p className="mono">{board.counts['COMPLETED'] ?? 0}</p>
              </div>
            </div>

            <button onClick={() => void run(async () => { await queuesApi.advance(selectedId); return 'Called next ticket' })}>
              Call next
            </button>

            <div className="grid">
              <label>
                Priority for this patient (0–9)
                <input type="number" min={0} max={9} value={priority} onChange={(e) => setPriority(e.target.value)} />
              </label>
              <label>&nbsp;
                <button type="button" onClick={joinCurrentPatient}>Join queue with this patient</button>
              </label>
            </div>
            {message && <p className="muted">{message}</p>}

            <table>
              <thead>
                <tr><th>Ticket</th><th>Status</th><th>Priority</th><th>Joined</th><th>Wait</th></tr>
              </thead>
              <tbody>
                {[...(board.now_serving ? [board.now_serving] : []), ...board.waiting].map((e: QueueEntry) => (
                  <tr key={e.id}>
                    <td className="mono">{e.ticket_number}</td>
                    <td>{e.status}</td>
                    <td>{e.priority}</td>
                    <td>{fmt(e.joined_at)}</td>
                    <td>{e.wait_time_min != null ? `${e.wait_time_min} min` : '—'}</td>
                  </tr>
                ))}
                {board.waiting.length === 0 && !board.now_serving && (
                  <tr><td colSpan={5} className="muted">Queue is empty.</td></tr>
                )}
              </tbody>
            </table>
          </>
        )}
      </div>
    </PanelShell>
  )
}

function QueueForm({ newType, setNewType, onSubmit }: {
  newType: string
  setNewType: (v: string) => void
  onSubmit: (e: FormEvent) => void
}) {
  return (
    <form onSubmit={onSubmit} className="stack">
      <div className="grid">
        <select value={newType} onChange={(e) => setNewType(e.target.value)}>
          {QUEUE_TYPES.map((t) => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>
        <button type="submit">Create queue</button>
      </div>
    </form>
  )
}
