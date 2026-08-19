"""Streamlit 前端 — 依 spec/ui-spec.md(計量學視覺系統)。

兩種模式(由條件自動切換):
  對照模式   — 只填 keyword:自動偵測 treatment/control 兩組,A/B 排序對照。
  單人回放   — 進階條件填了 kkud / member_uuid / session_id:使用者在 AB test
               只會歸屬一個組別,沒有對照可言 — 呈現「這個人這次搜尋實際看到
               什麼」(召回/排序回放),事件 metadata (exp/lang/locale/cf) 是
               這個模式的一級資訊。

核心命題:讓人分辨訊號與雜訊 — 顏色只給值得查的事(only_a/b、品質旗標、
強度警示),不可判讀的東西在視覺上主動退場(ui-spec §1.1)。
一律透過 FastAPI 取數,不直連 BigQuery。
"""
from __future__ import annotations

import html
import os
import sys

import requests
import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from src.domain.presentation import (  # noqa: E402  (ui-spec §9.2 共用純函式)
    band_gap,
    common_prefix_len,
    lamp_level,
    verdict_text,
)
from src.domain.relevance import RELEVANCE_DIMS  # noqa: E402

API_BASE = os.getenv("API_BASE", "http://localhost:8300")
RERANK_BOUNDARY = 100

st.set_page_config(page_title="個性化搜尋事件回放器", layout="wide")

# ── Design tokens (ui-spec §2) — 一次注入,元件只引用 CSS 變數 ─────────────────
st.markdown("""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans+Condensed:wght@400;500&family=IBM+Plex+Sans:wght@400;500&family=Noto+Sans+TC:wght@400;500&display=swap" rel="stylesheet">
<style>
:root{
  --paper:#F4F6F5; --surface:#FFFFFF; --ink:#16191A; --graphite:#616A6B;
  --faint:#9AA3A3; --rule:#D5DAD9; --tolerance:#E9EDEC;
  --measure:#0B5D5A; --counter:#8A5A12; --alert:#A32B24;
  --sans:'IBM Plex Sans','Noto Sans TC',sans-serif;
  --cond:'IBM Plex Sans Condensed','Noto Sans TC',sans-serif;
  --mono:'IBM Plex Mono',monospace;
}
.stApp{background:var(--paper);}
/* 隱藏 Streamlit 自帶 chrome (Deploy 工具列/選單) — 固定定位會蓋住標題摘要列 */
header[data-testid="stHeader"]{display:none;}
#MainMenu,footer{visibility:hidden;}
.block-container{padding-top:1.6rem;max-width:1400px;}
.ri *{font-variant-numeric:tabular-nums;}
.ri-title{font:500 15px/1.4 var(--sans);color:var(--ink);}
.ri-eyebrow{font:500 11px/1.2 var(--cond);letter-spacing:.06em;color:var(--graphite);text-transform:uppercase;}
.ri-note{font:400 10.5px/1.3 var(--cond);color:var(--graphite);}
/* 讀數列 (§5) */
.readout{display:grid;grid-template-columns:repeat(4,1fr);gap:1px;background:var(--rule);
  border:.5px solid var(--rule);border-radius:6px;overflow:hidden;margin:10px 0 14px;}
.readout>div{background:var(--surface);padding:12px 16px 10px;}
.readout .v{font:500 26px/1.1 var(--mono);color:var(--ink);}
.readout .v.alert{color:var(--alert);} .readout .v.counter{color:var(--counter);}
.readout .v.grey{color:var(--graphite);}
.readout .warn{font:400 11px/1.4 var(--sans);margin-top:2px;}
.readout .warn.alert{color:var(--alert);} .readout .warn.counter{color:var(--counter);}
@media (max-width:600px){ .readout{grid-template-columns:repeat(2,1fr);} } /* §3 */
/* 排序表 (§6) */
.rank-wrap{overflow-x:auto;} /* 窄屏表格自身橫捲 */
table.rank{width:100%;min-width:640px;border-collapse:collapse;background:var(--surface);
  border:.5px solid var(--rule);border-radius:6px;}
table.rank th{font:500 11px/1.2 var(--cond);letter-spacing:.06em;color:var(--graphite);
  text-align:left;padding:8px 10px;border-bottom:.5px solid var(--rule);}
table.rank td{padding:0 10px;height:34px;border-top:.5px solid var(--rule);
  font:400 12px/1.4 var(--sans);color:var(--ink);}
table.rank tr.hoverable{transition:background .12s;}
table.rank tr.hoverable:hover{background:#EFF3F2;}
@media (prefers-reduced-motion: reduce){ table.rank tr.hoverable{transition:none;} }
td.num,.mono{font:400 12.5px/1 var(--mono);}
td.rk{width:32px;text-align:right;}
td.mid{width:250px;max-width:250px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.pname{color:var(--ink);text-decoration:none;border-bottom:1px dotted var(--faint);}
.pname:hover{border-bottom-color:var(--ink);}
.pmid{font:400 10px/1 var(--mono);color:var(--faint);margin-left:4px;}
td.score{width:110px;text-align:right;}
td.lamps{width:74px;white-space:nowrap;padding-right:4px;}
.score .prefix{color:var(--faint);} /* §2.3 共同前綴淡化 */
.norerank{font:400 11px/1.2 var(--cond);color:var(--faint);}
/* 同分帶 (§6.1):括號軌線 + tolerance 底色 */
tr.band td{background:var(--tolerance);}
td.rail{width:10px;padding:0;}
tr.band td.rail{position:relative;}
tr.band td.rail::after{content:'';position:absolute;left:8px;top:0;bottom:0;width:2px;
  background:color-mix(in srgb, var(--graphite) 30%, transparent);}
tr.band-first td.rail::after{top:4px;border-top-left-radius:2px;}
tr.band-last td.rail::after{bottom:4px;}
/* 邊界分隔列 (§6.1/§6.5) */
tr.boundary td{height:24px;padding:0;border-top:none;text-align:center;
  font:400 10.5px/1.3 var(--cond);color:var(--graphite);background:var(--surface);}
tr.boundary .line{display:flex;align-items:center;gap:8px;}
tr.boundary .line::before,tr.boundary .line::after{content:'';flex:1;border-top:.5px solid var(--rule);}
tr.boundary.rerank td{color:var(--counter);}
/* 判讀 (§6.3) */
.v-only-a{color:var(--measure);font-weight:500;} .v-only-b{color:var(--counter);font-weight:500;}
.v-real{color:var(--ink);font-weight:500;} .v-tie{color:var(--graphite);} .v-id{color:var(--faint);}
tr.edge-a td:first-child{box-shadow:inset 3px 0 0 var(--measure);}
tr.edge-b td:first-child{box-shadow:inset 3px 0 0 var(--counter);}
/* 燈號 (§6.4)。第 4 格 (IP) 已定案為品牌 IP,與主題同性質,不特別標記 */
.lamp{display:inline-block;width:7px;height:14px;border-radius:1px;margin-right:2px;vertical-align:middle;}
.lamp.l0{background:var(--rule);} .lamp.l1{background:color-mix(in srgb,var(--ink) 25%,white);}
.lamp.l2{background:color-mix(in srgb,var(--ink) 50%,white);}
.lamp.l3{background:color-mix(in srgb,var(--ink) 75%,white);} .lamp.l4{background:var(--ink);}
.lamp.hollow{background:transparent;border:1px solid var(--faint);}
.lamp-q{font:400 12px/1 var(--mono);color:var(--faint);margin-left:2px;}
.ad{font:500 11px/1.2 var(--cond);letter-spacing:.06em;color:var(--counter);margin-left:4px;}
/* 特徵側欄 (§7) */
.flags{display:flex;gap:12px;flex-wrap:wrap;font:500 11px/1.4 var(--cond);letter-spacing:.02em;}
.flag-ok{color:var(--graphite);} .flag-alert{color:var(--alert);} .flag-warn{color:var(--counter);}
.uf-row{display:flex;gap:8px;align-items:baseline;padding:6px 0;border-top:.5px solid var(--rule);}
.uf-name{font:500 11px/1.2 var(--cond);letter-spacing:.06em;color:var(--graphite);width:70px;}
.uf-cov{font:400 10.5px/1.3 var(--cond);color:var(--graphite);white-space:nowrap;}
.uf-val{font:400 12px/1.5 var(--mono);color:var(--ink);word-break:break-all;}
.uf-val.empty{font-family:var(--sans);color:var(--faint);}
.chips span{display:inline-block;background:var(--paper);border:.5px solid var(--rule);
  border-radius:3px;padding:2px 8px;margin:0 4px 4px 0;font:400 11px/1.4 var(--mono);color:var(--ink);}
.panel{background:var(--surface);border:.5px solid var(--rule);border-radius:6px;padding:12px 14px;}
.dim{opacity:.4;pointer-events:none;}
.empty-state{font:400 13px/1.5 var(--sans);color:var(--graphite);padding:28px 0;}
</style>
""", unsafe_allow_html=True)


DIM_ZH = {"sellable": "可售", "location": "地點", "category": "類目",
          "ip": "IP", "theme": "主題", "text": "文本"}
_WD = "一二三四五六日"


def _esc(v) -> str:
    return html.escape(str(v))


def _get(path: str, params: dict):
    r = requests.get(f"{API_BASE}{path}", params=params, timeout=30)
    if r.status_code in (400, 404):
        return None, r.json().get("detail", "")
    r.raise_for_status()
    return r.json(), None


def _cf_txt(cf: dict | None) -> str:
    cf = cf or {}
    parts = []
    if cf.get("platform"):
        parts.append(str(cf["platform"]))
    if cf.get("hour") is not None:
        parts.append(f"{cf['hour']}時")
    wd = cf.get("weekday")
    if isinstance(wd, int) and 1 <= wd <= 7:
        parts.append(f"週{_WD[wd - 1]}")
    return "·".join(parts) if parts else "—"


def _lamps(rel, raw_code) -> str:
    """六格燈號。值語意 (RD 定案):0=最相關/通過→淡;值越大越偏離→越深。"""
    if rel is None or all(v is None for v in rel.values()):
        boxes = "".join("<span class='lamp hollow'></span>" for _ in RELEVANCE_DIMS)
        return (f"<span role='img' aria-label='相關性碼解碼失敗' "
                f"title='解碼失敗:{_esc(raw_code)}'>{boxes}"
                f"<span class='lamp-q'>?</span></span>")
    tip = f"{_esc(raw_code)} · " + " ".join(
        f"{DIM_ZH[d]}{rel[d]}" for d in RELEVANCE_DIMS) + " (0=最相關,值越大越偏離)"
    aria = ",".join(f"{DIM_ZH[d]}={rel[d]}" for d in RELEVANCE_DIMS)
    boxes = "".join(
        f"<span class='lamp l{lamp_level(rel[d])}' title='{tip}'></span>"
        for d in RELEVANCE_DIMS)
    return f"<span role='img' aria-label='{aria}'>{boxes}</span>"


def _prod_cell(mid, name, is_ad) -> str:
    """商品欄:名稱連 kkday 商品頁 (線上事件 → www),mid 退居小字;缺名時 mid 即連結。"""
    mid = _esc(mid)
    url = f"https://www.kkday.com/zh-tw/product/{mid}"
    label = _esc(name) if name else mid
    note = f"<span class='pmid'>{mid}</span>" if name else ""
    ad = "<span class='ad'>AD</span>" if is_ad else ""
    return (f"<a class='pname' href='{url}' target='_blank' rel='noreferrer' "
            f"title='開啟商品頁 · prod_mid {mid}'>{label}</a>{note}{ad}")


def _score_html(in_scope, sstr, plen) -> str:
    if not in_scope:
        return "<span class='norerank'>未進精排</span>"
    if sstr is None:
        return "<span class='v-id'>—</span>"
    return f"<span class='score'><span class='prefix'>{sstr[:plen]}</span>{sstr[plen:]}</span>"


# ══ 標題列 + 條件(§4:摘要常駐、條件收合)═══════════════════════════════════════

if "params" not in st.session_state:
    st.session_state.params = {
        "date": "2026-08-13", "keyword": "福岡", "lang": "", "locale": "",
        "currency": "",
        "kkud": "", "member_uuid": "", "session_id": "", "cache_hit": "(不限)",
    }
P = st.session_state.params

summary_bits = [f"<b>{_esc(P['keyword']) or '—'}</b>"]
if P["lang"] or P["locale"]:
    summary_bits.append(f"{_esc(P['lang'] or '?')} · {_esc(P['locale'] or '?')}")
summary_bits.append(f"{_esc(P['date'])} <span class='ri-note'>(UTC+8)</span>")
st.markdown(
    f"<div class='ri' style='display:flex;justify-content:space-between;align-items:baseline'>"
    f"<div class='ri-title'>{'&ensp;'.join(summary_bits)}</div>"
    f"<div class='ri-eyebrow'>搜尋事件回放</div></div>",
    unsafe_allow_html=True,
)

with st.expander("條件", expanded=False):
    c1, c2, c3, c4, c5 = st.columns([1.2, 1.6, 0.8, 0.8, 0.8])
    P["date"] = c1.text_input("日期 (UTC+8) *", value=P["date"])
    P["keyword"] = c2.text_input("keyword *", value=P["keyword"])
    P["lang"] = c3.text_input("lang", value=P["lang"])
    P["locale"] = c4.text_input("locale", value=P["locale"])
    P["currency"] = c5.text_input("currency", value=P["currency"])
    a1, a2, a3, a4 = st.columns(4)
    P["kkud"] = a1.text_input("kkud", value=P["kkud"],
                              help="填了即進入「單人回放」— 使用者只屬一組,無 A/B 對照")
    P["member_uuid"] = a2.text_input("member_uuid", value=P["member_uuid"],
                                     help="走 POST body,不進 URL;填了即進入單人回放")
    P["session_id"] = a3.text_input("session_id", value=P["session_id"],
                                    help="填了即進入單人回放")
    P["cache_hit"] = a4.selectbox("cache_hit", ["(不限)", "true", "false"],
                                  index=["(不限)", "true", "false"].index(P["cache_hit"]))

run = st.button("查詢", type="primary")
if not run and "ran" not in st.session_state:
    st.markdown("<div class='ri empty-state'>設定條件後按「查詢」開始。"
                "日期與 keyword 為必填 (*)。填入 kkud / member_uuid / session_id "
                "會切到「單人回放」— 查某個使用者在線上實際看到的召回結果。</div>",
                unsafe_allow_html=True)
    st.stop()
st.session_state["ran"] = True

# ── 必填檢查 (§8.1 文案:指出下一步) ──────────────────────────────────────────
if not P["date"]:
    st.markdown("<div class='ri empty-state'>選一個日期才能查詢。</div>", unsafe_allow_html=True)
    st.stop()
if not P["keyword"]:
    st.markdown("<div class='ri empty-state'>keyword 為必填。</div>", unsafe_allow_html=True)
    st.stop()

# 單人回放模式:使用者在 AB test 只會歸屬一個組別 → 沒有 A/B 對照
user_mode = bool(P["kkud"] or P["member_uuid"] or P["session_id"])

resp = requests.post(f"{API_BASE}/api/events/search", json={
    "date": P["date"],
    "keyword": P["keyword"] or None, "kkud": P["kkud"] or None,
    "member_uuid": P["member_uuid"] or None, "session_id": P["session_id"] or None,
    "locale": P["locale"] or None, "lang": P["lang"] or None,
    "currency": P["currency"] or None,
    "cache_hit": None if P["cache_hit"] == "(不限)" else P["cache_hit"] == "true",
}, timeout=30)
if resp.status_code == 400:
    st.markdown(f"<div class='ri empty-state'>{_esc(resp.json().get('detail'))}</div>",
                unsafe_allow_html=True)
    st.stop()
events = resp.json()["rows"]
if not events:
    loc = P["locale"] or "任一 locale"
    who = "(含使用者條件)" if user_mode else ""
    st.markdown(
        f"<div class='ri empty-state'>{_esc(P['date'][5:])} 的「{_esc(P['keyword'])}」在 "
        f"{_esc(loc)} 沒有 content 事件{who}。試著放寬 locale,或換一天。</div>",
        unsafe_allow_html=True)
    st.stop()

left, right = st.columns([2.6, 1], gap="medium")

# ══ 右欄先執行:事件選擇 + 特徵面板 (§7,兩種模式共用) ══════════════════════════
with right:
    pick = st.selectbox(
        "事件", [e["session_id"] for e in events],
        format_func=lambda s: next(
            f"{e['exp_version']} · {e['event_type']} · {e['session_id'][:18]}"
            for e in events if e["session_id"] == s),
    )
    picked_ev = next(e for e in events if e["session_id"] == pick)
    hints = {"keyword": picked_ev.get("keyword"),
             "exp_version": picked_ev.get("exp_version"),
             "locale": picked_ev.get("locale")}
    detail, derr = _get(f"/api/events/{pick}", {"date": P["date"], **hints})
    if detail is None:
        st.markdown(f"<div class='ri empty-state'>{_esc(derr)}</div>", unsafe_allow_html=True)
        st.stop()

    flags = detail["quality_flags"]
    joined_ok = not flags["join_failed"]
    f_join = ("<span class='flag-ok'>✓ recall 已串接</span>" if joined_ok
              else "<span class='flag-alert'>✕ 串不回 recall</span>")
    f_uf = ("<span class='flag-warn'>⚠ 上游未推 uf</span>" if flags["uf_absent"]
            else "<span class='flag-ok'>✓ uf 存在</span>")
    f_ltr = ("<span class='flag-warn'>⚠ ltr 由 cache 回收</span>"
             if flags["ltr_features_recovered"] else "<span class='flag-ok'>✓ ltr 原生</span>")
    join_note = ("" if joined_ok else
                 "<div class='ri-note' style='margin-top:4px'>串不回 recall 事件,"
                 "因此沒有特徵資料。排序仍可判讀。</div>")
    st.markdown(f"<div class='ri panel'><div class='ri-eyebrow' style='margin-bottom:6px'>串接品質</div>"
                f"<div class='flags'>{f_join}{f_uf}{f_ltr}</div>{join_note}</div>",
                unsafe_allow_html=True)

    cov = detail["coverage_baseline"]
    uf = detail["uf"]
    uf_rows_html = ""
    for name, cov_key, field in [("INTENT", "uf_intent", "intent"),
                                 ("PROFILE", "uf_profile", "profile"),
                                 ("LBS", "uf_lbs", "lbs")]:
        pct = cov[cov_key]
        low = " ○" if pct < 0.30 else ""   # §7.2 低覆蓋提示
        val = uf[field]
        val_html = (f"<span class='uf-val'>{_esc(val)}</span>" if val is not None
                    else "<span class='uf-val empty'>本筆無資料</span>")
        uf_rows_html += (f"<div class='uf-row'><span class='uf-name'>{name}</span>"
                         f"<span class='uf-cov'>{pct:.1%}{low}</span>{val_html}</div>")

    cf = detail["cf_summary"]
    chips = ""
    for label, v in [("", cf["platform"]),
                     ("", f"{cf['hour']}時" if cf["hour"] is not None else None),
                     ("", f"週{_WD[cf['weekday'] - 1]}"
                      if isinstance(cf.get("weekday"), int) and 1 <= cf["weekday"] <= 7 else None),
                     ("query.final ", cf["query_final"]),
                     ("tokens ", cf["query_tokens"])]:
        if v is not None:
            chips += f"<span>{_esc(label)}{_esc(v)}</span>"

    dim_cls = "" if joined_ok else " dim"
    st.markdown(
        f"<div class='ri panel{dim_cls}' style='margin-top:8px'>"
        f"<div class='ri-eyebrow'>USER FEATURE</div>{uf_rows_html}"
        f"<div class='ri-eyebrow' style='margin:10px 0 6px'>CONTEXT FEATURE"
        f" <span class='uf-cov'>{cov['cf']:.0%}</span></div>"
        f"<div class='chips'>{chips}</div></div>",
        unsafe_allow_html=True,
    )

    if joined_ok and st.button("展開完整 cf(138 KB)"):
        cf_full, cerr = _get(f"/api/events/{pick}/cf", {"date": P["date"], **hints})
        if cf_full:
            st.json(cf_full["cf_raw"])
        else:
            st.markdown(f"<div class='ri empty-state'>{_esc(cerr)}</div>",
                        unsafe_allow_html=True)


# ══ 左欄:單人回放 或 兩組對照 ═════════════════════════════════════════════════
with left:
    if user_mode:
        # ── 單人回放:選定事件的召回/排序結果,無 A/B ─────────────────────────
        pg = detail["pagination"]
        login = "已登入" if picked_ev.get("logged_in") else "未登入"
        cache_txt = "cache" if detail.get("cache_hit") else "live"
        cf_line = _cf_txt({"platform": cf["platform"], "hour": cf["hour"],
                           "weekday": cf["weekday"]})
        st.markdown(
            f"<div class='ri' style='margin-top:6px'>"
            f"<span style='color:var(--measure);font-weight:500'>"
            f"{_esc(detail.get('exp_version'))}</span>"
            f"<span class='ri-note'> · {_esc(detail.get('lang') or '?')}·"
            f"{_esc(detail.get('locale') or '?')} · {_esc(cf_line)}"
            f" · {login} · {cache_txt} · {_esc(detail.get('event_date_local') or '')}</span>"
            f"<div class='ri-note' style='margin-top:2px'>單人回放 — 使用者只歸屬一個實驗組,"
            f"無 A/B 對照;本頁 {pg.get('prod_cnt') or 0} 筆 · 全量 {pg.get('total_count') or '—'} 筆"
            f" · rank ≤ {pg.get('rerank_boundary')} 進精排</div></div>",
            unsafe_allow_html=True,
        )

        prods = detail["prods"]
        score_strs = {id(p): f"{p['ltr_score']:.5f}" for p in prods
                      if p.get("ltr_score") is not None}
        plen = common_prefix_len(list(score_strs.values()))

        band_sizes: dict = {}
        for p in prods:
            if p.get("tie_band") is not None:
                band_sizes[p["tie_band"]] = band_sizes.get(p["tie_band"], 0) + 1

        body = []
        prev_band = None
        prev_score = None
        crossed_rerank = False
        for i, p in enumerate(prods):
            band = p.get("tie_band")
            grouped = band is not None and band_sizes.get(band, 0) >= 2
            if not crossed_rerank and p["rank"] > RERANK_BOUNDARY:
                crossed_rerank = True
                body.append("<tr class='boundary rerank'><td colspan='6'><div class='line'>"
                            "精排邊界 · 第 101 名之後無 ltr_score,個性化不生效</div></td></tr>")
            if band is not None and prev_band is not None and band != prev_band:
                g = band_gap(prev_score, p.get("ltr_score"))
                if g and g["ulp"] is not None:
                    body.append(
                        f"<tr class='boundary'><td colspan='6'><div class='line'>"
                        f"帶邊界 · Δ{g['gap']:.1e} ≈ {g['ulp']:.0f} ULP</div></td></tr>")
            cls = ["hoverable"]
            if grouped:
                cls.append("band")
                if prev_band != band:
                    cls.append("band-first")
                nxt = prods[i + 1] if i + 1 < len(prods) else None
                if nxt is None or nxt.get("tie_band") != band:
                    cls.append("band-last")
            sstr = score_strs.get(id(p))
            body.append(
                f"<tr class='{' '.join(cls)}'>"
                f"<td class='rail'></td>"
                f"<td class='rk num'>{p['rank']}</td>"
                f"<td class='mid'>{_prod_cell(p['prod_mid'], p.get('prod_name'), p.get('is_ad'))}</td>"
                f"<td class='score num'>{_score_html(p.get('in_rerank_scope'), sstr, plen)}</td>"
                f"<td class='lamps'>{_lamps(p.get('relevance'), p.get('relevance_status_code') or '')}</td>"
                f"<td></td></tr>"
            )
            prev_band = band
            prev_score = p.get("ltr_score") or prev_score

        st.markdown(
            "<div class='rank-wrap'><table class='rank ri'><thead><tr>"
            "<th></th><th scope='col'>名次</th><th scope='col'>商品</th>"
            "<th scope='col' style='text-align:right'>分數</th>"
            "<th scope='col'>相關性</th><th></th>"
            "</tr></thead><tbody>" + "".join(body) + "</tbody></table></div>",
            unsafe_allow_html=True,
        )
        d = detail.get("dispersion") or {}
        if d.get("range") is not None and d.get("min_adjacent_gap_ulp") is not None:
            st.markdown(
                f"<div class='ri ri-note' style='margin-top:6px'>分數離散度:全距 {d['range']:.2e}"
                f" · 最小相鄰間距 ≈ {d['min_adjacent_gap_ulp']:.0f} ULP(≤10 ULP 視為同分)</div>",
                unsafe_allow_html=True)

    else:
        # ── 對照模式:自動偵測 treatment/control 兩組 ─────────────────────────
        cmp_params = {"date": P["date"], "keyword": P["keyword"],
                      "locale": P["locale"] or None}
        if P["cache_hit"] != "(不限)":
            cmp_params["cache_hit"] = P["cache_hit"]
        cmp_data, cmp_err = _get("/api/compare", cmp_params)

        if cmp_data is None:
            msg = cmp_err or "找不到 control 組事件,無法計算個性化強度。可改用兩個裝置對照。"
            st.markdown(f"<div class='ri empty-state'>{_esc(msg)}</div>", unsafe_allow_html=True)
        else:
            rows = cmp_data["rows"]
            m = cmp_data["metrics"]
            meta = cmp_data["meta"]
            a_meta = meta.get("a") or {}
            b_meta = meta.get("b") or {}
            all_out_of_scope = rows and all(not r["in_rerank_scope"] for r in rows)

            # 身分摘要:事件層級 metadata (exp / lang·locale / cf) 講一次就好,
            # 不進表格逐列重複 — 兩側不同時在這一行就看得出來
            def _side_desc(tag, color, mm):
                if not mm:
                    return f"<span style='color:var(--faint)'>{tag}:無事件</span>"
                loc = f"{mm.get('lang') or '?'}·{mm.get('locale') or '?'}"
                return (f"<span style='color:{color};font-weight:500'>{tag} "
                        f"{_esc(mm.get('exp_version'))}</span>"
                        f"<span class='ri-note'> ({_esc(loc)} · {_esc(_cf_txt(mm.get('cf')))})</span>")
            st.markdown(
                f"<div class='ri' style='margin-top:6px'>"
                f"{_side_desc('A treatment', 'var(--measure)', a_meta)}"
                f"<span style='color:var(--graphite)'> ↔ </span>"
                f"{_side_desc('B control', 'var(--counter)', b_meta)}</div>",
                unsafe_allow_html=True,
            )

            # 讀數列 (§5)
            strength = m["personalization_strength"]
            warning = m["warning"]
            s_cls, s_note = "", ""
            if all_out_of_scope:
                s_txt = "不適用"
                s_cls = "grey"
            else:
                s_txt = f"{strength:.0%}"
                if warning == "suspect_inactive":
                    s_cls, s_note = "alert", "兩組結果幾乎相同,個性化可能未生效"
                elif warning == "suspect_excessive":
                    s_cls, s_note = "counter", "兩組差異偏大,注意長尾商品曝光"
            note_html = f"<div class='warn {s_cls}'>{s_note}</div>" if s_note else ""
            st.markdown(f"""
<div class='ri readout'>
  <div><div class='ri-eyebrow'>個性化強度</div><div class='v {s_cls}'>{s_txt}</div>{note_html}</div>
  <div><div class='ri-eyebrow'>Top10 重疊</div><div class='v'>{m['top10_overlap']}/10</div></div>
  <div><div class='ri-eyebrow'>跨帶變動</div><div class='v'>{m.get('real_move_changes', 0)}</div></div>
  <div><div class='ri-eyebrow'>同帶內位移</div><div class='v grey'>{m['tie_unresolvable_changes']}</div></div>
</div>""", unsafe_allow_html=True)

            if all_out_of_scope:
                st.markdown("<div class='ri ri-note' style='margin-bottom:8px'>"
                            "── 精排邊界 · 第 101 名之後無 ltr_score,個性化不生效 ──</div>",
                            unsafe_allow_html=True)

            score_strs = {id(r): f"{r['ltr_score_a']:.5f}" for r in rows
                          if r.get("ltr_score_a") is not None}
            plen = common_prefix_len(list(score_strs.values()))

            V_CLS = {"only_a": "v-only-a", "only_b": "v-only-b", "real_move": "v-real",
                     "tie_unresolvable": "v-tie", "identical": "v-id"}

            band_sizes: dict = {}
            for r in rows:
                if r["rank_a"] is not None and r["band_a"] is not None:
                    band_sizes[r["band_a"]] = band_sizes.get(r["band_a"], 0) + 1

            body = []
            prev_band = None
            prev_band_last_score = None
            crossed_rerank = False
            in_band_pos = 0
            for i, r in enumerate(rows):
                ra, rb = r["rank_a"], r["rank_b"]
                band = r["band_a"] if ra is not None else None
                grouped = band is not None and band_sizes.get(band, 0) >= 2

                if not crossed_rerank and ra is not None and ra > RERANK_BOUNDARY:
                    crossed_rerank = True
                    body.append("<tr class='boundary rerank'><td colspan='7'><div class='line'>"
                                "精排邊界 · 第 101 名之後無 ltr_score,個性化不生效</div></td></tr>")

                if band is not None and prev_band is not None and band != prev_band:
                    g = band_gap(prev_band_last_score, r.get("ltr_score_a"))
                    if g and g["ulp"] is not None:
                        body.append(
                            f"<tr class='boundary'><td colspan='7'><div class='line'>"
                            f"帶邊界 · Δ{g['gap']:.1e} ≈ {g['ulp']:.0f} ULP</div></td></tr>")
                    in_band_pos = 0
                elif band == prev_band and band is not None:
                    in_band_pos += 1
                else:
                    in_band_pos = 0

                cls = ["hoverable"]
                if grouped:
                    cls.append("band")
                    if in_band_pos == 0:
                        cls.append("band-first")
                    nxt = rows[i + 1] if i + 1 < len(rows) else None
                    if nxt is None or nxt.get("band_a") != band or nxt.get("rank_a") is None:
                        cls.append("band-last")
                if r["verdict"] == "only_a":
                    cls.append("edge-a")
                elif r["verdict"] == "only_b":
                    cls.append("edge-b")

                vt = verdict_text(r["verdict"], ra, rb, r.get("relevance_diff_dims"))
                rel = r["relevance_a"] or r["relevance_b"]
                raw = ""
                if rel and all(v is not None for v in rel.values()):
                    raw = "".join(str(rel[d]) for d in RELEVANCE_DIMS)
                sstr = score_strs.get(id(r))
                body.append(
                    f"<tr class='{' '.join(cls)}'>"
                    f"<td class='rail'></td>"
                    f"<td class='rk num'>{ra if ra is not None else '—'}</td>"
                    f"<td class='rk num'>{rb if rb is not None else '—'}</td>"
                    f"<td class='mid'>{_prod_cell(r['prod_mid'], r.get('prod_name'), r.get('is_ad'))}</td>"
                    f"<td class='score num'>{_score_html(r['in_rerank_scope'], sstr, plen)}</td>"
                    f"<td class='lamps'>{_lamps(rel, raw)}</td>"
                    f"<td class='{V_CLS.get(r['verdict'], '')}'>{_esc(vt)}</td></tr>"
                )
                prev_band = band
                if band is not None:
                    prev_band_last_score = r.get("ltr_score_a") or prev_band_last_score

            st.markdown(
                "<div class='rank-wrap'><table class='rank ri'><thead><tr>"
                "<th></th><th scope='col'>A</th><th scope='col'>B</th>"
                "<th scope='col'>商品</th><th scope='col' style='text-align:right'>分數</th>"
                "<th scope='col'>相關性</th><th scope='col'>判讀</th>"
                "</tr></thead><tbody>" + "".join(body) + "</tbody></table></div>",
                unsafe_allow_html=True,
            )
            d = cmp_data["dispersion_a"]
            if d["range"] is not None and d.get("min_adjacent_gap_ulp") is not None:
                st.markdown(
                    f"<div class='ri ri-note' style='margin-top:6px'>A 組離散度:全距 {d['range']:.2e}"
                    f" · 相對差異 {d['relative_range']:.1e} · 最小相鄰間距 ≈ "
                    f"{d['min_adjacent_gap_ulp']:.0f} ULP(≤10 ULP 視為同分)</div>",
                    unsafe_allow_html=True)
