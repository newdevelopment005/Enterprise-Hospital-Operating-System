// Dependency-free interactive SVG charts: line (multi-series), grouped bars and
// forecast band charts — all with a hover crosshair + tooltip.

import { useEffect, useRef, useState } from 'react'

import type { Series } from '../lib/types'

const TXT = '#98a0b3'
const GRID = '#232936'

function useMeasured<T extends HTMLElement>(): [React.RefObject<T>, number] {
  const ref = useRef<T>(null)
  const [width, setWidth] = useState(0)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) setWidth(entry.contentRect.width)
    })
    observer.observe(el)
    setWidth(el.clientWidth)
    return () => observer.disconnect()
  }, [])
  return [ref, width]
}

function niceDomain(min: number, max: number): [number, number] {
  if (max === min) {
    max = min + 1
  }
  const pad = (max - min) * 0.08
  return [min - pad, max + pad]
}

function shortTime(iso: string): string {
  const date = new Date(iso)
  return `${date.getMonth() + 1}/${date.getDate()} ${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`
}

interface TooltipState {
  x: number
  y: number
  lines: { label: string; value: string; color: string }[]
}

function buildTooltip(series: Series[], index: number, fmt: (v: number, unit: string) => string, px: number, py: number): TooltipState {
  return {
    x: px,
    y: py,
    lines: series.flatMap((s) => {
      const point = s.points[index]
      if (!point) return []
      return [{ label: s.label, value: fmt(point.v, s.unit), color: s.color }]
    }),
  }
}

// --- sparkline --------------------------------------------------------------

export function Sparkline({ values, color, width = 96, height = 30 }: { values: number[]; color: string; width?: number; height?: number }) {
  if (values.length < 2) return <span className="spark-empty" />
  const [min, max] = niceDomain(Math.min(...values), Math.max(...values))
  const x = (i: number) => (i / (values.length - 1)) * (width - 2) + 1
  const y = (v: number) => height - 2 - ((v - min) / (max - min)) * (height - 4)
  const path = values.map((v, i) => `${i === 0 ? 'M' : 'L'}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' ')
  return (
    <svg viewBox={`0 0 ${width} ${height}`} width={width} height={height} aria-hidden="true">
      <path d={path} fill="none" stroke={color} strokeWidth={1.6} strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  )
}

// --- line chart (multi-series, interactive) ---------------------------------

export function LineChart({
  series,
  height = 240,
  fmt = (v) => String(Math.round(v)),
}: {
  series: Series[]
  height?: number
  fmt?: (v: number, unit: string) => string
}) {
  const [wrapRef, width] = useMeasured<HTMLDivElement>()
  const [hover, setHover] = useState<{ index: number; x: number; y: number } | null>(null)
  const W = Math.max(320, width)
  const H = height
  const top = 16
  const bottom = 24
  const left = 8
  const right = 8
  const plotW = W - left - right
  const plotH = H - top - bottom

  const allValues = series.flatMap((s) => s.points.map((p) => p.v))
  const [min, max] = niceDomain(Math.min(...allValues), Math.max(...allValues))
  const n = Math.max(...series.map((s) => s.points.length), 2)
  const x = (i: number) => left + (i / (n - 1)) * plotW
  const y = (v: number) => top + plotH - ((v - min) / (max - min)) * plotH

  const linePath = (s: Series) =>
    s.points.map((p, i) => `${i === 0 ? 'M' : 'L'}${x(i).toFixed(1)},${y(p.v).toFixed(1)}`).join(' ')

  const gridLines = [0, 1, 2, 3].map((g) => {
    const gy = top + (plotH / 3) * g
    return { gy, value: max - ((max - min) / 3) * g }
  })

  const hoverIndex = hover?.index ?? null

  return (
    <div className="chart-wrap" ref={wrapRef}>
      <svg viewBox={`0 0 ${W} ${H}`} className="chart-svg"
        onMouseMove={(e) => {
          const rect = e.currentTarget.getBoundingClientRect()
          const frac = Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width))
          const index = Math.round(frac * (n - 1))
          setHover({ index, x: x(index), y: e.clientY - rect.top })
        }}
        onMouseLeave={() => setHover(null)}>
        {gridLines.map((g) => (
          <g key={g.gy}>
            <line x1={left} x2={W - right} y1={g.gy} y2={g.gy} stroke={GRID} strokeWidth={1} />
            <text x={left + 2} y={g.gy - 3} fill={TXT} fontSize={10}>{fmt(g.value, '')}</text>
          </g>
        ))}
        {series.map((s) => (
          <path key={s.key} d={linePath(s)} fill="none" stroke={s.color} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
        ))}
        {hoverIndex !== null &&
          series.map((s) => {
            const p = s.points[hoverIndex]
            if (!p) return null
            return <circle key={`pt-${s.key}`} cx={x(hoverIndex)} cy={y(p.v)} r={3.5} fill={s.color} stroke="#0f1117" strokeWidth={1.5} />
          })}
        {hoverIndex !== null && <line x1={x(hoverIndex)} x2={x(hoverIndex)} y1={top} y2={top + plotH} stroke="#4b5563" strokeWidth={1} strokeDasharray="3 3" />}
      </svg>
      {hover && hoverIndex !== null && (
        <div className="chart-tip" style={{ left: Math.min(hover.x + 8, W - 160), top: 2 }}>
          <div className="tip-time">{shortTime(series[0]?.points[hoverIndex]?.t ?? '')}</div>
          {buildTooltip(series, hoverIndex, fmt, hover.x, hover.y).lines.map((l) => (
            <div key={l.label} className="tip-line">
              <span className="tip-dot" style={{ background: l.color }} />
              <span className="tip-label">{l.label}</span>
              <span className="tip-value">{l.value}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// --- grouped bar chart ------------------------------------------------------

export function GroupedBarChart({
  series,
  height = 240,
  fmt = (v) => String(Math.round(v)),
}: {
  series: Series[]
  height?: number
  fmt?: (v: number, unit: string) => string
}) {
  const [wrapRef, width] = useMeasured<HTMLDivElement>()
  const [hover, setHover] = useState<{ index: number; x: number; y: number } | null>(null)
  const W = Math.max(320, width)
  const H = height
  const top = 16
  const bottom = 24
  const left = 8
  const right = 8
  const plotH = H - top - bottom

  const allValues = series.flatMap((s) => s.points.map((p) => p.v))
  const max = Math.max(...allValues, 1)
  const n = Math.max(...series.map((s) => s.points.length), 2)
  const groupW = (W - left - right) / n
  const barW = Math.max(2, Math.min(16, (groupW / series.length) * 0.7))
  const x = (i: number) => left + i * groupW + groupW / 2
  const y = (v: number) => top + plotH - (v / max) * plotH

  const labels = series[0]?.points.map((p) => p.t.slice(0, 10)) ?? []

  return (
    <div className="chart-wrap" ref={wrapRef}>
      <svg viewBox={`0 0 ${W} ${H}`} className="chart-svg"
        onMouseMove={(e) => {
          const rect = e.currentTarget.getBoundingClientRect()
          const frac = Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width))
          const index = Math.min(n - 1, Math.floor(frac * n))
          setHover({ index, x: x(index), y: e.clientY - rect.top })
        }}
        onMouseLeave={() => setHover(null)}>
        {[0, 1, 2, 3].map((g) => {
          const gy = top + (plotH / 3) * g
          return (
            <g key={g}>
              <line x1={left} x2={W - right} y1={gy} y2={gy} stroke={GRID} strokeWidth={1} />
              <text x={left + 2} y={gy - 3} fill={TXT} fontSize={10}>{fmt(max - (max / 3) * g, '')}</text>
            </g>
          )
        })}
        {series.map((s, si) =>
          s.points.map((p, i) => {
            const cx = x(i) - (barW * series.length) / 2 + barW * si + barW / 2
            return <rect key={`${s.key}-${i}`} x={cx - barW / 2} y={y(p.v)} width={barW} height={Math.max(0, top + plotH - y(p.v))} rx={2} fill={s.color} opacity={0.88} />
          }),
        )}
        {hover && (
          <line x1={x(hover.index)} x2={x(hover.index)} y1={top} y2={top + plotH} stroke="#4b5563" strokeWidth={1} strokeDasharray="3 3" />
        )}
      </svg>
      {hover && (
        <div className="chart-tip" style={{ left: Math.min(hover.x + 8, W - 170), top: 2 }}>
          <div className="tip-time">{labels[hover.index] ?? ''}</div>
          {series.flatMap((s) => s.points[hover.index] ? [{ label: s.label, value: fmt(s.points[hover.index].v, s.unit), color: s.color }] : []).map((l) => (
            <div key={l.label} className="tip-line">
              <span className="tip-dot" style={{ background: l.color }} />
              <span className="tip-label">{l.label}</span>
              <span className="tip-value">{l.value}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// --- forecast band chart ------------------------------------------------------

export function BandLineChart({
  labels,
  values,
  bandLow,
  bandHigh,
  color,
  unit,
  height = 160,
  fmt = (v) => String(Math.round(v)),
}: {
  labels: string[]
  values: number[]
  bandLow: number[]
  bandHigh: number[]
  color: string
  unit: string
  height?: number
  fmt?: (v: number, unit: string) => string
}) {
  const [wrapRef, width] = useMeasured<HTMLDivElement>()
  const [hoverIndex, setHoverIndex] = useState<number | null>(null)
  const W = Math.max(300, width)
  const H = height
  const top = 12
  const bottom = 18
  const left = 6
  const right = 6
  const plotW = W - left - right
  const plotH = H - top - bottom

  const all = [...bandLow, ...bandHigh, ...values]
  const [min, max] = niceDomain(Math.min(...all), Math.max(...all))
  const n = Math.max(values.length, 2)
  const x = (i: number) => left + (i / (n - 1)) * plotW
  const y = (v: number) => top + plotH - ((v - min) / (max - min)) * plotH

  const bandTop = bandHigh.map((v, i) => x(i).toFixed(1) + ',' + y(v).toFixed(1)).join(' ')
  const bandBottom = bandLow.map((_v, i) => x(n - 1 - i).toFixed(1) + ',' + y(bandLow[n - 1 - i]).toFixed(1)).join(' ')
  const band = `M${bandTop} L${bandBottom} Z`
  const line = values.map((v, i) => `${i === 0 ? 'M' : 'L'}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' ')

  return (
    <div className="chart-wrap" ref={wrapRef}>
      <svg viewBox={`0 0 ${W} ${H}`} className="chart-svg"
        onMouseMove={(e) => {
          const rect = e.currentTarget.getBoundingClientRect()
          const frac = Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width))
          setHoverIndex(Math.round(frac * (n - 1)))
        }}
        onMouseLeave={() => setHoverIndex(null)}>
        <path d={band} fill={color} opacity={0.18} />
        <path d={line} fill="none" stroke={color} strokeWidth={2} strokeLinejoin="round" />
        {hoverIndex !== null && (
          <>
            <line x1={x(hoverIndex)} x2={x(hoverIndex)} y1={top} y2={top + plotH} stroke="#4b5563" strokeWidth={1} strokeDasharray="3 3" />
            <circle cx={x(hoverIndex)} cy={y(values[hoverIndex] ?? 0)} r={3.5} fill={color} stroke="#0f1117" strokeWidth={1.5} />
          </>
        )}
      </svg>
      {hoverIndex !== null && values[hoverIndex] !== undefined && (
        <div className="chart-tip" style={{ left: Math.min(x(hoverIndex) + 8, W - 170), top: 0 }}>
          <div className="tip-time">{labels[hoverIndex] ?? ''}</div>
          <div className="tip-line">
            <span className="tip-dot" style={{ background: color }} />
            <span className="tip-label">point</span>
            <span className="tip-value">{fmt(values[hoverIndex], unit)}</span>
          </div>
          <div className="tip-line">
            <span className="tip-label">q10–q90</span>
            <span className="tip-value muted">{fmt(bandLow[hoverIndex] ?? 0, unit)} – {fmt(bandHigh[hoverIndex] ?? 0, unit)}</span>
          </div>
        </div>
      )}
    </div>
  )
}