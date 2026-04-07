export default function KeywordEditorModal({ visible, kwInputText, onInputChange, onSave, onClose }) {
  if (!visible) return null;
  return (
    <div className="fixed inset-0 z-[600] flex items-center justify-center p-6 bg-slate-950/80 backdrop-blur-xl animate-in fade-in transition-all">
       <div className="absolute inset-0" onClick={onClose} />
       <div className="relative z-10 bg-white w-full max-w-[34rem] rounded-[2.5rem] shadow-2xl border border-white/20 overflow-hidden text-slate-900">
          <div className="bg-[#0F172A] px-10 py-7 text-white">
             <h2 className="text-xl font-black tracking-tight flex items-center gap-4">
                <span className="w-1.5 h-8 bg-indigo-500 rounded-full" />
                巡檢名單配置
             </h2>
          </div>
          <div className="p-10">
             <textarea value={kwInputText} onChange={e => onInputChange(e.target.value)} className="w-full h-80 bg-slate-100 border-2 border-slate-50 rounded-3xl p-6 text-[13px] font-bold focus:bg-white focus:border-indigo-500 transition-all outline-none resize-none mb-10 text-slate-900 shadow-inner" placeholder="esim, 日本旅遊, 大阪周遊券..." />
             <div className="flex gap-6 items-center">
                <button onClick={onClose} className="flex-1 py-5 text-xs font-black text-slate-400 uppercase tracking-[4px] hover:text-slate-950 transition-colors">取消</button>
                <button onClick={onSave} className="flex-[2] py-5 bg-[#0F172A] text-white rounded-3xl text-[13px] font-black shadow-2xl hover:bg-black uppercase tracking-[6px] active:scale-95 transition-all">儲存名單</button>
             </div>
          </div>
       </div>
    </div>
  )
}
