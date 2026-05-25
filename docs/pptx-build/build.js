// Build deck: 搜尋巡檢平台 功能操作 + 判斷邏輯
const pptxgen = require('pptxgenjs')
const path = require('path')

const REPO = '/Users/lance.chien/Documents/Projects/search_intention/explore_platform/.claude/worktrees/ab-check-runner'
const IMG = (n) => path.join(REPO, 'docs/images', n)

// ── Palette mirrors the platform spec tokens ────────────────────────────────
const C = {
  // Backgrounds
  pageBg:       'F5F4F1',
  card:         'FFFFFF',
  darkSlate:    '1A1A1A',
  // Text
  primary:      '1A1A1A',
  secondary:    '5F5E5A',
  tertiary:     '888780',
  white:        'FFFFFF',
  // Status palette (from RunStatusBar)
  amber:        'EF9F27',
  amberBg:      'FAEEDA',
  amberDark:    '854F0B',
  amberBorder:  'F0D49B',
  green:        '1D9E75',
  greenBg:      'EAF7F1',
  greenDark:    '0F6E56',
  greenBorder:  'B7E2D2',
  red:          'E24B4A',
  redBg:        'FCEBEB',
  redDark:      '791F1F',
  blue:         '378ADD',
  blueDark:     '0C447C',
  blueBg:       'E6F1FB',
  purple:       '6C5CE7',
  purpleDark:   '3C3489',
  purpleBg:     'EEEDFE',
  // Hair lines
  hair:         'D8D6D2',
}

const FONT = 'Microsoft JhengHei'  // PowerPoint substitutes to PingFang TC on macOS
const FONT_MONO = 'Consolas'

const pres = new pptxgen()
pres.layout = 'LAYOUT_WIDE'  // 13.3 × 7.5
pres.author = 'KKDay QA Squad'
pres.title = '搜尋巡檢平台 — 功能操作 + 判斷邏輯'
pres.subject = 'PR #27 → #28 最新版'

const W = 13.3
const H = 7.5
const M = 0.6  // base margin

// ── Helpers ─────────────────────────────────────────────────────────────────
function pageBg(slide) {
  slide.background = { color: C.pageBg }
}
function pageNumber(slide, n, total) {
  slide.addText(`${n} / ${total}`, {
    x: W - 1.2, y: H - 0.5, w: 1.0, h: 0.3,
    fontFace: FONT, fontSize: 10, color: C.tertiary, align: 'right',
  })
}
function pageFooter(slide) {
  slide.addShape(pres.shapes.LINE, {
    x: M, y: H - 0.55, w: W - M*2, h: 0,
    line: { color: C.hair, width: 0.5 },
  })
  slide.addText('搜尋巡檢平台 · PR #27 → #28 · 2026-05-25', {
    x: M, y: H - 0.5, w: 8, h: 0.3,
    fontFace: FONT, fontSize: 10, color: C.tertiary,
  })
}
function pageTitle(slide, title, subtitle) {
  slide.addText(title, {
    x: M, y: 0.45, w: W - M*2, h: 0.7,
    fontFace: FONT, fontSize: 28, bold: true, color: C.primary, margin: 0,
  })
  if (subtitle) {
    slide.addText(subtitle, {
      x: M, y: 1.15, w: W - M*2, h: 0.4,
      fontFace: FONT, fontSize: 14, color: C.secondary, margin: 0,
    })
  }
  // Subtle accent
  slide.addShape(pres.shapes.RECTANGLE, {
    x: M, y: 1.55, w: 0.4, h: 0.04,
    fill: { color: C.amber }, line: { type: 'none' },
  })
}
function chip(slide, text, opts) {
  // opts: x, y, w, h, bg, fg
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x: opts.x, y: opts.y, w: opts.w, h: opts.h,
    fill: { color: opts.bg }, line: { type: 'none' }, rectRadius: 0.04,
  })
  slide.addText(text, {
    x: opts.x, y: opts.y, w: opts.w, h: opts.h,
    fontFace: FONT, fontSize: opts.fontSize || 11, color: opts.fg,
    align: 'center', valign: 'middle', margin: 0, bold: opts.bold || false,
  })
}
function dot(slide, x, y, color, size = 0.13) {
  slide.addShape(pres.shapes.OVAL, {
    x, y, w: size, h: size,
    fill: { color }, line: { type: 'none' },
  })
}

const TOTAL_SLIDES = 24
let n = 0
function next() { n++ }

// ── 1. Cover ────────────────────────────────────────────────────────────────
next()
{
  const s = pres.addSlide()
  s.background = { color: C.darkSlate }
  // Amber accent bar (left)
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 0.18, h: H,
    fill: { color: C.amber }, line: { type: 'none' },
  })
  s.addText('SEARCH AUDIT', {
    x: 0.9, y: 2.1, w: 10, h: 0.4,
    fontFace: FONT, fontSize: 14, color: C.amber, charSpacing: 8, margin: 0,
  })
  s.addText('搜尋巡檢平台', {
    x: 0.9, y: 2.5, w: 12, h: 1.1,
    fontFace: FONT, fontSize: 54, bold: true, color: C.white, margin: 0,
  })
  s.addText('功能操作 + 判斷邏輯講解', {
    x: 0.9, y: 3.65, w: 12, h: 0.7,
    fontFace: FONT, fontSize: 28, color: C.white, margin: 0,
  })
  // Divider
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.9, y: 4.6, w: 0.5, h: 0.04,
    fill: { color: C.amber }, line: { type: 'none' },
  })
  s.addText([
    { text: 'PR #27 → #28 最新版', options: { breakLine: true, bold: true } },
    { text: '2026-05-25', options: { breakLine: true } },
    { text: 'KKDay QA Squad' },
  ], {
    x: 0.9, y: 4.75, w: 9, h: 1.5,
    fontFace: FONT, fontSize: 14, color: C.white, margin: 0, paraSpaceAfter: 6,
  })
}

// ── 2. 目錄 ──────────────────────────────────────────────────────────────────
next()
{
  const s = pres.addSlide()
  pageBg(s)
  pageTitle(s, '目錄', '本場分兩段:操作面 · 判斷邏輯面')
  const items = [
    { idx: '01', title: '平台用途與使用者', col: 'left' },
    { idx: '02', title: 'UI 架構:兩條 route', col: 'left' },
    { idx: '03', title: '單詞巡檢操作流程', col: 'left' },
    { idx: '04', title: 'Filter:全部 / 差異 / 需關注', col: 'left' },
    { idx: '05', title: 'Alert bar 五個 bucket', col: 'left' },
    { idx: '06', title: '批次巡檢三 tab 結構', col: 'left' },
    { idx: '07', title: '批次 5 個 lifecycle 狀態', col: 'left' },
    { idx: '08', title: '嚴重度 hover popup', col: 'right' },
    { idx: '09', title: '歷史紀錄 + Resume', col: 'right' },
    { idx: '10', title: '判定邏輯 5 步驟', col: 'right' },
    { idx: '11', title: 'Tier 判定矩陣', col: 'right' },
    { idx: '12', title: '地點 + Category + 同義詞 AI', col: 'right' },
    { idx: '13', title: '人工校正 + Baseline pipeline', col: 'right' },
    { idx: '14', title: '系統架構 + PR 史', col: 'right' },
  ]
  const left = items.filter(it => it.col === 'left')
  const right = items.filter(it => it.col === 'right')
  const drawColumn = (arr, x0) => {
    arr.forEach((it, i) => {
      const y = 1.95 + i * 0.62
      s.addText(it.idx, {
        x: x0, y, w: 0.6, h: 0.5,
        fontFace: FONT_MONO, fontSize: 18, color: C.amber, bold: true, margin: 0,
      })
      s.addText(it.title, {
        x: x0 + 0.7, y, w: 5, h: 0.5,
        fontFace: FONT, fontSize: 15, color: C.primary, margin: 0, valign: 'top',
      })
    })
  }
  drawColumn(left, M + 0.2)
  drawColumn(right, W / 2 + 0.2)
  pageFooter(s)
  pageNumber(s, n, TOTAL_SLIDES)
}

// ── 3. 平台用途與使用者 ────────────────────────────────────────────────────
next()
{
  const s = pres.addSlide()
  pageBg(s)
  pageTitle(s, '平台用途', '稽核 KKDay 搜尋結果品質;支援 AB 演算法巡檢')
  // Left card: 用途
  const cardY = 2.0
  const cardH = 4.5
  const colW = (W - M*2 - 0.4) / 2
  // Card 1 — 用途
  s.addShape(pres.shapes.RECTANGLE, {
    x: M, y: cardY, w: colW, h: cardH,
    fill: { color: C.card }, line: { color: C.hair, width: 0.5 },
  })
  s.addShape(pres.shapes.RECTANGLE, {
    x: M, y: cardY, w: 0.08, h: cardH,
    fill: { color: C.amber }, line: { type: 'none' },
  })
  s.addText('平台用途', {
    x: M + 0.3, y: cardY + 0.3, w: colW - 0.4, h: 0.5,
    fontFace: FONT, fontSize: 18, bold: true, color: C.primary, margin: 0,
  })
  s.addText([
    { text: '單詞巡檢', options: { bold: true, breakLine: true, fontSize: 14 } },
    { text: '輸入關鍵字,即時看 A/B 兩版搜尋結果並排,每筆商品自動標 T1/T2/T3/MISS', options: { breakLine: true, fontSize: 12, color: C.secondary } },
    { text: ' ', options: { fontSize: 6, breakLine: true } },
    { text: '批次巡檢', options: { bold: true, breakLine: true, fontSize: 14 } },
    { text: '一鍵跑全 baseline 守門關鍵字,自動產異常報表,可中途取消、續跑', options: { breakLine: true, fontSize: 12, color: C.secondary } },
    { text: ' ', options: { fontSize: 6, breakLine: true } },
    { text: 'A/B 演算法對比', options: { bold: true, breakLine: true, fontSize: 14 } },
    { text: '透過 test_exp 參數比對不同演算法版本對 baseline 的衝擊', options: { fontSize: 12, color: C.secondary } },
  ], {
    x: M + 0.4, y: cardY + 0.95, w: colW - 0.6, h: cardH - 1.1,
    fontFace: FONT, fontSize: 13, color: C.primary, margin: 0, paraSpaceAfter: 2, valign: 'top',
  })
  // Card 2 — 使用者
  const x2 = M + colW + 0.4
  s.addShape(pres.shapes.RECTANGLE, {
    x: x2, y: cardY, w: colW, h: cardH,
    fill: { color: C.card }, line: { color: C.hair, width: 0.5 },
  })
  s.addShape(pres.shapes.RECTANGLE, {
    x: x2, y: cardY, w: 0.08, h: cardH,
    fill: { color: C.green }, line: { type: 'none' },
  })
  s.addText('目標使用者', {
    x: x2 + 0.3, y: cardY + 0.3, w: colW - 0.4, h: 0.5,
    fontFace: FONT, fontSize: 18, bold: true, color: C.primary, margin: 0,
  })
  s.addText([
    { text: 'QA Engineer', options: { bold: true, breakLine: true, fontSize: 14 } },
    { text: '新演算法上線前回歸測試:確認守門商品仍排在預期位置、未引入嚴重 regression', options: { breakLine: true, fontSize: 12, color: C.secondary } },
    { text: ' ', options: { fontSize: 6, breakLine: true } },
    { text: 'Product Manager', options: { bold: true, breakLine: true, fontSize: 14 } },
    { text: '單詞品質審視:對特定關鍵字看 A/B 兩版差異,評估上線決策', options: { breakLine: true, fontSize: 12, color: C.secondary } },
    { text: ' ', options: { fontSize: 6, breakLine: true } },
    { text: '搜尋演算法 RD', options: { bold: true, breakLine: true, fontSize: 14 } },
    { text: '改動 ranking 邏輯後,跑全 baseline 確認沒動到關鍵商品,測試版可由 test_exp 接入', options: { fontSize: 12, color: C.secondary } },
  ], {
    x: x2 + 0.4, y: cardY + 0.95, w: colW - 0.6, h: cardH - 1.1,
    fontFace: FONT, fontSize: 13, color: C.primary, margin: 0, paraSpaceAfter: 2, valign: 'top',
  })
  pageFooter(s)
  pageNumber(s, n, TOTAL_SLIDES)
}

// ── 4. UI 架構 ──────────────────────────────────────────────────────────────
next()
{
  const s = pres.addSlide()
  pageBg(s)
  pageTitle(s, 'UI 架構', '兩條 React Router route · 共用 AppHeader 與 BaselineStatusBanner')
  // ascii-like diagram
  const dgX = M + 0.3
  const dgY = 2.0
  const dgW = W - M*2 - 0.6
  // Header bar
  s.addShape(pres.shapes.RECTANGLE, {
    x: dgX, y: dgY, w: dgW, h: 0.6,
    fill: { color: C.card }, line: { color: C.hair, width: 0.5 },
  })
  s.addText('AppHeader — 搜尋巡檢平台   [ 巡檢 | 批次 ]   連線狀態 ⟳', {
    x: dgX + 0.2, y: dgY, w: dgW - 0.4, h: 0.6,
    fontFace: FONT, fontSize: 13, color: C.primary, valign: 'middle', margin: 0,
  })
  // Baseline banner row
  s.addShape(pres.shapes.RECTANGLE, {
    x: dgX, y: dgY + 0.65, w: dgW, h: 0.4,
    fill: { color: C.amberBg }, line: { color: C.amberBorder, width: 0.5 },
  })
  s.addText('BaselineStatusBanner — 條件出現:BQ fetch 失敗 / row 數量級異常', {
    x: dgX + 0.2, y: dgY + 0.65, w: dgW - 0.4, h: 0.4,
    fontFace: FONT, fontSize: 11, color: C.amberDark, valign: 'middle', margin: 0,
  })
  // Two route cards
  const routeY = dgY + 1.3
  const routeH = 3.5
  const routeW = (dgW - 0.4) / 2
  // Left: /巡檢
  s.addShape(pres.shapes.RECTANGLE, {
    x: dgX, y: routeY, w: routeW, h: routeH,
    fill: { color: C.card }, line: { color: C.hair, width: 0.5 },
  })
  s.addShape(pres.shapes.RECTANGLE, {
    x: dgX, y: routeY, w: routeW, h: 0.5,
    fill: { color: C.blueDark }, line: { type: 'none' },
  })
  s.addText('/ 巡檢  (HomePage)', {
    x: dgX + 0.2, y: routeY, w: routeW - 0.4, h: 0.5,
    fontFace: FONT, fontSize: 14, bold: true, color: C.white, valign: 'middle', margin: 0,
  })
  s.addText([
    { text: '單詞巡檢主畫面', options: { bold: true, breakLine: true, fontSize: 13 } },
    { text: '· 搜尋框 + 巡檢 / 下載 / 設定', options: { breakLine: true } },
    { text: '· Alert bar(baseline 異常分組)', options: { breakLine: true } },
    { text: '· Filter bar(全部 / 差異 / 需關注)', options: { breakLine: true } },
    { text: '· A 欄 / B 欄結果並排', options: { breakLine: true } },
    { text: '· 右側 Drawer(精準 / 泛詞 baseline)', options: { breakLine: true } },
    { text: ' ', options: { fontSize: 6, breakLine: true } },
    { text: '搜尋狀態(keyword + filter + results)放 AppContext,從 /批次 切回不會被重設', options: { fontSize: 11, color: C.secondary } },
  ], {
    x: dgX + 0.3, y: routeY + 0.7, w: routeW - 0.5, h: routeH - 0.9,
    fontFace: FONT, fontSize: 12, color: C.primary, margin: 0, paraSpaceAfter: 2, valign: 'top',
  })
  // Right: /批次
  const r2 = dgX + routeW + 0.4
  s.addShape(pres.shapes.RECTANGLE, {
    x: r2, y: routeY, w: routeW, h: routeH,
    fill: { color: C.card }, line: { color: C.hair, width: 0.5 },
  })
  s.addShape(pres.shapes.RECTANGLE, {
    x: r2, y: routeY, w: routeW, h: 0.5,
    fill: { color: C.amberDark }, line: { type: 'none' },
  })
  s.addText('/ 批次  (BatchPage)', {
    x: r2 + 0.2, y: routeY, w: routeW - 0.4, h: 0.5,
    fontFace: FONT, fontSize: 14, bold: true, color: C.white, valign: 'middle', margin: 0,
  })
  s.addText([
    { text: '批次巡檢三 sub-tab', options: { bold: true, breakLine: true, fontSize: 13 } },
    { text: '· 精準詞 — 跑全部精準詞 baseline (~189)', options: { breakLine: true } },
    { text: '· 泛詞 — 跑全部泛詞 baseline (~59)', options: { breakLine: true } },
    { text: '· 歷史紀錄 — 最近 50 筆 run', options: { breakLine: true } },
    { text: ' ', options: { fontSize: 6, breakLine: true } },
    { text: 'PR #27 改成 async + sqlite checkpoint', options: { bold: true, fontSize: 12, breakLine: true, color: C.amberDark } },
    { text: '· 中途可取消 · 可從中斷處續跑', options: { breakLine: true } },
    { text: '· Polling timer 跨 route 存活,切到 /巡檢 仍持續跑', options: { fontSize: 11, color: C.secondary } },
  ], {
    x: r2 + 0.3, y: routeY + 0.7, w: routeW - 0.5, h: routeH - 0.9,
    fontFace: FONT, fontSize: 12, color: C.primary, margin: 0, paraSpaceAfter: 2, valign: 'top',
  })
  pageFooter(s)
  pageNumber(s, n, TOTAL_SLIDES)
}

// ── 5. 單詞巡檢操作流程 ────────────────────────────────────────────────────
next()
{
  const s = pres.addSlide()
  pageBg(s)
  pageTitle(s, '單詞巡檢:5 步流程', '從輸入關鍵字到看到判定結果')
  // Step blocks horizontal
  const steps = [
    { n: '1', title: '輸入關鍵字', body: '搜尋框打字,按 Enter 或點「巡檢」', color: C.blueDark },
    { n: '2', title: 'A/B 並排取結果', body: '同時呼叫 test_exp=A 與 test_exp=B,各拿前 300 筆', color: C.blueDark },
    { n: '3', title: 'Tier 自動標註', body: '每筆商品依規則 + AI 救回,輸出 T1/T2/T3/MISS', color: C.amberDark },
    { n: '4', title: 'Baseline 標記', body: '守門商品標 Top1/Top2 或 泛#N,異常進 Alert bar', color: C.amberDark },
    { n: '5', title: '使用者切換視圖', body: '全部 / 差異 / 需關注,Drawer 看守門商品全清單', color: C.green },
  ]
  const sx = 0.65
  const sy = 2.1
  const sw = (W - sx*2 - (steps.length-1)*0.2) / steps.length
  const sh = 3.8
  steps.forEach((step, i) => {
    const x = sx + i*(sw + 0.2)
    s.addShape(pres.shapes.RECTANGLE, {
      x, y: sy, w: sw, h: sh,
      fill: { color: C.card }, line: { color: C.hair, width: 0.5 },
    })
    // Top color band
    s.addShape(pres.shapes.RECTANGLE, {
      x, y: sy, w: sw, h: 0.08,
      fill: { color: step.color }, line: { type: 'none' },
    })
    // Big step number
    s.addText(step.n, {
      x: x + 0.2, y: sy + 0.3, w: 1.0, h: 1.2,
      fontFace: FONT, fontSize: 56, bold: true, color: step.color, margin: 0,
    })
    s.addText(step.title, {
      x: x + 0.2, y: sy + 1.6, w: sw - 0.4, h: 0.6,
      fontFace: FONT, fontSize: 15, bold: true, color: C.primary, margin: 0,
    })
    s.addText(step.body, {
      x: x + 0.2, y: sy + 2.2, w: sw - 0.4, h: 1.4,
      fontFace: FONT, fontSize: 11, color: C.secondary, margin: 0, valign: 'top',
    })
  })
  pageFooter(s)
  pageNumber(s, n, TOTAL_SLIDES)
}

// ── 6. A/B 並排顯示 ────────────────────────────────────────────────────────
next()
{
  const s = pres.addSlide()
  pageBg(s)
  pageTitle(s, 'A/B 並排顯示', 'test_exp 切換演算法版本 · 同一商品跨欄位 rank 用 ▲▼ 標')
  // Two columns
  const cy = 2.0
  const ch = 4.6
  const cw = (W - M*2 - 0.3) / 2
  // A col
  s.addShape(pres.shapes.RECTANGLE, {
    x: M, y: cy, w: cw, h: ch,
    fill: { color: C.card }, line: { color: C.hair, width: 0.5 },
  })
  chip(s, 'TEST_EXP  [ 0 ]', { x: M + 0.3, y: cy + 0.3, w: 1.5, h: 0.35, bg: C.blueBg, fg: C.blueDark, fontSize: 11 })
  s.addText('A', {
    x: M + 0.3, y: cy + 0.75, w: 0.5, h: 0.5,
    fontFace: FONT, fontSize: 24, bold: true, color: C.primary, margin: 0,
  })
  s.addText('@10  100   @50  96   @150  99', {
    x: cw - 3.4 + M, y: cy + 0.85, w: 3.0, h: 0.35,
    fontFace: FONT_MONO, fontSize: 11, color: C.tertiary, align: 'right', margin: 0,
  })
  // Sample row 1
  const rowA = (idx, y) => {
    s.addText(`#${idx}`, { x: M + 0.3, y, w: 0.5, h: 0.4, fontFace: FONT_MONO, fontSize: 13, color: C.tertiary, margin: 0 })
    chip(s, 'Top1', { x: M + 0.85, y: y + 0.05, w: 0.5, h: 0.3, bg: C.amberBg, fg: C.amberDark, fontSize: 9 })
    s.addText('日本吉卜力公園門票…', { x: M + 1.45, y, w: cw - 3.5, h: 0.4, fontFace: FONT, fontSize: 12, color: C.primary, margin: 0 })
    chip(s, 'T1', { x: cw - 1.5 + M, y: y + 0.05, w: 0.4, h: 0.3, bg: C.greenBg, fg: C.greenDark, fontSize: 9 })
    s.addText('B#1 ▲', { x: cw - 1.0 + M, y, w: 0.6, h: 0.4, fontFace: FONT, fontSize: 11, color: C.green, margin: 0, bold: true })
  }
  rowA(1, cy + 1.6)
  rowA(4, cy + 2.2)
  s.addText('…', { x: M + 0.4, y: cy + 3.0, w: 0.4, h: 0.3, fontFace: FONT, fontSize: 16, color: C.tertiary, margin: 0 })

  // B col
  const x2 = M + cw + 0.3
  s.addShape(pres.shapes.RECTANGLE, {
    x: x2, y: cy, w: cw, h: ch,
    fill: { color: C.card }, line: { color: C.hair, width: 0.5 },
  })
  chip(s, '[ 1 ]  TEST_EXP', { x: x2 + cw - 1.8, y: cy + 0.3, w: 1.5, h: 0.35, bg: C.purpleBg, fg: C.purpleDark, fontSize: 11 })
  s.addText('B', {
    x: x2 + cw - 0.8, y: cy + 0.75, w: 0.5, h: 0.5,
    fontFace: FONT, fontSize: 24, bold: true, color: C.primary, margin: 0, align: 'right',
  })
  s.addText('@10  52   @50  40   @150  44', {
    x: x2 + 0.3, y: cy + 0.85, w: 3.0, h: 0.35,
    fontFace: FONT_MONO, fontSize: 11, color: C.tertiary, margin: 0,
  })
  const rowB = (idx, y, cross, dir) => {
    s.addText(`#${idx}`, { x: x2 + 0.3, y, w: 0.5, h: 0.4, fontFace: FONT_MONO, fontSize: 13, color: C.tertiary, margin: 0 })
    chip(s, 'Top2', { x: x2 + 0.85, y: y + 0.05, w: 0.5, h: 0.3, bg: C.amberBg, fg: C.amberDark, fontSize: 9 })
    s.addText('【吉卜力公園接送】…', { x: x2 + 1.45, y, w: cw - 3.5, h: 0.4, fontFace: FONT, fontSize: 12, color: C.primary, margin: 0 })
    chip(s, 'T2', { x: x2 + cw - 1.5, y: y + 0.05, w: 0.4, h: 0.3, bg: C.purpleBg, fg: C.purpleDark, fontSize: 9 })
    s.addText(cross, { x: x2 + cw - 1.0, y, w: 0.7, h: 0.4, fontFace: FONT, fontSize: 11, color: dir === '▼' ? C.red : C.green, margin: 0, bold: true })
  }
  rowB(149, cy + 1.6, 'A#4 ▼', '▼')
  rowB(155, cy + 2.2, 'A#7 ▼', '▼')
  s.addText('…', { x: x2 + 0.4, y: cy + 3.0, w: 0.4, h: 0.3, fontFace: FONT, fontSize: 16, color: C.tertiary, margin: 0 })
  // Caption
  s.addText('• 切到「差異」filter 後,只剩 baseline 守門商品;每筆顯示跨欄位排名 + 方向箭頭', {
    x: M, y: cy + ch + 0.2, w: W - M*2, h: 0.3,
    fontFace: FONT, fontSize: 11, color: C.secondary, margin: 0,
  })
  pageFooter(s)
  pageNumber(s, n, TOTAL_SLIDES)
}

// ── 7. Filter bar 三態 ────────────────────────────────────────────────────
next()
{
  const s = pres.addSlide()
  pageBg(s)
  pageTitle(s, 'Filter bar 三態', '主畫面切換視角,挑出需要關心的商品')
  const items = [
    { label: '全部', count: 'N', desc: '顯示主搜尋的所有商品(A/B 各最多 300 筆)', color: C.primary, bg: C.card },
    { label: '⇄ 差異', count: 'M', desc: 'A/B 兩欄都只剩 baseline 守門商品(精準 Top1/Top2 + 泛 #1~#10,合併最多 12 筆),跨欄位顯示 B#N ▲▼', color: C.blueDark, bg: C.blueBg },
    { label: '🔔 需關注', count: 'K', desc: '過濾出符合 4 個判定條件之一的商品(下一頁詳述)— 不限 Tier,T1 也可能落進', color: C.amberDark, bg: C.amberBg },
  ]
  const ix = 0.65
  const iy = 2.0
  const ih = 3.8
  const iw = (W - ix*2 - 0.4) / 3
  items.forEach((it, i) => {
    const x = ix + i*(iw + 0.2)
    s.addShape(pres.shapes.RECTANGLE, {
      x, y: iy, w: iw, h: ih,
      fill: { color: C.card }, line: { color: C.hair, width: 0.5 },
    })
    // Chip header
    s.addShape(pres.shapes.RECTANGLE, {
      x: x + 0.3, y: iy + 0.4, w: iw - 0.6, h: 0.6,
      fill: { color: it.bg }, line: { type: 'none' },
    })
    s.addText(it.label, {
      x: x + 0.3, y: iy + 0.4, w: iw - 0.6, h: 0.6,
      fontFace: FONT, fontSize: 18, bold: true, color: it.color,
      align: 'center', valign: 'middle', margin: 0,
    })
    s.addText(it.count, {
      x: x + 0.3, y: iy + 1.15, w: iw - 0.6, h: 1.2,
      fontFace: FONT, fontSize: 60, bold: true, color: it.color, align: 'center', margin: 0,
    })
    s.addText('筆', {
      x: x + 0.3, y: iy + 2.3, w: iw - 0.6, h: 0.3,
      fontFace: FONT, fontSize: 11, color: C.tertiary, align: 'center', margin: 0,
    })
    s.addText(it.desc, {
      x: x + 0.3, y: iy + 2.7, w: iw - 0.6, h: ih - 2.9,
      fontFace: FONT, fontSize: 11, color: C.secondary, align: 'center', valign: 'top', margin: 0,
    })
  })
  s.addText('差異與需關注互斥;點同一個再點一次切回「全部」', {
    x: M, y: iy + ih + 0.2, w: W - M*2, h: 0.3,
    fontFace: FONT, fontSize: 11, color: C.tertiary, align: 'center', margin: 0,
  })
  pageFooter(s)
  pageNumber(s, n, TOTAL_SLIDES)
}

// ── 8. 需關注 4 條件 ★ ────────────────────────────────────────────────────
next()
{
  const s = pres.addSlide()
  pageBg(s)
  pageTitle(s, '「需關注」 4 條件', '任一成立就進列表 — 跟 Tier 無關,T1 也可能落進')
  const rules = [
    { idx: '①', title: 'T3 / MISS', cond: 'tier === 0 (MISS) 或 tier === 3 (T3 弱關聯)', why: '分類本身已不理想,應該被關注', color: C.red },
    { idx: '②', title: '已校正過', cond: 'is_calibrated === true', why: '人工校正過的商品,無論 Tier 都值得 review 是否仍恰當', color: C.blueDark },
    { idx: '③', title: 'Baseline 守門掉名', cond: 'baseline_tag 存在 AND rank > expected × BASELINE_DROP_MULTIPLIER (預設 3 倍)', why: '即使 T1,如果排名掉太多也算 ranking regression', color: C.amberDark },
    { idx: '④', title: 'A vs B 排名差 ≥ 5', cond: '同商品 |a_rank − b_rank| ≥ 5', why: '即使 T1,兩版差太多代表演算法不一致,要 review', color: C.purpleDark },
  ]
  const sx = M
  const sy = 1.9
  const sh = 1.05
  rules.forEach((r, i) => {
    const y = sy + i*(sh + 0.12)
    s.addShape(pres.shapes.RECTANGLE, {
      x: sx, y, w: W - M*2, h: sh,
      fill: { color: C.card }, line: { color: C.hair, width: 0.5 },
    })
    s.addShape(pres.shapes.RECTANGLE, {
      x: sx, y, w: 0.08, h: sh,
      fill: { color: r.color }, line: { type: 'none' },
    })
    s.addText(r.idx, {
      x: sx + 0.3, y, w: 0.7, h: sh,
      fontFace: FONT, fontSize: 38, bold: true, color: r.color, valign: 'middle', margin: 0,
    })
    s.addText(r.title, {
      x: sx + 1.1, y: y + 0.1, w: 3.5, h: 0.5,
      fontFace: FONT, fontSize: 16, bold: true, color: C.primary, margin: 0,
    })
    s.addText(r.cond, {
      x: sx + 1.1, y: y + 0.55, w: 5.5, h: 0.4,
      fontFace: FONT_MONO, fontSize: 11, color: C.secondary, margin: 0,
    })
    s.addText(r.why, {
      x: sx + 6.8, y: y + 0.15, w: W - sx - 7.4 - M, h: sh - 0.3,
      fontFace: FONT, fontSize: 11.5, color: C.primary, valign: 'middle', margin: 0,
    })
  })
  // Bottom note
  s.addText('要減少 T1 落進「需關注」:在 設定 → 把 BASELINE_DROP_MULTIPLIER 調大(預設 3)', {
    x: M, y: sy + 4*(sh + 0.12) + 0.05, w: W - M*2, h: 0.4,
    fontFace: FONT, fontSize: 12, color: C.amberDark, margin: 0, italic: true,
  })
  pageFooter(s)
  pageNumber(s, n, TOTAL_SLIDES)
}

// ── 9. Alert bar 五個 bucket ────────────────────────────────────────────────
next()
{
  const s = pres.addSlide()
  pageBg(s)
  pageTitle(s, 'Alert bar — Baseline 異常 5 個 bucket', '主畫面上方按異常類型分組,chip 直連 stage 商品頁')
  const buckets = [
    { name: 'A、B 雙消失', cond: '商品在 A 與 B 兩版都找不到', ex: '[Top1] 商品 (A,B)', sev: 'P0', color: C.red },
    { name: 'B 消失', cond: '商品在 A 出現、B 完全找不到', ex: '[泛#3] 商品名', sev: 'P0/P1', color: C.red },
    { name: 'A 消失', cond: '商品在 B 出現、A 完全找不到', ex: '[泛#5] 商品名', sev: 'INFO', color: C.amber },
    { name: 'A vs B 變動 > 5', cond: '同商品 A vs B 排名差距 > 5 名', ex: '[泛#7] 商品名 (B 低)', sev: 'P1/P2', color: C.purple },
    { name: 'A 排名偏離 baseline', cond: '在 A 排名 > expected × 3 倍', ex: '[Top2] 商品名', sev: 'INFO', color: C.amber },
  ]
  // Table headers
  const cy = 2.0
  const ch = 0.5
  s.addShape(pres.shapes.RECTANGLE, {
    x: M, y: cy, w: W - M*2, h: ch,
    fill: { color: C.darkSlate }, line: { type: 'none' },
  })
  const cols = [
    { x: M + 0.2, w: 2.6, label: '類別' },
    { x: M + 2.9, w: 4.2, label: '觸發條件' },
    { x: M + 7.2, w: 3.0, label: '範例' },
    { x: M + 10.3, w: 1.5, label: '嚴重度' },
  ]
  cols.forEach(c => {
    s.addText(c.label, {
      x: c.x, y: cy, w: c.w, h: ch,
      fontFace: FONT, fontSize: 11, color: C.white, bold: true, valign: 'middle', margin: 0, charSpacing: 4,
    })
  })
  const rh = 0.7
  buckets.forEach((b, i) => {
    const y = cy + ch + i * rh
    s.addShape(pres.shapes.RECTANGLE, {
      x: M, y, w: W - M*2, h: rh,
      fill: { color: i % 2 === 0 ? C.card : C.pageBg }, line: { color: C.hair, width: 0.5 },
    })
    s.addText(b.name, {
      x: cols[0].x, y, w: cols[0].w, h: rh,
      fontFace: FONT, fontSize: 12.5, bold: true, color: C.primary, valign: 'middle', margin: 0,
    })
    s.addText(b.cond, {
      x: cols[1].x, y, w: cols[1].w, h: rh,
      fontFace: FONT, fontSize: 11, color: C.secondary, valign: 'middle', margin: 0,
    })
    s.addText(b.ex, {
      x: cols[2].x, y, w: cols[2].w, h: rh,
      fontFace: FONT_MONO, fontSize: 11, color: C.tertiary, valign: 'middle', margin: 0,
    })
    chip(s, b.sev, { x: cols[3].x, y: y + 0.18, w: cols[3].w - 0.3, h: 0.35, bg: b.color, fg: C.white, fontSize: 11, bold: true })
  })
  pageFooter(s)
  pageNumber(s, n, TOTAL_SLIDES)
}

// ── 10. 批次巡檢三 tab 結構 ─────────────────────────────────────────────────
next()
{
  const s = pres.addSlide()
  pageBg(s)
  pageTitle(s, '批次巡檢 · 三 sub-tab 結構', 'PR #27 改成 async + sqlite checkpoint,每筆 query 跑完即時更新')
  const tabs = [
    { name: '精準詞', range: '~189 個 query', desc: 'Top1/Top2 高成交商品的守門 baseline · 跑完約 5-8 分鐘', color: C.blueDark, bg: C.blueBg },
    { name: '泛詞', range: '~59 個 query', desc: 'Profit rank 1-10 的廣度 baseline · 跑完約 2-3 分鐘', color: C.purpleDark, bg: C.purpleBg },
    { name: '歷史紀錄', range: '最近 50 筆', desc: '可篩 type;點 row 進 detail 看當時 checkpoint + alerts', color: C.amberDark, bg: C.amberBg },
  ]
  const tx = M
  const ty = 2.0
  const th = 2.5
  const tw = (W - M*2 - 0.4) / 3
  tabs.forEach((t, i) => {
    const x = tx + i * (tw + 0.2)
    s.addShape(pres.shapes.RECTANGLE, {
      x, y: ty, w: tw, h: th,
      fill: { color: C.card }, line: { color: C.hair, width: 0.5 },
    })
    s.addShape(pres.shapes.RECTANGLE, {
      x, y: ty, w: tw, h: 0.06,
      fill: { color: t.color }, line: { type: 'none' },
    })
    s.addText(t.name, {
      x: x + 0.3, y: ty + 0.25, w: tw - 0.5, h: 0.5,
      fontFace: FONT, fontSize: 20, bold: true, color: C.primary, margin: 0,
    })
    s.addText(t.range, {
      x: x + 0.3, y: ty + 0.85, w: tw - 0.5, h: 0.4,
      fontFace: FONT_MONO, fontSize: 13, color: t.color, margin: 0,
    })
    s.addText(t.desc, {
      x: x + 0.3, y: ty + 1.3, w: tw - 0.5, h: th - 1.5,
      fontFace: FONT, fontSize: 12, color: C.secondary, margin: 0, valign: 'top',
    })
  })
  // Highlights below
  const hy = ty + th + 0.5
  s.addText('PR #27 三大關鍵差異', {
    x: M, y: hy, w: W - M*2, h: 0.4,
    fontFace: FONT, fontSize: 16, bold: true, color: C.primary, margin: 0,
  })
  const highlights = [
    { t: '✓ 中途可取消', d: 'Worker 在下個 query boundary 退出,已跑完的 row 保留' },
    { t: '✓ 從中斷處續跑', d: 'parent ok 的 row 複製到新 run · 嚴格驗證 baseline 不變才繼續' },
    { t: '✓ 跨 SPA route 存活', d: 'Polling timer 放 AppContextProvider · 切到 /巡檢 仍持續推進' },
  ]
  const hx0 = M
  const hh = 0.65
  const hwSingle = (W - M*2 - 0.4) / 3
  highlights.forEach((h, i) => {
    const x = hx0 + i*(hwSingle + 0.2)
    s.addShape(pres.shapes.RECTANGLE, {
      x, y: hy + 0.5, w: hwSingle, h: hh*2,
      fill: { color: C.card }, line: { color: C.hair, width: 0.5 },
    })
    s.addText(h.t, {
      x: x + 0.2, y: hy + 0.6, w: hwSingle - 0.4, h: 0.45,
      fontFace: FONT, fontSize: 13, bold: true, color: C.green, margin: 0,
    })
    s.addText(h.d, {
      x: x + 0.2, y: hy + 1.05, w: hwSingle - 0.4, h: 0.7,
      fontFace: FONT, fontSize: 11, color: C.secondary, margin: 0, valign: 'top',
    })
  })
  pageFooter(s)
  pageNumber(s, n, TOTAL_SLIDES)
}

// ── 11. Lifecycle: Empty ────────────────────────────────────────────────────
next()
function lifecycleSlide(title, subtitle, imgPath, leftBullets) {
  const s = pres.addSlide()
  pageBg(s)
  pageTitle(s, title, subtitle)
  // Left text card
  const cy = 2.0
  const ch = 4.6
  const lw = 4.2
  s.addShape(pres.shapes.RECTANGLE, {
    x: M, y: cy, w: lw, h: ch,
    fill: { color: C.card }, line: { color: C.hair, width: 0.5 },
  })
  s.addText(leftBullets, {
    x: M + 0.3, y: cy + 0.3, w: lw - 0.6, h: ch - 0.6,
    fontFace: FONT, fontSize: 12.5, color: C.primary, margin: 0, paraSpaceAfter: 5, valign: 'top',
  })
  // Right image — calc to fit
  const ix = M + lw + 0.3
  const iw = W - ix - M
  const ih = iw / 1.63  // image aspect
  let imgW = iw
  let imgH = ih
  if (imgH > ch) {
    imgH = ch
    imgW = imgH * 1.63
  }
  const imgX = ix + (iw - imgW) / 2
  const imgY = cy + (ch - imgH) / 2
  s.addImage({ path: imgPath, x: imgX, y: imgY, w: imgW, h: imgH })
  pageFooter(s)
  pageNumber(s, n, TOTAL_SLIDES)
  return s
}

lifecycleSlide(
  '批次 Lifecycle ①  空狀態',
  '尚未啟動 — 只有設定列 + 空狀態提示',
  IMG('batch-01-empty.png'),
  [
    { text: 'UI 元素', options: { bold: true, fontSize: 14, breakLine: true } },
    { text: '· 頂端 Section Header(區塊名 + 3 sub-tab)', options: { breakLine: true } },
    { text: '· 設定列:LIMIT input + A/B 演算法 chip + 啟動 button', options: { breakLine: true } },
    { text: '· 空狀態提示 + 圖示', options: { breakLine: true } },
    { text: ' ', options: { fontSize: 8, breakLine: true } },
    { text: 'LIMIT 留空 = 全跑', options: { bold: true, fontSize: 13, breakLine: true, color: C.amberDark } },
    { text: '· 精準詞 → ~189 個 query', options: { breakLine: true, fontSize: 11, color: C.secondary } },
    { text: '· 泛詞 → ~59 個 query', options: { breakLine: true, fontSize: 11, color: C.secondary } },
    { text: ' ', options: { fontSize: 8, breakLine: true } },
    { text: '精準詞 + 泛詞可同時啟動,各跑各的,互不影響', options: { fontSize: 11, color: C.secondary, italic: true } },
  ]
)

// ── 12. Lifecycle: Running ──────────────────────────────────────────────────
next()
lifecycleSlide(
  '批次 Lifecycle ②  Running 執行中',
  '無大塊 status bar — 只有 inline 進度行 + 表格 row 狀態點',
  IMG('batch-02-running.png'),
  [
    { text: 'UI 設計(spec §5.3 Q1)', options: { bold: true, fontSize: 14, breakLine: true } },
    { text: '· 配置列右側「取消」紅 outline 按鈕取代啟動', options: { breakLine: true } },
    { text: '· 細進度行:「進度 N/M · 跑到 #idx <query>」 + 細藍進度條', options: { breakLine: true } },
    { text: '· 表格 row 即時換狀態點', options: { breakLine: true } },
    { text: ' ', options: { fontSize: 8, breakLine: true } },
    { text: '行內狀態 dots', options: { bold: true, fontSize: 13, breakLine: true } },
    { text: '○ 等待  ●(藍 pulse)執行中  ●(綠)完成  ●(紅)失敗', options: { fontFace: FONT, fontSize: 11, color: C.secondary, breakLine: true } },
    { text: ' ', options: { fontSize: 8, breakLine: true } },
    { text: '切到其他 tab 或 /巡檢,run 不會中斷', options: { fontSize: 12, color: C.green, italic: true, breakLine: true } },
    { text: '(polling timer 在 AppContextProvider · 跨 route 存活)', options: { fontSize: 10, color: C.tertiary } },
  ]
)

// ── 13. Lifecycle: Cancelled ────────────────────────────────────────────────
next()
lifecycleSlide(
  '批次 Lifecycle ③  Cancelled / Interrupted',
  '橘色 status bar + 續跑 CTA + 待續跑黃 row',
  IMG('batch-03-cancelled.png'),
  [
    { text: '出現條件', options: { bold: true, fontSize: 14, breakLine: true } },
    { text: '· 使用者點「取消」', options: { breakLine: true } },
    { text: '· Backend 重啟 — startup sweep 把 DB 還在 running 的 run 標 interrupted', options: { breakLine: true } },
    { text: ' ', options: { fontSize: 8, breakLine: true } },
    { text: 'Status Bar 內容', options: { bold: true, fontSize: 13, breakLine: true, color: C.amberDark } },
    { text: '· ⏸ icon + 已中斷 + run_id(可複製)', options: { breakLine: true } },
    { text: '· 「剩下 N 個 query 未跑」副標', options: { breakLine: true } },
    { text: '· 橘色進度條(已跑 / 總數)', options: { breakLine: true } },
    { text: '· 「續跑剩下 N 個」CTA(橘實心 button)', options: { breakLine: true } },
    { text: ' ', options: { fontSize: 8, breakLine: true } },
    { text: '尚未跑的 row 套淡黃底 + 「• 待續跑」狀態點', options: { fontSize: 12, color: C.amberDark, italic: true } },
  ]
)

// ── 14. Lifecycle: Done ─────────────────────────────────────────────────────
next()
lifecycleSlide(
  '批次 Lifecycle ④  Done 完成',
  '綠色 status bar + summary pills · 重新啟動會先彈 confirm 防誤丟',
  IMG('batch-04-done.png'),
  [
    { text: '出現條件', options: { bold: true, fontSize: 14, breakLine: true } },
    { text: '· 全部 query 跑完(包含 ok / error)', options: { breakLine: true } },
    { text: ' ', options: { fontSize: 8, breakLine: true } },
    { text: 'Status Bar 內容', options: { bold: true, fontSize: 13, breakLine: true, color: C.greenDark } },
    { text: '· ✓ icon + 完成 + run_id + 複製按鈕', options: { breakLine: true } },
    { text: '· 完整綠色進度條(N/N)', options: { breakLine: true } },
    { text: '· Summary pills:P0 N · P1 N · P2 N · INFO N', options: { breakLine: true } },
    { text: ' ', options: { fontSize: 8, breakLine: true } },
    { text: '「重新啟動新一輪」按鈕', options: { bold: true, fontSize: 13, breakLine: true } },
    { text: '會先彈 confirm dialog,避免誤丟現有 run 結果', options: { fontSize: 11, color: C.secondary, italic: true } },
  ]
)

// ── 15. Confirm dialog screenshot slide ─────────────────────────────────────
next()
{
  const s = pres.addSlide()
  pageBg(s)
  pageTitle(s, '重新啟動新一輪 · Confirm Dialog', '防誤丟現有 run · 結果一定會進歷史紀錄保存')
  // Center image
  const iw = 7
  const ih = iw / 1.63
  const ix = (W - iw) / 2
  s.addImage({ path: IMG('batch-05-confirm.png'), x: ix, y: 1.9, w: iw, h: ih })
  s.addText('• 點「確定開始」→ 開新 run、清掉表格 row。舊 run 仍在歷史紀錄(完成 / 取消 狀態都會留)', {
    x: M, y: 1.9 + ih + 0.2, w: W - M*2, h: 0.4,
    fontFace: FONT, fontSize: 11, color: C.secondary, align: 'center', margin: 0,
  })
  s.addText('• 點「取消」→ 維持現狀,可以再用「續跑」按鈕從中斷處接續(僅 cancelled / interrupted 狀態出現)', {
    x: M, y: 1.9 + ih + 0.55, w: W - M*2, h: 0.4,
    fontFace: FONT, fontSize: 11, color: C.secondary, align: 'center', margin: 0,
  })
  pageFooter(s)
  pageNumber(s, n, TOTAL_SLIDES)
}

// ── 16. 嚴重度 hover popup ──────────────────────────────────────────────────
next()
lifecycleSlide(
  '嚴重度 · Hover Popup 快速摘要',
  '滑鼠移到 P0/P1/P2/INFO chip → 浮出 alert 細節',
  IMG('batch-06-hover-popup.png'),
  [
    { text: 'Popup 內容', options: { bold: true, fontSize: 14, breakLine: true } },
    { text: '· Query 名稱 + 「N 筆 alert」', options: { breakLine: true } },
    { text: '· 每筆 alert 一行:嚴重度 chip + baseline 位置 + A/B 排名 + reason', options: { breakLine: true } },
    { text: '· 多筆時可滾動(游標進入 popup 不會消失)', options: { breakLine: true } },
    { text: ' ', options: { fontSize: 8, breakLine: true } },
    { text: '嚴重度等級', options: { bold: true, fontSize: 13, breakLine: true } },
    { text: 'P0 ' + '(紅)' + '· P1 ' + '(琥珀)' + '· P2 ' + '(紫)' + '· INFO' + '(灰)', options: { fontSize: 11, color: C.secondary, breakLine: true } },
    { text: ' ', options: { fontSize: 8, breakLine: true } },
    { text: '點 row 的「Query」欄', options: { bold: true, fontSize: 13, color: C.amberDark, breakLine: true } },
    { text: '→ navigate(/?keyword=<該詞>&filter=diff)跳主畫面差異模式看詳細', options: { fontSize: 11, color: C.secondary } },
  ]
)

// ── 17. 歷史紀錄 + Resume ───────────────────────────────────────────────────
next()
{
  const s = pres.addSlide()
  pageBg(s)
  pageTitle(s, '歷史紀錄 + Resume 安全保護', '最近 50 筆 run · 點 row 看 detail · 續跑會嚴格驗證')
  // Two images side by side
  const iw = 5.7
  const ih = iw / 1.63
  s.addImage({ path: IMG('batch-07-history-list.png'), x: M, y: 1.9, w: iw, h: ih })
  s.addImage({ path: IMG('batch-08-history-detail.png'), x: M + iw + 0.3, y: 1.9, w: iw, h: ih })
  s.addText('歷史列表(50 筆,可篩 type)', {
    x: M, y: 1.9 + ih + 0.05, w: iw, h: 0.3,
    fontFace: FONT, fontSize: 11, color: C.tertiary, align: 'center', margin: 0,
  })
  s.addText('Detail view — 完整 metadata + 當時 checkpoint', {
    x: M + iw + 0.3, y: 1.9 + ih + 0.05, w: iw, h: 0.3,
    fontFace: FONT, fontSize: 11, color: C.tertiary, align: 'center', margin: 0,
  })
  // Resume safety bottom
  const by = 1.9 + ih + 0.5
  s.addShape(pres.shapes.RECTANGLE, {
    x: M, y: by, w: W - M*2, h: 1.5,
    fill: { color: C.card }, line: { color: C.amberBorder, width: 1 },
  })
  s.addShape(pres.shapes.RECTANGLE, {
    x: M, y: by, w: 0.08, h: 1.5,
    fill: { color: C.amber }, line: { type: 'none' },
  })
  s.addText('Resume 嚴格驗證 — 任一不符就 fallback 跑全新一輪', {
    x: M + 0.3, y: by + 0.15, w: W - M*2 - 0.5, h: 0.4,
    fontFace: FONT, fontSize: 14, bold: true, color: C.amberDark, margin: 0,
  })
  s.addText([
    { text: '· type(精準 / 泛詞)、', options: {} },
    { text: 'version_a / version_b、', options: {} },
    { text: 'baseline_version、', options: {} },
    { text: '逐 idx 的 query 文字', options: {} },
    { text: '   全部必須跟 parent 完全一致才複製 ok 的 row。', options: { breakLine: true } },
    { text: '避免 BQ cron refresh 後 query 順序變,把 parent 對 query A 的 alerts 套到新 idx 的 query B。', options: { italic: true, color: C.secondary } },
  ], {
    x: M + 0.3, y: by + 0.6, w: W - M*2 - 0.5, h: 0.85,
    fontFace: FONT, fontSize: 11.5, color: C.primary, margin: 0, valign: 'top',
  })
  pageFooter(s)
  pageNumber(s, n, TOTAL_SLIDES)
}

// ── 18. 判定邏輯 5 步驟 ────────────────────────────────────────────────────
next()
{
  const s = pres.addSlide()
  pageBg(s)
  pageTitle(s, '判定邏輯 · 5 步驟流程', '每個關鍵字 + 每筆商品都跑這條 pipeline')
  const steps = [
    { n: '1', t: '關鍵字類型拆解', d: '純類別 / 目的地+類別 / 目的地+主題 / 純目的地 / POI · 沒地點時 GPT 拆解' },
    { n: '2', t: '地點比對', d: '3 層:字串包含 → ancestor 推論 → 國家 ISO fallback' },
    { n: '3', t: 'Category 比對', d: '內建關鍵字 → category code → 商品 title/描述交叉驗證' },
    { n: '4', t: 'Tier 判定', d: '綜合地點 + 類別 + 主題,輸出 T1 / T2 / T3 / MISS' },
    { n: '5', t: '同義詞 AI 救回', d: 'MISS 商品查同義詞表,沒有就問 AI,有則升 T2' },
  ]
  const sy = 1.95
  const sh = 0.85
  const sx = M
  const sw = W - M*2
  steps.forEach((step, i) => {
    const y = sy + i*(sh + 0.13)
    s.addShape(pres.shapes.RECTANGLE, {
      x: sx, y, w: sw, h: sh,
      fill: { color: C.card }, line: { color: C.hair, width: 0.5 },
    })
    // big numbered circle
    s.addShape(pres.shapes.OVAL, {
      x: sx + 0.15, y: y + 0.13, w: 0.6, h: 0.6,
      fill: { color: C.darkSlate }, line: { type: 'none' },
    })
    s.addText(step.n, {
      x: sx + 0.15, y: y + 0.13, w: 0.6, h: 0.6,
      fontFace: FONT, fontSize: 22, bold: true, color: C.amber,
      align: 'center', valign: 'middle', margin: 0,
    })
    s.addText(step.t, {
      x: sx + 1.0, y: y + 0.1, w: sw - 1.2, h: 0.4,
      fontFace: FONT, fontSize: 15, bold: true, color: C.primary, margin: 0,
    })
    s.addText(step.d, {
      x: sx + 1.0, y: y + 0.46, w: sw - 1.2, h: 0.4,
      fontFace: FONT, fontSize: 12, color: C.secondary, margin: 0,
    })
  })
  // bottom note
  s.addText('另有 步驟 6:Baseline 標註 — 標記守門商品 Top1/Top2 與 泛#N,觸發 Alert bar 異常分組', {
    x: M, y: sy + 5*(sh + 0.13) + 0.05, w: W - M*2, h: 0.4,
    fontFace: FONT, fontSize: 11, color: C.tertiary, italic: true, margin: 0,
  })
  pageFooter(s)
  pageNumber(s, n, TOTAL_SLIDES)
}

// ── 19. Tier 判定矩陣 ───────────────────────────────────────────────────────
next()
{
  const s = pres.addSlide()
  pageBg(s)
  pageTitle(s, 'Tier 判定矩陣', '4 個 tier 對應不同的相關性層級;hover 徽章看完整解釋')
  const tiers = [
    { t: 'T1', name: '完全相關', cond: '地點 ✓  +  類別完全符合(或主題出現於商品名)', desc: '精準命中,理想結果', color: C.green, bg: C.greenBg },
    { t: 'T2', name: '部分相關', cond: '地點 ✓ 但類別不符;或類別 ✓ 但地點不符;或同義詞命中', desc: '有關但不精準,可接受', color: C.blueDark, bg: C.blueBg },
    { t: 'T3', name: '疑似相關', cond: '地點 ✓ 但關鍵字只出現在描述;或商品名含詞但 category 不符', desc: '邊緣相關,要 review', color: C.purpleDark, bg: C.purpleBg },
    { t: 'MISS', name: '不相關', cond: '地點與類別皆不符 · 商品名/描述均未提及搜尋詞 · 無同義詞關係', desc: '明顯無關,要修', color: C.red, bg: C.redBg },
  ]
  const ty = 2.0
  const th = 1.05
  tiers.forEach((tier, i) => {
    const y = ty + i*(th + 0.12)
    s.addShape(pres.shapes.RECTANGLE, {
      x: M, y, w: W - M*2, h: th,
      fill: { color: C.card }, line: { color: C.hair, width: 0.5 },
    })
    // Big tier chip
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x: M + 0.2, y: y + 0.15, w: 1.3, h: 0.75,
      fill: { color: tier.bg }, line: { type: 'none' }, rectRadius: 0.08,
    })
    s.addText(tier.t, {
      x: M + 0.2, y: y + 0.15, w: 1.3, h: 0.75,
      fontFace: FONT, fontSize: 24, bold: true, color: tier.color,
      align: 'center', valign: 'middle', margin: 0,
    })
    s.addText(tier.name, {
      x: M + 1.7, y: y + 0.1, w: 2.0, h: 0.45,
      fontFace: FONT, fontSize: 15, bold: true, color: C.primary, margin: 0,
    })
    s.addText(tier.desc, {
      x: M + 1.7, y: y + 0.5, w: 2.0, h: 0.4,
      fontFace: FONT, fontSize: 11, color: C.secondary, margin: 0,
    })
    s.addText(tier.cond, {
      x: M + 3.9, y: y + 0.25, w: W - M*2 - 4.1, h: 0.6,
      fontFace: FONT, fontSize: 12, color: C.primary, margin: 0, valign: 'middle',
    })
  })
  pageFooter(s)
  pageNumber(s, n, TOTAL_SLIDES)
}

// ── 20. 地點 3 層 + Category + 同義詞 AI ─────────────────────────────────────
next()
{
  const s = pres.addSlide()
  pageBg(s)
  pageTitle(s, '地點 3 層比對 · Category · 同義詞 AI', '三套機制聯手處理「搜尋詞 ↔ 商品 metadata」的對應')
  // 3 columns
  const cy = 2.0
  const ch = 4.6
  const cw = (W - M*2 - 0.4) / 3
  // ─ 地點 ──
  const x1 = M
  s.addShape(pres.shapes.RECTANGLE, {
    x: x1, y: cy, w: cw, h: ch,
    fill: { color: C.card }, line: { color: C.hair, width: 0.5 },
  })
  s.addShape(pres.shapes.RECTANGLE, {
    x: x1, y: cy, w: cw, h: 0.06,
    fill: { color: C.blueDark }, line: { type: 'none' },
  })
  s.addText('地點 3 層', {
    x: x1 + 0.3, y: cy + 0.25, w: cw - 0.5, h: 0.5,
    fontFace: FONT, fontSize: 18, bold: true, color: C.primary, margin: 0,
  })
  s.addText([
    { text: '層 1 · 字串比對', options: { bold: true, fontSize: 13, breakLine: true } },
    { text: '商品 destination 清單直接包含搜尋地點', options: { fontSize: 11, color: C.secondary, breakLine: true } },
    { text: ' ', options: { fontSize: 6, breakLine: true } },
    { text: '層 2 · Ancestor 推論', options: { bold: true, fontSize: 13, breakLine: true } },
    { text: '搜尋地點 = 商品 destination 的上層', options: { fontSize: 11, color: C.secondary, breakLine: true } },
    { text: '例:「北海道」→ 札幌、函館 ✓', options: { fontSize: 10.5, color: C.tertiary, breakLine: true, italic: true } },
    { text: ' ', options: { fontSize: 6, breakLine: true } },
    { text: '層 3 · ISO Fallback', options: { bold: true, fontSize: 13, breakLine: true } },
    { text: '查不到 destination code 時改用 ISO 碼(JP / KR / TH …)比對 isoCountryCode', options: { fontSize: 11, color: C.secondary } },
  ], {
    x: x1 + 0.3, y: cy + 0.85, w: cw - 0.5, h: ch - 1.05,
    fontFace: FONT, fontSize: 12, color: C.primary, margin: 0, paraSpaceAfter: 2, valign: 'top',
  })
  // ─ Category ──
  const x2 = x1 + cw + 0.2
  s.addShape(pres.shapes.RECTANGLE, {
    x: x2, y: cy, w: cw, h: ch,
    fill: { color: C.card }, line: { color: C.hair, width: 0.5 },
  })
  s.addShape(pres.shapes.RECTANGLE, {
    x: x2, y: cy, w: cw, h: 0.06,
    fill: { color: C.amber }, line: { type: 'none' },
  })
  s.addText('Category 比對表', {
    x: x2 + 0.3, y: cy + 0.25, w: cw - 0.5, h: 0.5,
    fontFace: FONT, fontSize: 18, bold: true, color: C.primary, margin: 0,
  })
  s.addText([
    { text: 'esim / sim / wifi / 上網', options: { fontSize: 12, bold: true, breakLine: true } },
    { text: '→  CATEGORY_081', options: { fontFace: FONT_MONO, fontSize: 11, color: C.amberDark, breakLine: true } },
    { text: '門票 / ticket', options: { fontSize: 12, bold: true, breakLine: true } },
    { text: '→  CATEGORY_001', options: { fontFace: FONT_MONO, fontSize: 11, color: C.amberDark, breakLine: true } },
    { text: '一日遊 / tour', options: { fontSize: 12, bold: true, breakLine: true } },
    { text: '→  CATEGORY_020', options: { fontFace: FONT_MONO, fontSize: 11, color: C.amberDark, breakLine: true } },
    { text: '美食 / 餐廳 / buffet', options: { fontSize: 12, bold: true, breakLine: true } },
    { text: '→  CATEGORY_079', options: { fontFace: FONT_MONO, fontSize: 11, color: C.amberDark, breakLine: true } },
    { text: '交通 / 接送 / 新幹線 / jr', options: { fontSize: 12, bold: true, breakLine: true } },
    { text: '→  CATEGORY_120', options: { fontFace: FONT_MONO, fontSize: 11, color: C.amberDark, breakLine: true } },
    { text: ' ', options: { fontSize: 6, breakLine: true } },
    { text: '比對方式:先查 code,再確認搜索詞出現在商品 title / 描述', options: { fontSize: 10.5, color: C.secondary, italic: true } },
  ], {
    x: x2 + 0.3, y: cy + 0.85, w: cw - 0.5, h: ch - 1.05,
    fontFace: FONT, fontSize: 12, color: C.primary, margin: 0, paraSpaceAfter: 1, valign: 'top',
  })
  // ─ 同義詞 AI ──
  const x3 = x2 + cw + 0.2
  s.addShape(pres.shapes.RECTANGLE, {
    x: x3, y: cy, w: cw, h: ch,
    fill: { color: C.card }, line: { color: C.hair, width: 0.5 },
  })
  s.addShape(pres.shapes.RECTANGLE, {
    x: x3, y: cy, w: cw, h: 0.06,
    fill: { color: C.purple }, line: { type: 'none' },
  })
  s.addText('同義詞 AI 救回', {
    x: x3 + 0.3, y: cy + 0.25, w: cw - 0.5, h: 0.5,
    fontFace: FONT, fontSize: 18, bold: true, color: C.primary, margin: 0,
  })
  s.addText([
    { text: '案例', options: { bold: true, fontSize: 13, breakLine: true } },
    { text: '搜「chiikawa」遇到名稱有「吉伊卡哇」的商品,原本判 MISS', options: { fontSize: 11, color: C.secondary, breakLine: true } },
    { text: ' ', options: { fontSize: 6, breakLine: true } },
    { text: '救回流程', options: { bold: true, fontSize: 13, breakLine: true } },
    { text: '① 商品判 MISS', options: { fontSize: 11, breakLine: true } },
    { text: '② 查同義詞表(synonyms.json)', options: { fontSize: 11, breakLine: true } },
    { text: '③ 沒命中 → 問 GPT 判斷 keyword 與商品名的關係', options: { fontSize: 11, breakLine: true } },
    { text: '④ AI 找到 → 寫進表 + 升 T2;AI 說無關 → 維持 MISS', options: { fontSize: 11, breakLine: true } },
    { text: ' ', options: { fontSize: 6, breakLine: true } },
    { text: '設計重點', options: { bold: true, fontSize: 12, color: C.purpleDark, breakLine: true } },
    { text: '· 雙向索引(查 chiikawa 或 吉伊卡哇 皆命中)', options: { fontSize: 10.5, color: C.secondary, breakLine: true } },
    { text: '· 每 keyword 每巡檢只問 AI 一次', options: { fontSize: 10.5, color: C.secondary, breakLine: true } },
    { text: '· 同義詞命中固定升 T2', options: { fontSize: 10.5, color: C.secondary } },
  ], {
    x: x3 + 0.3, y: cy + 0.85, w: cw - 0.5, h: ch - 1.05,
    fontFace: FONT, fontSize: 12, color: C.primary, margin: 0, paraSpaceAfter: 1, valign: 'top',
  })
  pageFooter(s)
  pageNumber(s, n, TOTAL_SLIDES)
}

// ── 21. 人工校正 + Baseline pipeline ────────────────────────────────────────
next()
{
  const s = pres.addSlide()
  pageBg(s)
  pageTitle(s, '人工校正 + Baseline Pipeline', '人工覆寫 + 自動每日抽 BQ + warn-not-hold guardrail')
  const cy = 2.0
  const ch = 4.6
  const cw = (W - M*2 - 0.3) / 2
  // Left: 人工校正
  s.addShape(pres.shapes.RECTANGLE, {
    x: M, y: cy, w: cw, h: ch,
    fill: { color: C.card }, line: { color: C.hair, width: 0.5 },
  })
  s.addShape(pres.shapes.RECTANGLE, {
    x: M, y: cy, w: 0.08, h: ch,
    fill: { color: C.blueDark }, line: { type: 'none' },
  })
  s.addText('人工校正機制', {
    x: M + 0.3, y: cy + 0.25, w: cw - 0.4, h: 0.5,
    fontFace: FONT, fontSize: 18, bold: true, color: C.primary, margin: 0,
  })
  s.addText([
    { text: '操作方式', options: { bold: true, fontSize: 14, breakLine: true } },
    { text: '· hover 商品列右側 → 點「校正」按鈕', options: { breakLine: true } },
    { text: '· 改 Tier(T1/T2/T3/MISS)+ 註解 + (選用) 同義詞', options: { breakLine: true } },
    { text: '· 校正寫進 feedback.json(append-only)', options: { breakLine: true } },
    { text: ' ', options: { fontSize: 8, breakLine: true } },
    { text: '套用時機', options: { bold: true, fontSize: 14, breakLine: true } },
    { text: '· 下次搜尋同一個關鍵字 → 校正自動覆蓋 → tier 標「已校正」', options: { breakLine: true } },
    { text: '· 完整校正歷史保留供稽核', options: { breakLine: true } },
    { text: ' ', options: { fontSize: 8, breakLine: true } },
    { text: '影響:已校正過的商品會進「需關注」filter,提醒再 review', options: { fontSize: 11, color: C.amberDark, italic: true } },
  ], {
    x: M + 0.4, y: cy + 0.85, w: cw - 0.6, h: ch - 1.05,
    fontFace: FONT, fontSize: 12, color: C.primary, margin: 0, paraSpaceAfter: 2, valign: 'top',
  })
  // Right: Baseline pipeline
  const x2 = M + cw + 0.3
  s.addShape(pres.shapes.RECTANGLE, {
    x: x2, y: cy, w: cw, h: ch,
    fill: { color: C.card }, line: { color: C.hair, width: 0.5 },
  })
  s.addShape(pres.shapes.RECTANGLE, {
    x: x2, y: cy, w: 0.08, h: ch,
    fill: { color: C.amber }, line: { type: 'none' },
  })
  s.addText('Baseline Pipeline(PR #23)', {
    x: x2 + 0.3, y: cy + 0.25, w: cw - 0.4, h: 0.5,
    fontFace: FONT, fontSize: 18, bold: true, color: C.primary, margin: 0,
  })
  s.addText([
    { text: '三種更新來源', options: { bold: true, fontSize: 14, breakLine: true } },
    { text: '① 每日 cron(主路徑) — 07:00 TW 自動 BQ → 自動 reload', options: { breakLine: true } },
    { text: '② 立即從 BQ 抽取(手動 button) — 不等 cron', options: { breakLine: true } },
    { text: '③ CSV 上傳(Plan B) — BQ 失效或測試用', options: { breakLine: true } },
    { text: ' ', options: { fontSize: 8, breakLine: true } },
    { text: '版本管理', options: { bold: true, fontSize: 13, breakLine: true } },
    { text: '· 每次抽取建版本資料夾(時間戳記)', options: { breakLine: true, fontSize: 11 } },
    { text: '· 最多 14 版輪轉(~2 週)', options: { breakLine: true, fontSize: 11 } },
    { text: '· 可隨時 rollback', options: { breakLine: true, fontSize: 11 } },
    { text: ' ', options: { fontSize: 8, breakLine: true } },
    { text: 'Guardrail:warn-not-hold', options: { bold: true, fontSize: 13, color: C.amberDark, breakLine: true } },
    { text: '新版 row < 上版 × 50% → 仍 activate + UI banner 黃色警告', options: { fontSize: 10.5, color: C.secondary, breakLine: true } },
    { text: 'BQ 抽取失敗 → 不 activate,保持上一版 + UI banner 紅', options: { fontSize: 10.5, color: C.secondary } },
  ], {
    x: x2 + 0.4, y: cy + 0.85, w: cw - 0.6, h: ch - 1.05,
    fontFace: FONT, fontSize: 12, color: C.primary, margin: 0, paraSpaceAfter: 2, valign: 'top',
  })
  pageFooter(s)
  pageNumber(s, n, TOTAL_SLIDES)
}

// ── 22. 系統架構 + PR 史 ───────────────────────────────────────────────────
next()
{
  const s = pres.addSlide()
  pageBg(s)
  pageTitle(s, '系統架構 + 主要 PR 史', '前後端 stack · 從 PR #20 走到 PR #28 的關鍵改動')
  // Architecture diagram top
  const ay = 1.9
  const ah = 1.6
  s.addShape(pres.shapes.RECTANGLE, {
    x: M, y: ay, w: W - M*2, h: ah,
    fill: { color: C.card }, line: { color: C.hair, width: 0.5 },
  })
  s.addText('系統架構', {
    x: M + 0.3, y: ay + 0.15, w: 3, h: 0.35,
    fontFace: FONT, fontSize: 14, bold: true, color: C.primary, margin: 0,
  })
  const fy = ay + 0.55
  // Frontend box
  s.addShape(pres.shapes.RECTANGLE, {
    x: M + 0.3, y: fy, w: 5.5, h: 0.85,
    fill: { color: C.blueBg }, line: { color: C.blueDark, width: 0.5 },
  })
  s.addText('Frontend (vite :5888)', {
    x: M + 0.4, y: fy + 0.05, w: 5.3, h: 0.3,
    fontFace: FONT, fontSize: 12, bold: true, color: C.blueDark, margin: 0,
  })
  s.addText('React · React Router · Vite · Tailwind CSS · 無 TypeScript', {
    x: M + 0.4, y: fy + 0.35, w: 5.3, h: 0.5,
    fontFace: FONT_MONO, fontSize: 10, color: C.blueDark, margin: 0, valign: 'top',
  })
  // Backend box
  s.addShape(pres.shapes.RECTANGLE, {
    x: M + 6.0, y: fy, w: 6.0, h: 0.85,
    fill: { color: C.greenBg }, line: { color: C.greenDark, width: 0.5 },
  })
  s.addText('Backend (uvicorn :19426)', {
    x: M + 6.1, y: fy + 0.05, w: 5.8, h: 0.3,
    fontFace: FONT, fontSize: 12, bold: true, color: C.greenDark, margin: 0,
  })
  s.addText('FastAPI · SQLite (WAL) · APScheduler · daemon thread per ab-check run', {
    x: M + 6.1, y: fy + 0.35, w: 5.8, h: 0.5,
    fontFace: FONT_MONO, fontSize: 10, color: C.greenDark, margin: 0, valign: 'top',
  })
  // PR 史 table
  const py = ay + ah + 0.3
  const ph = 0.4
  const prs = [
    { n: '#20', t: 'UI 全面改版 + 批次 baseline 巡檢報表' },
    { n: '#21', t: 'stage_checker single-flight + stale TTL 修正' },
    { n: '#22', t: '批次巡檢拆出獨立 /batch route' },
    { n: '#23', t: 'BQ baseline auto fetch + 每日 cron + UI banner;HTML upload 廢棄' },
    { n: '#24', t: 'Docker mount:scripts/sql + GCP SA JSON' },
    { n: '#25', t: 'gitignore handoff/_secrets/' },
    { n: '#26', t: 'README + CLAUDE.md 同步' },
    { n: '#27', t: '批次巡檢改 async + sqlite checkpoint:cancel / resume / 50 筆歷史、跨 route polling、5 個視覺狀態' },
    { n: '#28', t: '⭐ lang / locale / channel v3 API 欄位前端可動態帶入;HomePage 與 BatchPage 共用同一份 context state' },
  ]
  s.addText('主要 PR 史', {
    x: M, y: py, w: 4, h: 0.4,
    fontFace: FONT, fontSize: 14, bold: true, color: C.primary, margin: 0,
  })
  prs.forEach((pr, i) => {
    const y = py + 0.45 + i*ph
    s.addShape(pres.shapes.RECTANGLE, {
      x: M, y, w: W - M*2, h: ph,
      fill: { color: i % 2 === 0 ? C.card : C.pageBg }, line: { color: C.hair, width: 0.5 },
    })
    s.addText(pr.n, {
      x: M + 0.15, y, w: 0.8, h: ph,
      fontFace: FONT_MONO, fontSize: 11, bold: true, color: pr.n === '#28' ? C.amberDark : C.tertiary,
      valign: 'middle', margin: 0,
    })
    s.addText(pr.t, {
      x: M + 1.0, y, w: W - M*2 - 1.2, h: ph,
      fontFace: FONT, fontSize: 11, color: pr.n === '#28' ? C.primary : C.secondary,
      bold: pr.n === '#28', valign: 'middle', margin: 0,
    })
  })
  pageFooter(s)
  pageNumber(s, n, TOTAL_SLIDES)
}

// ── 23. PR #28 · 多語系 / 多 channel 巡檢 ──────────────────────────────────
next()
{
  const s = pres.addSlide()
  pageBg(s)
  pageTitle(s, 'PR #28 · 多語系 / 多 channel 巡檢', 'v3 search API 的 lang / locale / channel 欄位改由前端動態帶入')

  // Top: 三欄 UI 入口卡
  const cy = 1.95
  const ch = 1.55
  const cards = [
    {
      x: M, label: 'lang',
      where: 'HomePage 搜尋列旁下拉',
      defaultVal: 'zh-tw',
      options: 'zh-tw · zh-hk · zh-cn · en · ja · ko · th',
      color: C.amber, colorBg: C.amberBg, colorDark: C.amberDark, colorBorder: C.amberBorder,
    },
    {
      x: M + 4.3, label: 'locale',
      where: 'HomePage 搜尋列旁下拉(緊鄰 lang)',
      defaultVal: 'tw',
      options: 'tw · hk · cn · jp · kr · th · us · global',
      color: C.purple, colorBg: C.purpleBg, colorDark: C.purpleDark, colorBorder: C.purple,
    },
    {
      x: M + 8.6, label: 'channel',
      where: 'SettingsPanel(齒輪)→ 搜尋設定',
      defaultVal: 'ios',
      options: 'ios · android · web',
      color: C.green, colorBg: C.greenBg, colorDark: C.greenDark, colorBorder: C.greenBorder,
    },
  ]
  cards.forEach(c => {
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
      x: c.x, y: cy, w: 4.1, h: ch,
      fill: { color: c.colorBg }, line: { color: c.colorBorder, width: 0.75 },
      rectRadius: 0.08,
    })
    s.addText(c.label, {
      x: c.x + 0.2, y: cy + 0.1, w: 3.7, h: 0.4,
      fontFace: FONT_MONO, fontSize: 22, bold: true, color: c.colorDark, margin: 0,
    })
    s.addText(c.where, {
      x: c.x + 0.2, y: cy + 0.5, w: 3.7, h: 0.3,
      fontFace: FONT, fontSize: 10, color: C.secondary, margin: 0,
    })
    // Default chip
    chip(s, '預設 ' + c.defaultVal, {
      x: c.x + 0.2, y: cy + 0.85, w: 1.4, h: 0.28,
      bg: c.color, fg: C.white, fontSize: 10, bold: true,
    })
    s.addText(c.options, {
      x: c.x + 0.2, y: cy + 1.2, w: 3.7, h: 0.3,
      fontFace: FONT_MONO, fontSize: 9, color: c.colorDark, margin: 0,
    })
  })

  // Middle banner: state sharing
  const by = cy + ch + 0.3
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x: M, y: by, w: W - M*2, h: 0.55,
    fill: { color: C.amberBg }, line: { color: C.amberBorder, width: 0.5 },
    rectRadius: 0.06,
  })
  s.addText([
    { text: '🌐  ', options: { fontSize: 14 } },
    { text: 'HomePage 設的 lang/locale + SettingsPanel 設的 channel ', options: { bold: true, color: C.amberDark } },
    { text: '→ ', options: { color: C.amberDark } },
    { text: 'BatchPage 跑 AB-check 也吃同一份(', options: { color: C.amberDark } },
    { text: 'AppContext 共用 state', options: { fontFace: FONT_MONO, bold: true, color: C.amberDark } },
    { text: ')', options: { color: C.amberDark } },
  ], {
    x: M + 0.2, y: by, w: W - M*2 - 0.3, h: 0.55,
    fontFace: FONT, fontSize: 12, valign: 'middle', margin: 0,
  })

  // Bottom: data flow + cache key + acceptance test
  const fy = by + 0.55 + 0.3
  const fh = 2.5

  // Left: data flow
  s.addShape(pres.shapes.RECTANGLE, {
    x: M, y: fy, w: 6.3, h: fh,
    fill: { color: C.card }, line: { color: C.hair, width: 0.5 },
  })
  s.addText('資料流', {
    x: M + 0.2, y: fy + 0.1, w: 5, h: 0.35,
    fontFace: FONT, fontSize: 13, bold: true, color: C.primary, margin: 0,
  })
  s.addText([
    { text: 'Frontend AppContext', options: { fontFace: FONT_MONO, color: C.blueDark, bold: true, breakLine: true } },
    { text: '   ↓ api.js (fetchUnifiedSearch / startABCheckRun)', options: { fontFace: FONT_MONO, color: C.secondary, breakLine: true } },
    { text: 'Pydantic Request models', options: { fontFace: FONT_MONO, color: C.purpleDark, bold: true, breakLine: true } },
    { text: '   UnifiedSearchRequest · ABCheckStartRequest', options: { fontFace: FONT_MONO, color: C.secondary, fontSize: 9, breakLine: true } },
    { text: '   CompareRequest · BatchRunRequest', options: { fontFace: FONT_MONO, color: C.secondary, fontSize: 9, breakLine: true } },
    { text: '   ↓ main.py endpoints', options: { fontFace: FONT_MONO, color: C.secondary, breakLine: true } },
    { text: 'ab_check / batch_engine / _process_version', options: { fontFace: FONT_MONO, color: C.purpleDark, bold: true, breakLine: true } },
    { text: '   ↓', options: { fontFace: FONT_MONO, color: C.secondary, breakLine: true } },
    { text: 'kkday_api.fetch_kkday_products_v3(', options: { fontFace: FONT_MONO, color: C.greenDark, bold: true, breakLine: true } },
    { text: '   lang=…, locale=…, channel=…)', options: { fontFace: FONT_MONO, color: C.greenDark, bold: true, breakLine: true } },
    { text: '   ↓', options: { fontFace: FONT_MONO, color: C.secondary, breakLine: true } },
    { text: 'v3 search API body 的 lang/locale/channel/source', options: { fontFace: FONT_MONO, color: C.primary } },
  ], {
    x: M + 0.2, y: fy + 0.45, w: 6.0, h: fh - 0.5,
    fontFace: FONT_MONO, fontSize: 10, valign: 'top', margin: 0, paraSpaceAfter: 1,
  })

  // Right: cache key + tests + follow-up
  s.addShape(pres.shapes.RECTANGLE, {
    x: M + 6.5, y: fy, w: W - M*2 - 6.5, h: fh,
    fill: { color: C.card }, line: { color: C.hair, width: 0.5 },
  })
  s.addText('關鍵設計 + 平台驗收', {
    x: M + 6.7, y: fy + 0.1, w: 5, h: 0.35,
    fontFace: FONT, fontSize: 13, bold: true, color: C.primary, margin: 0,
  })
  s.addText([
    { text: 'Cache key 隔離', options: { bold: true, color: C.primary, breakLine: true } },
    { text: 'ab_check._fetch_results 的 cache key:', options: { fontSize: 10, color: C.secondary, breakLine: true } },
    { text: '(query, version, lang, locale, channel)', options: { fontFace: FONT_MONO, fontSize: 10, color: C.greenDark, breakLine: true } },
    { text: '避免跨 locale 共用 stale 結果', options: { fontSize: 10, color: C.tertiary, breakLine: true } },
    { text: ' ', options: { breakLine: true } },
    { text: 'Run-level locale 持久化', options: { bold: true, color: C.primary, breakLine: true } },
    { text: 'ab_check_runs schema 加 lang/locale/channel 欄位', options: { fontSize: 10, color: C.greenDark, breakLine: true } },
    { text: '(既存 DB 走 ALTER TABLE 自動 migrate)', options: { fontSize: 9, color: C.tertiary, breakLine: true } },
    { text: 'Resume 自動沿用 parent locale', options: { fontSize: 10, color: C.greenDark, breakLine: true } },
    { text: '(start_run 讀 parent DB 蓋 caller)', options: { fontSize: 9, color: C.tertiary, breakLine: true } },
    { text: ' ', options: { breakLine: true } },
    { text: '平台驗收(8 個 pytest)', options: { bold: true, color: C.primary, breakLine: true } },
    { text: '✓ v3 body 落地 / 預設 fallback', options: { fontSize: 10, color: C.greenDark, breakLine: true } },
    { text: '✓ unified-search / ab-check forward', options: { fontSize: 10, color: C.greenDark, breakLine: true } },
    { text: '✓ DB 寫入 + 預設 + resume inherit', options: { fontSize: 10, color: C.greenDark, breakLine: true } },
    { text: ' ', options: { breakLine: true } },
    { text: 'Follow-up(未進此 PR)', options: { bold: true, color: C.amberDark, breakLine: true } },
    { text: '· CLI 缺 --lang/--locale/--channel flags', options: { fontSize: 9, color: C.amberDark } },
  ], {
    x: M + 6.7, y: fy + 0.45, w: W - M*2 - 6.9, h: fh - 0.5,
    fontFace: FONT, fontSize: 11, valign: 'top', margin: 0, paraSpaceAfter: 1,
  })

  pageFooter(s)
  pageNumber(s, n, TOTAL_SLIDES)
}

// ── 24. Closing / 相關連結 ──────────────────────────────────────────────────
next()
{
  const s = pres.addSlide()
  s.background = { color: C.darkSlate }
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 0.18, h: H,
    fill: { color: C.amber }, line: { type: 'none' },
  })
  s.addText('THANK YOU', {
    x: 0.9, y: 1.5, w: 12, h: 0.6,
    fontFace: FONT, fontSize: 18, color: C.amber, charSpacing: 12, margin: 0,
  })
  s.addText('問題 / 回報 / 一起改', {
    x: 0.9, y: 2.0, w: 12, h: 1.0,
    fontFace: FONT, fontSize: 36, bold: true, color: C.white, margin: 0,
  })
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.9, y: 3.1, w: 0.5, h: 0.04,
    fill: { color: C.amber }, line: { type: 'none' },
  })
  // Links
  const ly = 3.6
  const links = [
    { label: 'SIT 部署', url: 'http://autotest-service.sit.kkday.com:8081/explore_platform/' },
    { label: 'GitHub Repo', url: 'https://github.com/lancekkday/explore_platform' },
    { label: 'Confluence 文件', url: 'https://kkday.atlassian.net/wiki/spaces/QS/pages/1969225751' },
    { label: 'PR #27', url: 'https://github.com/lancekkday/explore_platform/pull/27' },
    { label: 'PR #28', url: 'https://github.com/lancekkday/explore_platform/pull/28' },
  ]
  links.forEach((l, i) => {
    const y = ly + i*0.55
    s.addText(l.label, {
      x: 0.9, y, w: 2.8, h: 0.4,
      fontFace: FONT, fontSize: 13, color: C.tertiary, margin: 0,
    })
    s.addText(l.url, {
      x: 3.7, y, w: 9, h: 0.4,
      fontFace: FONT_MONO, fontSize: 12, color: C.white, margin: 0, hyperlink: { url: l.url },
    })
  })
  s.addText('搜尋巡檢平台 · QA Squad · 2026-05-25', {
    x: 0.9, y: H - 0.7, w: 9, h: 0.3,
    fontFace: FONT, fontSize: 10, color: C.tertiary, margin: 0,
  })
}

// ── Write ───────────────────────────────────────────────────────────────────
const outPath = path.join(REPO, 'docs', '搜尋巡檢平台_功能操作_判斷邏輯_PR27.pptx')
pres.writeFile({ fileName: outPath }).then(name => {
  console.log('Wrote:', name)
  console.log('Slides total:', n)
})
