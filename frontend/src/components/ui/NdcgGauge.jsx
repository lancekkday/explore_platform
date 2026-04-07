import Tooltip from './Tooltip'

export default function NdcgGauge({ value = 0, label, tooltip }) {
  const pct = isNaN(value) ? 0 : Math.round((value || 0) * 100);
  const stroke = pct >= 80 ? '#10B981' : pct >= 60 ? '#F59E0B' : '#EF4444';
  const glow = pct >= 80 ? '0 0 10px #10B98160' : 'none';
  const dash = `${pct} ${100 - pct}`;
  return (
    <Tooltip title={label} content={tooltip} pos="down">
      <div className="flex flex-col items-center gap-1 shrink-0 transition-transform hover:scale-105">
        <div className="relative w-8 h-8" style={{ filter: `drop-shadow(${glow})` }}>
          <svg viewBox="0 0 36 36" className="w-full h-full -rotate-90">
            <circle cx="18" cy="18" r="15.9" fill="none" stroke="#F1F5F9" strokeWidth="6" />
            <circle cx="18" cy="18" r="15.9" fill="none" stroke={stroke} strokeWidth="6" strokeDasharray={dash} strokeLinecap="round" />
          </svg>
          <span className="absolute inset-0 flex items-center justify-center text-[10px] font-black text-slate-800 font-mono tracking-tighter">{pct}%</span>
        </div>
        <span className="text-[7.5px] font-black text-slate-500 uppercase tracking-[1px]">{label}</span>
      </div>
    </Tooltip>
  )
}
