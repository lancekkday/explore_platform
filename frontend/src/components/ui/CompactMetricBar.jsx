import Tooltip from './Tooltip'
import NdcgGauge from './NdcgGauge'

export default function CompactMetricBar({ data, color, env, envCode }) {
  if (!data) return (
    <div className="px-4 py-2 bg-slate-50 rounded-xl border border-dashed border-slate-200 text-slate-400 text-center font-black text-[9px] flex items-center justify-center gap-2">
       待命... {env}
    </div>
  );
  const m = data.metrics || {};
  const metrics = {
    ndcg_at_10: m.ndcg_at_10 ?? m.ndcg_10 ?? data.ndcg_at_10 ?? data.ndcg_10 ?? 0,
    ndcg_at_50: m.ndcg_at_50 ?? m.ndcg_50 ?? data.ndcg_at_50 ?? data.ndcg_50 ?? 0,
    ndcg_at_150: m.ndcg_at_150 ?? m.ndcg_150 ?? m.ndcg_at_300 ?? data.ndcg_at_150 ?? data.ndcg_150 ?? data.ndcg_at_300 ?? 0,
    recall_at_150: m.recall_at_150 ?? m.recall_at_300 ?? data.recall_at_150 ?? data.recall_at_300 ?? 0,
    mismatch_rate: m.mismatch_rate ?? data.mismatch_rate ?? 0,
  };

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
             <NdcgGauge value={metrics.ndcg_at_150} label="NDCG@150" tooltip="反映長尾搜尋結果的意圖穩定性。" />
          </div>
          <div className="flex gap-6 px-1">
             <Tooltip title="召回率 (Recall)" content="衡量在 300 筆商品中，有多少比例是符合意圖的商品。" pos="down">
                <div className="flex flex-col text-center">
                  <span className="text-[8px] text-slate-400 font-black uppercase tracking-widest">召回</span>
                  <span className="text-[13px] font-black text-indigo-700 font-mono italic">{Math.round(metrics.recall_at_150*100)}%</span>
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
