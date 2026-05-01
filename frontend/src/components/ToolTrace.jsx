import { useState } from 'react'

function ChevronIcon({ open }) {
  return (
    <svg
      className={`h-3 w-3 text-sky-500 transition-transform duration-200 ${open ? 'rotate-180' : ''}`}
      viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"
    >
      <path d="M19 9l-7 7-7-7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function StatusPill({ error }) {
  return error
    ? <span className="text-[10px] font-medium text-red-700 bg-red-50 border border-red-200 rounded-full px-2 py-0.5">failed</span>
    : <span className="text-[10px] font-medium text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-full px-2 py-0.5">ok</span>
}

function JsonBlock({ value }) {
  return (
    <pre className="text-[11px] bg-sky-50/70 border border-sky-100 rounded-lg p-3 text-slate-700 overflow-x-auto leading-relaxed max-h-48 scrollbar-thin font-mono">
      {JSON.stringify(value, null, 2)}
    </pre>
  )
}

// ── Friendly tool name + summary ──────────────────────────────────────────────

const TOOL_LABELS = {
  rag_search: { label: 'Researched destinations', icon: '📖' },
  live_conditions: { label: 'Checked current conditions', icon: '🌤️' },
  classify_destination: { label: 'Matched travel style', icon: '🧭' },
}

function friendlyName(toolName) {
  return TOOL_LABELS[toolName]?.label || toolName
}

function friendlyIcon(toolName) {
  return TOOL_LABELS[toolName]?.icon || '·'
}

// ── Single tool log row (expandable) ──────────────────────────────────────────

function ToolLogRow({ log }) {
  const [open, setOpen] = useState(false)

  return (
    <div className="border-b border-sky-100 last:border-0">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center justify-between w-full py-2.5 text-left gap-3 hover:bg-sky-50/50 transition-colors px-2 rounded"
      >
        <div className="flex items-center gap-2.5 min-w-0">
          <span className="text-sm">{friendlyIcon(log.tool_name)}</span>
          <StatusPill error={log.error} />
          <span className="text-xs text-slate-700 truncate">{friendlyName(log.tool_name)}</span>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <span className="text-[11px] text-slate-400 tabular-nums">{log.duration_ms}ms</span>
          <ChevronIcon open={open} />
        </div>
      </button>

      {open && (
        <div className="pb-3 space-y-2.5 px-2">
          <div>
            <p className="text-[10px] font-medium text-slate-500 uppercase tracking-wider mb-1">Input</p>
            <JsonBlock value={log.input_data} />
          </div>
          {log.error ? (
            <div>
              <p className="text-[10px] font-medium text-slate-500 uppercase tracking-wider mb-1">Error</p>
              <p className="text-xs text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2 font-mono">
                {log.error}
              </p>
            </div>
          ) : log.output_data ? (
            <div>
              <p className="text-[10px] font-medium text-slate-500 uppercase tracking-wider mb-1">Output</p>
              <JsonBlock value={log.output_data} />
            </div>
          ) : null}
        </div>
      )}
    </div>
  )
}

// ── Main wrapper ──────────────────────────────────────────────────────────────

export default function ToolTrace({ tools = [], toolLogs = [], cost = 0, loading = false }) {
  const [open, setOpen] = useState(false)

  if (!tools.length) return null

  // Build a friendly summary line: "Researched destinations · Checked current conditions"
  const uniqueTools = [...new Set(tools)]
  const summary = uniqueTools.map(friendlyName).join(' · ')

  return (
    <div className="max-w-[85%] border border-sky-100 rounded-xl overflow-hidden text-xs bg-white shadow-sky-soft">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center justify-between w-full px-4 py-2.5 hover:bg-sky-50/50 transition-colors"
      >
        <div className="flex items-center gap-2.5 min-w-0">
          <span className="text-sky-500 text-[11px] font-medium uppercase tracking-wider flex-shrink-0">
            How I planned this
          </span>
          <span className="text-slate-400">·</span>
          <span className="text-slate-600 truncate italic">{summary}</span>
        </div>
        <div className="flex items-center gap-2.5 flex-shrink-0">
          {cost > 0 && (
            <span className="text-slate-400 tabular-nums text-[11px]">${cost.toFixed(4)}</span>
          )}
          <ChevronIcon open={open} />
        </div>
      </button>

      {open && (
        <div className="border-t border-sky-100 px-4 bg-sky-50/30">
          {loading ? (
            <p className="text-slate-500 py-3 italic">Loading details…</p>
          ) : toolLogs.length > 0 ? (
            toolLogs.map((log) => <ToolLogRow key={log.id} log={log} />)
          ) : (
            <p className="text-slate-500 py-3 italic">No details available.</p>
          )}
        </div>
      )}
    </div>
  )
}