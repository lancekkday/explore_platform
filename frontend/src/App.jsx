import { useState, useEffect } from 'react'

// ─── SVG 圖示 ──────────────────────────────────────────────────────────────
const IconMapPin = () => (<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z"/><circle cx="12" cy="10" r="3"/></svg>)
const IconTag = () => (<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M12 2H2v10l9.29 9.29a1 1 0 0 0 1.41 0l7.3-7.3a1 1 0 0 0 0-1.41Z"/><path d="M7 7h.01"/></svg>)
const IconX = ({ size = 18 }) => (<svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><path d="M18 6 6 18M6 6l12 12"/></svg>)
const IconRefresh = () => (<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/></svg>)
const IconSearch = () => (<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>)
const IconBot = () => (<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M12 8V4H8"/><rect width="16" height="12" x="4" y="8" rx="2"/><path d="M2 14h2"/><path d="M20 14h2"/><path d="M15 13v2"/><path d="M9 13v2"/></svg>)
const IconGlobe = () => (<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><path d="M2 12h20"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>)

// ─── 工具提示 Component ──────────────────────────────────
function Tooltip({ title, content, pos = 'up', children }) {
  const isUp = pos === 'up';
  if (!content) return children;
  return (
    <div className="relative group/tip cursor-help">
      {children}
      <div className={`absolute left-1/2 -translate-x-1/2 hidden group-hover/tip:flex flex-col z-[9999] bg-[#0F172AD9] backdrop-blur-md text-white p-4 rounded-2xl shadow-2xl border border-white/10 w-72 animate-in fade-in transition-all outline-none ${isUp ? 'bottom-full mb-3' : 'top-full mt-3'}`}>
        <div className="text-[11px] font-black text-indigo-400 border-b border-white/10 pb-2 mb-2.5 flex items-center gap-2">
          <div className="w-1.5 h-1.5 bg-indigo-500 rounded-full animate-pulse" />
          {title}
        </div>
        <div className="text-[11px] leading-relaxed text-slate-100 font-bold break-words whitespace-normal tracking-wide">{content}</div>
        <div className={`absolute left-1/2 -translate-x-1/2 w-4 h-4 bg-[#0F172AD9] rotate-45 border-white/10 ${isUp ? 'top-full -translate-y-2 border-r border-b' : 'bottom-full translate-y-2 border-l border-t'}`} />
      </div>
    </div>
  )
}

// ─── 等級標籤 ──────────────────────────────────────────────
function TierBadge({ it }) {
  if (!it) return null;
  const { tier = 0, is_calibrated = false } = it;
  const base = 'inline-flex items-center px-1.5 py-0.5 text-[8.5px] font-black rounded border whitespace-nowrap shadow-sm tracking-[1px] leading-none';
  if (is_calibrated) return <span className={`${base} bg-indigo-600 text-white border-indigo-700`}>🎯 校正</span>;
  if (tier === 1) return <span className={`${base} bg-emerald-50 text-emerald-900 border-emerald-200`}>T1 首選</span>;
  if (tier === 2) return <span className={`${base} bg-blue-50 text-blue-900 border-blue-200`}>T2 相關</span>;
  if (tier === 3) return <span className={`${base} bg-orange-50 text-orange-900 border-orange-200`}>T3 疑似</span>;
  return <span className={`${base} bg-rose-50 text-rose-800 border-rose-200`}>MISS</span>;
}

// ─── 圓形指標 ──────────────────────────────────────────────────────────────
function NdcgGauge({ value = 0, label, tooltip }) {
  const pct = isNaN(value) ? 0 : Math.round((value || 0) * 100);
  const stroke = pct >= 80 ? '#10B981' : pct >= 60 ? '#F59E0B' : '#EF4444';
  const glow = pct >= 80 ? '0 0 10px #10B98160' : 'none';
  const dash = `${pct} ${100 - pct}`;
  return (
    <Tooltip title={label} content={tooltip} pos="down">
      <div className="flex flex-col items-center gap-1 shrink-0 transition-transform hover:scale-105">
        <div className="relative w-8 h-8" style={{ filter: `drop-shadow(${glow})` }}>
          <svg viewBox="0 0 36 36" className="w-full h-full -rotate-90">
            <circle cx="18" cy="18" r="15.9" fill="none" stroke="#F1F5F9" strokeWidth="6" />
            <circle cx="18" cy="18" r="15.9" fill="none" stroke={stroke} strokeWidth="6" strokeDasharray={dash} strokeLinecap="round" />
          </svg>
          <span className="absolute inset-0 flex items-center justify-center text-[10px] font-black text-slate-800 font-mono tracking-tighter">{pct}%</span>
        </div>
        <span className="text-[7.5px] font-black text-slate-500 uppercase tracking-[1px]">{label}</span>
      </div>
    </Tooltip>
  )
}

// ─── 環境數據看板 ────────────────────────────────────────────────────────────
function CompactMetricBar({ data, color, env, envCode }) {
    if (!data) return (
      <div className="px-4 py-2 bg-slate-50 rounded-xl border border-dashed border-slate-200 text-slate-400 text-center font-black text-[9px] flex items-center justify-center gap-2">
         待命... {env}
      </div>
    );
    const metrics = data.metrics || {};
    const ndcg150 = metrics.ndcg_at_150 !== undefined ? metrics.ndcg_at_150 : (metrics.ndcg_at_300 || 0);

    return (
      <div className="bg-white px-4 py-2 rounded-xl border border-slate-200 shadow-sm flex items-center justify-between relative border-l-8 hover:shadow-indigo-50 transition-all group" style={{ borderLeftColor: color }}>
         <div className="flex flex-col">
            <div className="flex items-center gap-2">
               <span className="text-[10px] font-black text-slate-900 tracking-wider font-sans">{env} 指標</span>
               <div className="px-1 py-0.5 bg-slate-100 rounded text-[6.5px] font-black text-slate-500 uppercase tracking-widest">{envCode}</div>
            </div>
            <span className="text-[9px] font-bold text-slate-400 italic">精密巡檢模組分析結果</span>
         </div>
         <div className="flex items-center gap-6">
            <div className="flex items-center gap-3 border-r border-slate-50 pr-6">
               <NdcgGauge value={metrics.ndcg_at_10} label="NDCG@10" tooltip="衡量前 10 名商品的排序品質。影響首屏使用者體驗。" />
               <NdcgGauge value={metrics.ndcg_at_50} label="NDCG@50" tooltip="指標穩定度：前 50 名排序精確度。" />
               <NdcgGauge value={ndcg150} label="NDCG@150" tooltip="反映長尾搜尋結果的意圖穩定性。" />
            </div>
            <div className="flex gap-6 px-1">
               <Tooltip title="召回率 (Recall)" content="衡量在 300 筆商品中，有多少比例是符合意圖的商品。" pos="down">
                  <div className="flex flex-col text-center">
                    <span className="text-[8px] text-slate-400 font-black uppercase tracking-widest">召回</span>
                    <span className="text-[13px] font-black text-indigo-700 font-mono italic">{Math.round((metrics.recall_at_150 || metrics.recall_at_300 || 0)*100)}%</span>
                  </div>
               </Tooltip>
               <Tooltip title="誤判率 (Noise)" content="搜尋結果中完全錯誤 (MISS) 的商品佔比。" pos="down">
                  <div className="flex flex-col text-center">
                    <span className="text-[8px] text-slate-400 font-black uppercase tracking-widest">誤判</span>
                    <span className="text-[13px] font-black text-rose-600 font-mono italic">{Math.round((metrics.mismatch_rate || 0)*100)}%</span>
                  </div>
               </Tooltip>
            </div>
         </div>
      </div>
    )
}

// ─── 核心應用面板 ────────────────────────────────────────────────────────────
export default function App() {
  const [tab, setTab] = useState('discovery')
  const [keyword, setKeyword] = useState('esim')
  const [searchMode, setSearchMode] = useState('both') 
  const [cookie, setCookie] = useState('')
  const [cookieInfo, setCookieInfo] = useState(null)
  const [singleAiMode, setSingleAiMode] = useState(false)
  const [doubtOnly, setDoubtOnly] = useState(false) 
  
  const [loading, setLoading] = useState(false)
  const [stageData, setStageData] = useState(null)
  const [prodData, setProdData] = useState(null)
  const [error, setError] = useState('')
  const [status, setStatus] = useState({ type: 'info', msg: '系統就緒' })

  const [edittingProduct, setEdittingProduct] = useState(null)
  const [calibTier, setCalibTier] = useState(1)
  const [calibComment, setCalibComment] = useState('')

  useEffect(() => {
    autoFetchCookie();
  }, [])

  const handleSearch = async (kw = keyword) => {
    if (!kw) return;
    setLoading(true); setError(''); setTab('discovery');
    try {
      const resp = await fetch('http://localhost:8000/api/compare', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ keyword: kw, cookie: cookie, count: 300, ai_enabled: singleAiMode })
      });
      const res = await resp.json();
      if (res && (res.stage || res.production)) {
          setStageData(res.stage);
          setProdData(res.production);
          setStatus({ type: 'success', msg: `巡檢完成` });
      } else {
          setError(res?.detail || '返回數據異常');
      }
    } catch (e) { setError('伺服器連線異常'); }
    setLoading(false);
  }

  const autoFetchCookie = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/guest-cookie?env=production').then(r => r.json());
      if (res && res.cookie) { setCookie(res.cookie); setCookieInfo(res); return res; }
      return null;
    } catch (e) { setError('憑證對接異常'); return null; }
  }

  const handleCalibrate = (p) => {
    if (!p) return;
    setEdittingProduct(p);
    setCalibTier(p.user_tier || p.tier || 1);
    setCalibComment(p.user_comment || p.comment || '');
  }

  const submitCalibration = async () => {
    if (!edittingProduct) return;
    try {
      const res = await fetch('http://localhost:8000/api/feedback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ keyword, product_id: edittingProduct.id, user_tier: parseInt(calibTier), comment: calibComment })
      }).then(r => r.json())
      if (res.success) {
        setEdittingProduct(null); handleSearch();
        setStatus({ type: 'success', msg: '校正完成' })
      }
    } catch (e) { setStatus({ type: 'error', msg: '標註失敗' }) }
  }

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
            <button onClick={() => setTab('audit')} className={`px-5 py-1.5 rounded-md text-[10.5px] font-black transition-all ${tab === 'audit' ? 'bg-white text-indigo-600 shadow-sm' : 'text-slate-400'}`}>統計報告</button>
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
                   <input type="text" value={keyword} onChange={e => setKeyword(e.target.value)} onKeyDown={e => e.key === 'Enter' && handleSearch()} className="w-full pl-10 pr-4 py-2 text-[13px] rounded-xl border-2 border-slate-100 bg-slate-50 focus:bg-white focus:border-indigo-500 outline-none transition-all font-black text-slate-900" placeholder="分析關鍵字..." />
                </div>
                
                <div className="flex items-center bg-slate-50 border-2 border-slate-100 rounded-xl px-3 py-1.5 hover:border-slate-300 transition-all">
                   <IconGlobe />
                   <select value={searchMode} onChange={e => setSearchMode(e.target.value)} className="bg-transparent text-[10.5px] font-black text-slate-800 outline-none cursor-pointer pl-1.5">
                      <option value="both">⚔️ 雙環境比對巡檢</option>
                      <option value="stage">🧪 僅 Stage 巡檢</option>
                      <option value="prod">🚀 僅 Production 巡檢</option>
                   </select>
                </div>

                <div className="flex gap-2 text-[10.5px] font-black">
                   <button onClick={() => setDoubtOnly(!doubtOnly)} className={`px-5 py-2 rounded-xl border-2 transition-all shadow-sm ${doubtOnly ? 'bg-[#0F172A] text-white border-slate-900' : 'bg-white text-slate-600 border-slate-200 hover:border-slate-800'}`}>
                      {doubtOnly ? '顯示完整列表' : '僅顯示待確認'}
                   </button>
                   <button onClick={() => setSingleAiMode(!singleAiMode)} className={`flex items-center gap-2 px-5 py-2 rounded-xl border-2 transition-all ${singleAiMode ? 'bg-[#0F172A] text-white border-slate-900' : 'bg-white text-slate-600 border-slate-200 hover:border-slate-800'}`}>
                      <IconBot /> AI 解析: {singleAiMode ? '啟用' : '關閉'}
                   </button>
                </div>

                <button onClick={() => handleSearch()} disabled={loading} className={`px-10 py-2 rounded-xl font-black text-[11px] tracking-[4px] uppercase transition-all shadow-lg ${loading ? 'bg-slate-100 text-slate-400 cursor-wait' : 'bg-[#0F172A] text-white hover:bg-black active:scale-95'}`}>
                   {loading ? 'ANALYZING...' : '開始巡檢'}
                </button>
             </div>

             <div className="flex-1 flex gap-4 overflow-hidden p-4 relative">
                {loading && (
                   <div className="absolute inset-0 bg-white/60 backdrop-blur-[1px] z-[40] flex flex-col items-center justify-center gap-3">
                      <div className="w-8 h-8 border-[4px] border-white/10 border-t-indigo-600 rounded-full animate-spin shadow-2xl" />
                      <div className="text-indigo-900 font-black text-[11px] tracking-[6px] animate-pulse uppercase">Syncing</div>
                   </div>
                )}
                <div className="flex-1 flex overflow-hidden w-full gap-4">
                   {(searchMode === 'both' || searchMode === 'stage') && (
                     <div className="flex-1 min-w-0 flex flex-col min-h-0 gap-4">
                        <CompactMetricBar data={stageData} env="STAGE 測試" envCode="STG-01" color="#10B981" />
                        <ResultList items={stageData?.results} title="STAGE 巡檢清單" total={stageData?.total || 0} color="#10B981" onCalibrate={handleCalibrate} doubtOnly={doubtOnly} />
                     </div>
                   )}
                   {(searchMode === 'both' || searchMode === 'prod') && (
                     <div className="flex-1 min-w-0 flex flex-col min-h-0 gap-4">
                        <CompactMetricBar data={prodData} env="PROD 正式" envCode="LIVE-01" color="#3B82F6" />
                        <ResultList items={prodData?.results} title="PROD 巡檢清單" total={prodData?.total || 0} color="#3B82F6" onCalibrate={handleCalibrate} doubtOnly={doubtOnly} />
                     </div>
                   )}
                </div>
             </div>
          </div>
        ) : (
          <div className="flex-1 flex items-center justify-center text-slate-100 flex-col opacity-10 select-none py-32">
             <div className="text-8xl mb-8">📊</div>
             <div className="text-4xl font-black uppercase tracking-[30px]">Summary Statistics</div>
          </div>
        )}
      </main>

      {/* 校正視窗 */}
      {edittingProduct && (
        <div className="fixed inset-0 z-[500] flex items-center justify-center p-6 bg-slate-950/80 backdrop-blur-xl animate-in fade-in transition-all">
           <div className="absolute inset-0" onClick={() => setEdittingProduct(null)} />
           <div className="relative bg-white w-full max-w-[34rem] rounded-[2.5rem] shadow-2xl border border-white/20 overflow-hidden text-slate-900">
              <div className="bg-[#0F172A] px-10 py-7 flex justify-between items-center text-white">
                 <h2 className="text-xl font-black tracking-tight flex items-center gap-4">
                    <span className="w-1.5 h-8 bg-indigo-500 rounded-full" />
                    意圖精準校正
                 </h2>
                 <button onClick={() => setEdittingProduct(null)} className="text-white/40 hover:text-white transform hover:rotate-90 transition-all p-2"><IconX size={26} /></button>
              </div>
              <div className="p-10">
                 <div className="px-7 py-6 bg-slate-50 border border-slate-200 rounded-3xl mb-10 font-bold text-[14.5px] text-slate-800 leading-relaxed shadow-inner">
                    <div className="text-[9px] text-slate-400 font-black uppercase tracking-[3px] mb-2 font-mono">PRODUCT REF: {edittingProduct.id}</div>
                    {edittingProduct.name}
                 </div>
                 <div className="mb-10 grid grid-cols-2 gap-4">
                    {[
                      { v: 1, l: "T1", d: "完全相關 / 首選方案", c: "bg-green-50/10 border-green-600 text-green-900" },
                      { v: 2, l: "T2", d: "部分相關 / 地點明確", c: "bg-blue-50/10 border-blue-600 text-blue-900" },
                      { v: 3, l: "T3", d: "疑似相關 / 類別合理", c: "bg-orange-50/10 border-orange-600 text-orange-900" },
                      { v: 0, l: "MISS", d: "完全錯誤 / 非相關商品", c: "bg-red-50/10 border-red-600 text-red-900" }
                    ].map(t => (
                      <button key={t.v} onClick={() => setCalibTier(t.v)} className={`px-6 py-4 rounded-2xl border-2 text-left transition-all relative ${calibTier === t.v ? t.c + ' shadow-xl scale-[1.03] bg-white' : 'border-slate-100 bg-slate-50 text-slate-400'}`}>
                         <span className="text-[16px] font-black block">{t.l}</span>
                         <span className="text-[10px] font-bold opacity-70">{t.d}</span>
                      </button>
                    ))}
                 </div>
                 <textarea value={calibComment} onChange={e => setCalibComment(e.target.value)} className="w-full h-28 bg-slate-100 border-2 border-slate-50 rounded-3xl p-6 text-[13px] font-bold focus:bg-white focus:border-indigo-500 transition-all outline-none resize-none mb-10 text-slate-900 shadow-inner" placeholder="請詳細輸入判定修正之邏輯原因..." />
                 <div className="flex gap-6 items-center">
                    <button onClick={() => setEdittingProduct(null)} className="flex-1 py-5 text-xs font-black text-slate-400 uppercase tracking-[4px] hover:text-slate-950 transition-colors">取消動作</button>
                    <button onClick={submitCalibration} className="flex-[2] py-5 bg-[#0F172A] text-white rounded-3xl text-[13px] font-black shadow-2xl hover:bg-black uppercase tracking-[6px] active:scale-95 transition-all">
                       儲存校正結果
                    </button>
                 </div>
              </div>
           </div>
        </div>
      )}
    </div>
  )
}

function ResultList({ items, title, total, color, onCalibrate, doubtOnly }) {
    const rawItems = Array.isArray(items) ? items : [];
    const displayed = doubtOnly 
      ? rawItems.filter(it => it && (it.tier === 0 || it.tier === 3 || it.is_calibrated))
      : rawItems;

    return (
      <div className="flex-1 flex flex-col min-h-0 bg-white border border-slate-200 rounded-[1.5rem] shadow-sm overflow-hidden text-slate-900">
         <div className="flex items-center justify-between py-2.5 px-5 border-b border-slate-100 bg-white/80 backdrop-blur-sm sticky top-0 z-10 shrink-0">
            <h3 className="font-black text-[11px] text-slate-800 tracking-[3px] uppercase flex items-center gap-2.5">
               <div className="w-1.5 h-3.5 rounded-full shadow-lg" style={{ backgroundColor: color }} />
               {title}
            </h3>
            <div className="flex items-center gap-2">
               <span className="text-[10.5px] font-black text-indigo-700 bg-indigo-50 px-3 py-0.5 rounded-full border border-indigo-100 tabular-nums">{displayed.length} / {total}</span>
            </div>
         </div>
         <div className="flex-1 overflow-y-auto custom-scroll px-2 py-1 bg-white">
            {displayed.length === 0 ? (
               <div className="py-20 text-center flex flex-col items-center justify-center opacity-30 select-none">
                  <div className="text-5xl mb-4">🔍</div>
                  <div className="text-[10px] font-black text-slate-400 uppercase tracking-[10px]">NO DATA</div>
               </div>
            ) : (
              <div className="flex flex-col gap-0.5">
                {displayed.map((it, i) => {
                  if (!it) return null;
                  return (
                    <div key={i} className={`flex items-center gap-4 py-1.5 px-4 border-b border-slate-50 hover:bg-slate-50/80 transition-all group rounded-xl relative border-l-2 ${it.tier === 0 ? 'border-l-rose-500 bg-rose-50/10' : 'border-l-transparent hover:border-l-indigo-300'}`}>
                      <div className="w-9 shrink-0 flex flex-col items-center">
                         <span className="text-[11.5px] font-black text-slate-900 leading-none font-mono">#{it.rank}</span>
                         {it.rank_delta !== undefined && it.rank_delta !== null && (
                           <span className={`text-[8.5px] font-black mt-1 px-1.5 py-0.5 rounded ${it.rank_delta > 0 ? 'bg-emerald-50 text-emerald-700' : it.rank_delta < 0 ? 'bg-rose-50 text-rose-700' : 'text-slate-300'}`}>
                              {it.rank_delta > 0 ? `▲${it.rank_delta}` : it.rank_delta < 0 ? `▼${Math.abs(it.rank_delta)}` : '•'}
                           </span>
                         )}
                      </div>
                      <div className="flex-1 min-w-0">
                         <div className="text-[13px] font-bold text-slate-800 truncate leading-tight select-all tracking-tight group-hover:text-slate-950 transition-colors" title={it.name}>{it.name}</div>
                         <div className="flex items-center gap-3 mt-1.5 opacity-70">
                            <span className="flex items-center gap-1 text-[9px] font-black text-slate-500">
                               <IconTag /><span className="uppercase tracking-[1px] leading-none">{it.main_cat_key || "UNIDENTIFIED"}</span>
                            </span>
                            <span className="flex items-center gap-1 text-[9px] font-black text-slate-500">
                               <IconMapPin /><span className="uppercase tracking-[1px] leading-none">{it.destinations?.[0] || "GLOBAL"}</span>
                            </span>
                         </div>
                      </div>
                      <div className="flex items-center gap-2.5 shrink-0">
                         <TierBadge it={it} />
                         <button onClick={() => onCalibrate(it)} className="h-7.5 px-4 rounded-lg border border-slate-200 bg-white text-slate-800 font-black text-[11px] shadow-sm hover:border-slate-800 hover:bg-slate-900 hover:text-white transition-all outline-none">
                            校正
                         </button>
                         {it.mismatch_reasons && it.mismatch_reasons.length > 0 && (
                            <Tooltip title="判定診斷詳情" content={it.mismatch_reasons.join(' | ')}>
                               <div className="w-5.5 h-5.5 flex items-center justify-center bg-rose-600 text-white font-black rounded-lg animate-pulse text-[11px] shadow-[0_0_8px_rgba(225,29,72,0.4)]">!</div>
                            </Tooltip>
                         )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
         </div>
      </div>
    )
 }
