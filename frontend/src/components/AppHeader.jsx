import { NavLink } from 'react-router-dom'
import { IconRefresh } from './icons/Icons'
import { useAppContext } from '../context/AppContext'

export default function AppHeader() {
  const { cookieInfo, cookieError, autoFetchCookie, preciseRun, broadRun } = useAppContext()
  const anyRunInflight =
    preciseRun.status === 'running' || preciseRun.status === 'starting' ||
    broadRun.status === 'running' || broadRun.status === 'starting'

  const tabClass = ({ isActive }) =>
    `relative px-3 py-2 text-[11px] font-semibold uppercase tracking-widest transition-colors ${
      isActive ? 'text-indigo-600' : 'text-slate-500 hover:text-slate-800'
    }`

  return (
    <header className="bg-white border-b border-slate-200 px-4 py-1.5 flex items-center justify-between shrink-0">
      <div className="flex items-center gap-4">
        {/* Brand */}
        <div className="flex items-center gap-2 text-slate-950">
          <span className="text-[11px] font-bold tracking-[3px] uppercase leading-none">搜尋巡檢平台</span>
          <span className="text-[8px] font-bold text-indigo-600 uppercase tracking-[2px] font-mono">Search Audit</span>
        </div>

        {/* Nav tabs */}
        <nav className="flex items-center gap-1 ml-4">
          <NavLink to="/" end className={tabClass}>
            {({ isActive }) => (
              <>
                巡檢
                {isActive && <span className="absolute inset-x-2 -bottom-px h-[2px] bg-indigo-600 rounded-full" />}
              </>
            )}
          </NavLink>
          <NavLink to="/batch" className={tabClass}>
            {({ isActive }) => (
              <>
                批次
                {anyRunInflight && (
                  <span className="ml-1 inline-block w-1.5 h-1.5 rounded-full bg-indigo-500 animate-pulse" />
                )}
                {isActive && <span className="absolute inset-x-2 -bottom-px h-[2px] bg-indigo-600 rounded-full" />}
              </>
            )}
          </NavLink>
        </nav>
      </div>

      <div className="flex items-center gap-2 text-[10px]">
        {cookieError && <div className="px-2 py-0.5 bg-red-50 text-red-600 border border-red-100 rounded">{cookieError}</div>}
        <div className="flex items-center gap-1.5 px-2 py-0.5 bg-slate-50 border border-slate-200 rounded-full">
          <div className={`w-1.5 h-1.5 rounded-full ${cookieInfo ? 'bg-emerald-500' : 'bg-red-500'}`} />
          <span className="text-slate-500 uppercase tracking-wide font-mono">{cookieInfo ? '連線正常' : '連線斷開'}</span>
        </div>
        <button onClick={autoFetchCookie} className="text-slate-300 hover:text-indigo-600">
          <IconRefresh />
        </button>
      </div>
    </header>
  )
}
