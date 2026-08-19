// Single KPI card: value, period-over-period delta, status dot and sparkline.

import { fmtNumber } from '../lib/exporters'
import type { KpiValue } from '../lib/types'
import { Sparkline } from './Charts'

const STATUS_COLOR: Record<string, string> = { ok: 'var(--accent-2)', warn: 'var(--amber)', alert: 'var(--danger)' }

export function KpiCard({ kpi }: { kpi: KpiValue }) {
  const good = (kpi.goodWhen === 'up' && kpi.deltaPct >= 0) || (kpi.goodWhen === 'down' && kpi.deltaPct <= 0)
  const delta = Math.abs(kpi.deltaPct).toFixed(1)

  return (
    <div className={`kpi-card status-${kpi.status}`}>
      <div className="kpi-top">
        <span className="kpi-label">{kpi.label}</span>
        <span className="kpi-dot" style={{ background: STATUS_COLOR[kpi.status] }} title={`status: ${kpi.status}`} />
      </div>
      <div className="kpi-value">{fmtNumber(kpi.value, kpi.format)}</div>
      <div className="kpi-delta-row">
        <span className={`kpi-delta ${good ? 'up' : 'down'}`} title={fmtNumber(kpi.value, kpi.format)}>
          {good ? '▲' : '▼'} {delta}%
        </span>
        <span className="kpi-ago">vs prior period</span>
      </div>
      <div className="kpi-spark">
        <Sparkline values={kpi.spark} color={good ? 'var(--accent-2)' : 'var(--danger)'} width={120} height={34} />
      </div>
      <p className="kpi-hint">{kpi.hint}</p>
    </div>
  )
}