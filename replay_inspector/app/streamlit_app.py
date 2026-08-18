"""Streamlit 前端 — 依 spec/ui-spec.md(計量學視覺系統)。

核心命題:讓人分辨訊號與雜訊 — 顏色只給值得查的事(only_a/b、品質旗標、
強度警示),不可判讀的東西在視覺上主動退場(ui-spec §1.1)。

一律透過 FastAPI 取數,不直連 BigQuery。本機 demo:
  USE_FAKE=1 uvicorn src.api.main:app --port 8300
  API_BASE=http://localhost:8300 streamlit run app/streamlit_app.py
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
.block-container{padding-top:1.2rem;max-width:1280px;}
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
/* 排序表 (§6) */
table.rank{width:100%;border-collapse:collapse;background:var(--surface);
  border:.5px solid var(--rule);border-radius:6px;}
table.rank th{font:500 11px/1.2 var(--cond);letter-spacing:.06em;color:var(--graphite);
  text-align:left;padding:8px 10px;border-bottom:.5px solid var(--rule);}
table.rank td{padding:0 10px;height:34px;border-top:.5px solid var(--rule);
  font:400 12px/1.4 var(--sans);color:var(--ink);}
table.rank tr.hoverable{transition:background .12s;}
table.rank tr.hoverable:hover{background:#EFF3F2;}
@media (prefers-reduced-motion: reduce){ table.rank tr.hoverable{transition:none;} }
td.num,.mono{font:400 12.5px/1 var(--mono);}
td.rk{width:32px;text-align:right;} td.mid{width:96px;} td.score{width:110px;text-align:right;}
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
/* 燈號 (§6.4) */
.lamp{display:inline-block;width:7px;height:14px;border-radius:1px;margin-right:2px;vertical-align:middle;}
.lamp.l0{background:var(--rule);} .lamp.l1{background:color-mix(in srgb,var(--ink) 25%,white);}
.lamp.l2{background:color-mix(in srgb,var(--ink) 50%,white);}
.lamp.l3{background:color-mix(in srgb,var(--ink) 75%,white);} .lamp.l4{background:var(--ink);}
.lamp.ip{border-top:1px dashed var(--graphite);} /* §6.4 第 4 格語意待確認 */
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


def _esc(v) -> str:
    return html.escape(str(v))


def _get(path: str, params: dict):
    r = requests.get(f"{API_BASE}{path}", params=params, timeout=30)
    if r.status_code in (400, 404):
        return None, r.json().get("detail", "")
    r.raise_for_status()
    return r.json(), None


# ══ 標題列 + 條件(§4:摘要常駐、條件收合)═══════════════════════════════════════

DIM_ZH = {"sellable": "可售", "location": "地點", "category": "類目",
          "ip": "IP", "theme": "主題", "text": "文本"}

if "params" not in st.session_state:
    st.session_state.params = {
        "date": "2026-08-13", "keyword": "福岡", "lang": "", "locale": "",
        "currency": "", "exp_a": "exp_a", "exp_b": "exp_b",
        "kkud": "", "member_uuid": "", "session_id": "", "cache_hit": "(不限)",
    }
P = st.session_state.params

summary_bits = [f"<b>{_esc(P['keyword']) or '—'}</b>"]
if P["lang"] or P["locale"]:
    summary_bits.append(f"{_esc(P['lang'] or '?')} · {_esc(P['locale'] or '?')}")
summary_bits.append(f"{_esc(P['date'])} <span class='ri-note'>(UTC+8)</span>")
summary_bits.append(
    f"<span style='color:var(--measure)'>A treatment {_esc(P['exp_a'])}</span>"
    f" ↔ <span style='color:var(--counter)'>B control {_esc(P['exp_b'])}</span>"
)
st.markdown(
    f"<div class='ri' style='display:flex;justify-content:space-between;align-items:baseline'>"
    f"<div class='ri-title'>{'&ensp;'.join(summary_bits)}</div>"
    f"<div class='ri-eyebrow'>搜尋事件回放</div></div>",
    unsafe_allow_html=True,
)

with st.expander("條件", expanded=False):
    c1, c2, c3, c4, c5, c6, c7 = st.columns([1.1, 1.3, 0.7, 0.7, 0.7, 1, 1])
    P["date"] = c1.text_input("日期 (UTC+8)", value=P["date"])
    P["keyword"] = c2.text_input("keyword", value=P["keyword"])
    P["lang"] = c3.text_input("lang", value=P["lang"])
    P["locale"] = c4.text_input("locale", value=P["locale"])
    P["currency"] = c5.text_input("currency", value=P["currency"])
    P["exp_a"] = c6.text_input("exp_a (treatment)", value=P["exp_a"])
    P["exp_b"] = c7.text_input("exp_b (control)", value=P["exp_b"])
    a1, a2, a3, a4 = st.columns(4)
    P["kkud"] = a1.text_input("kkud", value=P["kkud"])
    P["member_uuid"] = a2.text_input("member_uuid", value=P["member_uuid"],
                                     help="走 POST body,不進 URL")
    P["session_id"] = a3.text_input("session_id", value=P["session_id"])
    P["cache_hit"] = a4.selectbox("cache_hit", ["(不限)", "true", "false"],
                                  index=["(不限)", "true", "false"].index(P["cache_hit"]))

run = st.button("查詢", type="primary")
if not run and "ran" not in st.session_state:
    st.stop()
st.session_state["ran"] = True

# ── 空狀態文案 (§8.1:指出下一步,不道歉不含糊) ────────────────────────────────
if not P["date"]:
    st.markdown("<div class='ri empty-state'>選一個日期才能查詢。</div>", unsafe_allow_html=True)
    st.stop()
if not any([P["keyword"], P["kkud"], P["member_uuid"], P["session_id"]]):
    st.markdown("<div class='ri empty-state'>keyword、kkud、member_uuid、session_id 至少填一項。</div>",
                unsafe_allow_html=True)
    st.stop()

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
    st.markdown(
        f"<div class='ri empty-state'>{_esc(P['date'][5:])} 的「{_esc(P['keyword'])}」在 "
        f"{_esc(loc)} 沒有 content 事件。試著放寬 locale,或換一天。</div>",
        unsafe_allow_html=True)
    st.stop()

# ── compare ───────────────────────────────────────────────────────────────────
cmp_params = {"date": P["date"], "keyword": P["keyword"],
              "locale": P["locale"] or None, "exp_a": P["exp_a"], "exp_b": P["exp_b"]}
if P["cache_hit"] != "(不限)":
    cmp_params["cache_hit"] = P["cache_hit"]
cmp_data, cmp_err = _get("/api/compare", cmp_params) if (P["keyword"] and P["exp_a"] and P["exp_b"]) else (None, None)

left, right = st.columns([2.2, 1], gap="medium")

# ══ 讀數列 + 排序對照 (§5, §6) ═════════════════════════════════════════════════
with left:
    if cmp_data is None:
        msg = "找不到 control 組事件,無法計算個性化強度。可改用兩個裝置對照。" \
            if cmp_err else "需要 keyword 與 exp_a / exp_b 才能對照。"
        st.markdown(f"<div class='ri empty-state'>{_esc(msg)}</div>", unsafe_allow_html=True)
    else:
        rows = cmp_data["rows"]
        m = cmp_data["metrics"]
        all_out_of_scope = rows and all(not r["in_rerank_scope"] for r in rows)

        # 讀數列 (§5):四個數字,不加圖表
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

        # 排序表:§2.3 前綴淡化 — 前綴長度由可見列決定,不寫死
        score_strs = {id(r): f"{r['ltr_score_a']:.5f}" for r in rows
                      if r.get("ltr_score_a") is not None}
        plen = common_prefix_len(list(score_strs.values()))

        def _score_cell(r) -> str:
            if not r["in_rerank_scope"]:
                return "<span class='norerank'>未進精排</span>"
            s = score_strs.get(id(r))
            if s is None:
                return "<span class='v-id'>—</span>"
            return (f"<span class='score'><span class='prefix'>{s[:plen]}</span>"
                    f"{s[plen:]}</span>")

        def _lamps(rel, raw_code) -> str:
            if rel is None or all(v is None for v in rel.values()):
                boxes = "".join(
                    f"<span class='lamp hollow{' ip' if d == 'ip' else ''}'></span>"
                    for d in RELEVANCE_DIMS)
                return (f"<span role='img' aria-label='相關性碼解碼失敗' "
                        f"title='解碼失敗:{_esc(raw_code)}'>{boxes}"
                        f"<span class='lamp-q'>?</span></span>")
            tip = f"{_esc(raw_code)} · " + " ".join(
                f"{DIM_ZH[d]}{rel[d]}" for d in RELEVANCE_DIMS)
            aria = ",".join(f"{DIM_ZH[d]}={rel[d]}" for d in RELEVANCE_DIMS)
            boxes = ""
            for d in RELEVANCE_DIMS:
                lv = lamp_level(rel[d])
                ip_cls = " ip" if d == "ip" else ""
                ip_tip = ";IP 維度語意待確認" if d == "ip" else ""
                boxes += f"<span class='lamp l{lv}{ip_cls}' title='{tip}{ip_tip}'></span>"
            return f"<span role='img' aria-label='{aria}'>{boxes}</span>"

        V_CLS = {"only_a": "v-only-a", "only_b": "v-only-b", "real_move": "v-real",
                 "tie_unresolvable": "v-tie", "identical": "v-id"}

        # 帶分組 (§6.1):依 rank_a 序,band_a 相同者為一組;單筆成帶不畫括號不上底色
        body = []
        prev_band = None
        prev_band_last_score = None
        crossed_rerank = False
        band_sizes: dict = {}
        for r in rows:
            if r["rank_a"] is not None and r["band_a"] is not None:
                band_sizes[r["band_a"]] = band_sizes.get(r["band_a"], 0) + 1

        in_band_pos = 0
        for i, r in enumerate(rows):
            ra, rb = r["rank_a"], r["rank_b"]
            band = r["band_a"] if ra is not None else None
            grouped = band is not None and band_sizes.get(band, 0) >= 2

            # 精排邊界列 (§6.5)
            if not crossed_rerank and ra is not None and ra > RERANK_BOUNDARY:
                crossed_rerank = True
                body.append("<tr class='boundary rerank'><td colspan='7'><div class='line'>"
                            "精排邊界 · 第 101 名之後無 ltr_score,個性化不生效</div></td></tr>")

            # 帶邊界列 (§6.1):間距值是分組成立的理由,必須顯示
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
            ad = "<span class='ad'>AD</span>" if r["is_ad"] else ""
            rel = r["relevance_a"] or r["relevance_b"]
            raw = ""  # 原始碼進 tooltip;rows 未帶原碼時以解碼值重組
            if rel and all(v is not None for v in rel.values()):
                raw = "".join(str(rel[d]) for d in RELEVANCE_DIMS)
            body.append(
                f"<tr class='{' '.join(cls)}'>"
                f"<td class='rail'></td>"
                f"<td class='rk num'>{ra if ra is not None else '—'}</td>"
                f"<td class='rk num'>{rb if rb is not None else '—'}</td>"
                f"<td class='mid mono'>{_esc(r['prod_mid'])}{ad}</td>"
                f"<td class='score num'>{_score_cell(r)}</td>"
                f"<td class='lamps'>{_lamps(rel, raw)}</td>"
                f"<td class='{V_CLS.get(r['verdict'], '')}'>{_esc(vt)}</td></tr>"
            )
            prev_band = band
            if grouped or band is not None:
                prev_band_last_score = r.get("ltr_score_a") or prev_band_last_score

        st.markdown(
            "<table class='rank ri'><thead><tr>"
            "<th></th><th scope='col'>A</th><th scope='col'>B</th>"
            "<th scope='col'>PROD_MID</th><th scope='col' style='text-align:right'>分數</th>"
            "<th scope='col'>相關性</th><th scope='col'>判讀</th>"
            "</tr></thead><tbody>" + "".join(body) + "</tbody></table>",
            unsafe_allow_html=True,
        )
        d = cmp_data["dispersion_a"]
        if d["range"] is not None and d.get("min_adjacent_gap_ulp") is not None:
            st.markdown(
                f"<div class='ri ri-note' style='margin-top:6px'>A 組離散度:全距 {d['range']:.2e}"
                f" · 相對差異 {d['relative_range']:.1e} · 最小相鄰間距 ≈ "
                f"{d['min_adjacent_gap_ulp']:.0f} ULP(≤10 ULP 視為同分)</div>",
                unsafe_allow_html=True)

# ══ 特徵側欄 (§7:品質 → uf → cf) ══════════════════════════════════════════════
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
    weekday_zh = "一二三四五六日"
    wd = cf["weekday"]
    chips = ""
    for label, v in [("", cf["platform"]),
                     ("", f"{cf['hour']}時" if cf["hour"] is not None else None),
                     ("", f"週{weekday_zh[wd - 1]}" if isinstance(wd, int) and 1 <= wd <= 7 else None),
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

    if joined_ok:
        if st.button("展開完整 cf(138 KB)"):
            cf_full, cerr = _get(f"/api/events/{pick}/cf", {"date": P["date"], **hints})
            if cf_full:
                st.json(cf_full["cf_raw"])
            else:
                st.markdown(f"<div class='ri empty-state'>{_esc(cerr)}</div>",
                            unsafe_allow_html=True)
