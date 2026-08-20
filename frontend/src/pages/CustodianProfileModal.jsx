import { useEffect, useMemo, useState } from 'react'
import Modal from '../components/Modal.jsx'

function DetailRow({ label, value }) {
  return (
    <div className="custodian-profile-modal__row">
      <span>{label}</span>
      <strong>{value || '-'}</strong>
    </div>
  )
}

export default function CustodianProfileModal({ apiBase = '/api', custodian, onClose }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const key = useMemo(() => {
    const email = String(custodian?.email || '').trim()
    const name = String(custodian?.name || '').trim()
    if (email) return 'email=' + encodeURIComponent(email)
    if (name) return 'name=' + encodeURIComponent(name)
    return ''
  }, [custodian])

  useEffect(() => {
    if (!key) return
    let cancelled = false
    setLoading(true)
    setError('')
    fetch(apiBase + '/custodians/detail?' + key, { credentials: 'include' })
      .then(async response => {
        if (!response.ok) throw new Error('Unable to load custodian details.')
        return response.json()
      })
      .then(result => { if (!cancelled) setData(result) })
      .catch(loadError => { if (!cancelled) setError(loadError?.message || 'Unable to load custodian details.') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [apiBase, key])

  const matters = data?.cases || []
  const preservation = data?.holds || {}

  return (
    <Modal
      open={!!custodian}
      title={data?.name || custodian?.name || 'Custodian details'}
      onClose={onClose}
      width={760}
      footer={<button type="button" className="btn secondary" onClick={onClose}>Close</button>}
    >
      {loading && <p className="muted">Loading custodian details...</p>}
      {error && <div className="alert error">{error}</div>}
      {!loading && !error && data && (
        <div className="custodian-profile-modal">
          <section className="custodian-profile-modal__section">
            <h4>Details</h4>
            <div className="custodian-profile-modal__grid">
              <DetailRow label="First name" value={data.first_name} />
              <DetailRow label="Last name" value={data.last_name} />
              <DetailRow label="Email" value={data.email} />
              <DetailRow label="Campus" value={data.campus} />
              <DetailRow label="Department" value={data.department} />
              <DetailRow label="Employee ID" value={data.employee_id || data.external_id} />
              <DetailRow label="Job title" value={data.title} />
              <DetailRow label="Employment status" value={data.employment_status} />
            </div>
          </section>
          <section className="custodian-profile-modal__section">
            <h4>Matters</h4>
            {matters.length ? (
              <div className="custodian-profile-modal__matter-list">
                {matters.map(matter => (
                  <a key={matter.id} href={'/cases/' + matter.id} className="custodian-profile-modal__matter">
                    <span>{matter.name}</span>
                    <span className={'badge ' + (matter.closed ? '' : 'success')}>{matter.closed ? 'Inactive' : 'Active'}</span>
                  </a>
                ))}
              </div>
            ) : <p className="muted">This custodian is not assigned to a matter.</p>}
          </section>
          <section className="custodian-profile-modal__section">
            <h4>Preservation</h4>
            <div className="custodian-profile-modal__preservation">
              {[
                ['Email', preservation.email],
                ['OneDrive', preservation.onedrive],
                ['Box', preservation.box],
                ['Slack', preservation.slack],
                ['Rubrik restore', preservation.rubrik_restore],
              ].map(([label, active]) => (
                <span key={label} className={'badge ' + (active ? 'success' : '')}>{label}: {active ? 'Active' : 'Off'}</span>
              ))}
            </div>
          </section>
        </div>
      )}
    </Modal>
  )
}