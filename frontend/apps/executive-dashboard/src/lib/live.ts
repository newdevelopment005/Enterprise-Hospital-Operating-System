// Maps the analytics-service live overview payload onto the dashboard's
// Datasets shape so it is a drop-in replacement for the demo generator.

import type { AnalyticsOverview, Datasets, LocaleInfo, Series } from './types'

export function overviewToDatasets(overview: AnalyticsOverview): Datasets {
  const series = (slug: string): Series =>
    overview.series[slug] ?? { key: slug, label: slug, unit: 'number', color: '#455a64', points: [] }
  return {
    kpis: overview.kpis,
    admissions: series('admissions'),
    discharges: series('discharges'),
    revenue: series('revenue'),
    expenses: series('expenses'),
    occupancy: series('occupancy'),
    utilization: series('utilization'),
    waiting: series('waiting'),
    mortality: series('mortality'),
    readmission: series('readmission'),
    inventory: series('inventory'),
  }
}

// Currency formatter bound to the detected country's currency.
export function makeMoney(locale: LocaleInfo | null): (v: number, unit?: string) => string {
  const code = locale?.currencyCode ?? 'USD'
  return (v: number) => {
    try {
      return new Intl.NumberFormat(locale?.localeTag ?? 'en-US', {
        style: 'currency',
        currency: code,
        notation: v >= 10_000 ? 'compact' : 'standard',
        maximumFractionDigits: v >= 1000 ? 1 : 0,
      }).format(v)
    } catch {
      return `${locale?.currencySymbol ?? '$'}${Math.round(v).toLocaleString()}`
    }
  }
}

// Time formatter bound to the detected country's timezone.
export function makeTimeFormatter(locale: LocaleInfo | null): () => string {
  return () => {
    try {
      return new Intl.DateTimeFormat(locale?.localeTag ?? undefined, {
        timeZone: locale?.timezone,
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      }).format(new Date())
    } catch {
      return new Date().toLocaleTimeString()
    }
  }
}
