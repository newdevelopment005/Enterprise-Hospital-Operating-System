// Per-department KPI breakdown (Finance & Accounts, HR, Operations, ...).

import type { DepartmentKpis } from '../lib/types'

interface Props {
  departments: DepartmentKpis[]
  fmt: (v: number, format: string) => string
}

const STATUS_DOT: Record<string, string> = { ok: '#2e7d32', warn: '#f9a825', alert: '#c62828' }

export function DepartmentPanel({ departments, fmt }: Props) {
  if (departments.length === 0) return null
  return (
    <section className="departments">
      {departments.map((dept) => (
        <div className="panel dept-panel" key={dept.code}>
          <div className="panel-head">
            <h2>{dept.name}</h2>
            <span className="badge">{dept.kpis.length} metrics</span>
          </div>
          <table className="dept-table">
            <thead>
              <tr>
                <th>Metric</th>
                <th className="num">Value</th>
                <th className="num">Δ vs prior</th>
              </tr>
            </thead>
            <tbody>
              {dept.kpis.map((k) => (
                <tr key={k.key}>
                  <td>
                    <span className="status-dot" style={{ background: STATUS_DOT[k.status] ?? '#2e7d32' }} />
                    {k.label}
                  </td>
                  <td className="num">{fmt(k.value, k.format)}</td>
                  <td className={`num ${k.deltaPct >= 0 ? 'up' : 'down'}`}>
                    {k.deltaPct >= 0 ? '+' : ''}
                    {k.deltaPct.toFixed(1)}%
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </section>
  )
}
