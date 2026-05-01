import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import ChatInterface from '../components/ChatInterface'

function CompassIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="h-5 w-5 text-sky-600" stroke="currentColor" strokeWidth="1.5">
      <circle cx="12" cy="12" r="10" />
      <polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76" fill="currentColor" fillOpacity="0.15" />
    </svg>
  )
}

export default function ChatPage() {
  const { logout } = useAuth()
  const navigate = useNavigate()

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  return (
    <div className="flex flex-col h-screen">
      {/* Header */}
      <header className="flex items-center justify-between px-6 py-3.5 border-b border-sky-100 bg-white/80 backdrop-blur-md flex-shrink-0">
        <Link to="/" className="flex items-center gap-2.5 group">
          <CompassIcon />
          <div className="leading-tight">
            <div className="font-serif text-base text-slate-900 tracking-tight">
              The World Decoded
            </div>
            <div className="text-[11px] text-sky-600 italic -mt-0.5">for you</div>
          </div>
        </Link>

        <nav className="flex items-center gap-1">
          <Link
            to="/history"
            className="px-3.5 py-1.5 text-sm text-slate-600 hover:text-sky-700 hover:bg-sky-50 rounded-lg transition-colors font-medium"
          >
            Your trips
          </Link>
          <button
            onClick={handleLogout}
            className="px-3.5 py-1.5 text-sm text-slate-600 hover:text-sky-700 hover:bg-sky-50 rounded-lg transition-colors font-medium ml-1"
          >
            Sign out
          </button>
        </nav>
      </header>

      {/* Chat area */}
      <div className="flex-1 overflow-hidden max-w-4xl w-full mx-auto">
        <ChatInterface />
      </div>
    </div>
  )
}