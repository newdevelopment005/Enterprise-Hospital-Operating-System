// EHOS Executive Command Center.
//
// Real-time KPI cards, interactive charts, advisory forecasts from the
// prediction-service and executive briefings from the ai-service. The dashboard
// degrades gracefully to deterministic demo data when a backend is not running,
// so it always renders.

import { useCallback, useEffect, useMemo, useState } from 'react'

import { ForecastPanel } from './components/ForecastPanel'
import { InsightsPanel } from './components/InsightsPanel'
import { KpiCard } from './components/KpiCard'
import { GroupedBarChart, LineChart } from './components/Charts'
import { aiApi, fetchForecast, fetchPredictionTargets } from './lib/client'
import { buildDatasets, demoForecasts, ruleInsights } from './lib/demo'
import { exportExcel, exportPdf, fmtNumber } from './lib/exporters'
import type { Datasets, Forecast, Insight } from './lib/types'

const FORECAST_KEYS = [
  'patient-inflow.department.7d',
  'bed-occupancy.ward.7d',
  'icu-load.icu-unit.7d',
  'revenue.biller.monthly',
  'medicine-usage.medication.30d',
]

const MONEY = (v: number, unit: string) => {
  if (unit === '$') return fmtNumber(v, 'currency')
  if (v >= 1000) return `$${(v / 1000).toFixed(1)}k`
  return String(Math.round(v))
}
const NUM = (v: number) => String(Math.round(v))
const PCT = (v: number) => `${v.toFixed(1)}%`

function briefingPrompt(datasets: Datasets): string {
  const k = (key: string) => datasets.kpis.find((x) => x.key === key)!
  const line = (label: string, kpi: ReturnType<typeof k>) =>
    `${label}: ${fmtNumber(kpi.value, kpi.format)} (${kpi.deltaPct >= 0 ? '+' : ''}${kpi.deltaPct.toFixed(1)}% vs prior)`
  return [
    'Act as the EHOS executive command advisor. Review the hospital operating snapshot and',
    'produce a concise executive briefing in 5 clear bullets: biggest risk, best performing area,',
    'one capacity or financial watch point, one recommended next step, and one metric to watch today.',
    'Be concrete, data-driven and advisory (no automatic actions).',
    'Snapshot:',
    line('Admissions', k('admissions')),
    line('Discharges', k('discharges')),
    line('Revenue', k('revenue')),
    line('Expenses', k('expenses')),
    line('Bed occupancy', k('occupancy')),
    line('Waiting time', k('waiting')),
    line('Staff utilization', k('utilization')),
    line('Inventory readiness', k('inventory')),
    line('Mortality', k('mortality')),
    line('30-day readmission', k('readmission')),
  ].join('\n')
}

const REFRESH_OPTIONS = [
  { label: '5s', ms: 5000 },
  { label: '15s', ms: 15000 },
  { label: '60s', ms: 60000 },
  { label: 'paused', ms: 0 },
]

export default function App() {
  const [datasets, setDatasets] = useState<Datasets>(() => buildDatasets())
  const [forecasts, setForecasts] = useState<Forecast[]>([])
  const [targetsNote, setTargetsNote] = useState<string | null>(null)
  const [insights, setInsights] = useState<Insight[]>([])
  const [insightLoading, setInsightLoading] = useState(true)
  const [refreshMs, setRefreshMs] = useState(5000)
  const [lastUpdated, setLastUpdated] = useState(() => new Date())
  const [banner, setBanner] = useState<string | null>(null)

  // Real-time KPI refresh loop.
  useEffect(() => {
    const timer = setInterval(() => {
      setDatasets(() => buildDatasets())
      setLastUpdated(new Date())
    }, refreshMs || 100000)
    return () => clearInterval(timer)
  }, [refreshMs])

  // One-time loads: forecasts from prediction-service (+ demo fallback), targets.
  useEffect(() => {
    let cancelled = false
    ;(async () => {
      const targets = await fetchPredictionTargets()
      if (!cancelled) {
        if (targets.length > 0) setTargetsNote(`${targets.length} forecast targets served by prediction-service`)
        else setTargetsNote('prediction-service offline — sample forecasts (advisory)')
      }
      const hits: Forecast[] = []
      for (const key of FORECAST_KEYS) {
        const serving = await fetchForecast(key)
        if (!serving) continue
        hits.push({
          predictionKey: serving.prediction_key,
          entityType: serving.entity_type ?? key.split('.')[0],
          label: key.includes('patient') ? 'Patient inflow' : key.includes('occupancy') ? 'Bed occupancy' : key.includes('icu') ? 'ICU load' : key.includes('revenue') ? 'Daily revenue' : 'Medicine usage',
          horizon: serving.horizon ?? key.split('.')[2],
          windowFrom: serving.window_from ?? '',
          windowTo: serving.window_to ?? '',
          value: serving.forecast.value,
          q10: serving.forecast.q10,
          q90: serving.forecast.q90,
          confidence: serving.confidence ?? 0.9,
          modelVersion: serving.model_version,
          generatedAt: serving.generated_at,
          source: 'prediction-service',
          unit: key.includes('revenue') ? '$' : key.includes('occupancy') ? '%' : 'patients',
        })
      }
      if (!cancelled) setForecasts(hits.length > 0 ? hits : demoForecasts())
    })()
    return () => {
      cancelled = true
    }
  }, [])

  const runBriefing = useCallback(async (fresh: Datasets) => {
    setInsightLoading(true)
    const rule = ruleInsights(fresh).map((text) => ({ text, category: 'rule' as const }))
    try {
      const response = await aiApi.chat({
        message: briefingPrompt(fresh),
        user_id: '00000000-0000-0000-0000-000000000000',
        request_type: 'CHAT',
        use_rag: false,
      })
      const aiText = response.answer.split('\n').map((s) => s.trim()).filter((s) => s.length > 0)
      setInsights([...rule, ...aiText.map((text) => ({ text, category: 'ai' as const }))])
    } catch {
      setInsights(rule)
      setBanner('ai-service unavailable — showing rule-based insights.')
    } finally {
      setInsightLoading(false)
    }
  }, [])

  // Initial executive briefing.
  useEffect(() => {
    void runBriefing(buildDatasets())
  }, [runBriefing])

  const refreshNow = () => {
    const fresh = buildDatasets()
    setDatasets(fresh)
    setLastUpdated(new Date())
    void runBriefing(fresh)
  }

  const handleExportExcel = () => {
    exportExcel(datasets, forecasts, [...insights.map((i) => i.text)])
  }

  const { revenue, expenses, admissions, discharges, occupancy, utilization, waiting } = datasets

  const currencyFmt = useMemo(() => MONEY, [])

  return (
    <div className="shell">
      <header className="app-header">
        <div className="title-block">
          <h1>EHOS Executive Command Center</h1>
          <p>Real-time hospital KPIs · advisory forecasts · AI insights · no cloud</p>
        </div>
        <div className="header-actions">
          <span className="live-pill">
            <span className="live-dot" />
            LIVE · {lastUpdated.toLocaleTimeString()}
          </span>
          <select
            className="refresh-select"
            value={refreshMs}
            onChange={(e) => setRefreshMs(Number(e.target.value))}
            title="Refresh interval"
            aria-label="Refresh interval">
            {REFRESH_OPTIONS.map((o) => (
              <option key={o.ms} value={o.ms}>{o.label === 'paused' ? '⏸ paused' : `refresh ${o.label}`}</option>
            ))}
          </select>
          <button className="ghost" onClick={exportPdf}>Export PDF</button>
          <button className="ghost" onClick={handleExportExcel}>Export Excel</button>
        </div>
      </header>

      {banner && <div className="banner">{banner}</div>}

      <section className="kpi-grid">
        {datasets.kpis.map((kpi) => (
          <KpiCard key={kpi.key} kpi={kpi} />
        ))}
      </section>

      <section className="charts">
        <div className="panel chart-col">
          <div className="panel-head">
            <h2>Admissions vs discharges</h2>
            <span className="badge">last 30 days</span>
          </div>
          <LineChart series={[admissions, discharges]} fmt={NUM} height={230} />
        </div>
        <div className="panel chart-col">
          <div className="panel-head">
            <h2>Revenue vs expenses</h2>
            <span className="badge">daily</span>
          </div>
          <GroupedBarChart series={[revenue, expenses]} fmt={currencyFmt} height={230} />
        </div>
        <div className="panel chart-col">
          <div className="panel-head">
            <h2>Occupancy &amp; staff utilisation</h2>
            <span className="badge">last 30 days</span>
          </div>
          <LineChart series={[occupancy, utilization]} fmt={PCT} height={230} />
        </div>
        <div className="panel chart-col">
          <div className="panel-head">
            <h2>Waiting time</h2>
            <span className="badge">last 72h</span>
          </div>
          <LineChart series={[waiting]} fmt={(v) => `${Math.round(v)} min`} height={230} />
        </div>
      </section>

      <ForecastPanel forecasts={forecasts} targetsNote={targetsNote} />

      <InsightsPanel insights={insights} loading={insightLoading} onRefresh={refreshNow} />

      <footer className="app-footer">
        <span>Forecasts are advisory only (PREDICTIVE_ANALYTICS_ARCHITECTURE §10) — no metric triggers automatic actions.</span>
      </footer>
    </div>
  )
}