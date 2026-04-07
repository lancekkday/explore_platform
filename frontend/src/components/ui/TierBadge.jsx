export default function TierBadge({ it }) {
  if (!it) return null;
  const { tier = 0, is_calibrated = false } = it;
  const base = 'inline-flex items-center px-1.5 py-0.5 text-[8.5px] font-black rounded border whitespace-nowrap shadow-sm tracking-[1px] leading-none';
  if (is_calibrated) return <span className={`${base} bg-indigo-600 text-white border-indigo-700`}>🎯 校正</span>;
  if (tier === 1) return <span className={`${base} bg-emerald-50 text-emerald-900 border-emerald-200`}>T1 首選</span>;
  if (tier === 2) return <span className={`${base} bg-blue-50 text-blue-900 border-blue-200`}>T2 相關</span>;
  if (tier === 3) return <span className={`${base} bg-orange-50 text-orange-900 border-orange-200`}>T3 疑似</span>;
  return <span className={`${base} bg-rose-50 text-rose-800 border-rose-200`}>MISS</span>;
}
