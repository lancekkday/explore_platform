export default function Tooltip({ title, content, pos = 'up', children }) {
  const isUp = pos === 'up';
  if (!content) return children;
  return (
    <div className="relative group/tip cursor-help">
      {children}
      <div className={`absolute left-1/2 -translate-x-1/2 hidden group-hover/tip:flex flex-col z-[9999] bg-[#0F172AD9] backdrop-blur-md text-white p-4 rounded-2xl shadow-2xl border border-white/10 w-72 animate-in fade-in transition-all outline-none ${isUp ? 'bottom-full mb-3' : 'top-full mt-3'}`}>
        <div className="text-[11px] font-black text-indigo-400 border-b border-white/10 pb-2 mb-2.5 flex items-center gap-2">
          <div className="w-1.5 h-1.5 bg-indigo-500 rounded-full animate-pulse" />
          {title}
        </div>
        <div className="text-[11px] leading-relaxed text-slate-100 font-bold break-words whitespace-normal tracking-wide">{content}</div>
        <div className={`absolute left-1/2 -translate-x-1/2 w-4 h-4 bg-[#0F172AD9] rotate-45 border-white/10 ${isUp ? 'top-full -translate-y-2 border-r border-b' : 'bottom-full translate-y-2 border-l border-t'}`} />
      </div>
    </div>
  )
}
