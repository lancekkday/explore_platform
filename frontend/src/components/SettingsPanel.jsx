import { useState, useEffect, useRef } from 'react'
import { IconRefresh } from './icons/Icons'
import {
  uploadBaseline, fetchBaselineVersions, rollbackBaseline, archiveBaselineVersion, fetchBaselineKeywords,
  refreshBaselineFromBQ, fetchBaselineSourceStatus, updateBaselineCronSchedule,
} from '../api'

// v3 search API channel 欄位只認這三種
const CHANNEL_OPTIONS = ['ios', 'android', 'web']

export default function SettingsPanel({
  visible, onClose,
  versionA, setVersionA,
  versionB, setVersionB,
  enableAB, setEnableAB,
  searchApi, setSearchApi,
  aiEnabled, setAiEnabled,
  channel, setChannel,
  cookieInfo, onRefreshCookie,
  onOpenKeywordEditor,
  onOpenScheduleModal,
  schedules,
}) {
  const [versions, setVersions] = useState([])
  const [baselineTotal, setBaselineTotal] = useState(null)
  const [uploading, setUploading] = useState(false)
  const [uploadMsg, setUploadMsg] = useState(null)
  const [pendingCsvFile, setPendingCsvFile] = useState(null)
  const fileRef = useRef()

  // BQ cron state
  const [sourceStatus, setSourceStatus] = useState(null)
  const [cronHour, setCronHour] = useState(7)
  const [cronMinute, setCronMinute] = useState(0)
  const [cronEnabled, setCronEnabled] = useState(true)
  const [bqFetching, setBqFetching] = useState(false)

  const reloadSourceStatus = () =>
    fetchBaselineSourceStatus().then(r => {
      if (!r?.success) return
      setSourceStatus(r)
      if (r.cron) {
        setCronHour(r.cron.hour)
        setCronMinute(r.cron.minute)
        setCronEnabled(r.cron.enabled)
      }
    }).catch(() => {})

  useEffect(() => {
    if (!visible) return
    fetchBaselineVersions().then(r => { if (r?.versions) setVersions(r.versions) }).catch(() => {})
    fetchBaselineKeywords().then(r => { if (r?.total != null) setBaselineTotal(r.total) }).catch(() => {})
    reloadSourceStatus()
  }, [visible])

  const handleBqRefresh = async () => {
    setBqFetching(true)
    setUploadMsg(null)
    try {
      const res = await refreshBaselineFromBQ()
      const lr = res.last_run
      if (res.success) {
        setUploadMsg({
          ok: true,
          text: `BQ fetch 成功！精準詞 ${lr.precise_rows} / 泛詞 ${lr.broad_rows}` +
            (lr.warnings?.length ? `（warning: ${lr.warnings.join('; ')}）` : ''),
        })
      } else {
        setUploadMsg({ ok: false, text: `BQ fetch 失敗：${lr?.error || '未知錯誤'}` })
      }
      fetchBaselineVersions().then(r => { if (r?.versions) setVersions(r.versions) }).catch(() => {})
      fetchBaselineKeywords().then(r => { if (r?.total != null) setBaselineTotal(r.total) }).catch(() => {})
      reloadSourceStatus()
    } catch (e) {
      setUploadMsg({ ok: false, text: `BQ fetch 失敗：${e.message || '未知錯誤'}` })
    }
    setBqFetching(false)
  }

  const handleCronUpdate = async () => {
    try {
      const res = await updateBaselineCronSchedule(cronHour, cronMinute, cronEnabled)
      if (res.success) {
        setUploadMsg({ ok: true, text: `Cron 已更新：每天 ${String(cronHour).padStart(2,'0')}:${String(cronMinute).padStart(2,'0')}` })
        reloadSourceStatus()
      } else {
        setUploadMsg({ ok: false, text: `Cron 更新失敗：${res.detail || ''}` })
      }
    } catch (e) {
      setUploadMsg({ ok: false, text: `Cron 更新失敗：${e.message || ''}` })
    }
  }

  const doUpload = async (file, type) => {
    setUploading(true)
    setUploadMsg(null)
    try {
      const res = await uploadBaseline(file, type)
      if (res.success) {
        const v = res.version
        setUploadMsg({ ok: true, text: `上傳成功！精準詞 ${v.precise_keywords} 個、泛詞 ${v.broad_keywords} 個` })
        fetchBaselineVersions().then(r => { if (r?.versions) setVersions(r.versions) }).catch(() => {})
        fetchBaselineKeywords().then(r => { if (r?.total != null) setBaselineTotal(r.total) }).catch(() => {})
      } else {
        setUploadMsg({ ok: false, text: res.detail || '上傳失敗' })
      }
    } catch (err) {
      setUploadMsg({ ok: false, text: '上傳失敗：' + (err.message || '未知錯誤') })
    }
    setUploading(false)
    if (fileRef.current) fileRef.current.value = ''
  }

  const handleUpload = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    if (!file.name.toLowerCase().endsWith('.csv')) {
      setUploadMsg({ ok: false, text: '只支援 .csv 檔案（HTML 上傳已停用）' })
      if (fileRef.current) fileRef.current.value = ''
      return
    }
    setPendingCsvFile(file)
  }

  const handleCsvTypeSelect = (type) => {
    if (pendingCsvFile) {
      doUpload(pendingCsvFile, type)
      setPendingCsvFile(null)
    }
  }

  const handleSwitchVersion = async (ts) => {
    const res = await rollbackBaseline(ts)
    if (res.success) {
      setVersions(prev => prev.map(v => ({ ...v, is_active: v.timestamp === ts })))
      fetchBaselineKeywords().then(r => { if (r?.total != null) setBaselineTotal(r.total) }).catch(() => {})
      setUploadMsg({ ok: true, text: `已切換至版本 ${ts}` })
    }
  }

  const handleArchiveVersion = async (ts) => {
    const res = await archiveBaselineVersion(ts)
    if (res.success) {
      setVersions(prev => prev.filter(v => v.timestamp !== ts))
      setUploadMsg({ ok: true, text: `已刪除版本 ${ts}` })
    }
  }

  if (!visible) return null

  const activeVersion = versions.find(v => v.is_active)

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
                  {[
                    { value: 'ajax', label: 'Web_AJAX' },
                    { value: 'v3', label: 'Search_V3' },
                  ].map(({ value, label }) => (
                    <button
                      key={value}
                      onClick={() => setSearchApi(value)}
                      className={`px-3 py-1 rounded-lg border text-[10px] font-black transition-all ${
                        searchApi === value
                          ? 'bg-indigo-600 text-white border-indigo-700'
                          : 'bg-white text-slate-500 border-slate-200 hover:border-slate-400'
                      }`}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </div>

              <div className="flex items-center justify-between">
                <label className="text-[12px] font-bold text-slate-700">Channel</label>
                <select
                  value={channel}
                  onChange={e => setChannel(e.target.value)}
                  title="API channel/source 欄位 (例:ios / android / web)"
                  className="px-2 py-1 text-[12px] font-black border-2 border-slate-200 rounded-lg bg-white text-slate-800 outline-none focus:border-indigo-500"
                >
                  {CHANNEL_OPTIONS.map(opt => <option key={opt} value={opt}>{opt}</option>)}
                  {!CHANNEL_OPTIONS.includes(channel) && <option value={channel}>{channel}</option>}
                </select>
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

          {/* Baseline Management */}
          <section>
            <h3 className="text-[10px] font-black text-slate-400 uppercase tracking-[3px] mb-3">BASELINE 管理</h3>
            <div className="space-y-3">
              {/* Current status */}
              <div className="px-3 py-2.5 bg-slate-50 rounded-xl border border-slate-100">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-bold text-slate-600">目前 Baseline</span>
                  <span className="text-[11px] font-black text-indigo-600">{baselineTotal ?? '—'} 個關鍵字</span>
                </div>
                {activeVersion && (
                  <div className="text-[9px] text-slate-400 mt-1">
                    版本 {activeVersion.timestamp} | 來源: {activeVersion.source || '—'}
                  </div>
                )}
              </div>

              {/* BQ Auto Fetch */}
              <div className="px-3 py-2.5 bg-indigo-50/60 rounded-xl border border-indigo-100 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-black text-indigo-700 uppercase tracking-wider">BQ 自動 fetch</span>
                  <button
                    onClick={() => setCronEnabled(!cronEnabled)}
                    className={`relative inline-flex w-9 h-5 rounded-full transition-colors duration-200 shrink-0 ${cronEnabled ? 'bg-indigo-600' : 'bg-slate-300'}`}
                  >
                    <span className={`absolute top-[3px] w-[14px] h-[14px] bg-white rounded-full shadow-md transition-all duration-200 ${cronEnabled ? 'left-[19px]' : 'left-[3px]'}`} />
                  </button>
                </div>

                {sourceStatus?.last_run && (
                  <div className="text-[9px] text-slate-500 leading-relaxed">
                    上次 fetch：<span className="font-bold text-slate-700">{sourceStatus.last_run.ts}</span>
                    （{sourceStatus.last_run.trigger}）
                    {sourceStatus.last_run.success
                      ? <span className="ml-1 text-emerald-600">✓ 成功</span>
                      : <span className="ml-1 text-red-600">✗ 失敗</span>}
                    {sourceStatus.last_run.warnings?.length > 0 && (
                      <div className="text-amber-700 mt-0.5">⚠ {sourceStatus.last_run.warnings.join('; ')}</div>
                    )}
                    {sourceStatus.last_run.error && (
                      <div className="text-red-600 mt-0.5">Error: {sourceStatus.last_run.error}</div>
                    )}
                  </div>
                )}

                <div className="flex items-center gap-2">
                  <label className="text-[10px] font-bold text-slate-600">每日 cron</label>
                  <input
                    type="number" min="0" max="23"
                    value={cronHour}
                    onChange={e => setCronHour(Math.max(0, Math.min(23, parseInt(e.target.value) || 0)))}
                    className="w-12 px-1 py-0.5 text-[11px] font-black text-center border border-slate-200 rounded outline-none focus:border-indigo-500"
                  />
                  <span className="text-[11px] font-black text-slate-500">:</span>
                  <input
                    type="number" min="0" max="59"
                    value={cronMinute}
                    onChange={e => setCronMinute(Math.max(0, Math.min(59, parseInt(e.target.value) || 0)))}
                    className="w-12 px-1 py-0.5 text-[11px] font-black text-center border border-slate-200 rounded outline-none focus:border-indigo-500"
                  />
                  <span className="text-[9px] text-slate-500">TW</span>
                  <button
                    onClick={handleCronUpdate}
                    className="ml-auto px-2 py-1 bg-indigo-600 text-white rounded text-[10px] font-black hover:bg-indigo-700"
                  >
                    儲存
                  </button>
                </div>

                <button
                  onClick={handleBqRefresh}
                  disabled={bqFetching}
                  className="w-full px-3 py-1.5 bg-white border border-indigo-300 rounded-lg text-[10px] font-black text-indigo-700 hover:bg-indigo-50 transition-all disabled:opacity-50"
                >
                  {bqFetching ? '抽取中...' : '⚡ 立即從 BQ 抽取'}
                </button>
              </div>

              {/* Manual CSV upload (Plan B) */}
              <div>
                <input ref={fileRef} type="file" accept=".csv" onChange={handleUpload} className="hidden" />
                <button
                  onClick={() => fileRef.current?.click()}
                  disabled={uploading}
                  className="w-full px-4 py-2.5 border-2 border-dashed border-slate-300 rounded-xl text-[11px] font-black text-slate-600 hover:border-indigo-400 hover:text-indigo-600 transition-all disabled:opacity-50"
                >
                  {uploading ? '上傳中...' : '上傳 CSV（手動匯出備援）'}
                </button>
                {pendingCsvFile && (
                  <div className="mt-2 px-3 py-2.5 bg-amber-50 border border-amber-200 rounded-lg">
                    <div className="text-[10px] font-bold text-amber-700 mb-2">
                      請選擇 CSV 類型：{pendingCsvFile.name}
                    </div>
                    <div className="flex gap-2">
                      <button onClick={() => handleCsvTypeSelect('precise')}
                        className="flex-1 px-3 py-1.5 bg-indigo-600 text-white rounded-lg text-[10px] font-black hover:bg-indigo-700 transition-all">
                        精準詞 (Precise)
                      </button>
                      <button onClick={() => handleCsvTypeSelect('broad')}
                        className="flex-1 px-3 py-1.5 bg-teal-600 text-white rounded-lg text-[10px] font-black hover:bg-teal-700 transition-all">
                        泛詞 (Broad)
                      </button>
                      <button onClick={() => { setPendingCsvFile(null); if (fileRef.current) fileRef.current.value = '' }}
                        className="px-3 py-1.5 border border-slate-300 text-slate-500 rounded-lg text-[10px] font-black hover:border-slate-400 transition-all">
                        取消
                      </button>
                    </div>
                  </div>
                )}
                {uploadMsg && (
                  <div className={`mt-2 px-3 py-2 rounded-lg text-[10px] font-bold ${uploadMsg.ok ? 'bg-emerald-50 text-emerald-700' : 'bg-red-50 text-red-600'}`}>
                    {uploadMsg.text}
                  </div>
                )}
              </div>

              {/* Version selector */}
              {versions.length > 0 && (
                <div>
                  <label className="text-[10px] font-bold text-slate-500 mb-1 block">歷史版本（點擊切換）</label>
                  <div className="space-y-1.5 max-h-40 overflow-y-auto">
                    {versions.map(v => (
                      <div key={v.timestamp} className="flex items-center gap-1.5">
                        <button
                          onClick={() => !v.is_active && handleSwitchVersion(v.timestamp)}
                          className={`flex-1 px-3 py-2 rounded-lg border text-left transition-all ${
                            v.is_active
                              ? 'border-indigo-400 bg-indigo-50 text-indigo-800'
                              : 'border-slate-150 bg-white text-slate-600 hover:border-slate-300'
                          }`}
                        >
                          <div className="flex items-center justify-between">
                            <span className="text-[10px] font-black">{v.timestamp}</span>
                            <span className="text-[9px] font-bold">
                              {v.is_active && <span className="text-indigo-600 mr-1">使用中</span>}
                              精準 {v.precise_keywords} / 泛 {v.broad_keywords}
                            </span>
                          </div>
                          {v.source && <div className="text-[9px] text-slate-400 mt-0.5">{v.source}</div>}
                        </button>
                        {!v.is_active && (
                          <button
                            onClick={() => handleArchiveVersion(v.timestamp)}
                            className="px-2 py-2 rounded-lg border border-slate-200 text-slate-400 hover:text-red-500 hover:border-red-300 transition-all text-[10px]"
                            title="刪除此版本"
                          >
                            ✕
                          </button>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}
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

        </div>
      </div>
    </div>
  )
}
