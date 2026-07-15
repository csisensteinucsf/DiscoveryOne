import { Fragment, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

const lightBtn = { background:'#E5EEF3', color:'#00598C', border:'1px solid #C9D7E2' }

function Chip({ kind = 'default', children, title }) {
  const base = {
    display: 'inline-block',
    padding: '2px 8px',
    borderRadius: 999,
    fontSize: 11,
    lineHeight: '16px',
    border: '1px solid #e5e7eb',
    background: '#f8fafc',
    color: '#334155',
    whiteSpace: 'nowrap',
    marginRight: 6,
    marginBottom: 4,
  }
  const theme =
    kind === 'red'
      ? { borderColor: '#fecaca', background: '#fee2e2', color: '#991b1b' }
      : kind === 'green'
      ? { borderColor: '#bbf7d0', background: '#dcfce7', color: '#065f46' }
      : kind === 'blue'
      ? { borderColor: '#bfdbfe', background: '#dbeafe', color: '#1e3a8a' }
      : kind === 'yellow'
      ? { borderColor: '#fde68a', background: '#fef3c7', color: '#92400e' }
      : {}
  const compact =
    kind === 'blue-letter' || kind === 'yellow-letter'
      ? {
          minWidth: 18,
          height: 18,
          lineHeight: '16px',
          textAlign: 'center',
          padding: '0 5px',
          fontWeight: 700,
        }
      : {}
  const letterTheme =
    kind === 'blue-letter'
      ? { borderColor: '#bfdbfe', background: '#dbeafe', color: '#1e3a8a' }
      : kind === 'yellow-letter'
      ? { borderColor: '#fde68a', background: '#fef3c7', color: '#92400e' }
      : {}
  return <span title={title} style={{ ...base, ...theme, ...compact, ...letterTheme }}>{children}</span>
}

function CaseList({ items = [] }) {
  if (!items.length) return <span>-</span>
  return (
    <>
      {items.map((k, idx) => (
        <Fragment key={k.id}>
          <Link to={`/cases/${k.id}`} onClick={e => e.stopPropagation()} style={{ textDecoration: 'none', color: 'inherit' }}>
            {k.name}
          </Link>
          {k.is_claimant ? <Chip kind="blue-letter" title="Claimant in this case">C</Chip> : null}
          {idx < items.length - 1 ? ', ' : ''}
        </Fragment>
      ))}
    </>
  )
}

export default function Custodians({ apiBase = '/api' }) {
  const [q, setQ] = useState('')
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState(null)
  const nav = useNavigate()

  async function load() {
    setLoading(true)
    setErr(null)
    try {
      const url = q ? `${apiBase}/custodians?q=${encodeURIComponent(q)}` : `${apiBase}/custodians`
      const r = await fetch(url, { credentials:'include' })
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      const data = await r.json()
      setRows(Array.isArray(data) ? data : [])
    } catch(e) {
      setErr(String(e))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const onSearch = (e) => { e.preventDefault(); load() }

  return (
    <div className="wrap">
      <div className="page-header" style={{ marginBottom: '1rem' }}>
        <h2 style={{ margin: 0, color: 'var(--sidebar-fg)' }}>Custodians</h2>
        <form onSubmit={onSearch} className="row" style={{ gap: 8 }}>
          <input
            type="text" placeholder="Search name, email, case, department..."
            value={q} onChange={e => setQ(e.target.value)}
            style={{ minWidth: 320 }}
          />
          <button type="submit" className="btn" style={lightBtn}>Search</button>
        </form>
      </div>

      {err && <div className="alert error">Error: {err}</div>}
      <div className="card">
        <table className="table">
          <thead>
            <tr>
              <th style={{width:'16%'}}>Name</th>
              <th style={{width:'18%'}}>Email</th>
              <th>Open cases</th>
              <th>Closed cases</th>
              <th style={{width:130}}>Active holds</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={5}>Loading...</td></tr>
            ) : rows.length === 0 ? (
              <tr><td colSpan={5}>No custodians found.</td></tr>
            ) : rows.map((c,i) => (
              <tr
                key={i}
                onClick={() => {
                  const params = new URLSearchParams()
                  if (c.email) params.set('email', c.email)
                  else if (c.name) params.set('name', c.name)
                  if ([...params.keys()].length === 0) return
                  nav(`/custodians/detail?${params.toString()}`)
                }}
                style={{cursor:'pointer'}}
              >
                <td>
                  <div>{c.name || '-'}</div>
                  <div style={{ marginTop: 4 }}>
                    {c.is_separated ? <Chip kind="yellow-letter" title="Separated employee">S</Chip> : null}
                  </div>
                </td>
                <td>{c.email || '-'}</td>
                <td><CaseList items={c.open_cases || []} /></td>
                <td><CaseList items={c.closed_cases || []} /></td>
                <td>{c.active_holds ? <Chip kind="red">Yes</Chip> : <Chip>No</Chip>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

