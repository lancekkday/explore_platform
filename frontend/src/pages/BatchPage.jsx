import { useState } from 'react'
import ABCheckRunPanel from '../components/ABCheckRunPanel'
import ABCheckHistoryTable from '../components/ABCheckHistoryTable'

const TABS = [
  { key: 'precise', label: '精準詞' },
  { key: 'broad',   label: '泛詞' },
  { key: 'history', label: '歷史紀錄' },
]

// Spec §5.2 — sub-tab selected = medium + 2px bottom border; unselected = regular secondary
function SubTab({ active, onClick, children }) {
  return (
    <button
      onClick={onClick}
      className={`relative pb-[2px] text-[12px] transition-colors ${
        active
          ? 'text-text-primary font-medium'
          : 'text-text-secondary hover:text-text-primary'
      }`}
    >
      {children}
      {active && <span className="absolute inset-x-0 -bottom-px h-[2px] bg-text-primary" />}
    </button>
  )
}

export default function BatchPage() {
  const [tab, setTab] = useState('precise')

  return (
    <div className="flex-1 flex flex-col overflow-hidden bg-page-bg p-3">
      {/* Main Card — spec §4 圓角 12px + 0.5px 邊框 + 白底 */}
      <div className="flex-1 flex flex-col bg-white rounded-xl overflow-hidden" style={{ border: '0.5px solid rgba(0,0,0,0.08)' }}>
        {/* §5.2 Section Header */}
        <div
          className="flex items-center justify-between shrink-0"
          style={{ padding: '12px 18px', borderBottom: '0.5px solid rgba(0,0,0,0.08)' }}
        >
          <span className="text-[13px] font-medium text-text-primary">批次 Baseline 巡檢</span>
          <nav className="flex items-center gap-[18px]">
            {TABS.map(t => (
              <SubTab key={t.key} active={tab === t.key} onClick={() => setTab(t.key)}>
                {t.label}
              </SubTab>
            ))}
          </nav>
        </div>

        {/* Active panel */}
        <div className="flex-1 flex flex-col overflow-hidden">
          {tab === 'precise' && <ABCheckRunPanel type="precise" />}
          {tab === 'broad'   && <ABCheckRunPanel type="broad" />}
          {tab === 'history' && <ABCheckHistoryTable />}
        </div>
      </div>
    </div>
  )
}
