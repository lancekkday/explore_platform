import { useState, useEffect } from 'react'

const Toggle = ({ label, hint, checked, onChange, disabled }) => (
  <div className={`flex items-center justify-between p-4 rounded-2xl border-2 transition-all ${checked ? 'border-indigo-200 bg-indigo-50/40' : 'border-slate-100 bg-slate-50/40'} ${disabled ? 'opacity-40 pointer-events-none' : ''}`}>
    <div className="flex flex-col gap-0.5">
      <span className="text-[13px] font-black text-slate-800">{label}</span>
      {hint && <span className="text-[10px] text-slate-400 font-bold">{hint}</span>}
    </div>
    <button
      onClick={() => onChange(!checked)}
      className={`relative inline-flex w-11 h-6 rounded-full transition-colors duration-200 focus:outline-none shrink-0 ${checked ? 'bg-indigo-600' : 'bg-slate-200'}`}
    >
      <span className={`absolute top-[3px] w-[18px] h-[18px] bg-white rounded-full shadow-md transition-all duration-200 ${checked ? 'left-[22px]' : 'left-[3px]'}`} />
    </button>
  </div>
)

export default function SettingsPanel({ settings, onSave }) {
  const [envs, setEnvs] = useState({ stage: true, production: false })
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState('')

  useEffect(() => {
    if (settings?.environments) {
      setEnvs(settings.environments)
    }
  }, [settings])

  const dirty = settings?.environments
    ? (envs.stage !== settings.environments.stage || envs.production !== settings.environments.production)
    : false

  const handleToggle = (env, val) => {
    const next = { ...envs, [env]: val }
    if (!next.stage && !next.production) {
      setMsg('至少需啟用一個環境')
      return
    }
    setMsg('')
    setEnvs(next)
  }

  const handleSave = async () => {
    setSaving(true)
    setMsg('')
    try {
      await onSave({ environments: envs })
      setMsg('儲存成功')
      setTimeout(() => setMsg(''), 2000)
    } catch {
      setMsg('儲存失敗')
    }
    setSaving(false)
  }

  const bothEnabled = envs.stage && envs.production

  return (
    <div className="flex-1 flex items-start justify-center p-8 overflow-y-auto">
      <div className="w-full max-w-lg">
        <div className="bg-white border border-slate-200 rounded-[1.5rem] shadow-sm overflow-hidden">
          <div className="px-8 py-5 border-b border-slate-100">
            <h2 className="text-[15px] font-black text-slate-900 tracking-tight uppercase">環境設定</h2>
            <p className="text-[10.5px] text-slate-400 font-bold mt-1">選擇啟用的巡檢環境，兩者皆啟用時將執行雙環境比對巡檢</p>
          </div>

          <div className="p-6 flex flex-col gap-3">
            <Toggle
              label="Stage 測試環境"
              hint="www.stage.kkday.com"
              checked={envs.stage}
              onChange={(v) => handleToggle('stage', v)}
            />
            <Toggle
              label="Production 正式環境"
              hint="www.kkday.com"
              checked={envs.production}
              onChange={(v) => handleToggle('production', v)}
            />

            {bothEnabled && (
              <div className="mt-1 px-4 py-3 bg-amber-50 border border-amber-200 rounded-xl">
                <p className="text-[11px] font-bold text-amber-700">
                  雙環境模式已啟用 — 巡檢將同時比對 Stage 與 Production 結果
                </p>
              </div>
            )}

            {msg && (
              <div className={`text-[11px] font-bold text-center py-1.5 ${msg.includes('成功') ? 'text-emerald-600' : 'text-rose-500'}`}>
                {msg}
              </div>
            )}
          </div>

          <div className="px-6 pb-6">
            <button
              onClick={handleSave}
              disabled={saving || !dirty}
              className={`w-full py-2.5 rounded-xl text-[11px] font-black tracking-[3px] uppercase transition-all ${
                dirty
                  ? 'bg-[#0F172A] text-white hover:bg-black active:scale-[0.98] shadow-lg'
                  : 'bg-slate-100 text-slate-300 cursor-not-allowed'
              }`}
            >
              {saving ? 'SAVING...' : '儲存設定'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
