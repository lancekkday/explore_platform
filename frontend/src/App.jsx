import { useState, useEffect, useRef } from 'react'
import { normalizeKw } from './utils/safeString'
import {
  IconRefresh, IconSearch, IconBot, IconGlobe,
  IconPlay, IconSquare, IconArchive, IconHistory,
} from './components/icons/Icons'
import CompactMetricBar from './components/ui/CompactMetricBar'
import ResultList from './components/ResultList'
import CalibrationModal from './components/CalibrationModal'
import KeywordEditorModal from './components/KeywordEditorModal'
import {
  fetchCompare, fetchGuestCookie, saveFeedback,
  fetchKeywords, updateKeywords,
  startBatch as apiBatchStart, stopBatch as apiBatchStop,
  fetchBatchStatus, fetchBatchResults, fetchBatchHistory,
  fetchBatchHistoryDetail, fetchSingleHistory, fetchSingleHistoryDetail,
  fetchSchedules, addSchedule, updateSchedule, deleteSchedule,
} from './api'
import ScheduleModal from './components/ScheduleModal'

export default function App() {
  const [tab, setTab] = useState('discovery')
  const [keyword, setKeyword] = useState('esim')
  const [cookie, setCookie] = useState('')
  const [cookieInfo, setCookieInfo] = useState(null)
  const [singleAiMode, setSingleAiMode] = useState(false)
  const [doubtOnly, setDoubtOnly] = useState(false)

  const [loading, setLoading] = useState(false)
  const [stageData, setStageData] = useState(null)
  const [error, setError] = useState('')

  const [edittingProduct, setEdittingProduct] = useState(null)
  const [calibTier, setCalibTier] = useState(1)
  const [calibComment, setCalibComment] = useState('')

  const [auditKeywords, setAuditKeywords] = useState([])
  const [batchStatus, setBatchStatus] = useState({ is_running: false, progress: 0, current_keyword: null })
  const [batchResults, setBatchResults] = useState({})
  const [batchHistory, setBatchHistory] = useState([])
  const [kwEditorVisible, setKwEditorVisible] = useState(false)
  const [kwInputText, setKwInputText] = useState('')

  const [singleHistory, setSingleHistory] = useState([])
  const [showSingleHistory, setShowSingleHistory] = useState(false)

  const [schedules, setSchedules] = useState([])
  const [scheduleModalVisible, setScheduleModalVisible] = useState(false)
  const [editingSchedule, setEditingSchedule] = useState(null)

  const hasAutoSearched = useRef(false);

  // ── Functions declared before useEffect hooks that reference them ──────────

  async function fetchAuditData() {
    try {
      const [kwRes, statRes, resRes, histRes, schedRes] = await Promise.all([
        fetchKeywords(),
        fetchBatchStatus(),
        fetchBatchResults(),
        fetchBatchHistory(),
        fetchSchedules(),
      ]);
      if (kwRes?.keywords) setAuditKeywords(kwRes.keywords);
      if (statRes) setBatchStatus(statRes);
      if (resRes?.results) setBatchResults(resRes.results);
      if (histRes?.history) setBatchHistory(histRes.history);
      if (Array.isArray(schedRes)) setSchedules(schedRes);
    } catch { /* silent: polling failure is non-critical */ }
  }

  async function autoFetchCookie() {
    try {
      const res = await fetchGuestCookie('stage');
      if (res && res.cookie) { setCookie(res.cookie); setCookieInfo(res); return res; }
      return null;
    } catch {
      setError('憑證對接異常');
      return null;
    }
  }

  async function handleSearch(kw = keyword) {
    if (!kw) return;
    setLoading(true); setError(''); setTab('discovery');
    try {
      const res = await fetchCompare(kw, cookie, 300, singleAiMode);
      if (res && res.stage) {
        setStageData(res.stage);
      } else {
        setError(res?.detail || '返回數據異常');
      }
    } catch {
      setError('伺服器連線異常');
    }
    setLoading(false);
  }

  // ── Effects ────────────────────────────────────────────────────────────────

  useEffect(() => {
    autoFetchCookie();
    fetchAuditData();
    const timer = setInterval(() => {
      if (batchStatus?.is_running) fetchAuditData();
    }, 3000);
    return () => clearInterval(timer);
  }, [batchStatus?.is_running])

  useEffect(() => { fetchAuditData(); }, [tab])

  const findResult = (kw) => {
    if (!kw || !batchResults) return null;
    return batchResults[normalizeKw(kw)] || null;
  }

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const kw = params.get('keyword');
    if (kw && !hasAutoSearched.current) {
      const cached = findResult(kw);
      if (cached && cached.stage?.results) {
        setKeyword(kw); setTab('discovery');
        setStageData(cached.stage);
        hasAutoSearched.current = true;
      } else if (cookie) {
        setKeyword(kw); handleSearch(kw);
        hasAutoSearched.current = true;
      }
    }
  }, [cookie, batchResults]);

  // ── Handlers ───────────────────────────────────────────────────────────────

  const handleCalibrate = (p) => {
    if (!p) return;
    setEdittingProduct(p);
    setCalibTier(p.user_tier || p.tier || 1);
    setCalibComment(p.user_comment || p.comment || '');
  }

  const submitCalibration = async () => {
    if (!edittingProduct) return;
    try {
      const res = await saveFeedback(keyword, edittingProduct.id, parseInt(calibTier), calibComment);
      if (res.success) { setEdittingProduct(null); handleSearch(); }
    } catch { /* silent */ }
  }

  const handleStartBatch = async () => {
    await apiBatchStart(cookie)
    fetchAuditData()
  }
  const handleStopBatch = async () => {
    await apiBatchStop()
    fetchAuditData()
  }

  const saveKeywords = async () => {
    const kws = kwInputText.split(/\n|,/).map(s => s.trim()).filter(s => s);
    await updateKeywords(kws);
    setKwEditorVisible(false); fetchAuditData();
  }

  const handleToggleSingleHistory = async () => {
    if (!showSingleHistory) {
      try {
        const res = await fetchSingleHistory();
        if (res?.history) setSingleHistory(res.history);
      } catch { /* silent */ }
    }
    setShowSingleHistory(v => !v);
  }

  const handleRestoreSingle = async (id) => {
    try {
      const res = await fetchSingleHistoryDetail(id);
      if (res?.results) {
        const d = res.results;
        setKeyword(d.keyword);
        setStageData(d.stage);
        setProdData(d.production);
        setShowSingleHistory(false);
      }
    } catch { alert("載入失敗"); }
  }

  const handleSaveSchedule = async (config) => {
    try {
      console.log('[Schedule] saving config:', JSON.stringify(config))
      let res
      if (config.id) {
        res = await updateSchedule(config.id, config);
      } else {
        res = await addSchedule(config);
      }
      console.log('[Schedule] save response:', JSON.stringify(res))
      setScheduleModalVisible(false);
      setEditingSchedule(null);
      fetchAuditData();
    } catch (e) {
      console.error('[Schedule] save failed:', e)
      alert(`儲存失敗: ${e?.message || e}`)
    }
  }

  const handleToggleSchedule = async (s) => {
    try {
      await updateSchedule(s.id, { enabled: s.enabled ? 0 : 1 });
      fetchAuditData();
    } catch { /* silent */ }
  }

  const handleDeleteSchedule = async (id) => {
    try {
      await deleteSchedule(id);
      fetchAuditData();
    } catch { /* silent */ }
  }

  const handleRestoreHistory = async (id) => {
    if (!window.confirm(`確定要載入存檔 #${String(id).padStart(3,'0')} 嗎？目前的巡檢結果將被覆蓋。`)) return;
    try {
      const res = await fetchBatchHistoryDetail(id);
      if (res?.results) setBatchResults(res.results);
    } catch { /* silent */ }
  }

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div className="min-h-screen bg-[#F8FAFC] flex flex-col h-screen overflow-hidden text-[13px] select-none text-slate-900 antialiased font-sans">
      <header className="bg-white border-b border-slate-200 px-8 py-2.5 flex items-center justify-between shrink-0 z-[100] shadow-sm">
        <div className="flex items-center gap-10">
          <div className="flex flex-col text-slate-950">
            <span className="text-[13px] font-black tracking-[4px] uppercase leading-none">意圖巡檢中心</span>
            <span className="text-[8px] font-black text-indigo-600 uppercase tracking-[3px] mt-1 font-mono">Operations Hub</span>
          </div>
          <nav className="flex bg-slate-100 p-0.5 rounded-lg border border-slate-200">
            <button onClick={() => setTab('discovery')} className={`px-5 py-1.5 rounded-md text-[10.5px] font-black transition-all ${tab === 'discovery' ? 'bg-white text-indigo-600 shadow-sm' : 'text-slate-400'}`}>單次巡檢</button>
            <button onClick={() => setTab('audit')} className={`px-5 py-1.5 rounded-md text-[10.5px] font-black transition-all ${tab === 'audit' ? 'bg-white text-indigo-600 shadow-sm' : 'text-slate-400'}`}>批次巡檢</button>
          </nav>
        </div>
        <div className="flex items-center gap-5 text-[10px] font-black">
           {error && <div className="px-3 py-1 bg-red-50 text-red-600 border border-red-100 rounded-lg animate-pulse">{error}</div>}
           <div className="flex items-center gap-3 px-4 py-1.5 bg-slate-50 border border-slate-200 rounded-full">
              <div className={`w-1.5 h-1.5 rounded-full ${cookieInfo ? 'bg-emerald-500 shadow-[0_0_8px_#10B981]' : 'bg-red-500'}`} />
              <span className="text-slate-500 tracking-wider uppercase font-mono">{cookieInfo ? '連線正常' : '連線斷開'}</span>
           </div>
           <button onClick={autoFetchCookie} className="text-slate-300 hover:text-indigo-600 transition-all active:rotate-180 duration-500"><IconRefresh /></button>
        </div>
      </header>

      <main className="flex-1 flex flex-col overflow-hidden bg-[#F8FAFC]">
        {tab === 'discovery' ? (
          <div className="flex-1 flex flex-col min-h-0">
             <div className="px-8 py-2.5 bg-white border-b border-slate-200 flex items-center gap-4 shrink-0 z-20 shadow-sm">
                <div className="flex-1 relative group">
                   <span className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400 group-focus-within:text-indigo-600"><IconSearch /></span>
                   <input type="text" value={keyword} onChange={e => setKeyword(e.target.value)} onKeyDown={e => e.key === 'Enter' && handleSearch()} className="w-full pl-10 pr-[80px] py-2 text-[13px] rounded-xl border-2 border-slate-100 bg-slate-50 focus:bg-white focus:border-indigo-500 outline-none transition-all font-black text-slate-900" placeholder="分析關鍵字..." />
                   <button
                     onClick={handleToggleSingleHistory}
                     className={`absolute right-2 top-1/2 -translate-y-1/2 px-3 py-1 flex items-center gap-1.5 bg-white border rounded-lg transition-all font-black shadow-sm z-30 ${showSingleHistory ? 'border-indigo-600 text-indigo-600' : 'border-slate-200 text-slate-500 hover:border-slate-400 hover:text-slate-800'}`}
                   >
                      <IconHistory size={14} /> <span className="text-[10px] uppercase tracking-wider">歷史</span>
                   </button>

                   {showSingleHistory && (
                     <div className="absolute top-[calc(100%+8px)] left-0 right-0 bg-white border border-slate-200 rounded-2xl shadow-2xl p-4 z-[300] max-h-[400px] overflow-y-auto">
                       <div className="text-[11px] font-black uppercase tracking-widest text-slate-400 mb-3 px-2 flex justify-between items-center">
                          <span>🕒 最近巡檢紀錄</span>
                          <button onClick={() => setShowSingleHistory(false)}>✕</button>
                       </div>
                       {singleHistory && singleHistory.length > 0 ? (
                          <div className="grid grid-cols-1 gap-1">
                             {singleHistory.map(h => (
                                <div key={h.id} onClick={() => handleRestoreSingle(h.id)} className="flex items-center justify-between p-3 rounded-xl hover:bg-slate-50 cursor-pointer border border-transparent hover:border-slate-100 group">
                                   <div className="flex flex-col">
                                      <span className="font-black text-[13px] text-slate-800 tracking-tight">{h.keyword}</span>
                                      <span className="text-[9px] font-bold text-slate-400 uppercase tracking-widest mt-0.5">{new Date(h.timestamp).toLocaleString()}</span>
                                   </div>
                                   <div className="flex items-center gap-4">
                                      <div className="flex flex-col items-end">
                                         <span className="text-[10px] font-black text-indigo-500 uppercase leading-none">nDCG Score</span>
                                         <span className="text-[14px] font-black text-slate-900">{(h.ndcg * 100).toFixed(1)}%</span>
                                      </div>
                                      <div className="w-8 h-8 rounded-full bg-slate-50 flex items-center justify-center text-slate-300 group-hover:text-indigo-600 transition-all">→</div>
                                   </div>
                                </div>
                             ))}
                          </div>
                       ) : (
                          <div className="py-10 text-center text-slate-300 font-black italic tracking-widest uppercase">No Records</div>
                       )}
                     </div>
                   )}
                </div>

                <div className="flex items-center gap-1.5 bg-slate-50 border-2 border-slate-100 rounded-xl px-3 py-1.5">
                   <IconGlobe />
                   <span className="text-[10.5px] font-black text-slate-600 pl-1">🧪 Stage</span>
                </div>

                <div className="flex gap-2 text-[10.5px] font-black">
                   <button onClick={() => setDoubtOnly(!doubtOnly)} className={`px-5 py-2 rounded-xl border-2 transition-all shadow-sm ${doubtOnly ? 'bg-[#0F172A] text-white border-slate-900' : 'bg-white text-slate-600 border-slate-200 hover:border-slate-800'}`}>
                      {doubtOnly ? '顯示完整列表' : '僅顯示待確認'}
                   </button>
                   <button onClick={() => setSingleAiMode(!singleAiMode)} className={`flex items-center gap-2 px-5 py-2 rounded-xl border-2 transition-all ${singleAiMode ? 'bg-[#0F172A] text-white border-slate-900' : 'bg-white text-slate-600 border-slate-200 hover:border-slate-800'}`}>
                      <IconBot /> AI 解析: {singleAiMode ? '啟用' : '關閉'}
                   </button>
                </div>

                <button
                   onClick={() => handleSearch()}
                   disabled={loading || !cookieInfo}
                   title={!cookieInfo ? '尚未取得 Cookie，請等待連線完成後再試' : undefined}
                   className={`px-10 py-2 rounded-xl font-black text-[11px] tracking-[4px] uppercase transition-all shadow-lg ${
                     (loading || !cookieInfo)
                       ? 'bg-slate-200 text-slate-400 cursor-not-allowed border-2 border-slate-300'
                       : 'bg-[#0F172A] text-white hover:bg-black active:scale-95 border-2 border-[#0F172A]'
                   }`}
                >
                   {loading ? 'ANALYZING...' : !cookieInfo ? '等待連線...' : '開始巡檢'}
                </button>
             </div>

             <div className="flex-1 flex gap-4 overflow-hidden p-4 relative">
                {loading && (
                   <div className="absolute inset-0 bg-white/60 backdrop-blur-[1px] z-[40] flex flex-col items-center justify-center gap-3">
                      <div className="w-8 h-8 border-[4px] border-white/10 border-t-indigo-600 rounded-full animate-spin shadow-2xl" />
                      <div className="text-indigo-900 font-black text-[11px] tracking-[6px] animate-pulse uppercase">Syncing</div>
                   </div>
                )}
                <div className="flex-1 flex overflow-hidden w-full">
                   <div className="flex-1 min-w-0 flex flex-col min-h-0 gap-4">
                      <CompactMetricBar data={stageData} env="STAGE 測試" envCode="STG-01" color="#10B981" />
                      <ResultList items={stageData?.results} title="STAGE 巡檢清單" total={stageData?.total || 0} color="#10B981" onCalibrate={handleCalibrate} doubtOnly={doubtOnly} keyword={keyword} />
                   </div>
                </div>
             </div>
          </div>
        ) : (
          <div className="flex-1 flex flex-col min-h-0 bg-slate-50 overflow-hidden">
             <div className="px-8 py-2.5 bg-white border-b border-slate-200 shadow-sm flex items-center gap-4 shrink-0 z-20">
                <h2 className="text-[14px] font-black text-slate-900 tracking-tight uppercase leading-none shrink-0">批次指令中心</h2>

                <div className="flex items-center gap-1.5 bg-slate-50 border-2 border-slate-100 rounded-xl px-3 py-1.5 shrink-0">
                   <IconGlobe />
                   <span className="text-[10.5px] font-black text-slate-600 pl-1">🧪 Stage</span>
                </div>

                <div className="flex-1 max-w-xs">
                   <div className="flex justify-between items-end mb-1"><span className="text-[8px] font-black text-slate-400 font-mono uppercase">Progress</span><span className="text-[11px] font-black text-indigo-700 font-mono italic">{batchStatus.progress}%</span></div>
                   <div className="w-full h-1 bg-slate-100 rounded-full overflow-hidden border border-slate-200 shadow-inner"><div className="h-full bg-indigo-600 transition-all duration-700" style={{ width: `${batchStatus.progress}%` }} /></div>
                </div>

                <div className="flex gap-2 shrink-0">
                   <button onClick={() => { setKwInputText(auditKeywords.map(k => k.keyword).join(', ')); setKwEditorVisible(true); }} className="px-6 py-2 border border-slate-200 bg-white text-slate-500 rounded-xl text-[10.5px] font-black hover:border-slate-800 transition-all shadow-sm">任務配置</button>
                   <button onClick={() => { setEditingSchedule(null); setScheduleModalVisible(true); }} className={`px-6 py-2 border rounded-xl text-[10.5px] font-black transition-all shadow-sm ${schedules.some(s => s.enabled) ? 'border-indigo-300 bg-indigo-50 text-indigo-700 hover:border-indigo-500' : 'border-slate-200 bg-white text-slate-500 hover:border-slate-800'}`}>排程設定</button>
                   {batchStatus.is_running ? (
                      <button onClick={handleStopBatch} className="px-10 py-2 bg-rose-500 text-white rounded-xl text-[11px] font-black shadow-lg flex items-center gap-2"><IconSquare /> 終止</button>
                   ) : (
                      <button onClick={handleStartBatch} disabled={auditKeywords.length === 0} title={auditKeywords.length === 0 ? '請先至「任務配置」新增關鍵字' : undefined} className={`px-10 py-2 rounded-xl text-[11px] font-black shadow-xl tracking-[4px] uppercase flex items-center gap-2 ${auditKeywords.length === 0 ? 'bg-slate-200 text-slate-400 cursor-not-allowed' : 'bg-[#0F172A] text-white active:scale-95'}`}><IconPlay /> 啟動</button>
                   )}
                </div>
             </div>
             <div className="flex-1 overflow-hidden flex flex-col p-4 gap-4">
                <div className="flex-1 bg-white border border-slate-200 rounded-[1.5rem] shadow-sm overflow-hidden flex flex-col">
                   <div className="overflow-y-auto flex-1 custom-scroll">
                      <table className="w-full text-left">
                        <thead>
                           <tr className="bg-slate-50 border-b border-slate-200 sticky top-0 z-10 font-mono text-[9px] text-slate-400 uppercase tracking-widest">
                              <th className="px-8 py-3">核心關鍵字</th>
                              <th className="px-4 py-3 text-center border-l border-slate-100">Status</th>
                              <th className="px-6 py-3 text-center border-l border-slate-100">STG ND@10</th>
                              <th className="px-6 py-3 text-center border-l border-slate-100">誤判率</th>
                              <th className="px-8 py-3 text-right border-l border-slate-100">ACTION</th>
                           </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-50">
                           {auditKeywords.map((kwObj) => {
                              const kwStr = kwObj.keyword;
                              const res = findResult(kwStr);
                              const isDone = !!res;
                              const isActive = normalizeKw(kwStr) === normalizeKw(batchStatus.current_keyword);
                              const m = res?.stage?.metrics || res?.stage || {};
                              return (
                                 <tr key={kwStr} className={`hover:bg-slate-50 transition-all ${isActive ? 'bg-indigo-50/50 border-l-[6px] border-l-indigo-600' : ''}`}>
                                    <td className="px-8 py-3.5 font-black text-[14px] text-slate-900 uppercase tracking-tight">{kwStr}</td>
                                    <td className="px-4 py-3.5 text-center border-l border-slate-50">
                                       {isDone ? <span className="text-[10px] font-black text-emerald-600 uppercase font-mono italic">Done</span> : isActive ? <span className="text-[10px] font-black text-indigo-700 animate-pulse font-mono uppercase tracking-widest">Active</span> : <span className="text-[10px] font-black text-slate-200 font-mono uppercase">Wait</span>}
                                    </td>
                                    <td className="px-6 py-3.5 border-l border-slate-50 text-center font-mono font-black text-emerald-600">{isDone ? `${Math.round((m.ndcg_at_10 || m.ndcg_10 || 0)*100)}%` : '-'}</td>
                                    <td className="px-6 py-3.5 border-l border-slate-50 text-center font-black text-rose-500 text-[11px]">{isDone ? `${Math.round((m.mismatch_rate || 0)*100)}%` : '-'}</td>
                                    <td className="px-8 py-3.5 text-right border-l border-slate-50">
                                       <button onClick={() => window.open(`${import.meta.env.BASE_URL}?keyword=${encodeURIComponent(kwStr)}`, '_blank')} disabled={!isDone} className={`px-4 py-1.5 rounded-lg border text-[10px] font-black shadow-sm ${isDone ? 'bg-white border-slate-200 text-slate-800 hover:border-slate-800 hover:bg-slate-900 hover:text-white transition-all' : 'bg-slate-50 text-slate-200 cursor-not-allowed'}`}>詳細報告</button>
                                    </td>
                                 </tr>
                              );
                           })}
                        </tbody>
                      </table>
                   </div>
                </div>
                <div className="h-52 bg-white border border-slate-200 rounded-[1.5rem] shadow-sm flex flex-col shrink-0 overflow-hidden">
                   <div className="px-8 py-2.5 bg-slate-50/80 border-b border-slate-200 flex items-center gap-2">
                      <IconArchive />
                      <span className="text-[11px] font-black text-slate-800 uppercase tracking-[3px] font-mono">巡檢紀錄 (Inspection Archives)</span>
                   </div>
                   <div className="flex-1 overflow-y-auto custom-scroll">
                      <table className="w-full text-left">
                         <thead className="bg-white sticky top-0 z-10 border-b border-slate-100 font-mono text-[9px] text-slate-400 uppercase tracking-widest italic opacity-60">
                            <tr>
                              <th className="px-8 py-2">Run</th>
                              <th className="px-6 py-2">時間</th>
                              <th className="px-6 py-2">搜索詞</th>
                              <th className="px-6 py-2 text-center">平均 NDCG@10</th>
                              <th className="px-8 py-2 text-right">Action</th>
                            </tr>
                         </thead>
                         <tbody className="divide-y divide-slate-50">
                            {batchHistory.map((h) => {
                               const ndcg = Math.round((h.avg_ndcg || 0) * 100)
                               const ndcgColor = ndcg >= 80 ? 'bg-emerald-50 text-emerald-700 border-emerald-100'
                                 : ndcg >= 50 ? 'bg-amber-50 text-amber-700 border-amber-100'
                                 : 'bg-rose-50 text-rose-600 border-rose-100'
                               const tsDate = h.timestamp ? new Date(h.timestamp) : null
                               const datePart = tsDate ? tsDate.toLocaleDateString('zh-TW', {year:'numeric',month:'2-digit',day:'2-digit'}).replace(/\//g,'-') : '-'
                               const timePart = tsDate ? tsDate.toLocaleTimeString('zh-TW', {hour:'2-digit',minute:'2-digit',hour12:false}) : ''
                               return (
                                 <tr key={h.id} className="hover:bg-indigo-50/20 transition-all font-bold">
                                   <td className="px-8 py-2.5 text-slate-400 font-mono text-[11px]">#{h.id.toString().padStart(3,'0')}</td>
                                   <td className="px-6 py-2.5 text-slate-700 text-[12px]">
                                     {datePart} <span className="text-slate-400 font-mono ml-1">{timePart}</span>
                                   </td>
                                   <td className="px-6 py-2.5 max-w-[280px]">
                                     {(() => {
                                       const kws = h.keywords || []
                                       const preview = kws.slice(0, 4).join('、')
                                       const overflow = kws.length > 4
                                       return (
                                         <span className="text-[11px] text-slate-600 font-bold">
                                           {preview || '-'}
                                           {overflow && <span className="text-slate-400 ml-1">…+{kws.length - 4}</span>}
                                         </span>
                                       )
                                     })()}
                                   </td>
                                   <td className="px-6 py-2.5 text-center">
                                     <span className={`px-2 py-0.5 font-black font-mono rounded border text-[11px] ${ndcgColor}`}>{ndcg}%</span>
                                   </td>
                                   <td className="px-8 py-2.5 text-right">
                                     <button onClick={() => handleRestoreHistory(h.id)} className="px-4 py-1.5 bg-white border border-slate-200 text-slate-800 rounded-lg text-[9px] font-black hover:border-slate-800 hover:bg-slate-900 hover:text-white transition-all shadow-sm">載入存檔</button>
                                   </td>
                                 </tr>
                               )
                            })}
                         </tbody>
                      </table>
                   </div>
                </div>
                {schedules.length > 0 && (
                  <div className="bg-white border border-slate-200 rounded-[1.5rem] shadow-sm overflow-hidden shrink-0">
                     <div className="px-8 py-2.5 bg-slate-50/80 border-b border-slate-200 flex items-center justify-between">
                        <span className="text-[11px] font-black text-slate-800 uppercase tracking-[3px] font-mono">定期排程狀態</span>
                        <button onClick={() => { setEditingSchedule(null); setScheduleModalVisible(true); }} className="text-[10px] font-black text-indigo-600 hover:text-indigo-800 transition-colors">+ 新增排程</button>
                     </div>
                     <div className="divide-y divide-slate-50">
                        {schedules.map(s => {
                          const freqLabel = { daily:'每天', weekly:'每週', biweekly:'每兩週', monthly:'每月' }[s.freq] || s.freq
                          const timeStr = `${String(s.hour).padStart(2,'0')}:${String(s.minute).padStart(2,'0')}`
                          const dowStr = s.day_of_week ? ` (${s.day_of_week.split(',').map(d => ['一','二','三','四','五','六','日'][Number(d)]).join('/')})` : ''
                          return (
                            <div key={s.id} className="px-8 py-3 flex items-center gap-4">
                               <button onClick={() => handleToggleSchedule(s)} className={`relative inline-flex w-9 h-5 rounded-full transition-colors duration-200 focus:outline-none focus:ring-0 shrink-0 ${s.enabled ? 'bg-emerald-500' : 'bg-slate-200'}`}>
                                  <span className={`absolute top-[3px] w-[14px] h-[14px] bg-white rounded-full shadow-md transition-all duration-200 ${s.enabled ? 'left-[19px]' : 'left-[3px]'}`} />
                               </button>
                               <div className="flex-1 min-w-0">
                                  <div className="flex items-center flex-wrap gap-x-2 gap-y-0.5">
                                    <span className="text-[12px] font-black text-slate-800">{freqLabel} {timeStr}{dowStr}</span>
                                    {s.next_run && <span className="text-[10px] text-slate-400 font-mono">下次: {s.next_run.slice(0,16).replace('T',' ')}</span>}
                                  </div>
                                  <div className="flex items-center gap-1.5 mt-1 flex-wrap">
                                    {s.keywords && s.keywords.length > 0 ? (
                                      <>
                                        {s.keywords.slice(0, 4).map((k, i) => (
                                          <span key={i} className="bg-slate-100 text-slate-600 text-[9px] font-bold px-1.5 py-0.5 rounded-md font-mono">
                                            {typeof k === 'string' ? k : k.keyword}
                                          </span>
                                        ))}
                                        {s.keywords.length > 4 && (
                                          <span className="text-[9px] text-slate-400 font-mono">+{s.keywords.length - 4}</span>
                                        )}
                                      </>
                                    ) : (
                                      <span className="text-[9px] text-slate-400 font-mono">使用全域名單 ({auditKeywords.length} 個關鍵字)</span>
                                    )}
                                  </div>
                               </div>
                               <div className="flex gap-2 shrink-0">
                                  <button onClick={() => { setEditingSchedule(s); setScheduleModalVisible(true); }} className="px-3 py-1 border border-slate-200 rounded-lg text-[9px] font-black text-slate-600 hover:border-slate-800 transition-all">編輯</button>
                                  <button onClick={() => handleDeleteSchedule(s.id)} className="px-3 py-1 border border-rose-100 rounded-lg text-[9px] font-black text-rose-500 hover:border-rose-400 transition-all">刪除</button>
                               </div>
                            </div>
                          )
                        })}
                     </div>
                  </div>
                )}
             </div>
          </div>
        )}
      </main>

      <CalibrationModal
        product={edittingProduct}
        calibTier={calibTier}
        calibComment={calibComment}
        onTierChange={setCalibTier}
        onCommentChange={setCalibComment}
        onSubmit={submitCalibration}
        onClose={() => setEdittingProduct(null)}
      />
      <KeywordEditorModal
        visible={kwEditorVisible}
        kwInputText={kwInputText}
        onInputChange={setKwInputText}
        onSave={saveKeywords}
        onClose={() => setKwEditorVisible(false)}
      />
      <ScheduleModal
        visible={scheduleModalVisible}
        schedule={editingSchedule}
        onSave={handleSaveSchedule}
        onClose={() => { setScheduleModalVisible(false); setEditingSchedule(null); }}
      />
    </div>
  )
}
