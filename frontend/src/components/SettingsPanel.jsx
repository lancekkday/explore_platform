import { IconRefresh } from './icons/Icons'

export default function SettingsPanel({
  visible, onClose,
  versionA, setVersionA,
  versionB, setVersionB,
  enableAB, setEnableAB,
  searchApi, setSearchApi,
  aiEnabled, setAiEnabled,
  cookieInfo, onRefreshCookie,
  onOpenKeywordEditor,
  onOpenScheduleModal,
  schedules,
}) {
  if (!visible) return null

  return (
    <div className="fixed inset-0 z-[500] flex justify-end" onClick={onClose}>
      <div className="absolute inset-0 bg-black/30 backdrop-blur-[2px]" />
      <div
        className="relative w-[400px] max-w-full h-full bg-white shadow-2xl overflow-y-auto"
        onClick={e => e.stopPropagation()}
      >
        <div className="px-6 py-4 bg-[#0F172A] text-white flex items-center justify-between">
          <h2 className="text-[13px] font-black tracking-[3px] uppercase">平台設定</h2>
          <button onClick={onClose} className="text-white/60 hover:text-white text-[18px] font-bold">✕</button>
        </div>

        <div className="p-6 space-y-6">
          {/* Search Settings */}
          <section>
            <h3 className="text-[10px] font-black text-slate-400 uppercase tracking-[3px] mb-3">搜尋設定</h3>
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <label className="text-[12px] font-bold text-slate-700">Search API</label>
                <div className="flex gap-1">
                  {['ajax', 'v3'].map(v => (
                    <button
                      key={v}
                      onClick={() => setSearchApi(v)}
                      className={`px-3 py-1 rounded-lg border text-[10px] font-black transition-all ${
                        searchApi === v
                          ? 'bg-indigo-600 text-white border-indigo-700'
                          : 'bg-white text-slate-500 border-slate-200 hover:border-slate-400'
                      }`}
                    >
                      {v.toUpperCase()}
                    </button>
                  ))}
                </div>
              </div>

              <div className="flex items-center justify-between">
                <label className="text-[12px] font-bold text-slate-700">Version A 預設值</label>
                <input
                  type="number"
                  value={versionA}
                  onChange={e => setVersionA(parseInt(e.target.value) || 0)}
                  className="w-16 px-2 py-1 text-[12px] font-black text-center border-2 border-slate-200 rounded-lg focus:border-indigo-500 outline-none"
                />
              </div>

              <div className="flex items-center justify-between">
                <label className="text-[12px] font-bold text-slate-700">Version B 預設值</label>
                <input
                  type="number"
                  value={versionB ?? 3}
                  onChange={e => setVersionB(parseInt(e.target.value) || 0)}
                  className="w-16 px-2 py-1 text-[12px] font-black text-center border-2 border-slate-200 rounded-lg focus:border-indigo-500 outline-none"
                />
              </div>

              <div className="flex items-center justify-between">
                <label className="text-[12px] font-bold text-slate-700">A/B 對比模式</label>
                <button
                  onClick={() => setEnableAB(!enableAB)}
                  className={`relative inline-flex w-9 h-5 rounded-full transition-colors duration-200 shrink-0 ${enableAB ? 'bg-indigo-600' : 'bg-slate-200'}`}
                >
                  <span className={`absolute top-[3px] w-[14px] h-[14px] bg-white rounded-full shadow-md transition-all duration-200 ${enableAB ? 'left-[19px]' : 'left-[3px]'}`} />
                </button>
              </div>

              <div className="flex items-center justify-between">
                <label className="text-[12px] font-bold text-slate-700">AI 解析</label>
                <button
                  onClick={() => setAiEnabled(!aiEnabled)}
                  className={`relative inline-flex w-9 h-5 rounded-full transition-colors duration-200 shrink-0 ${aiEnabled ? 'bg-indigo-600' : 'bg-slate-200'}`}
                >
                  <span className={`absolute top-[3px] w-[14px] h-[14px] bg-white rounded-full shadow-md transition-all duration-200 ${aiEnabled ? 'left-[19px]' : 'left-[3px]'}`} />
                </button>
              </div>
            </div>
          </section>

          {/* Connection Settings */}
          <section>
            <h3 className="text-[10px] font-black text-slate-400 uppercase tracking-[3px] mb-3">連線設定</h3>
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <div>
                  <label className="text-[12px] font-bold text-slate-700">連線狀態</label>
                  <div className="flex items-center gap-1.5 mt-1">
                    <div className={`w-2 h-2 rounded-full ${cookieInfo ? 'bg-emerald-500' : 'bg-red-500'}`} />
                    <span className="text-[10px] font-bold text-slate-500">{cookieInfo ? '已連線 (Stage)' : '未連線'}</span>
                  </div>
                </div>
                <button
                  onClick={onRefreshCookie}
                  className="px-3 py-1.5 border border-slate-200 rounded-lg text-[10px] font-black text-slate-600 hover:border-slate-400 transition-all flex items-center gap-1.5"
                >
                  <IconRefresh /> 重新連線
                </button>
              </div>
            </div>
          </section>

          {/* Batch Settings */}
          <section>
            <h3 className="text-[10px] font-black text-slate-400 uppercase tracking-[3px] mb-3">批次設定</h3>
            <div className="space-y-2">
              <button
                onClick={() => { onClose(); onOpenKeywordEditor() }}
                className="w-full px-4 py-2.5 border border-slate-200 rounded-xl text-[11px] font-black text-slate-700 hover:border-slate-400 transition-all text-left"
              >
                任務配置（關鍵字管理）
              </button>
              <button
                onClick={() => { onClose(); onOpenScheduleModal() }}
                className={`w-full px-4 py-2.5 border rounded-xl text-[11px] font-black transition-all text-left ${
                  schedules?.some(s => s.enabled)
                    ? 'border-indigo-300 bg-indigo-50 text-indigo-700'
                    : 'border-slate-200 text-slate-700 hover:border-slate-400'
                }`}
              >
                排程設定 {schedules?.filter(s => s.enabled).length > 0 && `(${schedules.filter(s => s.enabled).length} 個啟用中)`}
              </button>
            </div>
          </section>
        </div>
      </div>
    </div>
  )
}
