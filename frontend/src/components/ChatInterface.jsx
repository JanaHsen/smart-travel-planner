import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import api from '../api/client'
import ToolTrace from './ToolTrace'

// ── Typing indicator ──────────────────────────────────────────────────────────

function ThinkingDots() {
  return (
    <div className="flex gap-1.5 items-center px-4 py-3.5">
      {[0, 150, 300].map((delay) => (
        <span
          key={delay}
          className="w-2 h-2 bg-sky-400 rounded-full animate-bounce"
          style={{ animationDelay: `${delay}ms` }}
        />
      ))}
    </div>
  )
}

// ── Message bubbles ───────────────────────────────────────────────────────────

function UserBubble({ content }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[72%] bg-sky-600 text-white rounded-2xl rounded-tr-md px-4 py-3 text-sm leading-relaxed whitespace-pre-wrap shadow-sky-soft">
        {content}
      </div>
    </div>
  )
}

function AssistantBubble({ message }) {
  if (message.pending) {
    return (
      <div className="flex justify-start">
        <div className="bg-white border border-sky-100 rounded-2xl rounded-tl-md shadow-sky-soft">
          <ThinkingDots />
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-2.5 items-start w-full">
      <div className="max-w-[85%] bg-white border border-sky-100 text-slate-800 rounded-2xl rounded-tl-md px-6 py-5 text-sm leading-relaxed shadow-sky-soft">
        {message.content ? (
          <div className="prose-travel">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {message.content}
            </ReactMarkdown>
          </div>
        ) : (
          <span className="text-slate-400 italic">No response.</span>
        )}
      </div>
      <ToolTrace
        tools={message.tools}
        toolLogs={message.toolLogs}
        cost={message.cost}
        loading={message.loadingTrace}
      />
    </div>
  )
}

// ── Send / spinner icons ──────────────────────────────────────────────────────

function SendIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="h-4 w-4" stroke="currentColor" strokeWidth="2">
      <path d="M22 2L11 13M22 2L15 22l-4-9-9-4 20-7z" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function SpinnerIcon() {
  return (
    <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
    </svg>
  )
}

// ── Empty state ───────────────────────────────────────────────────────────────

function EmptyState({ onPick }) {
  const suggestions = [
    'A quiet beach in Southeast Asia for two weeks in March, around $2,000',
    'Cultural city break in Europe for a long weekend in autumn',
    'Adventure trip with hiking and wildlife — somewhere I have not been',
    'Honeymoon in early December — warm, romantic, not too touristy',
  ]
  return (
    <div className="flex flex-col items-center justify-center h-full gap-8 px-4 text-center max-w-2xl mx-auto">
      <div>
        <h2 className="font-serif text-3xl text-slate-900 leading-tight">
          Where to next?
        </h2>
        <p className="text-sm text-slate-500 mt-3 italic">
          Tell me what you're dreaming of. I'll plan the rest.
        </p>
      </div>
      <div className="grid gap-2.5 w-full">
        {suggestions.map((s) => (
          <button
            key={s}
            onClick={() => onPick(s)}
            className="text-left text-sm text-slate-700 bg-white border border-sky-100 hover:border-sky-300 hover:bg-sky-50/50 rounded-xl px-4 py-3 transition-colors shadow-sky-soft hover:shadow-sky-card"
          >
            <span className="text-sky-500 mr-2">→</span>
            {s}
          </button>
        ))}
      </div>
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

export default function ChatInterface() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const bottomRef = useRef(null)
  const textareaRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const resizeTextarea = () => {
    const ta = textareaRef.current
    if (!ta) return
    ta.style.height = 'auto'
    ta.style.height = Math.min(ta.scrollHeight, 160) + 'px'
  }

  const send = async (overrideText) => {
    const query = (overrideText ?? input).trim()
    if (!query || loading) return

    const userId = `u-${Date.now()}`
    const assistantId = `a-${Date.now()}`

    setMessages((prev) => [
      ...prev,
      { id: userId, role: 'user', content: query },
      { id: assistantId, role: 'assistant', content: '', tools: [], toolLogs: [], cost: 0, pending: true, loadingTrace: false },
    ])
    setInput('')
    setError(null)
    setLoading(true)

    if (textareaRef.current) textareaRef.current.style.height = 'auto'

    try {
      const { data } = await api.post('/trips/plan', { query })

      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId
            ? { ...m, content: data.answer, tools: data.tools_used, cost: data.cost_usd, runId: data.run_id, pending: false, loadingTrace: true }
            : m
        )
      )

      try {
        const { data: detail } = await api.get(`/trips/${data.run_id}`)
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId ? { ...m, toolLogs: detail.tool_calls, loadingTrace: false } : m
          )
        )
      } catch {
        setMessages((prev) =>
          prev.map((m) => (m.id === assistantId ? { ...m, loadingTrace: false } : m))
        )
      }
    } catch (err) {
      setMessages((prev) => prev.filter((m) => m.id !== assistantId))
      setError(err.response?.data?.detail || 'Something went wrong. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      send()
    }
  }

  return (
    <div className="flex flex-col h-full">
      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-8 space-y-5 scrollbar-thin">
        {messages.length === 0 ? (
          <EmptyState onPick={(s) => send(s)} />
        ) : (
          messages.map((msg) => (
            <div key={msg.id}>
              {msg.role === 'user' ? (
                <UserBubble content={msg.content} />
              ) : (
                <AssistantBubble message={msg} />
              )}
            </div>
          ))
        )}

        {error && (
          <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-xl px-4 py-3">
            {error}
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input bar */}
      <div className="border-t border-sky-100 bg-white/80 backdrop-blur-md px-4 py-4 flex-shrink-0">
        <div className="flex gap-3 items-end max-w-3xl mx-auto">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => { setInput(e.target.value); resizeTextarea() }}
            onKeyDown={handleKeyDown}
            placeholder="Where shall we go?"
            rows={1}
            disabled={loading}
            className="flex-1 resize-none bg-sky-50/50 border border-sky-200 text-slate-800 placeholder-slate-400 rounded-xl px-4 py-3 text-sm leading-relaxed focus:outline-none focus:ring-2 focus:ring-sky-400 focus:border-sky-300 focus:bg-white transition-all disabled:opacity-60 min-h-[48px] shadow-sky-soft"
          />
          <button
            onClick={() => send()}
            disabled={!input.trim() || loading}
            className="flex items-center gap-2 px-5 h-[48px] bg-sky-600 hover:bg-sky-500 active:bg-sky-700 disabled:bg-slate-200 disabled:text-slate-400 disabled:cursor-not-allowed text-white rounded-xl text-sm font-medium transition-colors flex-shrink-0 shadow-sky-soft hover:shadow-sky-glow"
          >
            {loading ? <SpinnerIcon /> : <SendIcon />}
            <span>{loading ? 'Planning…' : 'Send'}</span>
          </button>
        </div>
        <p className="text-center text-[11px] text-slate-400 mt-2.5 italic">
          Press Enter to send · Shift + Enter for a new line
        </p>
      </div>
    </div>
  )
}