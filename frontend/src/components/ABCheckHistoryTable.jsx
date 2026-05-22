export default function ABCheckHistoryTable() {
  // 歷史 tab 詳細實作在 step 7 (列表 + 點 row 進 detail view 重用 RunPanel)。
  return (
    <div className="flex-1 overflow-y-auto bg-slate-50 px-4 py-3 custom-scroll">
      <div className="py-16 text-center text-[12px] text-slate-400">
        <div className="text-slate-300 text-[36px] mb-3">📜</div>
        <div>歷史紀錄 tab — step 7 接</div>
        <div className="text-[10px] mt-2">屆時會顯示最近 50 筆 run,點 row 可看詳細 alerts</div>
      </div>
    </div>
  )
}
