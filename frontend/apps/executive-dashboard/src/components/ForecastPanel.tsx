// Advisory forecast cards from the prediction-service (with demo fallback).

import { fmtNumber } from '../lib/exporters'
import type { Forecast } from '../lib/types'
import { BandLineChart } from './Charts'

export function ForecastPanel({ forecasts, targetsNote }: { forecasts: Forecast[]; targetsNote: string | null }) {
  if (forecasts.length === 0) {
    return (
      <section className="panel">
        <h2>Forecasts</h2>
        <p className="muted">No forecast data available. Start the prediction-service and train a model, or seed predictions via POST /api/v1/predictions/generate.</p>
      </section>
    )
  }
  return (
    <section className="panel">
      <div className="panel-head">
        <h2>Advisory forecasts</h2>
        {targetsNote && <span className="badge">{targetsNote}</span>}
      </div>
      <div className="forecast-grid">
        {forecasts.map((f) => {
          const fmt = (v: number) => fmtNumber(v, f.unit === '$' || f.unit === '$k' ? 'currency' : 'number')
          return (
            <div className={`forecast-card source-${f.source}`} key={f.predictionKey}>
              <div className="forecast-head">
                <div>
                  <h3>{f.label}</h3>
                  <span className="muted">
                    {f.windowFrom} → {f.windowTo} · horizon {f.horizon}
                  </span>
                </div>
                <span className={`tag source-${f.source}`}>{f.source}</span>
              </div>
              <BandLineChart
                labels={Array.from({ length: f.value.length }, (_, i) => `${f.windowFrom.slice(5)} +${i + 1}d`)}
                values={f.value}
                bandLow={f.q10}
                bandHigh={f.q90}
                color="#3b82f6"
                unit={f.unit}
                fmt={fmt}
              />
              <div className="forecast-meta">
                <span>confidence {Math.round(f.confidence * 100)}%</span>
                <span>{f.modelVersion}</span>
                <span>model-based outlook · advisory</span>
              </div>
            </div>
          )
        })}
      </div>
    </section>
  )
}