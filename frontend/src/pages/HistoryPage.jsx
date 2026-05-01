import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import api from '../api/client'

const PAGE_SIZE = 20

const TOOL_LABELS = {
  rag_search: 'Researched destinations',
  live_conditions: 'Checked conditions',
  classify_destination: 'Matched travel style',
}
const friendlyTool = (name) => TOOL_LABELS[name] || name

function ChevronIcon({ open }) {
  return (
    <svg
      className={`h-4 w-4 text-sky-500 flex-shrink-0 transition-transform duration-200 ${open ? 'rotate-180' : ''}`}
      viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
    >
      <path d="M19 9l-7 7-7-7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function CompassIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="h-5 w-5 text-sky-600" stroke="currentColor" strokeWidth="1.5">
      <circle cx="12" cy="12" r="10" />
      <polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76" fill="currentColor" fillOpacity="0.15" />
    </svg>
  )
}

function StatusBadge({ status }) {
  const styles =
    status === 'completed'
      ? 'text-emerald-700 bg-emerald-50 border-emerald-200'
      : 'text-red-700 bg-red-50 border-red-200'
  return (
    <span className={`text-[10px] font-medium px-2 py-0.5 rounded-full border ${styles}`}>
      {status}
    </span>
  )
}

function ToolBadge({ name }) {
  return (
    <span className="text-[10px] bg-sky-50 border border-sky-100 text-sky-700 px-2 py-0.5 rounded-full italic">
      {friendlyTool(name)}
    </span>
  )
}

function RunRow({ run }) {
  const [open, setOpen] = useState(false)

  const date = new Date(run.created_at).toLocaleString(undefined, {
    month: 'short', day: 'numeric', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })

  // Deduplicate tools used for the badge row
  const uniqueTools = [...new Set(run.tools_used || [])]

  return (
    <div className="border border-sky-100 rounded-xl overflow-hidden bg-white shadow-sky-soft hover:shadow-sky-card transition-shadow">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-start justify-between w-full px-5 py-4 hover:bg-sky-50/40 transition-colors text-left gap-4"
      >
        <div className="flex-1 min-w-0">
          <p className="text-sm text-slate-800 font-medium truncate">{run.query}</p>
          <div className="flex items-center gap-2 mt-2 flex-wrap">
            <span className="text-xs text-slate-500">{date}</span>
            <StatusBadge status={run.status} />
            {uniqueTools.map((t) => <ToolBadge key={t} name={t} />)}
          </div>
        </div>

        <div className="flex items-center gap-3 flex-shrink-0 mt-0.5">
          {run.estimated_cost_usd > 0 && (
            <span className="text-xs text-slate-400 tabular-nums">
              ${run.estimated_cost_usd.toFixed(4)}
            </span>
          )}
          <ChevronIcon open={open} />
        </div>
      </button>

      {open && (
        <div className="px-5 py-4 bg-sky-50/40 border-t border-sky-100">
          {run.response ? (
            <p className="text-sm text-slate-700 leading-relaxed whitespace-pre-wrap">{run.response}</p>
          ) : (
            <p className="text-sm text-slate-400 italic">No response recorded.</p>
          )}
        </div>
      )}
    </div>
  )
}

function Pagination({ page, totalPages, onChange }) {
  if (totalPages <= 1) return null
  return (
    <div className="flex items-center justify-center gap-3 mt-10">
      <button
        onClick={() => onChange(page - 1)}
        disabled={page === 1}
        className="px-4 py-2 text-sm bg-white border border-sky-200 hover:border-sky-400 hover:bg-sky-50 disabled:opacity-40 disabled:cursor-not-allowed text-slate-700 rounded-lg transition shadow-sky-soft"
      >
        Previous
      </button>
      <span className="text-sm text-slate-500 tabular-nums">
        {page} / {totalPages}
      </span>
      <button
        onClick={() => onChange(page + 1)}
        disabled={page === totalPages}
        className="px-4 py-2 text-sm bg-white border border-sky-200 hover:border-sky-400 hover:bg-sky-50 disabled:opacity-40 disabled:cursor-not-allowed text-slate-700 rounded-lg transition shadow-sky-soft"
      >
        Next
      </button>
    </div>
  )
}

export default function HistoryPage() {
  const [runs, setRuns] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    api
      .get('/trips/history', { params: { page, page_size: PAGE_SIZE } })
      .then(({ data }) => {
        if (cancelled) return
        setRuns(data.runs)
        setTotal(data.total)
      })
      .catch(() => { if (!cancelled) setError('Could not load your trips.') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [page])

  const totalPages = Math.ceil(total / PAGE_SIZE)

  return (
    <div className="min-h-screen">
      {/* Header */}
      <header className="flex items-center justify-between px-6 py-3.5 border-b border-sky-100 bg-white/80 backdrop-blur-md sticky top-0 z-10">
        <Link to="/" className="flex items-center gap-2.5 group">
          <CompassIcon />
          <div className="leading-tight">
            <div className="font-serif text-base text-slate-900 tracking-tight">
              The World Decoded
            </div>
            <div className="text-[11px] text-sky-600 italic -mt-0.5">for you</div>
          </div>
        </Link>

        <Link
          to="/"
          className="flex items-center gap-1.5 text-sm text-slate-600 hover:text-sky-700 hover:bg-sky-50 px-3.5 py-1.5 rounded-lg transition-colors font-medium"
        >
          <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M19 12H5M12 5l-7 7 7 7" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          Back to chat
        </Link>
      </header>

      {/* Content */}
      <main className="max-w-4xl mx-auto px-4 py-10">
        <div className="mb-8">
          <h1 className="font-serif text-3xl text-slate-900 leading-tight">
            Your trips
          </h1>
          <p className="text-sm text-slate-500 mt-2 italic">
            {!loading && total > 0
              ? `${total} ${total === 1 ? 'plan' : 'plans'} so far. Each one a beginning.`
              : 'A travel diary in the making.'}
          </p>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-20 text-slate-500 gap-2">
            <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
            </svg>
            <span className="italic">Gathering your journeys…</span>
          </div>
        ) : error ? (
          <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-xl px-4 py-3">
            {error}
          </div>
        ) : runs.length === 0 ? (
          <div className="text-center py-20 bg-white border border-sky-100 rounded-2xl shadow-sky-soft">
            <div className="text-5xl mb-4">🗺️</div>
            <p className="font-serif text-xl text-slate-800 mb-2">No trips yet</p>
            <p className="text-sm text-slate-500 mb-6 italic">Every great journey starts with a single question.</p>
            <Link
              to="/"
              className="inline-flex items-center gap-1.5 text-sm bg-sky-600 hover:bg-sky-500 text-white font-medium px-5 py-2.5 rounded-lg transition-colors shadow-sky-soft hover:shadow-sky-glow"
            >
              Plan your first trip
              <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M5 12h14M12 5l7 7-7 7" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </Link>
          </div>
        ) : (
          <>
            <div className="space-y-3">
              {runs.map((run) => <RunRow key={run.id} run={run} />)}
            </div>
            <Pagination page={page} totalPages={totalPages} onChange={setPage} />
          </>
        )}
      </main>
    </div>
  )
}