import { useState } from 'react'
import { patientApi } from './lib/client'
import type { PatientDetail, PatientSummary } from './lib/types'
import { MergePanel } from './components/MergePanel'
import { PatientDetailView } from './components/PatientDetail'
import { PatientSearch } from './components/PatientSearch'
import { RegistrationForm } from './components/RegistrationForm'

export default function App() {
  const [activeTab, setActiveTab] = useState<'register' | 'search' | 'merge'>('register')
  const [openId, setOpenId] = useState<string | null>(null)
  const [detail, setDetail] = useState<PatientDetail | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [searchPatients, setSearchPatients] = useState<PatientSummary[]>([])
  const [detailError, setDetailError] = useState<string | null>(null)

  const noted = (text: string) => {
    setMessage(text)
    window.setTimeout(() => setMessage(null), 5000)
  }

  const openDetail = async (id: string) => {
    setOpenId(id)
    setDetailError(null)
    try {
      setDetail(await patientApi.get(id))
    } catch (err) {
      setDetailError(err instanceof Error ? err.message : 'Failed to load patient')
      setDetail(null)
    }
  }

  return (
    <main className="container">
      <header>
        <h1>EHOS · Patient Registration</h1>
        <nav className="tabs">
          <button className={activeTab === 'register' ? 'active' : ''} onClick={() => setActiveTab('register')}>
            Register
          </button>
          <button className={activeTab === 'search' ? 'active' : ''} onClick={() => setActiveTab('search')}>
            Search
          </button>
          <button className={activeTab === 'merge' ? 'active' : ''} onClick={() => setActiveTab('merge')}>
            Merge
          </button>
        </nav>
      </header>

      {message && (
        <p className="alert-ok" role="status">
          {message}
        </p>
      )}
      {detailError && <p className="alert-error">{detailError}</p>}

      {activeTab === 'register' && (
        <RegistrationForm onRegistered={(id) => noted(`Patient registered: ${id}`)} />
      )}

      {activeTab === 'search' && (
        <PatientSearch
          onOpen={openDetail}
          onLoaded={(patients) => setSearchPatients(patients)}
        />
      )}

      {activeTab === 'merge' && <MergePanel patients={searchPatients} onMerged={noted} />}

      {openId && detail && (
        <PatientDetailView
          patient={detail}
          onClose={() => setOpenId(null)}
          onChanged={() => void openDetail(openId)}
        />
      )}
    </main>
  )
}