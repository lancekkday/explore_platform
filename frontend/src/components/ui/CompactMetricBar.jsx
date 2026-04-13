import Tooltip from './Tooltip'
import NdcgGauge from './NdcgGauge'

export default function CompactMetricBar({ data, color, env, envCode }) {
  if (!data) return (
    <div className="px-4 py-2 bg-slate-50 rounded-xl border border-dashed border-slate-200 text-slate-400 text-center font-black text-[9px] flex items-center justify-center gap-2">
       待命... {env}
    </div>
  );
  const m = data.metrics || {};
  // Detect legacy format: has tier_breakdown but no relevance_rate
  const tb = m.tier_breakdown || data.tier_breakdown;
  const tbTotal = tb?.total || 0;
  const isLegacy = tb && tbTotal > 0 && m.relevance_rate === undefined && data.relevance_rate === undefined;
  const fromTb = (field) => isLegacy ? (tb[field] || 0) / tbTotal : 0;
  const metrics = {
    ndcg_at_10:      m.ndcg_at_10  ?? m.ndcg_10  ?? data.ndcg_at_10  ?? data.ndcg_10  ?? 0,
    ndcg_at_50:      m.ndcg_at_50  ?? m.ndcg_50  ?? data.ndcg_at_50  ?? data.ndcg_50  ?? 0,
    ndcg_at_150:     m.ndcg_at_150 ?? m.ndcg_150 ?? data.ndcg_at_150 ?? data.ndcg_150 ?? 0,
    relevance_rate:  isLegacy ? fromTb('tier1') + fromTb('tier2') : (m.relevance_rate  ?? data.relevance_rate  ?? 0),
    tier3_rate:      isLegacy ? fromTb('tier3')                   : (m.tier3_rate      ?? data.tier3_rate      ?? 0),
    mismatch_rate:   isLegacy ? fromTb('mismatch')                : (m.mismatch_rate   ?? data.mismatch_rate   ?? 0),
  };

  const rel  = Math.round(metrics.relevance_rate * 100);
  const t3   = Math.round(metrics.tier3_rate     * 100);
  const miss = Math.round(metrics.mismatch_rate  * 100);

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
          <div className="flex items-center gap-3 border-r border-slate-100 pr-6">
             <NdcgGauge value={metrics.ndcg_at_10} label="NDCG@10" tooltip="衡量前 10 名商品的排序品質。影響首屏使用者體驗。" />
             <NdcgGauge value={metrics.ndcg_at_50} label="NDCG@50" tooltip="指標穩定度：前 50 名排序精確度。" />
             <NdcgGauge value={metrics.ndcg_at_150} label="NDCG@150" tooltip="反映長尾搜尋結果的意圖穩定性。" />
          </div>
          <div className="flex flex-col gap-1 min-w-[160px]">
             <div className="flex justify-between text-[9px] font-black font-mono">
               <Tooltip title="召回率" content="T1+T2 符合意圖的商品佔全部取回結果的比例。" pos="down">
                 <span className="text-emerald-600">{rel}% 相關</span>
               </Tooltip>
               <Tooltip title="鬆散相關 (T3)" content="商品與意圖有部分關聯但不精確，佔全部取回結果的比例。" pos="down">
                 <span className="text-amber-500">{t3}% T3</span>
               </Tooltip>
               <Tooltip title="誤判率" content="完全不符合意圖 (Miss) 的商品佔全部取回結果的比例。" pos="down">
                 <span className="text-rose-500">{miss}% 誤判</span>
               </Tooltip>
             </div>
             <div className="flex h-2 rounded-full overflow-hidden w-full">
               <div className="bg-emerald-400 transition-all" style={{ width: `${rel}%` }} />
               <div className="bg-amber-300 transition-all"  style={{ width: `${t3}%`  }} />
               <div className="bg-rose-400 transition-all"   style={{ width: `${miss}%` }} />
               <div className="bg-slate-100 flex-1" />
             </div>
          </div>
       </div>
    </div>
  )
}
