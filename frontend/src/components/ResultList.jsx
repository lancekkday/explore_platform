import { safeString } from '../utils/safeString'
import TierBadge from './ui/TierBadge'
import { IconTag } from './icons/Icons'

export default function ResultList({ items, title, total, color, onCalibrate, doubtOnly }) {
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
                       <div className="text-[13px] font-bold text-slate-800 truncate leading-tight select-all tracking-tight group-hover:text-slate-950 transition-colors" title={safeString(it.name)}>{safeString(it.name)}</div>
                       {it.mismatch_reasons && it.mismatch_reasons.length > 0 && (
                          <div className="mt-1 flex items-center gap-1.5 px-2 py-0.5 bg-rose-50/50 border border-rose-100/50 rounded text-[9px] font-black text-rose-500/80 italic leading-none w-fit">
                             <div className="w-1 h-1 bg-rose-400 rounded-full animate-pulse" />
                             {it.mismatch_reasons.join(' | ')}
                          </div>
                       )}
                       <div className="flex items-center gap-3 mt-1.5 opacity-70">
                          <span className="flex items-center gap-1 text-[9px] font-black text-slate-500">
                             <IconTag /><span className="uppercase tracking-[1px] leading-none">{safeString(it.main_cat_key) || "UNIDENTIFIED"}</span>
                          </span>
                          <span className="flex items-center gap-1 text-[9px] font-black text-slate-500">
                             <span className="uppercase tracking-[1px] leading-none">
                               {(() => {
                                  const dests = Array.isArray(it.destinations) ? it.destinations : [];
                                  if (dests.length === 0) return "GLOBAL";
                                  const first = dests[0];
                                  return typeof first === 'object' ? safeString(first.name) : safeString(first);
                               })()}
                             </span>
                          </span>
                       </div>
                    </div>
                    <div className="flex items-center gap-2.5 shrink-0">
                       <TierBadge it={it} />
                       <button onClick={() => onCalibrate(it)} className="h-7.5 px-4 rounded-lg border border-slate-200 bg-white text-slate-800 font-black text-[11px] shadow-sm hover:border-slate-800 hover:bg-slate-900 hover:text-white transition-all outline-none">
                          校正
                       </button>
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
