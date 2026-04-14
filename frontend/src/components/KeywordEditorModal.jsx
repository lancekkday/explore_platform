export default function KeywordEditorModal({ visible, kwInputText, onInputChange, onSave, onClose }) {
  if (!visible) return null;

  const kwCount = kwInputText
    ? kwInputText.split(/[,\n]/).map(s => s.trim()).filter(s => s).length
    : 0;

  return (
    <div className="fixed inset-0 z-[600] flex items-center justify-center p-6 bg-slate-950/80 backdrop-blur-xl animate-in fade-in transition-all">
       <div className="absolute inset-0" onClick={onClose} />
       <div className="relative z-10 bg-white w-full max-w-[34rem] rounded-[2rem] shadow-2xl border border-slate-100 overflow-hidden text-slate-900">
          <div className="bg-white border-b border-slate-100 px-8 py-5 flex items-center justify-between">
             <div className="flex items-center gap-3">
                <span className="w-1 h-7 bg-indigo-500 rounded-full" />
                <div>
                   <h2 className="text-[15px] font-black tracking-tight text-slate-900">巡檢名單配置</h2>
                   <p className="text-[8px] font-black text-slate-400 uppercase tracking-[3px] mt-0.5">KEYWORD CONFIGURATION</p>
                </div>
             </div>
             <button onClick={onClose} className="text-slate-300 hover:text-slate-700 transition-colors text-xl leading-none">×</button>
          </div>
          <div className="px-8 py-6">
             <textarea
               value={kwInputText}
               onChange={e => onInputChange(e.target.value)}
               className="w-full h-72 bg-slate-50 border border-slate-200 rounded-2xl p-5 text-[13px] font-bold focus:bg-white focus:border-indigo-400 transition-all outline-none resize-none text-slate-900"
               placeholder="esim, 日本旅遊, 大阪周遊券..."
             />
             <div className="flex items-center justify-between mt-2.5 mb-6 px-1">
                <span className="text-[10px] font-black text-slate-400 font-mono">以逗號或換行分隔</span>
                <span className="text-[10px] font-black text-indigo-500 font-mono">共 {kwCount} 個關鍵字</span>
             </div>
             <div className="flex gap-3 items-center">
                <button onClick={onClose} className="flex-1 py-3 text-[11px] font-black text-slate-400 uppercase tracking-[3px] hover:text-slate-700 border border-slate-200 rounded-xl transition-all">取消</button>
                <button onClick={onSave} className="flex-[2] py-3 bg-indigo-600 text-white rounded-xl text-[12px] font-black shadow-md hover:bg-indigo-700 uppercase tracking-[4px] active:scale-95 transition-all">儲存名單</button>
             </div>
          </div>
       </div>
    </div>
  )
}
