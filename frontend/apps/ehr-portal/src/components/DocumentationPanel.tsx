// Clinical documentation panel: templates, clinical notes, note versions.

import { FormEvent, useState } from 'react'
import { documentationApi } from '../lib/client'
import type { ClinicalNoteDoc, ClinicalNoteDocCreate, DocTemplate } from '../lib/types'
import { PanelShell, fmt, useLoad } from './Panels'

const NOTE_TYPES = ['SOAP', 'PROGRESS', 'DISCHARGE', 'PROCEDURE', 'CONSULTATION', 'H&P', 'NURSING', 'CONSENT']

export function DocumentationPanel({ patientId, authorId }: { patientId: string; authorId: string }) {
  const { data: notes, reload: reloadNotes } = useLoad(() => documentationApi.listNotes(patientId))
  const { data: templates, reload: reloadTemplates } = useLoad(() => documentationApi.listTemplates())

  // Create template form
  const [tplName, setTplName] = useState('')
  const [tplType, setTplType] = useState('SOAP')
  const [tplContent, setTplContent] = useState('')
  const [tplBusy, setTplBusy] = useState(false)
  const [tplError, setTplError] = useState<string | null>(null)
  const [tplSuccess, setTplSuccess] = useState<string | null>(null)

  // Create note form
  const [noteType, setNoteType] = useState('SOAP')
  const [noteTitle, setNoteTitle] = useState('')
  const [noteContent, setNoteContent] = useState('')
  const [noteBusy, setNoteBusy] = useState(false)
  const [noteError, setNoteError] = useState<string | null>(null)
  const [noteSuccess, setNoteSuccess] = useState<string | null>(null)

  // Versions viewer
  const [versionsFor, setVersionsFor] = useState<string | null>(null)
  const { data: versions, reload: reloadVersions } = useLoad(() =>
    versionsFor ? documentationApi.noteVersions(versionsFor) : Promise.resolve([]),
  )

  const handleCreateTemplate = async (e: FormEvent) => {
    e.preventDefault()
    if (!tplName.trim()) return
    setTplBusy(true)
    setTplError(null)
    setTplSuccess(null)
    try {
      await documentationApi.createTemplate({
        name: tplName.trim(),
        note_type: tplType,
        content: tplContent.trim() || undefined,
        is_active: true,
      })
      setTplSuccess('Template created')
      setTplName('')
      setTplContent('')
      await reloadTemplates()
    } catch (err) {
      setTplError(err instanceof Error ? err.message : 'Failed to create template')
    } finally {
      setTplBusy(false)
    }
  }

  const handleCreateNote = async (e: FormEvent) => {
    e.preventDefault()
    if (!noteContent.trim()) return
    setNoteBusy(true)
    setNoteError(null)
    setNoteSuccess(null)
    try {
      const payload: ClinicalNoteDocCreate = {
        patient_id: patientId,
        author_id: authorId,
        note_type: noteType,
        title: noteTitle.trim() || undefined,
        content: noteContent.trim(),
      }
      await documentationApi.createNote(payload)
      setNoteSuccess('Note saved')
      setNoteTitle('')
      setNoteContent('')
      await reloadNotes()
    } catch (err) {
      setNoteError(err instanceof Error ? err.message : 'Failed to save note')
    } finally {
      setNoteBusy(false)
    }
  }

  const applyTemplate = (tpl: DocTemplate) => {
    setNoteTitle(tpl.name)
    setNoteContent(tpl.content ?? '')
    setNoteType(tpl.note_type)
  }

  const handleSign = async (noteId: string) => {
    try {
      await documentationApi.signNote(noteId, authorId)
      await reloadNotes()
    } catch (err) {
      setNoteError(err instanceof Error ? err.message : 'Failed to sign note')
    }
  }

  const handleCancel = async (noteId: string) => {
    try {
      await documentationApi.cancelNote(noteId)
      await reloadNotes()
    } catch (err) {
      setNoteError(err instanceof Error ? err.message : 'Failed to cancel note')
    }
  }

  const toggleVersions = async (noteId: string) => {
    if (versionsFor === noteId) {
      setVersionsFor(null)
    } else {
      setVersionsFor(noteId)
      await reloadVersions()
    }
  }

  return (
    <PanelShell
      title="Clinical Documentation"
      addForm={
        <form onSubmit={handleCreateTemplate} className="grid">
          <input placeholder="Template name" value={tplName} onChange={(e) => setTplName(e.target.value)} />
          <select value={tplType} onChange={(e) => setTplType(e.target.value)}>
            {NOTE_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
          <input placeholder="Template body" value={tplContent} onChange={(e) => setTplContent(e.target.value)} />
          <button type="submit" disabled={tplBusy}>{tplBusy ? 'Creating…' : 'Create Template'}</button>
          {tplError && <p className="alert-error">{tplError}</p>}
          {tplSuccess && <p className="muted">{tplSuccess}</p>}
        </form>
      }
    >
      {/* Templates */}
      <h3>Document Templates</h3>
      <table>
        <thead>
          <tr><th>Name</th><th>Type</th><th>Active</th><th></th></tr>
        </thead>
        <tbody>
          {(templates?.items ?? []).map((t: DocTemplate) => (
            <tr key={t.id}>
              <td>{t.name}</td>
              <td>{t.note_type}</td>
              <td>{t.is_active ? '✓' : '✗'}</td>
              <td><button onClick={() => applyTemplate(t)}>Use</button></td>
            </tr>
          ))}
          {(templates?.items?.length ?? 0) === 0 && <tr><td colSpan={4} className="muted">No templates yet.</td></tr>}
        </tbody>
      </table>

      {/* Notes */}
      <h3>Notes — this patient</h3>
      <form onSubmit={handleCreateNote} className="card">
        <h4>Create note</h4>
        <div className="grid">
          <select value={noteType} onChange={(e) => setNoteType(e.target.value)}>
            {NOTE_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
          <input placeholder="Title" value={noteTitle} onChange={(e) => setNoteTitle(e.target.value)} />
        </div>
        <textarea rows={4} placeholder="Note content" value={noteContent} onChange={(e) => setNoteContent(e.target.value)} />
        <button type="submit" disabled={noteBusy}>{noteBusy ? 'Saving…' : 'Save Note'}</button>
        {noteError && <p className="alert-error">{noteError}</p>}
        {noteSuccess && <p className="muted">{noteSuccess}</p>}
      </form>

      <table>
        <thead>
          <tr><th>Type</th><th>Title</th><th>Status</th><th>Author</th><th>Signed</th><th>Actions</th></tr>
        </thead>
        <tbody>
          {(notes?.items ?? []).map((n: ClinicalNoteDoc) => (
            <tr key={n.id}>
              <td>{n.note_type}</td>
              <td>{n.title ?? '—'}</td>
              <td>{n.status}</td>
              <td className="mono">{n.author_id.slice(0, 8)}…</td>
              <td>{fmt(n.signed_at ?? undefined)}</td>
              <td>
                {n.status === 'DRAFT' && <button onClick={() => handleSign(n.id)}>Sign</button>}
                {n.status !== 'CANCELLED' && <button onClick={() => handleCancel(n.id)}>Cancel</button>}
                <button onClick={() => toggleVersions(n.id)}>{versionsFor === n.id ? 'Hide versions' : 'Versions'}</button>
              </td>
            </tr>
          ))}
          {(notes?.items?.length ?? 0) === 0 && <tr><td colSpan={6} className="muted">No notes for this patient.</td></tr>}
        </tbody>
      </table>

      {versionsFor && (
        <>
          <h3>Versions — {versionsFor.slice(0, 8)}…</h3>
          <table>
            <thead>
              <tr><th>Version</th><th>Changed by</th><th>Summary</th><th>Created</th></tr>
            </thead>
            <tbody>
              {(versions ?? []).map((v) => (
                <tr key={v.id}>
                  <td className="mono">{v.version_number}</td>
                  <td className="mono">{v.changed_by.slice(0, 8)}…</td>
                  <td>{v.change_summary ?? '—'}</td>
                  <td>{fmt(v.created_at)}</td>
                </tr>
              ))}
              {(versions?.length ?? 0) === 0 && <tr><td colSpan={4} className="muted">No versions recorded.</td></tr>}
            </tbody>
          </table>
        </>
      )}
    </PanelShell>
  )
}