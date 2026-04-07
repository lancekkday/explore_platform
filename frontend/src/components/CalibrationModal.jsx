import { safeString } from '../utils/safeString'
import { IconX } from './icons/Icons'

export default function CalibrationModal({ product, calibTier, calibComment, onTierChange, onCommentChange, onSubmit, onClose }) {
  if (!product) return null;
  return (
    <div className="fixed inset-0 z-[500] flex items-center justify-center p-6 bg-slate-950/80 backdrop-blur-xl animate-in fade-in transition-all">
       <div className="absolute inset-0" onClick={onClose} />
       <div className="relative z-10 bg-white w-full max-w-[34rem] rounded-[2.5rem] shadow-2xl border border-white/20 overflow-hidden text-slate-900">
          <div className="bg-[#0F172A] px-10 py-7 flex justify-between items-center text-white">
             <h2 className="text-xl font-black tracking-tight flex items-center gap-4">
                <span className="w-1.5 h-8 bg-indigo-500 rounded-full" />
                意圖精準校正
             </h2>
             <button onClick={onClose} className="text-white/40 hover:text-white transform hover:rotate-90 transition-all p-2"><IconX size={26} /></button>
          </div>
          <div className="p-10">
             <div className="px-7 py-6 bg-slate-50 border border-slate-200 rounded-3xl mb-10 font-bold text-[14.5px] text-slate-800 leading-relaxed shadow-inner">
                <div className="text-[9px] text-slate-400 font-black uppercase tracking-[3px] mb-2 font-mono">PRODUCT REF: {product.id}</div>
                {safeString(product.name)}
             </div>
             <div className="mb-10 grid grid-cols-2 gap-4">
                {[
                  { v: 1, l: "T1", d: "完全相關 / 首選方案", c: "bg-green-50/10 border-green-600 text-green-900" },
                  { v: 2, l: "T2", d: "部分相關 / 地點明確", c: "bg-blue-50/10 border-blue-600 text-blue-900" },
                  { v: 3, l: "T3", d: "疑似相關 / 類別合理", c: "bg-orange-50/10 border-orange-600 text-orange-900" },
                  { v: 0, l: "MISS", d: "完全錯誤 / 非相關商品", c: "bg-red-50/10 border-red-600 text-red-900" }
                ].map(t => (
                  <button key={t.v} onClick={() => onTierChange(t.v)} className={`px-6 py-4 rounded-2xl border-2 text-left transition-all relative ${calibTier === t.v ? t.c + ' shadow-xl scale-[1.03] bg-white' : 'border-slate-100 bg-slate-50 text-slate-400'}`}>
                     <span className="text-[16px] font-black block">{t.l}</span>
                     <span className="text-[10px] font-bold opacity-70">{t.d}</span>
                  </button>
                ))}
             </div>
             <textarea value={calibComment} onChange={e => onCommentChange(e.target.value)} className="w-full h-28 bg-slate-100 border-2 border-slate-50 rounded-3xl p-6 text-[13px] font-bold focus:bg-white focus:border-indigo-500 transition-all outline-none resize-none mb-10 text-slate-900 shadow-inner" placeholder="請詳細輸入判定修正之邏輯原因..." />
             <div className="flex gap-6 items-center">
                <button onClick={onClose} className="flex-1 py-5 text-xs font-black text-slate-400 uppercase tracking-[4px] hover:text-slate-950 transition-colors">取消動作</button>
                <button onClick={onSubmit} className="flex-[2] py-5 bg-[#0F172A] text-white rounded-3xl text-[13px] font-black shadow-2xl hover:bg-black uppercase tracking-[6px] active:scale-95 transition-all">
                   儲存校正結果
                </button>
             </div>
          </div>
       </div>
    </div>
  )
}
