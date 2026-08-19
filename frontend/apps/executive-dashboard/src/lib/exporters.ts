// Offline export helpers: Excel (SpreadsheetML 2003, opens in Excel without
// dependencies) and PDF (browser print dialog with a dedicated print stylesheet).

import type { Datasets, Forecast } from './types'

export function fmtNumber(value: number, format: string): string {
  if (format === 'currency') return `$${value.toLocaleString('en-US', { maximumFractionDigits: 0, minimumFractionDigits: 0 })}`
  if (format === 'percent') return `${value.toFixed(1)}%`
  if (format === 'minutes') return `${Math.round(value)} min`
  return value.toLocaleString('en-US', { maximumFractionDigits: 1 })
}

export function fmtDate(iso: string): string {
  if (!iso) return ''
  return iso.slice(0, 16).replace('T', ' ')
}

function xmlEscape(value: string | number): string {
  return String(value).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

function rowsFor(header: string[], body: (string | number)[][]): string {
  const head = `<Row>${header.map((h) => `<Cell ss:StyleID="hdr"><Data ss:Type="String">${xmlEscape(h)}</Data></Cell>`).join('')}</Row>`
  const rows = body.map((cells) => `<Row>${cells.map((c) => `<Cell><Data ss:Type="String">${xmlEscape(c)}</Data></Cell>`).join('')}</Row>`).join('')
  return head + rows
}

function worksheet(name: string, rows: string): string {
  return `<Worksheet ss:Name="${xmlEscape(name)}"><Table>${rows}</Table></Worksheet>`
}

export function exportExcel(datasets: Datasets, forecasts: Forecast[], insights: string[]): void {
  const now = new Date()
  const stamp = now.toISOString().slice(0, 19).replace(/[:T]/g, '-')

  const kpiSheet = rowsFor(
    ['KPI', 'Value', 'Delta %', 'Status', 'Last updated'],
    datasets.kpis.map((k) => [k.label, fmtNumber(k.value, k.format), k.deltaPct.toFixed(1), k.status, fmtDate(k.asOf)]),
  )

  const trendSheet =
    rowsFor(['Date', 'Admissions', 'Discharges', 'Revenue', 'Expenses', 'Bed occupancy %', 'Waiting min', 'Mortality', 'Readmission %', 'Inventory %'],
      datasets.admissions.points.map((p, i) => [
        p.t.slice(0, 10),
        fmtNumber(datasets.admissions.points[i]?.v ?? 0, 'number'),
        fmtNumber(datasets.discharges.points[i]?.v ?? 0, 'number'),
        fmtNumber(datasets.revenue.points[i]?.v ?? 0, 'currency'),
        fmtNumber(datasets.expenses.points[i]?.v ?? 0, 'currency'),
        fmtNumber(datasets.occupancy.points[i]?.v ?? 0, 'percent'),
        fmtNumber(datasets.waiting.points[i]?.v ?? 0, 'minutes'),
        fmtNumber(datasets.mortality.points[i]?.v ?? 0, 'number'),
        fmtNumber(datasets.readmission.points[i]?.v ?? 0, 'percent'),
        fmtNumber(datasets.inventory.points[i]?.v ?? 0, 'percent'),
      ]),
    )

  const forecastSheet =
    rowsFor(['Prediction', 'Entity', 'Horizon', 'Window', 'Day 1', 'Day 3', 'Day 7', 'Confidence', 'Model', 'Source', 'Generated'],
      forecasts.map((f) => [
        f.label,
        f.entityType,
        f.horizon,
        `${f.windowFrom} → ${f.windowTo}`,
        fmtNumber(f.value[0] ?? 0, 'number'),
        fmtNumber(f.value[2] ?? 0, 'number'),
        fmtNumber(f.value[6] ?? 0, 'number'),
        `${(f.confidence * 100).toFixed(0)}%`,
        f.modelVersion,
        f.source,
        fmtDate(f.generatedAt),
      ]),
    )

  const insightSheet = rowsFor(['Annex', 'Insight'], insights.map((s, i) => [String(i + 1), s]))

  const xml = `<?xml version="1.0"?>
<?mso-application progid="Excel.Sheet"?>
<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"
          xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">
 <Styles>
   <Style ss:ID="hdr"><Font ss:Bold="1"/><Interior ss:Color="#e7eaf3" ss:Pattern="Solid"/></Style>
 </Styles>
 ${worksheet('KPIs', kpiSheet)}
 ${worksheet('Trends', trendSheet)}
 ${worksheet('Forecasts', forecastSheet)}
 ${worksheet('AI Insights', insightSheet)}
</Workbook>`

  download(`EHOS-Executive-Dashboard-${stamp}.xls`, xml, 'application/vnd.ms-excel')
}

export function exportPdf(): void {
  // Print-friendly layout (see @media print in styles.css) + browser save-as-PDF.
  window.print()
}

function download(filename: string, content: string, mime: string): void {
  const blob = new Blob([content], { type: `${mime};charset=utf-8;` })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}