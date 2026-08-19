// AI insights panel: HospitalGPT briefing (ai-service) with rule-based fallback.

import type { Insight } from '../lib/types'

export function InsightsPanel({ insights, loading, onRefresh }: { insights: Insight[]; loading: boolean; onRefresh: () => void }) {
  return (
    <section className="panel">
      <div className="panel-head">
        <h2>AI insights</h2>
        <button className="ghost" onClick={onRefresh} disabled={loading}>
          {loading ? 'Thinking…' : 'Refresh briefing'}
        </button>
      </div>
      {insights.length === 0 ? (
        <p className="muted">Generate an executive briefing from the current KPI snapshot.</p>
      ) : (
        <ul className="insight-list">
          {insights.map((insight, i) => (
            <li key={`${insight.category}-${i}`} className={`insight insight-${insight.category}`}>
              <span className="tag tag-cat">{insight.category === 'ai' ? 'HospitalGPT' : 'rule'}</span>
              <span>{insight.text}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}