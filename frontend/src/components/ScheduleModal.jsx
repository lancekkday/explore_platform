import { useState, useEffect } from 'react'

const FREQ_OPTIONS = [
  { value: 'daily',    label: '每天' },
  { value: 'weekly',   label: '每週' },
  { value: 'biweekly', label: '每兩週' },
  { value: 'monthly',  label: '每月' },
]

const DOW_LABELS = ['一', '二', '三', '四', '五', '六', '日']

function Toggle({ value, onChange, disabled }) {
  return (
    <button
      onClick={() => !disabled && onChange(!value)}
      className={`relative inline-flex w-11 h-6 rounded-full transition-colors duration-200 focus:outline-none focus:ring-0 shrink-0 ${value ? 'bg-emerald-500' : 'bg-slate-200'} ${disabled ? 'opacity-40 cursor-not-allowed' : 'cursor-pointer'}`}
    >
      <span className={`absolute top-[3px] w-[18px] h-[18px] bg-white rounded-full shadow-md transition-all duration-200 ${value ? 'left-[23px]' : 'left-[3px]'}`} />
    </button>
  )
}

function computeNextRun(freq, hour, minute, daysOfWeek) {
  const now = new Date()
  const candidate = new Date(now)
  candidate.setSeconds(0, 0)
  candidate.setHours(hour, minute)

  if (freq === 'daily') {
    if (candidate <= now) candidate.setDate(candidate.getDate() + 1)
    return candidate
  }
  if (freq === 'monthly') {
    candidate.setDate(1)
    if (candidate <= now) { candidate.setMonth(candidate.getMonth() + 1); candidate.setDate(1) }
    return candidate
  }
  if (freq === 'weekly' || freq === 'biweekly') {
    // find next matching day
    const days = daysOfWeek.length > 0 ? daysOfWeek : [1] // default Mon
    const weeks = freq === 'biweekly' ? 2 : 1
    for (let d = 0; d <= 7 * weeks; d++) {
      const test = new Date(now)
      test.setDate(now.getDate() + d)
      test.setHours(hour, minute, 0, 0)
      // JS getDay: 0=Sun..6=Sat; our dow: 0=Mon..6=Sun
      const jsDay = test.getDay()
      const ourDay = jsDay === 0 ? 6 : jsDay - 1
      if (days.includes(ourDay) && test > now) return test
    }
  }
  return candidate
}

export default function ScheduleModal({ visible, schedule, onSave, onClose }) {
  const [enabled, setEnabled] = useState(false)
  const [freq, setFreq] = useState('daily')
  const [hour, setHour] = useState(9)
  const [minute, setMinute] = useState(0)
  const [daysOfWeek, setDaysOfWeek] = useState([1]) // Mon default
  const [env, setEnv] = useState('stage')
  const [aiEnabled, setAiEnabled] = useState(false)
  const [slackNotify, setSlackNotify] = useState(false)
  const [autoDiff, setAutoDiff] = useState(false)
  const [kwText, setKwText] = useState('')

  useEffect(() => {
    if (!visible) return
    if (schedule) {
      setEnabled(!!schedule.enabled)
      setFreq(schedule.freq || 'daily')
      setHour(schedule.hour ?? 9)
      setMinute(schedule.minute ?? 0)
      setDaysOfWeek(schedule.day_of_week ? schedule.day_of_week.split(',').map(Number) : [1])
      setEnv(schedule.env || 'stage')
      setAiEnabled(!!schedule.ai_enabled)
      setSlackNotify(!!schedule.slack_notify)
      setAutoDiff(!!schedule.auto_diff)
      // Populate keywords textarea
      const kws = schedule.keywords || []
      setKwText(kws.map(k => (typeof k === 'string' ? k : k.keyword)).join('\n'))
    } else {
      setEnabled(false); setFreq('daily'); setHour(9); setMinute(0)
      setDaysOfWeek([1]); setEnv('stage'); setAiEnabled(false)
      setSlackNotify(false); setAutoDiff(false); setKwText('')
    }
  }, [visible, schedule])

  if (!visible) return null

  const toggleDow = (d) => setDaysOfWeek(prev =>
    prev.includes(d) ? (prev.length > 1 ? prev.filter(x => x !== d) : prev) : [...prev, d].sort()
  )

  const nextRun = enabled ? computeNextRun(freq, hour, minute, daysOfWeek) : null
  const nextRunStr = nextRun
    ? `${nextRun.toLocaleDateString('zh-TW')} ${String(nextRun.getHours()).padStart(2,'0')}:${String(nextRun.getMinutes()).padStart(2,'0')}`
    : null

  const parsedKws = kwText
    ? kwText.split(/[,\n]/).map(s => s.trim()).filter(s => s).map(s => ({ keyword: s, ai_enabled: aiEnabled }))
    : null  // null = use global list

  const handleSave = () => {
    onSave({
      ...(schedule?.id ? { id: schedule.id } : {}),
      enabled,
      freq,
      hour,
      minute,
      day_of_week: (freq === 'weekly' || freq === 'biweekly') ? daysOfWeek.join(',') : null,
      env,
      ai_enabled: aiEnabled,
      slack_notify: slackNotify,
      auto_diff: autoDiff,
      keywords: parsedKws,
    })
  }

  const hourOptions = Array.from({ length: 24 }, (_, i) => i)

  return (
    <div className="fixed inset-0 z-[600] flex items-center justify-center p-6 bg-slate-950/80 backdrop-blur-xl animate-in fade-in transition-all overflow-y-auto">
       <div className="absolute inset-0" onClick={onClose} />
       <div className="relative z-10 bg-white w-full max-w-[26rem] rounded-[2rem] shadow-2xl border border-white/20 overflow-hidden text-slate-900">

          {/* Header */}
          <div className="bg-white border-b border-slate-100 px-7 py-5 flex items-center justify-between">
             <div className="flex items-center gap-3">
                <span className="w-1 h-7 bg-indigo-500 rounded-full" />
                <div>
                   <h2 className="text-[15px] font-black tracking-tight text-slate-900">定期巡檢配置</h2>
                   <p className="text-[8px] font-black text-slate-400 uppercase tracking-[3px] mt-0.5">SCHEDULED INSPECTION CONFIG</p>
                </div>
             </div>
             <button onClick={onClose} className="text-slate-300 hover:text-slate-700 transition-colors text-xl leading-none">×</button>
          </div>

          <div className="p-6 flex flex-col gap-5">

             {/* 啟用開關 */}
             <div className="flex items-center justify-between">
                <div>
                   <div className="text-[13px] font-black text-slate-900">啟用定期巡檢</div>
                   <div className="text-[10px] text-slate-400 mt-0.5">啟用後為自動巡檢模式</div>
                </div>
                <Toggle value={enabled} onChange={setEnabled} />
             </div>

             <div className="h-px bg-slate-100" />

             {/* 頻率 + 時間 */}
             <div className="flex gap-3">
                <div className="flex-1">
                   <div className="text-[9px] font-black text-slate-400 uppercase tracking-widest mb-1.5">執行頻率</div>
                   <select value={freq} onChange={e => setFreq(e.target.value)} className="w-full border border-slate-200 rounded-xl px-3 py-2 text-[12px] font-black text-slate-800 bg-white outline-none cursor-pointer">
                      {FREQ_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                   </select>
                </div>
                <div className="flex-1">
                   <div className="text-[9px] font-black text-slate-400 uppercase tracking-widest mb-1.5">執行時間</div>
                   <div className="flex gap-1">
                      <select value={hour} onChange={e => setHour(Number(e.target.value))} className="flex-1 border border-slate-200 rounded-xl px-2 py-2 text-[12px] font-black text-slate-800 bg-white outline-none cursor-pointer">
                         {hourOptions.map(h => <option key={h} value={h}>{String(h).padStart(2,'0')}</option>)}
                      </select>
                      <span className="self-center text-slate-400 font-black">:</span>
                      <input
                        type="number"
                        min={0} max={59}
                        value={String(minute).padStart(2, '0')}
                        onChange={e => {
                          const v = Math.max(0, Math.min(59, Number(e.target.value)))
                          setMinute(isNaN(v) ? 0 : v)
                        }}
                        className="flex-1 border border-slate-200 rounded-xl px-2 py-2 text-[12px] font-black text-slate-800 bg-white outline-none text-center"
                      />
                   </div>
                </div>
             </div>

             {/* 週/雙週 — 選星期幾 */}
             {(freq === 'weekly' || freq === 'biweekly') && (
               <div>
                  <div className="text-[9px] font-black text-slate-400 uppercase tracking-widest mb-2">執行日</div>
                  <div className="flex gap-1.5">
                     {DOW_LABELS.map((label, i) => (
                       <button key={i} onClick={() => toggleDow(i)} className={`w-8 h-8 rounded-lg text-[11px] font-black transition-all ${daysOfWeek.includes(i) ? 'bg-[#0F172A] text-white' : 'bg-slate-100 text-slate-500 hover:bg-slate-200'}`}>
                          {label}
                       </button>
                     ))}
                  </div>
               </div>
             )}

             <div className="h-px bg-slate-100" />

             {/* 巡檢環境 */}
             <div>
                <div className="text-[9px] font-black text-slate-400 uppercase tracking-widest mb-2">巡檢環境</div>
                <div className="flex gap-2">
                   {[
                     { val: 'stage', label: '僅 Stage 巡檢', disabled: false },
                     { val: 'production', label: 'Production', disabled: true },
                     { val: 'both', label: 'Stage + Production', disabled: true },
                   ].map(({ val, label, disabled }) => (
                     <button
                       key={val}
                       onClick={() => !disabled && setEnv(val)}
                       title={disabled ? '暫停支援（Datadome 封鎖）' : undefined}
                       className={`flex-1 py-2 px-2 rounded-xl text-[10px] font-black transition-all border
                         ${disabled ? 'opacity-30 cursor-not-allowed border-slate-200 text-slate-400' :
                           env === val ? 'bg-[#0F172A] text-white border-[#0F172A]' :
                           'bg-white text-slate-600 border-slate-200 hover:border-slate-400'}`}
                     >
                       {label}
                     </button>
                   ))}
                </div>
             </div>

             <div className="h-px bg-slate-100" />

             {/* 執行選項 */}
             <div>
                <div className="text-[9px] font-black text-slate-400 uppercase tracking-widest mb-3">執行選項</div>
                <div className="flex flex-col gap-3">
                   {[
                     { label: 'AI 解析', sub: '啟用 AI 解析結果（收費）', val: aiEnabled, set: setAiEnabled },
                     { label: 'Slack 通知', sub: '執行完成發送結果至 Slack', val: slackNotify, set: setSlackNotify },
                     { label: '自動比對', sub: '與上次巡檢結果自動比對 diff', val: autoDiff, set: setAutoDiff },
                   ].map(({ label, sub, val, set }) => (
                     <div key={label} className="flex items-center justify-between">
                        <div>
                           <div className="text-[12px] font-black text-slate-800">{label}</div>
                           <div className="text-[9px] text-slate-400">{sub}</div>
                        </div>
                        <Toggle value={val} onChange={set} />
                     </div>
                   ))}
                </div>
             </div>

             <div className="h-px bg-slate-100" />

             {/* 巡檢關鍵字 */}
             <div>
                <div className="flex items-center justify-between mb-1.5">
                   <div className="text-[9px] font-black text-slate-400 uppercase tracking-widest">巡檢關鍵字</div>
                   {parsedKws
                     ? <span className="text-[9px] font-black text-indigo-500 font-mono">共 {parsedKws.length} 個</span>
                     : <span className="text-[9px] font-black text-slate-400 font-mono">使用全域名單</span>
                   }
                </div>
                <textarea
                  value={kwText}
                  onChange={e => setKwText(e.target.value)}
                  rows={4}
                  className="w-full bg-slate-50 border border-slate-200 rounded-xl px-3 py-2.5 text-[11px] font-bold text-slate-800 focus:bg-white focus:border-indigo-400 outline-none resize-none transition-all"
                  placeholder={"留空則使用全域名單\nesim\n日本旅遊\n大阪周遊券"}
                />
             </div>

             {/* 下次執行預覽 */}
             {nextRunStr && (
               <>
                  <div className="h-px bg-slate-100" />
                  <div className="bg-indigo-50 border border-indigo-100 rounded-2xl px-4 py-3">
                     <div className="text-[9px] font-black text-indigo-400 uppercase tracking-widest mb-1">下次執行預覽</div>
                     <div className="text-[14px] font-black text-indigo-700 font-mono">{nextRunStr}</div>
                  </div>
               </>
             )}

             {/* 操作按鈕 */}
             <div className="flex gap-3 pt-1">
                <button onClick={onClose} className="flex-1 py-3 text-[11px] font-black text-slate-400 uppercase tracking-[3px] hover:text-slate-700 border border-slate-200 rounded-xl transition-all">取消</button>
                <button onClick={handleSave} className="flex-[2] py-3 bg-indigo-600 text-white rounded-xl text-[12px] font-black shadow-md hover:bg-indigo-700 uppercase tracking-[4px] active:scale-95 transition-all">儲存設定</button>
             </div>
          </div>
       </div>
    </div>
  )
}
