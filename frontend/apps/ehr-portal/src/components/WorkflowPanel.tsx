// Workflow panel: workflow definitions, instances for a patient, fired transitions.

import { FormEvent, useState } from 'react'
import { workflowApi } from '../lib/client'
import type { WorkflowDefinition, WorkflowInstance, WorkflowEventFire } from '../lib/types'
import { PanelShell, fmt, useLoad } from './Panels'

export function WorkflowPanel({ patientId, authorId }: { patientId: string; authorId: string }) {
  const { data: definitions, reload: reloadDefs } = useLoad(() => workflowApi.listDefinitions())
  const { data: instances, reload: reloadInstances } = useLoad(() => workflowApi.listInstances(patientId))

  // Create definition form
  const [defKey, setDefKey] = useState('')
  const [defName, setDefName] = useState('')
  const [defState, setDefState] = useState('CREATED')
  const [defBusy, setDefBusy] = useState(false)
  const [defError, setDefError] = useState<string | null>(null)
  const [defSuccess, setDefSuccess] = useState<string | null>(null)

  // Create instance form
  const [instDefId, setInstDefId] = useState('')
  const [instType, setInstType] = useState('PATIENT')
  const [instBusy, setInstBusy] = useState(false)
  const [instError, setInstError] = useState<string | null>(null)
  const [instSuccess, setInstSuccess] = useState<string | null>(null)

  // Fire event form
  const [fireInstanceId, setFireInstanceId] = useState('')
  const [fireEvent, setFireEvent] = useState('')
  const [fireComment, setFireComment] = useState('')
  const [fireBusy, setFireBusy] = useState(false)
  const [fireError, setFireError] = useState<string | null>(null)
  const [fireSuccess, setFireSuccess] = useState<string | null>(null)

  const { data: transitions, reload: reloadTransitions } = useLoad(() =>
    fireInstanceId ? workflowApi.transitions(fireInstanceId) : Promise.resolve([]),
  )

  const handleCreateDef = async (e: FormEvent) => {
    e.preventDefault()
    if (!defKey.trim() || !defName.trim()) return
    setDefBusy(true)
    setDefError(null)
    setDefSuccess(null)
    try {
      await workflowApi.createDefinition({ key: defKey.trim(), name: defName.trim(), initial_state: defState })
      setDefSuccess('Definition created')
      setDefKey('')
      setDefName('')
      await reloadDefs()
    } catch (err) {
      setDefError(err instanceof Error ? err.message : 'Failed to create definition')
    } finally {
      setDefBusy(false)
    }
  }

  const handleCreateInstance = async (e: FormEvent) => {
    e.preventDefault()
    if (!instDefId || !instType.trim()) return
    setInstBusy(true)
    setInstError(null)
    setInstSuccess(null)
    try {
      await workflowApi.createInstance({
        definition_id: instDefId,
        entity_type: instType,
        entity_id: patientId,
        patient_id: patientId,
      })
      setInstSuccess('Workflow instance started')
      await reloadInstances()
    } catch (err) {
      setInstError(err instanceof Error ? err.message : 'Failed to start instance')
    } finally {
      setInstBusy(false)
    }
  }

  const handleFire = async (e: FormEvent) => {
    e.preventDefault()
    if (!fireInstanceId || !fireEvent.trim()) return
    setFireBusy(true)
    setFireError(null)
    setFireSuccess(null)
    try {
      const payload: WorkflowEventFire = { event: fireEvent.trim(), actor_id: authorId, comment: fireComment.trim() || undefined }
      await workflowApi.fireEvent(fireInstanceId, payload)
      setFireSuccess(`Event "${fireEvent}" fired`)
      setFireEvent('')
      setFireComment('')
      await Promise.all([reloadInstances(), reloadTransitions()])
    } catch (err) {
      setFireError(err instanceof Error ? err.message : 'Failed to fire event')
    } finally {
      setFireBusy(false)
    }
  }

  const definitionName = (id: string) => definitions?.items?.find((d: WorkflowDefinition) => d.id === id)?.name ?? '?'

  const handleLifecycle = async (instanceId: string, action: 'pause' | 'resume' | 'cancel') => {
    try {
      if (action === 'pause') await workflowApi.pauseInstance(instanceId)
      else if (action === 'resume') await workflowApi.resumeInstance(instanceId)
      else await workflowApi.cancelInstance(instanceId)
      await reloadInstances()
    } catch (err) {
      setFireError(err instanceof Error ? err.message : `Failed to ${action} instance`)
    }
  }

  return (
    <PanelShell
      title="Workflows"
      addForm={
        <form onSubmit={handleCreateDef} className="grid">
          <input placeholder="Key (e.g. IMAGING_ORDERS)" value={defKey} onChange={(e) => setDefKey(e.target.value)} />
          <input placeholder="Name" value={defName} onChange={(e) => setDefName(e.target.value)} />
          <input placeholder="Initial state" value={defState} onChange={(e) => setDefState(e.target.value)} />
          <button type="submit" disabled={defBusy}>{defBusy ? 'Creating…' : 'Create Definition'}</button>
          {defError && <p className="alert-error">{defError}</p>}
          {defSuccess && <p className="muted">{defSuccess}</p>}
        </form>
      }
    >
      {/* Definitions */}
      <h3>Definitions</h3>
      <table>
        <thead>
          <tr><th>Key</th><th>Name</th><th>Initial state</th><th>Active</th><th>Created</th></tr>
        </thead>
        <tbody>
          {(definitions?.items ?? []).map((d: WorkflowDefinition) => (
            <tr key={d.id}>
              <td className="mono">{d.key}</td>
              <td>{d.name}</td>
              <td>{d.initial_state}</td>
              <td>{d.is_active ? '✓' : '✗'}</td>
              <td>{fmt(d.created_at)}</td>
            </tr>
          ))}
          {(definitions?.items?.length ?? 0) === 0 && <tr><td colSpan={5} className="muted">No definitions yet.</td></tr>}
        </tbody>
      </table>

      {/* Instances for this patient */}
      <h3>Instances — this patient</h3>
      <form onSubmit={handleCreateInstance} className="card">
        <h4>Start workflow</h4>
        <div className="grid">
          <select value={instDefId} onChange={(e) => setInstDefId(e.target.value)}>
            <option value="">— Select definition —</option>
            {(definitions?.items ?? []).filter((d: WorkflowDefinition) => d.is_active).map((d: WorkflowDefinition) => (
              <option key={d.id} value={d.id}>{d.key} — {d.name}</option>
            ))}
          </select>
          <input placeholder="Entity type (e.g. PATIENT)" value={instType} onChange={(e) => setInstType(e.target.value)} />
        </div>
        <button type="submit" disabled={instBusy}>{instBusy ? 'Starting…' : 'Start Instance'}</button>
        {instError && <p className="alert-error">{instError}</p>}
        {instSuccess && <p className="muted">{instSuccess}</p>}
      </form>

      <table>
        <thead>
          <tr><th>ID</th><th>Definition</th><th>State</th><th>Status</th><th>Started</th><th>Actions</th></tr>
        </thead>
        <tbody>
          {(instances?.items ?? []).map((inst: WorkflowInstance) => (
            <tr key={inst.id}>
              <td className="mono">{inst.id.slice(0, 8)}…</td>
              <td>{definitionName(inst.definition_id)}</td>
              <td>{inst.current_state}</td>
              <td>{inst.status}</td>
              <td>{fmt(inst.started_at)}</td>
              <td>
                {inst.status === 'RUNNING' && (
                  <button onClick={() => handleLifecycle(inst.id, 'pause')}>Pause</button>
                )}
                {inst.status === 'PAUSED' && (
                  <button onClick={() => handleLifecycle(inst.id, 'resume')}>Resume</button>
                )}
                {inst.status !== 'COMPLETED' && inst.status !== 'CANCELLED' && (
                  <button onClick={() => handleLifecycle(inst.id, 'cancel')}>Cancel</button>
                )}
              </td>
            </tr>
          ))}
          {(instances?.items?.length ?? 0) === 0 && <tr><td colSpan={6} className="muted">No workflows for this patient.</td></tr>}
        </tbody>
      </table>

      {/* Fire event */}
      <h3>Transitions</h3>
      <form onSubmit={handleFire} className="card">
        <h4>Fire event</h4>
        <div className="grid">
          <select value={fireInstanceId} onChange={(e) => setFireInstanceId(e.target.value)}>
            <option value="">— Select instance —</option>
            {(instances?.items ?? []).filter((inst: WorkflowInstance) => inst.status === 'RUNNING').map((inst: WorkflowInstance) => (
              <option key={inst.id} value={inst.id}>{inst.id.slice(0, 8)}… ({definitionName(inst.definition_id)} — {inst.current_state})</option>
            ))}
          </select>
          <input placeholder="Event (e.g. START)" value={fireEvent} onChange={(e) => setFireEvent(e.target.value)} />
          <input placeholder="Comment" value={fireComment} onChange={(e) => setFireComment(e.target.value)} />
        </div>
        <button type="submit" disabled={fireBusy}>{fireBusy ? 'Firing…' : 'Fire Event'}</button>
        {fireError && <p className="alert-error">{fireError}</p>}
        {fireSuccess && <p className="muted">{fireSuccess}</p>}
      </form>

      <table>
        <thead>
          <tr><th>Instance</th><th>Event</th><th>From</th><th>To</th><th>Actor</th><th>Performed</th></tr>
        </thead>
        <tbody>
          {(transitions ?? []).map((t) => (
            <tr key={t.id}>
              <td className="mono">{t.instance_id.slice(0, 8)}…</td>
              <td>{t.event}</td>
              <td>{t.from_state}</td>
              <td>{t.to_state}</td>
              <td className="mono">{t.actor_id.slice(0, 8)}…</td>
              <td>{fmt(t.performed_at)}</td>
            </tr>
          ))}
          {(transitions?.length ?? 0) === 0 && <tr><td colSpan={6} className="muted">Select an instance to view transitions.</td></tr>}
        </tbody>
      </table>
    </PanelShell>
  )
}