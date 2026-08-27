// Reporting panel: report definitions, report instances, scheduled reports.

import { FormEvent, useState } from 'react'
import { reportingApi } from '../lib/client'
import type { ReportDefinition, ReportInstance, ReportDefinitionCreate, ScheduledReport } from '../lib/types'
import { PanelShell, fmt, useLoad } from './Panels'

const REPORT_TYPES = ['PATIENT_SUMMARY', 'FINANCIAL', 'CLINICAL', 'OPERATIONAL', 'REGULATORY']

export function ReportingPanel({ patientId, authorId }: { patientId: string; authorId: string }) {
  const { data: definitions, reload: reloadDefs } = useLoad(() => reportingApi.listDefinitions())
  const { data: instances, reload: reloadInstances } = useLoad(() => reportingApi.listInstances(undefined, undefined))
  const { data: scheduled, reload: reloadScheduled } = useLoad(() => reportingApi.listScheduled())

  // Create definition form
  const [defName, setDefName] = useState('')
  const [defType, setDefType] = useState('OPERATIONAL')
  const [defDesc, setDefDesc] = useState('')
  const [defBusy, setDefBusy] = useState(false)
  const [defError, setDefError] = useState<string | null>(null)
  const [defSuccess, setDefSuccess] = useState<string | null>(null)

  // Create instance form
  const [instDefId, setInstDefId] = useState('')
  const [instBusy, setInstBusy] = useState(false)
  const [instError, setInstError] = useState<string | null>(null)
  const [instSuccess, setInstSuccess] = useState<string | null>(null)

  // Create scheduled report form
  const [schedDefId, setSchedDefId] = useState('')
  const [schedCron, setSchedCron] = useState('0 0 * * *')
  const [schedEmail, setSchedEmail] = useState('')
  const [schedBusy, setSchedBusy] = useState(false)
  const [schedError, setSchedError] = useState<string | null>(null)
  const [schedSuccess, setSchedSuccess] = useState<string | null>(null)

  const handleCreateDef = async (e: FormEvent) => {
    e.preventDefault()
    if (!defName.trim()) return
    setDefBusy(true)
    setDefError(null)
    setDefSuccess(null)
    try {
      const payload: ReportDefinitionCreate = {
        name: defName.trim(),
        report_type: defType,
        description: defDesc.trim() || undefined,
        is_active: true,
      }
      await reportingApi.createDefinition(payload)
      setDefSuccess('Definition created')
      setDefName('')
      setDefDesc('')
      await reloadDefs()
    } catch (err) {
      setDefError(err instanceof Error ? err.message : 'Failed to create definition')
    } finally {
      setDefBusy(false)
    }
  }

  const handleCreateInstance = async (e: FormEvent) => {
    e.preventDefault()
    if (!instDefId) return
    setInstBusy(true)
    setInstError(null)
    setInstSuccess(null)
    try {
      await reportingApi.createInstance({
        report_definition_id: instDefId,
        parameters: patientId ? { patient_id: patientId } : undefined,
        requested_by: authorId,
      })
      setInstSuccess('Report instance queued')
      await reloadInstances()
    } catch (err) {
      setInstError(err instanceof Error ? err.message : 'Failed to create report instance')
    } finally {
      setInstBusy(false)
    }
  }

  const handleCreateScheduled = async (e: FormEvent) => {
    e.preventDefault()
    if (!schedDefId || !schedCron.trim()) return
    setSchedBusy(true)
    setSchedError(null)
    setSchedSuccess(null)
    try {
      await reportingApi.createScheduled({
        report_definition_id: schedDefId,
        schedule_cron: schedCron.trim(),
        delivery_email: schedEmail.trim() || undefined,
        is_active: true,
      })
      setSchedSuccess('Scheduled report created')
      setSchedEmail('')
      await reloadScheduled()
    } catch (err) {
      setSchedError(err instanceof Error ? err.message : 'Failed to create scheduled report')
    } finally {
      setSchedBusy(false)
    }
  }

  const definitionName = (id: string) => definitions?.items?.find((d: ReportDefinition) => d.id === id)?.name ?? '?'

  const handleStart = async (instanceId: string) => {
    try {
      await reportingApi.startInstance(instanceId)
      await reloadInstances()
    } catch (err) {
      setInstError(err instanceof Error ? err.message : 'Failed to start instance')
    }
  }

  const handleComplete = async (instanceId: string) => {
    try {
      await reportingApi.completeInstance(instanceId)
      await reloadInstances()
    } catch (err) {
      setInstError(err instanceof Error ? err.message : 'Failed to complete instance')
    }
  }

  const handleDeactivate = async (scheduledId: string) => {
    try {
      await reportingApi.deactivateScheduled(scheduledId)
      await reloadScheduled()
    } catch (err) {
      setSchedError(err instanceof Error ? err.message : 'Failed to deactivate schedule')
    }
  }

  return (
    <PanelShell
      title="Reporting"
      addForm={
        <form onSubmit={handleCreateDef} className="grid">
          <input placeholder="Report name" value={defName} onChange={(e) => setDefName(e.target.value)} />
          <select value={defType} onChange={(e) => setDefType(e.target.value)}>
            {REPORT_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
          <input placeholder="Description" value={defDesc} onChange={(e) => setDefDesc(e.target.value)} />
          <button type="submit" disabled={defBusy}>{defBusy ? 'Creating…' : 'Create Definition'}</button>
          {defError && <p className="alert-error">{defError}</p>}
          {defSuccess && <p className="muted">{defSuccess}</p>}
        </form>
      }
    >
      {/* Definitions */}
      <h3>Report Definitions</h3>
      <table>
        <thead>
          <tr><th>Name</th><th>Type</th><th>Description</th><th>Active</th><th>Created</th></tr>
        </thead>
        <tbody>
          {(definitions?.items ?? []).map((d: ReportDefinition) => (
            <tr key={d.id}>
              <td>{d.name}</td>
              <td>{d.report_type}</td>
              <td>{d.description ?? '—'}</td>
              <td>{d.is_active ? '✓' : '✗'}</td>
              <td>{fmt(d.created_at)}</td>
            </tr>
          ))}
          {(definitions?.items?.length ?? 0) === 0 && <tr><td colSpan={5} className="muted">No definitions yet.</td></tr>}
        </tbody>
      </table>

      {/* Instances */}
      <h3>Report Instances</h3>
      <form onSubmit={handleCreateInstance} className="card">
        <h4>Generate report</h4>
        <div className="grid">
          <select value={instDefId} onChange={(e) => setInstDefId(e.target.value)}>
            <option value="">— Select definition —</option>
            {(definitions?.items ?? []).filter((d: ReportDefinition) => d.is_active).map((d: ReportDefinition) => (
              <option key={d.id} value={d.id}>{d.name} ({d.report_type})</option>
            ))}
          </select>
        </div>
        <button type="submit" disabled={instBusy}>{instBusy ? 'Queuing…' : 'Generate Report'}</button>
        {instError && <p className="alert-error">{instError}</p>}
        {instSuccess && <p className="muted">{instSuccess}</p>}
      </form>

      <table>
        <thead>
          <tr><th>ID</th><th>Definition</th><th>Status</th><th>Started</th><th>Completed</th><th>Actions</th></tr>
        </thead>
        <tbody>
          {(instances?.items ?? []).map((inst: ReportInstance) => (
            <tr key={inst.id}>
              <td className="mono">{inst.id.slice(0, 8)}…</td>
              <td>{definitionName(inst.report_definition_id)}</td>
              <td>{inst.status}</td>
              <td>{fmt(inst.started_at ?? undefined)}</td>
              <td>{fmt(inst.completed_at ?? undefined)}</td>
              <td>
                {inst.status === 'PENDING' && <button onClick={() => handleStart(inst.id)}>Start</button>}
                {inst.status === 'RUNNING' && <button onClick={() => handleComplete(inst.id)}>Complete</button>}
              </td>
            </tr>
          ))}
          {(instances?.items?.length ?? 0) === 0 && <tr><td colSpan={6} className="muted">No report instances.</td></tr>}
        </tbody>
      </table>

      {/* Scheduled reports */}
      <h3>Scheduled Reports</h3>
      <form onSubmit={handleCreateScheduled} className="card">
        <h4>Schedule report</h4>
        <div className="grid">
          <select value={schedDefId} onChange={(e) => setSchedDefId(e.target.value)}>
            <option value="">— Select definition —</option>
            {(definitions?.items ?? []).filter((d: ReportDefinition) => d.is_active).map((d: ReportDefinition) => (
              <option key={d.id} value={d.id}>{d.name}</option>
            ))}
          </select>
          <input placeholder="Cron (e.g. 0 0 * * *)" value={schedCron} onChange={(e) => setSchedCron(e.target.value)} />
          <input placeholder="Delivery email" value={schedEmail} onChange={(e) => setSchedEmail(e.target.value)} />
        </div>
        <button type="submit" disabled={schedBusy}>{schedBusy ? 'Scheduling…' : 'Schedule Report'}</button>
        {schedError && <p className="alert-error">{schedError}</p>}
        {schedSuccess && <p className="muted">{schedSuccess}</p>}
      </form>

      <table>
        <thead>
          <tr><th>Definition</th><th>Cron</th><th>Email</th><th>Last run</th><th>Next run</th><th>Active</th><th></th></tr>
        </thead>
        <tbody>
          {(scheduled?.items ?? []).map((s: ScheduledReport) => (
            <tr key={s.id}>
              <td>{definitionName(s.report_definition_id)}</td>
              <td className="mono">{s.schedule_cron}</td>
              <td>{s.delivery_email ?? '—'}</td>
              <td>{fmt(s.last_run_at ?? undefined)}</td>
              <td>{fmt(s.next_run_at ?? undefined)}</td>
              <td>{s.is_active ? '✓' : '✗'}</td>
              <td>
                {s.is_active && <button onClick={() => handleDeactivate(s.id)}>Deactivate</button>}
              </td>
            </tr>
          ))}
          {(scheduled?.items?.length ?? 0) === 0 && <tr><td colSpan={7} className="muted">No scheduled reports.</td></tr>}
        </tbody>
      </table>
    </PanelShell>
  )
}