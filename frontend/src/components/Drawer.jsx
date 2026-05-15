function Ear({ active, type, onClick, label }) {
  const tone = type === 'exact'
    ? active
      ? 'bg-amber-600 text-white border-amber-600'
      : 'bg-amber-50 text-amber-800 border-amber-300 hover:bg-amber-100'
    : active
      ? 'bg-indigo-600 text-white border-indigo-600'
      : 'bg-indigo-50 text-indigo-700 border-indigo-300 hover:bg-indigo-100'

  return (
    <button
      onClick={onClick}
      className={`w-[22px] h-[68px] rounded-r-[6px] border border-l-0 flex items-center justify-center text-[10px] font-medium tracking-widest transition-colors ${tone}`}
      style={{ writingMode: 'vertical-rl', paddingTop: '2px' }}
    >
      {label}
    </button>
  )
}

export default function Drawer({
  drawerOpen,
  drawerType,
  setDrawerOpen,
  setDrawerType,
  preciseItems = [],
  broadItems = [],
}) {
  const items = drawerType === 'exact' ? preciseItems : drawerType === 'broad' ? broadItems : []
  const isOpen = !!drawerOpen && !!drawerType

  const toggle = (next) => {
    if (drawerType === next && drawerOpen) {
      setDrawerOpen(false)
      setDrawerType(null)
    } else {
      setDrawerType(next)
      setDrawerOpen(true)
    }
  }

  return (
    <div className="flex items-stretch shrink-0">
      <div
        className="overflow-hidden bg-white border-slate-200 rounded-md transition-[width] duration-200 ease-out"
        style={{
          width: isOpen ? '144px' : '0px',
          borderWidth: isOpen ? '1px' : '0px',
          marginRight: isOpen ? '6px' : '0px',
        }}
      >
        <div className="p-2.5 overflow-y-auto h-full">
          {items.length === 0 ? (
            <div className="text-[10px] text-slate-400">（無資料）</div>
          ) : (
            items.map((it, i) => {
              const isPrecise = drawerType === 'exact'
              const prefix = isPrecise
                ? `Top${i + 1}`
                : `#${it.profit_rank ?? i + 1}`
              const prefixCls = isPrecise
                ? 'text-amber-700'
                : 'text-indigo-700'
              const name = it.name || it.prod_nm || `#${it.prod_mid}`
              const href = it.prod_mid
                ? `https://www.stage.kkday.com/zh-tw/product/${it.prod_mid}`
                : undefined
              return (
                <a
                  key={it.prod_mid || i}
                  href={href}
                  target={href ? '_blank' : undefined}
                  rel={href ? 'noopener noreferrer' : undefined}
                  className={`flex items-baseline gap-1.5 py-1 leading-[1.4] transition-colors ${
                    href ? 'hover:bg-slate-50 cursor-pointer' : ''
                  } ${i === items.length - 1 ? '' : 'border-b border-slate-100'}`}
                  title={`${prefix} ${name}`}
                >
                  <span className={`text-[10px] font-semibold tabular-nums shrink-0 ${prefixCls}`}>
                    {prefix}
                  </span>
                  <span className={`text-[11px] truncate min-w-0 flex-1 ${
                    href ? 'text-slate-800 hover:text-indigo-600 hover:underline' : 'text-slate-800'
                  }`}>
                    {name}
                  </span>
                </a>
              )
            })
          )}
        </div>
      </div>
      <div className="flex flex-col gap-1.5 pt-1">
        <Ear
          type="exact"
          active={isOpen && drawerType === 'exact'}
          onClick={() => toggle('exact')}
          label="精準詞"
        />
        <Ear
          type="broad"
          active={isOpen && drawerType === 'broad'}
          onClick={() => toggle('broad')}
          label="泛詞"
        />
      </div>
    </div>
  )
}
