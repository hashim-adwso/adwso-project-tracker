"""Look and feel: palette, type, and small reusable display pieces."""
from __future__ import annotations

import html
from datetime import date

import streamlit as st

# Lapis lazuli and saffron — two materials from Afghanistan's north and north-east.
LAPIS = "#1F3A68"
LAPIS_BRIGHT = "#2E5AAC"
SAFFRON = "#D9A23A"
INK = "#18202E"
SLATE = "#667085"
PAPER = "#F4F6F9"
LINE = "#E1E6EE"
POMEGRANATE = "#B23A4E"
LEAF = "#2F7D5B"

STATUS_STYLE = {
    "Not started": {"fg": "#475467", "bg": "#EEF1F5", "dot": "#98A2B3"},
    "In progress": {"fg": LAPIS_BRIGHT, "bg": "#E8EEF9", "dot": LAPIS_BRIGHT},
    "Overdue":     {"fg": POMEGRANATE, "bg": "#F8E9EC", "dot": POMEGRANATE},
    "Blocked":     {"fg": "#9A5B00", "bg": "#FBF0DC", "dot": "#C27C0E"},
    "Completed":   {"fg": LEAF, "bg": "#E6F2EC", "dot": LEAF},
    "Cancelled":   {"fg": "#667085", "bg": "#F2F4F7", "dot": "#C0C6D0"},
}
PRIORITY_STYLE = {
    "Low": ("#667085", "Low"),
    "Normal": ("#475467", "Normal"),
    "High": ("#B26A00", "High priority"),
}
e = html.escape


CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Figtree:wght@400;500;600;700;800&display=swap');

html, body, [class*="css"], .stApp, button, input, textarea, select {{
  font-family: 'Figtree', system-ui, sans-serif !important;
}}
.stApp {{ background: {PAPER}; color: {INK}; }}
[data-testid="stHeader"] {{ background: transparent; }}
.block-container {{ padding-top: 1.2rem; max-width: 1280px; }}
h1, h2, h3 {{ color: {INK}; letter-spacing: -0.01em; }}

/* Sidebar */
[data-testid="stSidebar"] {{ background: {LAPIS}; }}
[data-testid="stSidebar"] * {{ color: #E7ECF5; }}
[data-testid="stSidebarNav"] a span {{ color: #E7ECF5 !important; font-weight: 500; }}
[data-testid="stSidebarNav"] a[aria-current="page"] {{ background: rgba(255,255,255,.12); }}
[data-testid="stSidebarNav"] a[aria-current="page"] span {{ color: #fff !important; font-weight: 700; }}
[data-testid="stSidebar"] button {{ background: rgba(255,255,255,.08); border-color: rgba(255,255,255,.25); }}
[data-testid="stSidebar"] button:hover {{ border-color: {SAFFRON}; }}
[data-testid="stSidebarHeader"] img {{ height:2.6rem; max-width:none; }}
[data-testid="stSidebarNavSeparator"] {{ border-color: rgba(255,255,255,.15); }}

.tt-brand {{ display:flex; align-items:center; gap:.6rem; margin:.2rem 0 1.2rem; }}
.tt-mark {{ width:34px; height:34px; border-radius:9px; background:{SAFFRON};
  display:grid; place-items:center; color:{LAPIS}; font-weight:800; font-size:1rem; }}
.tt-brand b {{ font-size:1.05rem; color:#fff; display:block; line-height:1.1; }}
.tt-brand small {{ color:#B8C4DA; font-size:.78rem; }}
.tt-me {{ border-top:1px solid rgba(255,255,255,.15); padding-top:.8rem; margin-top:.6rem; font-size:.85rem; }}
.tt-me b {{ color:#fff; display:block; }}
.tt-me span {{ color:#B8C4DA; }}

/* Page heading */
.tt-head {{ display:flex; align-items:flex-end; justify-content:space-between; gap:1rem;
  border-bottom:2px solid {INK}; padding-bottom:.6rem; margin-bottom:1.2rem; }}
.tt-head h1 {{ font-size:2rem; font-weight:800; margin:0; padding:0; line-height:1.1; }}
.tt-head p {{ margin:.25rem 0 0; color:{SLATE}; font-size:.95rem; }}

/* Status pill / chips */
.tt-pill {{ display:inline-flex; align-items:center; gap:.35rem; padding:.12rem .55rem; border-radius:999px;
  font-size:.75rem; font-weight:600; white-space:nowrap; }}
.tt-pill i {{ width:7px; height:7px; border-radius:50%; display:inline-block; }}
.tt-chip {{ display:inline-block; font-size:.74rem; font-weight:600; padding:.08rem .45rem; border-radius:5px;
  border:1px solid {LINE}; color:{SLATE}; background:#fff; white-space:nowrap; }}
.tt-proj {{ display:inline-flex; align-items:center; gap:.35rem; font-size:.78rem; font-weight:600; color:{SLATE}; }}
.tt-proj i {{ width:9px; height:9px; border-radius:2px; display:inline-block; }}

/* Board */
.tt-col-head {{ display:flex; align-items:center; justify-content:space-between; padding:.35rem .2rem .6rem;
  border-bottom:3px solid var(--c); margin-bottom:.6rem; }}
.tt-col-head b {{ font-size:.95rem; }}
.tt-col-head span {{ font-size:.8rem; color:{SLATE}; font-weight:600; }}
[class*="st-key-card_"] {{ background:#fff; border:1px solid {LINE} !important; border-radius:10px;
  padding:.75rem .85rem .35rem !important; gap:.35rem !important; }}
[class*="st-key-card_"]:hover {{ border-color:#C3CCDA !important; }}
.tt-card-title {{ font-weight:700; font-size:.98rem; line-height:1.3; margin:.25rem 0 .35rem; color:{INK}; }}
.tt-meta {{ display:flex; flex-wrap:wrap; gap:.35rem .7rem; align-items:center; font-size:.8rem; color:{SLATE}; }}
.tt-due-over {{ color:{POMEGRANATE}; font-weight:700; }}
.tt-due-soon {{ color:#B26A00; font-weight:700; }}
.tt-bar {{ height:5px; border-radius:3px; background:#EDF0F5; overflow:hidden; margin:.5rem 0 .1rem; }}
.tt-bar > div {{ height:100%; border-radius:3px; }}
.tt-empty-col {{ border:1.5px dashed {LINE}; border-radius:10px; padding:1.1rem; text-align:center;
  color:{SLATE}; font-size:.85rem; }}

/* Numbers strip */
.tt-stats {{ display:grid; grid-template-columns:repeat(4, minmax(0,1fr)); background:#fff; border:1px solid {LINE};
  border-radius:12px; margin-bottom:1.4rem; overflow:hidden; }}
.tt-stat {{ padding:1rem 1.2rem; border-right:1px solid {LINE}; }}
.tt-stat:last-child {{ border-right:none; }}
.tt-stat b {{ font-size:2.1rem; font-weight:800; line-height:1; display:block; color:{INK}; }}
.tt-stat span {{ color:{SLATE}; font-size:.88rem; }}
.tt-stat.warn b {{ color:{POMEGRANATE}; }}
@media (max-width: 700px) {{
  .tt-stats {{ grid-template-columns:repeat(2, minmax(0,1fr)); }}
  .tt-stat:nth-child(2) {{ border-right:none; }}
  .tt-stat:nth-child(-n+2) {{ border-bottom:1px solid {LINE}; }}
}}

/* Project progress rows */
.tt-prow {{ display:grid; grid-template-columns: minmax(0,2.2fr) minmax(0,3fr) 3.5rem; gap:1rem; align-items:center;
  padding:.7rem 0; border-bottom:1px solid {LINE}; }}
.tt-prow:last-child {{ border-bottom:none; }}
.tt-prow b {{ display:block; font-size:.95rem; }}
.tt-prow small {{ color:{SLATE}; }}
.tt-stack {{ display:flex; height:10px; border-radius:5px; overflow:hidden; background:#EDF0F5; }}
.tt-prow em {{ font-style:normal; font-weight:800; text-align:right; }}
.tt-legend {{ display:flex; gap:1rem; flex-wrap:wrap; font-size:.8rem; color:{SLATE}; margin:.2rem 0 .4rem; }}
.tt-legend i {{ width:9px; height:9px; border-radius:2px; display:inline-block; margin-right:.3rem; }}

/* Activity log */
.tt-log {{ border-left:2px solid {LINE}; margin-left:.3rem; padding-left:1rem; }}
.tt-log-item {{ position:relative; padding:.1rem 0 .9rem; font-size:.88rem; }}
.tt-log-item:before {{ content:""; position:absolute; left:-1.36rem; top:.42rem; width:9px; height:9px;
  border-radius:50%; background:#fff; border:2px solid {SLATE}; }}
.tt-log-item.note:before {{ border-color:{SAFFRON}; background:{SAFFRON}; }}
.tt-log-item small {{ color:{SLATE}; display:block; }}
.tt-log-item p {{ margin:.15rem 0 0; white-space:pre-wrap; }}

/* Gate (sign-in / waiting) */
.tt-gate {{ max-width:520px; margin:12vh auto 1.4rem; text-align:center; }}
.tt-gate .tt-mark {{ width:56px; height:56px; font-size:1.5rem; border-radius:14px; margin:0 auto 1.2rem; }}
.tt-gate h1 {{ font-size:2rem; font-weight:800; margin:0 0 .5rem; }}
.tt-gate p {{ color:{SLATE}; font-size:1rem; line-height:1.55; }}

.tt-banner {{ background:#FFF6E3; border:1px solid #F0D9A6; color:#6B4E10; border-radius:8px;
  padding:.45rem .8rem; font-size:.85rem; margin-bottom:.9rem; }}

/* Buttons and inputs */
.stButton button[kind="primary"], .stFormSubmitButton button[kind="primary"] {{
  background:{LAPIS_BRIGHT}; border-color:{LAPIS_BRIGHT}; font-weight:600; }}
.stButton button[kind="primary"]:hover {{ background:{LAPIS}; border-color:{LAPIS}; }}
.stButton button[kind="tertiary"] {{ color:{LAPIS_BRIGHT}; font-weight:600; padding-left:0; }}
:focus-visible {{ outline:2px solid {SAFFRON} !important; outline-offset:2px; }}
/* Activity type tags */
.tt-type {{ display:inline-flex; align-items:center; gap:.3rem; font-size:.74rem; font-weight:600; color:{SLATE};
  background:#fff; border:1px solid {LINE}; border-radius:5px; padding:.06rem .45rem; white-space:nowrap; }}
.tt-recur {{ display:inline-flex; align-items:center; gap:.3rem; font-size:.74rem; font-weight:700; color:#7A4D00;
  background:#FBF0DC; border-radius:5px; padding:.06rem .45rem; white-space:nowrap; }}
.tt-key {{ display:inline-block; font-size:.72rem; font-weight:700; color:{LAPIS}; background:#E8EEF9;
  border-radius:5px; padding:.06rem .45rem; white-space:nowrap; }}
.tt-ref {{ font-weight:700; color:{SLATE}; font-size:.78rem; margin-right:.35rem; }}

/* Week schedule */
.tt-day-head {{ padding:.3rem .1rem .45rem; border-bottom:3px solid {LINE}; margin-bottom:.5rem; }}
.tt-day-head b {{ display:block; font-size:.92rem; }}
.tt-day-head span {{ font-size:.8rem; color:{SLATE}; }}
.tt-day-head.today {{ border-bottom-color:{SAFFRON}; }}
.tt-day-head.today b {{ color:{LAPIS}; }}
.tt-day-head.off b, .tt-day-head.off span {{ color:#98A2B3; }}
.tt-running {{ background:#fff; border:1px solid {LINE}; border-radius:10px; padding:.6rem .9rem; margin-bottom:1rem; }}
.tt-running h4 {{ margin:0 0 .4rem; font-size:.9rem; }}
.tt-run-row {{ display:grid; grid-template-columns:minmax(0,3fr) minmax(0,2fr) 3rem; gap:.8rem; align-items:center;
  font-size:.86rem; padding:.3rem 0; border-top:1px solid {LINE}; }}
.tt-run-row:first-of-type {{ border-top:none; }}
.tt-run-row small {{ color:{SLATE}; }}

/* Month grid */
.tt-month {{ display:grid; grid-template-columns:repeat(7, minmax(0,1fr)); border:1px solid {LINE}; border-radius:12px;
  overflow:hidden; background:#fff; }}
.tt-month .h {{ background:#EEF1F5; font-size:.78rem; font-weight:700; color:{SLATE}; padding:.4rem .5rem; }}
.tt-month .c {{ min-height:96px; border-top:1px solid {LINE}; border-left:1px solid {LINE}; padding:.3rem .35rem; font-size:.75rem; }}
.tt-month .c:nth-child(7n+1) {{ border-left:none; }}
.tt-month .c.out {{ background:#FAFBFC; color:#B0B7C3; }}
.tt-month .c.today {{ box-shadow: inset 0 0 0 2px {SAFFRON}; }}
.tt-month .n {{ font-weight:700; font-size:.8rem; margin-bottom:.2rem; display:block; }}
.tt-month .ev {{ display:block; border-radius:4px; padding:.05rem .3rem; margin-bottom:.15rem; white-space:nowrap;
  overflow:hidden; text-overflow:ellipsis; font-weight:600; }}
@media (max-width: 800px) {{ .tt-month .c {{ min-height:64px; }} .tt-month .ev {{ font-size:.66rem; }} }}

/* Date ticks inside the activity window */
.tt-tick {{ display:flex; gap:.6rem; align-items:baseline; font-size:.9rem; }}
.tt-tick small {{ color:{SLATE}; }}

/* Money */
.tt-money {{ display:grid; grid-template-columns:repeat(4, minmax(0,1fr)); gap:0; background:#fff; border:1px solid {LINE};
  border-radius:12px; overflow:hidden; margin-bottom:1.2rem; }}
.tt-money > div {{ padding:.9rem 1.1rem; border-right:1px solid {LINE}; }}
.tt-money > div:last-child {{ border-right:none; }}
.tt-money b {{ display:block; font-size:1.45rem; font-weight:800; line-height:1.15; font-variant-numeric:tabular-nums; }}
.tt-money span {{ color:{SLATE}; font-size:.85rem; }}
.tt-money small {{ display:block; color:{SLATE}; font-size:.78rem; margin-top:.15rem; }}
@media (max-width: 800px) {{ .tt-money {{ grid-template-columns:repeat(2, minmax(0,1fr)); }}
  .tt-money > div:nth-child(2) {{ border-right:none; }} .tt-money > div:nth-child(-n+2) {{ border-bottom:1px solid {LINE}; }} }}
.tt-burn {{ height:12px; border-radius:6px; background:#EDF0F5; overflow:hidden; margin:.4rem 0 .2rem; }}
.tt-burn > div {{ height:100%; background:{LAPIS_BRIGHT}; }}
.tt-cat {{ display:grid; grid-template-columns:minmax(0,2.4fr) minmax(0,3fr) 7.5rem 4rem; gap:.9rem; align-items:center;
  padding:.55rem 0; border-bottom:1px solid {LINE}; font-size:.9rem; }}
.tt-cat:last-child {{ border-bottom:none; }}
.tt-cat em {{ font-style:normal; text-align:right; font-variant-numeric:tabular-nums; color:{SLATE}; }}
.tt-cat strong {{ text-align:right; font-variant-numeric:tabular-nums; }}
.tt-note {{ font-size:.84rem; color:{SLATE}; background:#fff; border:1px solid {LINE}; border-radius:8px; padding:.55rem .8rem; }}
.tt-who {{ font-size:.82rem; color:{SLATE}; }}
</style>
"""


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def gate(title: str, body: str) -> None:
    inject_css()
    st.markdown(
        f'<div class="tt-gate"><div class="tt-mark">✓</div><h1>{e(title)}</h1><p>{e(body)}</p></div>',
        unsafe_allow_html=True,
    )


def page_head(title: str, subtitle: str = "") -> None:
    sub = f"<p>{e(subtitle)}</p>" if subtitle else ""
    st.markdown(f'<div class="tt-head"><div><h1>{e(title)}</h1>{sub}</div></div>', unsafe_allow_html=True)


def status_pill(status: str) -> str:
    s = STATUS_STYLE.get(status, STATUS_STYLE["Not started"])
    return (f'<span class="tt-pill" style="color:{s["fg"]};background:{s["bg"]}">'
            f'<i style="background:{s["dot"]}"></i>{e(status)}</span>')


def priority_chip(priority: str) -> str:
    if priority != "High":
        return ""
    color, label = PRIORITY_STYLE["High"]
    return f'<span class="tt-chip" style="color:{color};border-color:{color}55">{e(label)}</span>'


def type_tag(a: dict) -> str:
    from core.acts import FREQUENCIES, KINDS
    if a["recurring"]:
        return f'<span class="tt-recur" title="This activity repeats">↻ Recurring {e(FREQUENCIES.get(a["frequency"], "").lower())}</span>'
    return f'<span class="tt-type">{e(KINDS[a["kind"]])}</span>'


def key_tag(a: dict) -> str:
    return '<span class="tt-key" title="Shown to management">Key activity</span>' if a["key_activity"] else ""


def progress_bar(pct: int, color: str) -> str:
    pct = max(0, min(100, int(pct or 0)))
    return f'<div class="tt-bar" title="{pct}% complete"><div style="width:{pct}%;background:{color}"></div></div>'


def fmt_day(v) -> str:
    from datetime import date
    if not v:
        return ""
    dd = v if isinstance(v, date) else date.fromisoformat(str(v)[:10])
    return dd.strftime("%d %b %Y")


def money(v: float | None, cur: str = "") -> str:
    if v is None:
        return "–"
    s = f"{abs(v):,.2f}"
    s = f"{cur} {s}".strip()
    return f"−{s}" if v < 0 else s
