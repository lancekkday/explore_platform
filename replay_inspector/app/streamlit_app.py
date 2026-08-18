"""Streamlit 前端 — spec §6。單頁三段:條件列 → 對照面板+排序表 → 特徵面板。

一律透過 FastAPI 取數,不直連 BigQuery(規則集中在 API 層,MCP tool 共用)。
本機 demo:`USE_FAKE=1 uvicorn src.api.main:app --port 8300` 再
`API_BASE=http://localhost:8300 streamlit run app/streamlit_app.py`。
"""
from __future__ import annotations

import html
import os

import requests
import streamlit as st

API_BASE = os.getenv("API_BASE", "http://localhost:8300")

st.set_page_config(page_title="個性化搜尋事件回放器", layout="wide")

# ── 樣式:六格燈號 / 判讀底色 ──────────────────────────────────────────────────
# 第 4 格 (ip) 獨立配色:待 spec 9.1 確認語意 — 若確認為使用者 IP 地理,
# 它是六碼中唯一的 user×商品維度。
DIM_LABELS = {
    "sellable": "可售", "location": "地點", "category": "類目",
    "ip": "IP⚠", "theme": "主題", "text": "文本",
}
VERDICT_TEXT = {
    "identical": "一致",
    "tie_unresolvable": "同分帶,不可判讀",
    "real_move": "真實變動",
    "only_a": "僅 A — 個性化證據",
    "only_b": "僅 B — 個性化證據",
}


def _get(path: str, params: dict):
    r = requests.get(f"{API_BASE}{path}", params=params, timeout=30)
    if r.status_code == 400:
        st.error(f"參數錯誤:{r.json().get('detail')}")
        st.stop()
    if r.status_code == 404:
        st.warning(f"查無資料:{r.json().get('detail')}")
        st.stop()
    r.raise_for_status()
    return r.json()


def _esc(v) -> str:
    """所有插進 unsafe_allow_html markdown 的動態值一律先 escape —
    keyword / cf tokens 是線上 log 的原始使用者輸入,不可信。"""
    return html.escape(str(v))


def _lamp(dim: str, val) -> str:
    """單一維度燈號 HTML。val None=未知(灰)、0/2=依值上色。"""
    ip_dim = dim == "ip"
    if val is None:
        bg, fg = "#e2e8f0", "#64748b"
        txt = "?"
    else:
        txt = str(val)
        if ip_dim:
            bg, fg = ("#c7d2fe", "#3730a3") if val else ("#eef2ff", "#818cf8")
        else:
            bg, fg = ("#bbf7d0", "#166534") if val else ("#f1f5f9", "#94a3b8")
    title = f"{DIM_LABELS[dim]}={txt}" + (";語意待 RD 確認 (spec 9.1)" if ip_dim else "")
    return (
        f"<span title='{title}' style='display:inline-block;width:16px;height:16px;"
        f"line-height:16px;text-align:center;font-size:10px;border-radius:3px;"
        f"background:{bg};color:{fg};margin-right:1px;"
        f"{'outline:1.5px solid #6366f1;' if ip_dim else ''}'>{txt}</span>"
    )


def _lamps(rel: dict | None) -> str:
    if not rel:
        return "<span style='color:#94a3b8;font-size:11px'>—</span>"
    return "".join(_lamp(d, rel.get(d)) for d in
                   ["sellable", "location", "category", "ip", "theme", "text"])


# ══ 6.1 條件列 ═════════════════════════════════════════════════════════════════

st.title("個性化搜尋事件回放器")
st.caption("同一個 keyword,treatment 與 control 看到的結果差在哪、為什麼。唯讀工具。")

c1, c2, c3, c4, c5, c6, c7 = st.columns([1.2, 1.5, 0.7, 0.7, 0.7, 1, 1])
date = c1.text_input("日期 (UTC+8) *", value="2026-08-13", help="必填,分區裁剪用")
keyword = c2.text_input("keyword", value="福岡")
lang = c3.text_input("lang", value="")
locale = c4.text_input("locale", value="")
currency = c5.text_input("currency", value="")
exp_a = c6.text_input("exp_a (treatment)", value="exp_a")
exp_b = c7.text_input("exp_b (control)", value="exp_b")

with st.expander("進階條件"):
    a1, a2, a3, a4 = st.columns(4)
    kkud = a1.text_input("kkud (device_id)")
    member_uuid = a2.text_input("member_uuid", help="走 POST body,不進 URL")
    session_id = a3.text_input("session_id")
    cache_hit = a4.selectbox("cache_hit", ["(不限)", "true", "false"])

run = st.button("查詢", type="primary")
if not run and "ran" not in st.session_state:
    st.stop()
st.session_state["ran"] = True

if not date:
    st.error("date 為必填(UTC+8)")
    st.stop()

# ── 事件列表(身分摘要用)──────────────────────────────────────────────────────
search_body = {
    "date": date,
    "keyword": keyword or None,
    "kkud": kkud or None,
    "member_uuid": member_uuid or None,
    "session_id": session_id or None,
    "locale": locale or None,
    "lang": lang or None,
    "currency": currency or None,
    "cache_hit": None if cache_hit == "(不限)" else cache_hit == "true",
}
resp = requests.post(f"{API_BASE}/api/events/search", json=search_body, timeout=30)
if resp.status_code == 400:
    st.error(f"參數錯誤:{resp.json().get('detail')}")
    st.stop()
events = resp.json()["rows"]

# ══ 6.2 對照面板 ═══════════════════════════════════════════════════════════════

if keyword and exp_a and exp_b:
    cmp_params = {
        "date": date, "keyword": keyword,
        "locale": locale or None, "exp_a": exp_a, "exp_b": exp_b,
    }
    # UI 選了 cache_hit 條件時,compare 選 session 也要尊重同一條件
    if cache_hit != "(不限)":
        cmp_params["cache_hit"] = cache_hit
    cmp_data = _get("/api/compare", cmp_params)
    m = cmp_data["metrics"]

    st.subheader("對照面板")
    ev_a = next((e for e in events if e["exp_version"] == exp_a), None)
    ev_b = next((e for e in events if e["exp_version"] == exp_b), None)
    id_line = []
    for tag, ev in (("A/treatment", ev_a), ("B/control", ev_b)):
        if ev:
            login = "已登入" if ev.get("logged_in") else "未登入"
            id_line.append(
                f"**{tag}** `{ev['exp_version']}` · {login} · {ev['event_type']}"
                f" · {ev['event_date_local']}"
            )
    if id_line:
        st.markdown(" | ".join(id_line))

    k1, k2, k3, k4 = st.columns(4)
    strength = m["personalization_strength"]
    warning = m["warning"]
    k1.metric("個性化強度", f"{strength:.0%}")
    if warning == "suspect_inactive":
        k1.error("疑似個性化未生效 (<5%)")
    elif warning == "suspect_excessive":
        k1.warning("疑似個性化過度,長尾風險 (>60%)")
    k2.metric("Top10 重疊", m["top10_overlap"])
    k3.metric("位置變動數", m["rank_changes"])
    k4.metric("同分帶內變動數", m["tie_unresolvable_changes"])

    d = cmp_data["dispersion_a"]
    if d["range"] is not None:
        gap = d["min_adjacent_gap"]
        ulp = d["min_adjacent_gap_ulp"]
        gap_txt = (f" · 最小相鄰間距 {gap:.3g}" if gap is not None else "")
        ulp_txt = (f"(≈ {ulp:.1f} 個 float32 ULP)" if ulp is not None else "")
        st.caption(
            f"A 組分數離散度:全距 {d['range']:.3g} · 相對差異 {d['relative_range']:.2g}"
            f"{gap_txt}{ulp_txt}"
            f" — 間距 ≤10 ULP 的相鄰對視為同分,順序不可判讀"
        )

    # ══ 6.3 排序表 ═══════════════════════════════════════════════════════════
    st.subheader("排序表")
    st.caption("精排邊界:rank ≤ 100 進精排;之後為純召回序 (total_count 常見數百)")

    # 4.4:整頁落在精排範圍外 → 頂部提示
    ranks_present = [r["rank_a"] for r in cmp_data["rows"] if r["rank_a"] is not None] + \
                    [r["rank_b"] for r in cmp_data["rows"] if r["rank_b"] is not None]
    if ranks_present and min(ranks_present) > 100:
        st.info("本頁所有商品皆在精排範圍外(rank > 100)— 純召回序,個性化不生效,"
                "排序差異屬既有產品行為而非 bug")

    header = "<tr><th style='text-align:left'>prod_mid</th><th>A</th><th>B</th>" \
             "<th style='text-align:right'>ltr_score(A)</th>" \
             "<th style='text-align:left'>相關性 (可售/地點/類目/IP/主題/文本)</th>" \
             "<th style='text-align:left'>判讀</th></tr>"
    body_rows = []
    crossed_boundary = False
    for r in cmp_data["rows"]:
        # 4.4:在 rank=100 邊界處插一條標示列
        ra = r["rank_a"]
        if not crossed_boundary and ra is not None and ra > 100:
            crossed_boundary = True
            body_rows.append(
                "<tr><td colspan='6' style='border-top:2px dashed #f59e0b;"
                "color:#b45309;font-size:11px;padding:2px 6px'>"
                "─── 精排邊界 rank=100:以下未進精排,僅依召回序排列 ───</td></tr>"
            )
        v = r["verdict"]
        row_bg = "#fef9c3" if v in ("only_a", "only_b") else "transparent"
        verdict_label = _esc(VERDICT_TEXT.get(v, v))
        ad = " <span style='font-size:10px;background:#fee2e2;color:#991b1b;" \
             "padding:0 4px;border-radius:3px'>AD</span>" if r["is_ad"] else ""
        # 4.4:未進精排的列,分數欄明示「未進精排」而非空白
        score = r.get("ltr_score_a")
        score_cell = ("<span style='color:#94a3b8;font-size:11px'>未進精排</span>"
                      if not r["in_rerank_scope"]
                      else (f"{score:.5f}" if score is not None else "—"))
        rel = r["relevance_a"] or r["relevance_b"]
        body_rows.append(
            f"<tr style='background:{row_bg};border-top:1px solid #e2e8f0'>"
            f"<td style='font-family:monospace'>{_esc(r['prod_mid'])}{ad}</td>"
            f"<td style='text-align:center'>{ra if ra is not None else '—'}</td>"
            f"<td style='text-align:center'>{r['rank_b'] if r['rank_b'] is not None else '—'}</td>"
            f"<td style='text-align:right;font-family:monospace;font-size:11px'>{score_cell}</td>"
            f"<td>{_lamps(rel)}</td>"
            f"<td style='font-size:12px'>{verdict_label}</td></tr>"
        )
    st.markdown(
        f"<table style='width:100%;border-collapse:collapse;font-size:13px'>"
        f"{header}{''.join(body_rows)}</table>",
        unsafe_allow_html=True,
    )

# ══ 6.4 特徵面板 ═══════════════════════════════════════════════════════════════

st.subheader("特徵面板")
if not events:
    st.info("無符合條件的事件")
    st.stop()

pick = st.selectbox(
    "選擇事件",
    [e["session_id"] for e in events],
    format_func=lambda s: next(
        f"{e['session_id']} · {e['exp_version']} · {e['event_type']}"
        for e in events if e["session_id"] == s
    ),
)
picked_ev = next(e for e in events if e["session_id"] == pick)
# cluster hint:帶上叢集鍵讓 BQ 點查能剪枝,不掃整個分區窗
_hints = {
    "keyword": picked_ev.get("keyword"),
    "exp_version": picked_ev.get("exp_version"),
    "locale": picked_ev.get("locale"),
}
detail = _get(f"/api/events/{pick}", {"date": date, **_hints})

flags = detail["quality_flags"]
joined_ok = not flags["join_failed"]

# 順序固定:品質旗標最上面 — 它決定下面的數值能不能信 (spec 6.4)
f1, f2, f3 = st.columns(3)
if flags["join_failed"]:
    f1.error("join_failed:串不回 recall — 以下 uf/cf 不可信")
else:
    f1.success("join OK")
if flags["uf_absent"]:
    f2.warning("uf_absent:串到了但上游沒推 uf")
if flags["ltr_features_recovered"]:
    f3.warning("ltr_features 由 cache donor 回收,非原生")

cov = detail["coverage_baseline"]
grey = "opacity:0.35;pointer-events:none;" if not joined_ok else ""
uf = detail["uf"]
uf_rows = "".join(
    f"<tr><td style='width:90px'><b>{name}</b></td>"
    f"<td style='width:110px'><span style='font-size:11px;background:#e0e7ff;"
    f"color:#3730a3;padding:1px 6px;border-radius:8px'>覆蓋率基準 {cov[key]:.0%}</span></td>"
    f"<td style='font-family:monospace;font-size:12px'>"
    f"{_esc(uf[field]) if uf[field] is not None else '<i>本筆無資料</i>'}</td></tr>"
    for name, key, field in [
        ("intent", "uf_intent", "intent"),
        ("profile", "uf_profile", "profile"),
        ("lbs", "uf_lbs", "lbs"),
    ]
)
cf = detail["cf_summary"]
# cf 的覆蓋率基準是 100% (spec 4.5) — 與 uf 一樣並列顯示
cf_badge = (
    f"<span style='font-size:11px;background:#e0e7ff;color:#3730a3;"
    f"padding:1px 6px;border-radius:8px;margin-right:8px'>cf 覆蓋率基準 {cov['cf']:.0%}</span>"
)
cf_chips = cf_badge + "".join(
    f"<span style='display:inline-block;background:#f1f5f9;border-radius:10px;"
    f"padding:2px 10px;margin-right:6px;font-size:12px'>{k}: {_esc(v)}</span>"
    for k, v in [
        ("platform", cf["platform"]), ("hour", cf["hour"]),
        ("weekday", cf["weekday"]), ("query.final", cf["query_final"]),
        ("tokens", cf["query_tokens"]),
    ]
)
st.markdown(
    f"<div style='{grey}'>"
    f"<table style='font-size:13px'>{uf_rows}</table>"
    f"<div style='margin-top:8px'>{cf_chips}</div></div>",
    unsafe_allow_html=True,
)

if joined_ok and st.button("展開完整 cf(約 138 KB,單筆載入)"):
    cf_full = _get(f"/api/events/{pick}/cf", {"date": date, **_hints})
    st.json(cf_full["cf_raw"])
