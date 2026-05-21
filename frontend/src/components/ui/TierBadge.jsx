const TIER_TIPS = {
  calibrated: '🎯 已人工校正\n此商品的 Tier 已由人工覆寫，優先於系統判定',
  1: 'T1 首選\n地點與類別完全符合搜尋意圖，為最佳匹配商品',
  2: 'T2 相關\n部分符合搜尋意圖（地點或類別其一吻合），屬合理相關商品',
  3: 'T3 疑似\n與搜尋意圖關聯性較低，僅在描述中提及或同國異城',
  0: 'MISS 誤判\n與搜尋意圖不符，不應出現在搜尋結果中',
}

export default function TierBadge({ it }) {
  if (!it) return null;
  const { tier = 0, is_calibrated = false } = it;
  const base = 'inline-flex items-center px-1.5 py-0.5 text-[9px] font-black rounded border whitespace-nowrap shadow-sm tracking-[0.5px] leading-none cursor-help';
  if (is_calibrated) return <span title={TIER_TIPS.calibrated} className={`${base} bg-indigo-600 text-white border-indigo-700`}>🎯 校正</span>;
  if (tier === 1) return <span title={TIER_TIPS[1]} className={`${base} bg-emerald-50 text-emerald-900 border-emerald-200`}>T1 首選</span>;
  if (tier === 2) return <span title={TIER_TIPS[2]} className={`${base} bg-blue-50 text-blue-900 border-blue-200`}>T2 相關</span>;
  if (tier === 3) return <span title={TIER_TIPS[3]} className={`${base} bg-orange-50 text-orange-900 border-orange-200`}>T3 疑似</span>;
  return <span title={TIER_TIPS[0]} className={`${base} bg-rose-50 text-rose-800 border-rose-200`}>MISS</span>;
}
