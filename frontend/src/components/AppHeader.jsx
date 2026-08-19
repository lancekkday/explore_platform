import { NavLink } from 'react-router-dom'
import { IconRefresh } from './icons/Icons'
import { useAppContext } from '../context/AppContext'

export default function AppHeader() {
  const { cookieInfo, cookieError, autoFetchCookie, preciseRun, broadRun } = useAppContext()
  const anyRunInflight =
    preciseRun.status === 'running' || preciseRun.status === 'starting' ||
    broadRun.status === 'running' || broadRun.status === 'starting'

  // Spec §5.1 — selected = white bg + rounded + primary text + medium
  const tabClass = ({ isActive }) =>
    `inline-flex items-center gap-1 px-3 py-[5px] rounded-lg text-[12px] transition-colors ${
      isActive
        ? 'bg-white text-text-primary font-medium border border-border-hair'
        : 'text-text-secondary hover:text-text-primary'
    }`

  return (
    <header
      className="bg-page-bg flex items-center justify-between shrink-0"
      style={{ padding: '14px 16px', borderBottom: '0.5px solid rgba(0,0,0,0.08)' }}
    >
      <div className="flex items-baseline gap-2.5">
        <span className="text-[15px] font-medium text-text-primary leading-none">搜尋巡檢平台</span>
        <span className="text-[10px] font-medium text-text-tertiary uppercase leading-none" style={{ letterSpacing: '0.14em' }}>
          Search Audit
        </span>
      </div>

      <div className="flex items-center gap-[14px]">
        <nav className="flex items-center gap-1">
          <NavLink to="/" end className={tabClass}>巡檢</NavLink>
          <NavLink to="/batch" className={tabClass}>
            批次
            {anyRunInflight && (
              <span className="inline-block w-1.5 h-1.5 rounded-full bg-status-blue animate-pulse" />
            )}
          </NavLink>
          {/* 回放器是獨立技術棧 (Streamlit,repo 內 replay_inspector/) — 只拆入口。
              預設同站子路徑 /explore_platform/replay/ (dev 由 Vite proxy、prod 由
              nginx 反代到 Streamlit);VITE_REPLAY_URL 可覆寫 */}
          <a
            href={import.meta.env.VITE_REPLAY_URL || '/explore_platform/replay/'}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 px-3 py-[5px] rounded-lg text-[12px] transition-colors text-text-secondary hover:text-text-primary"
            title="個性化搜尋事件回放器 (另開新分頁)"
          >
            回放 <span className="text-[9px] opacity-60">↗</span>
          </a>
        </nav>

        <div className="flex items-center gap-1.5">
          {cookieError && (
            <span className="text-[10px] text-text-red-dk">{cookieError}</span>
          )}
          <span
            className="inline-block w-1.5 h-1.5 rounded-full"
            style={{ background: cookieInfo ? '#639922' : '#E24B4A' }}
          />
          <span className="text-[11px] text-text-secondary">
            {cookieInfo ? '連線正常' : '連線斷開'}
          </span>
          <button
            onClick={autoFetchCookie}
            className="text-text-tertiary hover:text-text-primary transition-colors"
            title="重抓 cookie"
          >
            <IconRefresh />
          </button>
        </div>
      </div>
    </header>
  )
}
