// Deterministic demo hospital data engine.
//
// The Executive Command Center consumes live KPI aggregates once an analytics
// service exposes them (see PREDICTIVE_ANALYTICS_ARCHITECTURE.md). Until then
// this module produces a realistic, internally-consistent hospital time series
// (admissions -> census/occupancy -> discharges -> revenue/expenses ->
// workforce/inventory/outcomes) so the dashboard is fully usable offline.
//
// All values derive from one seeded PRNG: stable within a day, but a small live
// "tick" is added each poll so the dashboard visibly refreshes in real time.

import type { Datasets, Forecast, KpiStatus, KpiValue, Series, SeriesPoint } from './types'

// --- seeded PRNG (mulberry32) ------------------------------------------------

function mulberry32(seed: number): () => number {
  let a = seed >>> 0
  return () => {
    a = (a + 0x6d2b79f5) | 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

function seedFromNow(now = new Date()): number {
  const start = new Date(now.getFullYear(), 0, 0)
  const day = Math.floor((now.getTime() - start.getTime()) / 86400000)
  return now.getFullYear() * 1000 + day
}

function gaussianish(rng: () => number): number {
  return (rng() + rng() + rng() - 1.5) / 2
}

const DAILY_PROFILE = [0.55, 0.42, 0.4, 0.44, 0.5, 0.62, 0.8, 1.0, 1.1, 1.05, 1.0, 0.98, 0.95, 0.92, 0.9, 0.96, 1.18, 1.32, 1.24, 1.02, 0.88, 0.8, 0.72, 0.62]
const TAU_DAYS = 4.4 // mean length of stay drives census smoothing
const DAYS = 60
const HOURS = DAYS * 24
const LOS_HOURS = Math.round(TAU_DAYS * 24)
const DISPLAY_DAYS = 30
const BEDS = 420

// --- hospital model ----------------------------------------------------------

interface RawModel {
  admissionsHourly: number[]
  deathsByDay: number[]
  readmitsByDay: number[]
  byDay: number[][]
  byHour: number[][]
  current: Record<string, number>
  prior: Record<string, number>
  forecastValues: number[][]
  forecastQ10: number[][]
  forecastQ90: number[][]
}

function buildRaw(seed: number): RawModel {
  const rng = mulberry32(seed)
  const now = new Date()
  const startDow = now.getDay()

  const admissionsHourly: number[] = []
  const dischargeHourly: number[] = []
  const dailyAdm = new Array(DAYS).fill(0)
  const dailyDis = new Array(DAYS).fill(0)
  const dailyDeaths = new Array(DAYS).fill(0)
  const dailyReadmits = new Array(DAYS).fill(0)
  const dailyCensus = new Array(DAYS).fill(0)

  let census = 0.86 * BEDS
  let trend = 0
  const meanPerHour = (0.86 * BEDS) / (TAU_DAYS * 24)

  for (let h = 0; h < HOURS; h++) {
    const day = Math.floor(h / 24)
    const dow = (startDow + day) % 7
    const hour = h % 24
    const weekend = dow >= 5 ? 0.85 : 1
    const seasonal = 1 + 0.07 * Math.sin((h / (24 * 7)) * Math.PI * 2)
    trend = trend * 0.9995 + rng() * 0.045
    const wave = meanPerHour * DAILY_PROFILE[hour] * weekend * seasonal * (1 + trend) * (1 + 0.11 * gaussianish(rng))
    admissionsHourly.push(Math.max(0, wave))
    dailyAdm[day] += admissionsHourly[h]

    let discharged = 0
    if (h >= LOS_HOURS) {
      discharged = admissionsHourly[h - LOS_HOURS] * 0.84
    }
    dischargeHourly.push(Math.max(0, discharged))
    dailyDis[day] += dischargeHourly[h]

    census += admissionsHourly[h] - dischargeHourly[h]
    census = Math.max(0.6 * BEDS, Math.min(0.97 * BEDS, census))
    dailyCensus[day] = census

    if (h % 24 === 23) {
      dailyDeaths[day] = dailyAdm[day] * 0.014 * (0.8 + rng() * 0.4)
      dailyReadmits[day] = dailyDis[day] * 0.11 * (0.75 + rng() * 0.5)
    }
  }

  const last = DAYS - DISPLAY_DAYS
  const admD = dailyAdm.slice(last)
  const disD = dailyDis.slice(last)
  const censusD = dailyCensus.slice(last)
  const deathsD = dailyDeaths.slice(last)
  const readmitsD = dailyReadmits.slice(last)
  const occPctD = censusD.map((c) => (c / BEDS) * 100)
  const utilPctD = censusD.map((c) => utilFromOccupancy(c, 12))
  const readmitRateD = disD.map((d, i) => (readmitsD[i] / Math.max(1, d)) * 100)
  const revenueD = admD.map((a, i) => a * 2200 + a * 1.4 * 350 + censusD[i] * 190)
  const expenseD = censusD.map((c) => 150000 + c * 380)
  const inventoryD = inventoryDaily(seed)

  const adm72 = admissionsHourly.slice(-72)
  const dis72 = dischargeHourly.slice(-72)
  const occ72 = censusRun(admissionsHourly, dischargeHourly, BEDS).slice(-72)
  const utilHour = occ72.map((o, i) => utilFromOccupancy(o, hourOfDayFor(i)))
  const waitHour = waitingFromArrivals(adm72)

  const today = DISPLAY_DAYS - 1
  const yest = DISPLAY_DAYS - 2
  const disRate = (d: number): number => (readmitsD[d] / Math.max(1, disD[d])) * 100

  const current = {
    admissions: admD[today],
    discharges: disD[today],
    revenue: revenueD[today],
    expenses: expenseD[today],
    occupancy: occPctD[today],
    waiting: waitHour[waitHour.length - 1],
    utilization: utilPctD[today],
    inventory: inventoryD[today],
    mortality: deathsD[today],
    readmission: disRate(today),
  }
  const prior = {
    admissions: admD[yest],
    discharges: disD[yest],
    revenue: revenueD[yest],
    expenses: expenseD[yest],
    occupancy: occPctD[yest],
    waiting: waitHour[waitHour.length - 25],
    utilization: utilPctD[yest],
    inventory: inventoryD[yest],
    mortality: deathsD[yest],
    readmission: disRate(yest),
  }

  // Advisory daily forecasts (7 steps) — demo stand-in for prediction-service.
  const fDaily = (base: number[]): { v: number[]; lo: number[]; hi: number[] } => {
    const avg = base.reduce((a, b) => a + b, 0) / Math.max(1, base.length)
    const values: number[] = []
    const lo: number[] = []
    const hi: number[] = []
    for (let i = 0; i < 7; i++) {
      const v = Math.max(0, avg * (0.96 + 0.012 * i) * (1 + 0.05 * gaussianish(rng)))
      values.push(v)
      lo.push(v * 0.9)
      hi.push(v * 1.1)
    }
    return { v: values, lo, hi }
  }

  const inflow = fDaily(admD)
  const occF = fDaily(censusD.map((c) => (c / BEDS) * 100))
  const icuF = fDaily(censusD.map((c) => c * 0.08))
  const revF = fDaily(revenueD.map((x) => x / 1000))
  const usageF = fDaily(censusD.map((c) => c * 0.34))

  return {
    admissionsHourly,
    deathsByDay: deathsD,
    readmitsByDay: readmitsD,
    byDay: [admD, disD, censusD, occPctD, deathsD, readmitsD, revenueD, expenseD, inventoryD, readmitRateD, utilPctD],
    byHour: [adm72, dis72, occ72, utilHour, waitHour],
    current,
    prior,
    forecastValues: [inflow.v, occF.v, icuF.v, revF.v, usageF.v],
    forecastQ10: [inflow.lo, occF.lo, icuF.lo, revF.lo, usageF.lo],
    forecastQ90: [inflow.hi, occF.hi, icuF.hi, revF.hi, usageF.hi],
  }
}

function censusRun(admissions: number[], discharge: number[], beds: number): number[] {
  let census = 0.86 * beds
  const out: number[] = []
  for (let h = 0; h < admissions.length; h++) {
    census += admissions[h] - discharge[h]
    census = Math.max(0.6 * beds, Math.min(0.97 * beds, census))
    out.push(census)
  }
  return out
}

function hourOfDayFor(indexFromEnd: number): number {
  const now = new Date()
  const hoursBack = 71 - indexFromEnd
  const h = (now.getHours() - hoursBack) % 24
  return (h + 24) % 24
}

function utilFromOccupancy(census: number, hour: number): number {
  const dayShift = hour >= 8 && hour < 20 ? 0.72 : 0.52
  const staffingCushion = dayShift / 0.72
  return Math.min(98, ((census / BEDS) * 100) / Math.max(0.2, staffingCushion) + 4)
}

function waitingFromArrivals(arrivals: number[]): number[] {
  return arrivals.map((a, i) => {
    const peak = i % 24 >= 8 && i % 24 <= 12 ? 1.55 : i % 24 === 20 ? 1.35 : 1
    return Math.round((12 + a * 8) * peak * 10) / 10
  })
}

function inventoryDaily(seed: number): number[] {
  const rng = mulberry32(seed ^ 0x5eed)
  const out: number[] = []
  let level = 78
  for (let d = 0; d < DISPLAY_DAYS; d++) {
    level -= 3.2 + rng() * 3
    if (level < 46) level += 30 + rng() * 18
    if (d % 4 === 0) level += 6 + rng() * 5
    out.push(Math.max(35, Math.min(100, level + gaussianish(rng) * 2)))
  }
  return out
}

// --- labels ------------------------------------------------------------------

function hourlyLabels(now = new Date()): string[] {
  const out: string[] = []
  for (let i = 71; i >= 0; i--) out.push(new Date(now.getTime() - i * 3600000).toISOString())
  return out
}

function dailyLabels(days: number, now = new Date()): string[] {
  const out: string[] = []
  for (let i = days - 1; i >= 0; i--) out.push(new Date(now.getTime() - i * 86400000).toISOString())
  return out
}

// --- public construction -----------------------------------------------------

const COLORS = {
  blue: '#3b82f6',
  green: '#22c55e',
  amber: '#f59e0b',
  red: '#ef4444',
  violet: '#8b5cf6',
  cyan: '#06b6d4',
}

function series(key: string, label: string, unit: string, color: string, labels: string[], values: number[]): Series {
  return {
    key,
    label,
    unit,
    color,
    points: values.map((v, i) => ({ t: labels[i], v }) as SeriesPoint),
  }
}

const CARD_KEYS = new Set(['occupancy', 'waiting', 'utilization', 'inventory', 'mortality', 'readmission'])
function statusOf(key: string, value: number, deltaPct: number): KpiStatus {
  if (!CARD_KEYS.has(key)) return 'ok'
  if (key === 'inventory') return value < 65 ? 'alert' : value < 78 ? 'warn' : 'ok'
  if (key === 'occupancy') return value > 93 ? 'alert' : value > 88 ? 'warn' : 'ok'
  if (key === 'utilization') return value > 97 ? 'alert' : value > 93 ? 'warn' : 'ok'
  if (key === 'waiting') return value > 60 ? 'alert' : value > 40 ? 'warn' : 'ok'
  if (key === 'mortality') return deltaPct > 8 ? 'warn' : 'ok'
  if (key === 'readmission') return value > 14 ? 'warn' : 'ok'
  return 'ok'
}

export function buildDatasets(now = new Date()): Datasets {
  const model = buildRaw(seedFromNow(now))
  const hours = hourlyLabels(now)
  const days = dailyLabels(DISPLAY_DAYS, now)

  const hourSeries = {
    admissions: series('admissions', 'Admissions', 'patients', COLORS.blue, hours, model.byHour[0]),
    discharges: series('discharges', 'Discharges', 'patients', COLORS.green, hours, model.byHour[1]),
    occupancy: series('occupancy', 'Bed occupancy', '%', COLORS.violet, hours, model.byHour[2]),
    utilization: series('utilization', 'Staff utilization', '%', COLORS.cyan, hours, model.byHour[3]),
    waiting: series('waiting', 'Waiting time', 'min', COLORS.amber, hours, model.byHour[4]),
  }
  const daySeries = {
    admissions: series('admissions', 'Admissions', 'patients', COLORS.blue, days, model.byDay[0]),
    discharges: series('discharges', 'Discharges', 'patients', COLORS.green, days, model.byDay[1]),
    occupancy: series('occupancy', 'Bed occupancy', '%', COLORS.violet, days, model.byDay[3]),
    utilization: series('utilization', 'Staff utilization', '%', COLORS.cyan, days, model.byDay[10]),
    revenue: series('revenue', 'Revenue', '$', COLORS.green, days, model.byDay[6]),
    expenses: series('expenses', 'Expenses', '$', COLORS.red, days, model.byDay[7]),
    mortality: series('mortality', 'Deaths / day', 'count', COLORS.red, days, model.byDay[4]),
    readmission: series('readmission', '30-day readmission', '%', COLORS.amber, days, model.byDay[9]),
    inventory: series('inventory', 'Inventory readiness', '%', COLORS.green, days, model.byDay[8]),
  }

  const mkKpi = (
    key: string,
    label: string,
    format: KpiValue['format'],
    value: number,
    prior: number,
    goodWhen: 'up' | 'down',
    hint: string,
    spark: number[],
  ): KpiValue => {
    const deltaPct = prior > 0 ? ((value - prior) / prior) * 100 : 0
    return {
      key,
      label,
      value,
      format,
      deltaPct,
      goodWhen,
      status: statusOf(key, value, deltaPct),
      hint,
      spark,
      asOf: now.toISOString(),
    }
  }

  const live = (base: number, amp: number) => base + Math.sin(now.getTime() / 6000) * amp * 0.2

  const kpis: KpiValue[] = [
    mkKpi('admissions', 'Admissions today', 'number', Math.round(live(model.current.admissions, 0.4)), model.prior.admissions, 'up', 'Cumulative inpatient admissions today', model.byDay[0].slice(-24)),
    mkKpi('discharges', 'Discharges today', 'number', Math.round(live(model.current.discharges, 0.4)), model.prior.discharges, 'up', 'Patients discharged today', model.byDay[1].slice(-24)),
    mkKpi('revenue', 'Revenue today', 'currency', live(model.current.revenue, 500), model.prior.revenue, 'up', 'Estimated daily gross revenue', model.byDay[6].slice(-24)),
    mkKpi('expenses', 'Expenses today', 'currency', live(model.current.expenses, 400), model.prior.expenses, 'down', 'Estimated daily operating cost', model.byDay[7].slice(-24)),
    mkKpi('occupancy', 'Bed occupancy', 'percent', live(model.current.occupancy, 0.25), model.prior.occupancy, 'down', `${Math.round((model.current.occupancy / 100) * BEDS)} of ${BEDS} beds in use`, model.byHour[2].slice(-24)),
    mkKpi('waiting', 'Waiting time', 'minutes', Math.round(live(model.current.waiting, 1)), model.prior.waiting, 'down', 'Average ED wait (minutes)', hourSeries.waiting.points.slice(-24).map((p) => p.v)),
    mkKpi('utilization', 'Staff utilization', 'percent', live(model.current.utilization, 0.5), model.prior.utilization, 'down', 'Census vs staffed coverage', model.byHour[3].slice(-24)),
    mkKpi('inventory', 'Inventory readiness', 'percent', live(model.current.inventory, 1), model.prior.inventory, 'up', 'Stock availability vs par levels', model.byDay[8].slice(-24)),
    mkKpi('mortality', 'Mortality today', 'number', live(model.current.mortality, 0.05), model.prior.mortality, 'down', 'Deaths today', model.byDay[4].slice(-24)),
    mkKpi('readmission', '30-day readmission', 'percent', live(model.current.readmission, 0.2), model.prior.readmission, 'down', 'Readmissions within 30 days', model.byDay[9].slice(-24)),
  ]

  return {
    kpis,
    admissions: daySeries.admissions,
    discharges: daySeries.discharges,
    revenue: daySeries.revenue,
    expenses: daySeries.expenses,
    occupancy: daySeries.occupancy,
    utilization: daySeries.utilization,
    waiting: hourSeries.waiting,
    mortality: daySeries.mortality,
    readmission: daySeries.readmission,
    inventory: daySeries.inventory,
  }
}

// --- demo forecasts ----------------------------------------------------------

const FORECAST_LABELS: { key: string; label: string; unit: string }[] = [
  { key: 'patient-inflow.department.7d', label: 'Patient inflow', unit: 'patients' },
  { key: 'bed-occupancy.ward.7d', label: 'Bed occupancy', unit: '%' },
  { key: 'icu-load.icu-unit.7d', label: 'ICU load', unit: 'patients' },
  { key: 'revenue.biller.monthly', label: 'Daily revenue', unit: '$k' },
  { key: 'medicine-usage.medication.30d', label: 'Medicine usage', unit: 'units' },
]

export function demoForecasts(now = new Date()): Forecast[] {
  const model = buildRaw(seedFromNow(now))
  const start = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1)
  return FORECAST_LABELS.map((spec, i) => ({
    predictionKey: spec.key,
    entityType: spec.key.split('.')[0],
    label: spec.label,
    horizon: spec.key.split('.')[2],
    windowFrom: start.toISOString().slice(0, 10),
    windowTo: new Date(start.getTime() + 6 * 86400000).toISOString().slice(0, 10),
    value: model.forecastValues[i],
    q10: model.forecastQ10[i],
    q90: model.forecastQ90[i],
    confidence: 0.9,
    modelVersion: 'builtin.seasonal_naive',
    generatedAt: now.toISOString(),
    source: 'demo',
    unit: spec.unit,
  }))
}

// --- rule-based insights -----------------------------------------------------

export function ruleInsights(datasets: Datasets): string[] {
  const out: string[] = []
  const byKey = (key: string) => datasets.kpis.find((k) => k.key === key)!
  const occ = byKey('occupancy')
  const util = byKey('utilization')
  const inventory = byKey('inventory')
  const waiting = byKey('waiting')

  if (occ.status !== 'ok') out.push(`Bed occupancy at ${occ.value.toFixed(1)}% — surge watch beyond the 88% comfort threshold.`)
  else out.push(`Bed occupancy at ${occ.value.toFixed(1)}% is within the operating band.`)
  if (util.status !== 'ok') out.push(`Staff utilization at ${util.value.toFixed(1)}% — consider shift-level capacity adjustments.`)
  if (inventory.status === 'alert') out.push(`Inventory readiness dropped to ${inventory.value.toFixed(1)}% — restock is proposed for the pharmacy/inventory agents.`)
  if (waiting.status !== 'ok') out.push(`ED waiting time peaking near ${waiting.value.toFixed(0)} minutes this shift.`)

  const adm = byKey('admissions')
  const dis = byKey('discharges')
  const ratio = adm.value - dis.value
  out.push(ratio > 5 ? `Admissions are running ${Math.round(ratio)} ahead of discharges — census is rising.` : 'Flow is balanced: admissions and discharges are in step.')

  const rev = byKey('revenue')
  const exp = byKey('expenses')
  const marginK = (rev.value - exp.value) / 1000
  out.push(`Daily operating margin ${marginK.toFixed(0)}k (revenue ${(rev.value / 1000).toFixed(0)}k vs expenses ${(exp.value / 1000).toFixed(0)}k).`)

  const mort = byKey('mortality')
  const rate = (mort.value / Math.max(1, adm.value)) * 1000
  out.push(`Mortality ${mort.value.toFixed(1)} deaths today (${rate.toFixed(1)} per 1,000 admissions).`)
  return out
}