import { safeString } from '../utils/safeString'
import { IconX } from './icons/Icons'

const TIERS = [
  { v: 1, l: 'T1', d: '完全相關 / 首選', active: 'border-emerald-500 bg-emerald-50 text-emerald-900' },
  { v: 2, l: 'T2', d: '部分相關 / 地點吻合', active: 'border-blue-500 bg-blue-50 text-blue-900' },
  { v: 3, l: 'T3', d: '疑似相關 / 類別合理', active: 'border-orange-500 bg-orange-50 text-orange-900' },
  { v: 0, l: 'MISS', d: '完全錯誤 / 非相關商品', active: 'border-rose-500 bg-rose-50 text-rose-900' },
]

export default function CalibrationModal({ product, calibTier, calibComment, calibSynonyms, onTierChange, onCommentChange, onSynonymsChange, onSubmit, onClose }) {
  if (!product) return null
  return (
    <div className="fixed inset-0 z-[500] flex items-center justify-center p-4 bg-slate-950/70 backdrop-blur-sm">
      <div className="absolute inset-0" onClick={onClose} />
      <div className="relative z-10 bg-white w-full max-w-[28rem] max-h-[90vh] overflow-y-auto rounded-xl shadow-2xl text-slate-900">
        {/* Header */}
        <div className="bg-[#0F172A] px-5 py-3.5 flex justify-between items-center text-white">
          <h2 className="text-[13px] font-black tracking-[3px] uppercase flex items-center gap-2.5">
            <span className="w-1 h-4 bg-indigo-400 rounded-full" />
            意圖精準校正
          </h2>
          <button onClick={onClose} className="text-white/50 hover:text-white transition-colors p-1" aria-label="關閉">
            <IconX size={18} />
          </button>
        </div>

        <div className="p-5 space-y-4">
          {/* Product ref */}
          <div className="px-3.5 py-2.5 bg-slate-50 border border-slate-200 rounded-lg">
            <div className="text-[9px] text-slate-400 font-black uppercase tracking-[2px] mb-1 font-mono">
              PRODUCT REF · {product.id}
            </div>
            <div className="text-[12px] font-bold text-slate-800 leading-snug">
              {safeString(product.name)}
            </div>
          </div>

          {/* Tier picker */}
          <div className="grid grid-cols-2 gap-2">
            {TIERS.map(t => {
              const isActive = calibTier === t.v
              return (
                <button
                  key={t.v}
                  onClick={() => onTierChange(t.v)}
                  className={`px-3 py-2 rounded-lg border-2 text-left transition-all ${
                    isActive
                      ? `${t.active} shadow-sm`
                      : 'border-slate-200 bg-white text-slate-500 hover:border-slate-300'
                  }`}
                >
                  <div className="text-[13px] font-black leading-none">{t.l}</div>
                  <div className={`text-[10px] mt-1 ${isActive ? 'opacity-80' : 'text-slate-400'}`}>
                    {t.d}
                  </div>
                </button>
              )
            })}
          </div>

          {/* Comment */}
          <div>
            <div className="text-[10px] text-slate-500 font-bold uppercase tracking-[2px] mb-1.5">
              校正原因 <span className="text-slate-400 normal-case tracking-normal font-normal">（選填）</span>
            </div>
            <textarea
              value={calibComment}
              onChange={e => onCommentChange(e.target.value)}
              className="w-full h-20 bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-[12px] focus:bg-white focus:border-indigo-400 transition-colors outline-none resize-none text-slate-800 placeholder:text-slate-400"
              placeholder="請詳細輸入判定修正之邏輯原因…"
            />
          </div>

          {/* Synonyms */}
          <div>
            <div className="text-[10px] text-slate-500 font-bold uppercase tracking-[2px] mb-1.5">
              同義詞 / 別名 <span className="text-slate-400 normal-case tracking-normal font-normal">（選填，逗號分隔）</span>
            </div>
            <input
              value={calibSynonyms}
              onChange={e => onSynonymsChange(e.target.value)}
              className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-[12px] focus:bg-white focus:border-indigo-400 transition-colors outline-none text-slate-800 placeholder:text-slate-400"
              placeholder="例：吉伊卡哇, チーカワ"
            />
            <div className="text-[10px] text-slate-400 mt-1 leading-snug">
              填入後自動寫入同義詞表,之後搜同關鍵字時所有含這些詞的商品都會套用此 Tier 判定。
            </div>
          </div>

          {/* Actions */}
          <div className="flex gap-2 pt-2">
            <button
              onClick={onClose}
              className="flex-1 py-2.5 rounded-lg text-[11px] font-black uppercase tracking-[2px] border border-slate-200 text-slate-600 hover:bg-slate-50 hover:border-slate-300 transition-colors"
            >
              取消
            </button>
            <button
              onClick={onSubmit}
              className="flex-[2] py-2.5 rounded-lg text-[11px] font-black uppercase tracking-[2px] bg-indigo-600 text-white hover:bg-indigo-700 active:scale-[0.98] transition-all shadow-sm"
            >
              儲存校正結果
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
