import { useState } from 'react'
import ABCheckRunPanel from '../components/ABCheckRunPanel'
import ABCheckHistoryTable from '../components/ABCheckHistoryTable'

const TABS = [
  { key: 'precise', label: '精準詞' },
  { key: 'broad',   label: '泛詞' },
  { key: 'history', label: '歷史紀錄' },
]

function TabButton({ active, onClick, children }) {
  return (
    <button
      onClick={onClick}
      className={`relative px-4 py-2 text-[11px] font-semibold tracking-wide transition-colors ${
        active
          ? 'text-slate-900 bg-white'
          : 'text-slate-500 hover:text-slate-700 hover:bg-slate-100'
      }`}
    >
      {children}
      {active && <span className="absolute inset-x-0 bottom-0 h-0.5 bg-slate-900" />}
    </button>
  )
}

export default function BatchPage() {
  const [tab, setTab] = useState('precise')

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* Tab bar */}
      <div className="bg-slate-50 border-b border-slate-200 px-4 flex items-end shrink-0">
        <span className="text-[12px] font-bold text-slate-800 uppercase tracking-[3px] mr-4 mb-2">
          批次 baseline 巡檢
        </span>
        <div className="flex">
          {TABS.map(t => (
            <TabButton key={t.key} active={tab === t.key} onClick={() => setTab(t.key)}>
              {t.label}
            </TabButton>
          ))}
        </div>
      </div>

      {/* Active panel */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {tab === 'precise' && <ABCheckRunPanel type="precise" />}
        {tab === 'broad'   && <ABCheckRunPanel type="broad" />}
        {tab === 'history' && <ABCheckHistoryTable />}
      </div>
    </div>
  )
}
