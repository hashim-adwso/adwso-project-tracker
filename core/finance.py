"""Budget pages: summary, budget lines, daily ledger, invoices and instalments."""
from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import date, timedelta

import pandas as pd
import streamlit as st

from core import db, money, ui
from core.ui import e
from core.work import can, flash, me, show_flash


def _d(v):
    return date.fromisoformat(str(v)[:10]) if v else None


def strip(cells: list[tuple[str, str, str]]) -> str:
    inner = "".join(f'<div><b>{e(v)}</b><span>{e(label)}</span>{f"<small>{e(sub)}</small>" if sub else ""}</div>'
                    for v, label, sub in cells)
    return f'<div class="tt-money">{inner}</div>'


def elapsed_pct() -> float | None:
    s = db.settings()
    if not (s["start_date"] and s["end_date"]):
        return None
    a, b, t = _d(s["start_date"]), _d(s["end_date"]), date.today()
    total = (b - a).days + 1
    return max(0.0, min(100.0, ((t - a).days + 1) / total * 100)) if total > 0 else None


# =========================================================================== page
def page_budget() -> None:
    show_flash()
    s = db.settings()
    t = money.totals()
    edit = can("edit_finance")
    sub = "Spending against each budget line, payments from the partner, and the daily ledger."
    if not edit:
        sub += " View only: the finance focal point records entries."
    ui.page_head("Budget and finance", sub)
    if t["demo_rows"]:
        st.markdown(f'<div class="tt-banner">{t["demo_rows"]} demo entries are loaded so these pages can be '
                    'presented. Their descriptions start with [Demo]. Remove them on the Project settings page '
                    'before recording real figures.</div>', unsafe_allow_html=True)
    tabs = st.tabs(["Summary", "Budget lines", "Daily ledger", "Invoices and instalments"])
    with tabs[0]:
        summary(t, s)
    with tabs[1]:
        budget_lines(t)
    with tabs[2]:
        ledger(t, edit)
    with tabs[3]:
        invoices_tab(t, s, edit)


def summary(t: dict, s: dict, compact: bool = False) -> None:
    cur, alt = t["currency"], t["alt"]
    ep = elapsed_pct()
    st.markdown(strip([
        (ui.money(t["budget"], cur), "Total budget", f"{ui.money(t['budget_alt'], alt)} in the agreement"),
        (ui.money(t["spent"], cur), "Spent to date", f"{t['burn']:.1f}% of the budget"),
        (ui.money(t["balance"], cur), "Remaining budget", ""),
        (ui.money(t["cash"], cur), "Cash in hand for the project", "Received from the partner minus spending"),
    ]), unsafe_allow_html=True)
    st.markdown(strip([
        (ui.money(t["invoiced"], alt), "Requested from the partner", f"{t['n_invoices']} invoice(s) and requests"),
        (ui.money(t["received"], alt), "Received from the partner", f"{t['n_instalments']} instalment(s)"),
        (ui.money(t["outstanding"], alt), "Requested but not yet received", ""),
        (f"{(t['received'] / t['budget_alt'] * 100) if t['budget_alt'] else 0:.1f}%", "Of the agreement received", ""),
    ]), unsafe_allow_html=True)
    if t["uncredited"]:
        st.caption(f"{t['uncredited']} instalment(s) have no bank-credited amount yet, so cash in hand may be understated.")

    burn = min(100, t["burn"])
    tick = f'<div style="position:relative;height:0"><div title="Time elapsed" style="position:absolute;left:{ep:.1f}%;top:-14px;width:2px;height:16px;background:{ui.SAFFRON}"></div></div>' if ep is not None else ""
    st.markdown(f"**Spending pace.** {t['burn']:.1f}% of the budget is spent"
                + (f", and {ep:.0f}% of the project period has passed (the saffron mark)." if ep is not None else ".")
                + f'<div class="tt-burn"><div style="width:{burn:.1f}%"></div></div>{tick}', unsafe_allow_html=True)

    if compact:
        return
    left, right = st.columns([1.4, 1], gap="large")
    with left:
        st.subheader("By budget category")
        cats: dict[str, list] = defaultdict(lambda: [0.0, 0.0])
        order = []
        for ln in money.line_summary():
            if ln["category"] not in cats:
                order.append(ln["category"])
            cats[ln["category"]][0] += ln["budget"]
            cats[ln["category"]][1] += ln["spent"]
        rows = ""
        for c in order:
            b, sp = cats[c]
            p = sp / b * 100 if b else 0
            col = ui.POMEGRANATE if p > 100 else (ui.SAFFRON if p > 90 else ui.LAPIS_BRIGHT)
            rows += (f'<div class="tt-cat"><div>{e(c)}</div><div class="tt-burn" style="margin:0">'
                     f'<div style="width:{min(p, 100):.1f}%;background:{col}"></div></div>'
                     f'<em>{ui.money(sp, "")} / {ui.money(b, "")}</em><strong>{p:.0f}%</strong></div>')
        st.markdown(rows, unsafe_allow_html=True)
        st.caption(f"Amounts in {cur}.")
    with right:
        st.subheader("Spending by month")
        m = money.monthly_spending()
        if m:
            chart = pd.DataFrame({"Month": [datetime_month(x["month"]) for x in m],
                                  f"Spent ({cur})": [round(x["amount"], 2) for x in m]}).set_index("Month")
            st.bar_chart(chart, color=ui.LAPIS_BRIGHT, height=260)
        else:
            st.markdown('<div class="tt-empty-col">No spending recorded yet.</div>', unsafe_allow_html=True)
        watch = [ln for ln in money.line_summary() if ln["pct"] > 90]
        if watch:
            st.subheader("Lines to watch")
            for ln in watch:
                msg = "over budget" if ln["pct"] > 100 else "above 90% used"
                st.markdown(f"**{e(ln['code'])}** {e(ln['description'])}: {ln['pct']:.0f}% used, {msg}.")
        terms = s.get("payment_terms")
        if terms:
            st.subheader("Payment terms")
            st.markdown(f'<div class="tt-note">{e(terms).replace(chr(10), "<br>")}</div>', unsafe_allow_html=True)


def datetime_month(ym: str) -> str:
    y, m = ym.split("-")
    return f"{calendar.month_abbr[int(m)]} {y}"


def budget_lines(t: dict) -> None:
    cur, alt = t["currency"], t["alt"]
    ls = money.line_summary()
    df = pd.DataFrame([{
        "id": ln["id"], "Code": ln["code"], "Partner line": ln["donor_line"], "Category": ln["category"],
        "Budget line": ln["description"], f"Budget ({cur})": ln["budget"], f"Budget ({alt})": ln["budget_alt"],
        f"Spent ({cur})": ln["spent"], f"Balance ({cur})": ln["balance"], "Used": round(ln["pct"], 1),
        "Entries": ln["entries"], "Last expense": _d(ln["last_day"]),
    } for ln in ls])
    num = lambda: st.column_config.NumberColumn(format="%,.2f")  # noqa: E731
    ev = st.dataframe(
        df, hide_index=True, key="bl_table", on_select="rerun", selection_mode="single-row",
        column_order=["Code", "Partner line", "Budget line", f"Budget ({cur})", f"Spent ({cur})", f"Balance ({cur})",
                      "Used", f"Budget ({alt})", "Entries", "Last expense", "Category"],
        column_config={"Budget line": st.column_config.TextColumn(width="large"),
                       f"Budget ({cur})": num(), f"Budget ({alt})": num(), f"Spent ({cur})": num(),
                       f"Balance ({cur})": num(), "Last expense": st.column_config.DateColumn(format="DD MMM YYYY"),
                       "Used": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.1f%%")},
        height=min(35 * (len(df) + 1) + 3, 720))
    st.caption(f"Totals: budget {ui.money(t['budget'], cur)} ({ui.money(t['budget_alt'], alt)}), spent "
               f"{ui.money(t['spent'], cur)}, balance {ui.money(t['balance'], cur)}. "
               f"{alt} figures are as agreed in the budget annex. Select a line to see its expenses.")
    st.download_button("Download budget lines (CSV)", df.drop(columns=["id"]).to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"budget_lines_{date.today():%Y%m%d}.csv", mime="text/csv")
    sel = ev.selection.rows if ev and ev.selection else []
    if sel:
        ln = ls[sel[0]]
        st.subheader(f"{ln['code']} {ln['description']}")
        st.caption(f"Budget basis: {ln['units']}" if ln["units"] else "")
        ex = money.expenses(line_id=ln["id"])
        if not ex:
            st.markdown('<div class="tt-empty-col">No expenses recorded on this line yet.</div>', unsafe_allow_html=True)
        else:
            st.dataframe(pd.DataFrame([{"Date": _d(x["day"]), "Description": x["description"], "Paid to": x["payee"],
                                        "Voucher": x["voucher"], f"Amount ({cur})": x["amount"]} for x in ex]),
                         hide_index=True, column_config={f"Amount ({cur})": num(),
                                                         "Date": st.column_config.DateColumn(format="DD MMM YYYY")})


def ledger(t: dict, edit: bool) -> None:
    cur = t["currency"]
    s = db.settings()
    ls = money.lines()
    lmap = {ln["id"]: ln for ln in ls}
    if edit:
        with st.expander("Record an expense", expanded=False):
            with st.form("exp", clear_on_submit=True):
                c1, c2 = st.columns([1, 2.5])
                day = c1.date_input("Date paid", date.today(), format="DD/MM/YYYY")
                line = c2.selectbox("Budget line", [ln["id"] for ln in ls],
                                    format_func=lambda i: f"{lmap[i]['code']}  {lmap[i]['description']}",
                                    index=None, placeholder="Choose the budget line")
                desc = st.text_input("Description", placeholder="e.g. October salary, MHPSS counsellors (8)")
                c3, c4, c5, c6 = st.columns([1.6, 1, 1.2, 1.2])
                payee = c3.text_input("Paid to")
                voucher = c4.text_input("Voucher no.")
                method = c5.selectbox("Paid by", money.PAY_METHODS)
                amount = c6.number_input(f"Amount ({cur})", min_value=0.0, step=10.0, format="%.2f")
                if st.form_submit_button("Record expense", type="primary"):
                    problems = []
                    if not line:
                        problems.append("Choose the budget line.")
                    if not desc.strip():
                        problems.append("Add a description.")
                    if amount <= 0:
                        problems.append("Enter an amount above zero.")
                    if problems:
                        st.error(" ".join(problems))
                    else:
                        warn = []
                        if s["start_date"] and s["end_date"] and not (_d(s["start_date"]) <= day <= _d(s["end_date"])):
                            warn.append("The date is outside the project period, so the cost may not be eligible.")
                        bal = next(x for x in money.line_summary() if x["id"] == line)["balance"]
                        if amount > bal:
                            warn.append(f"This takes {lmap[line]['code']} over its budget by "
                                        f"{ui.money(amount - bal, cur)}. Check the partner's budget flexibility rules.")
                        money.add_expense(day, line, desc, payee, voucher, method, amount, me()["name"])
                        flash("Expense recorded" + ("; " + " ".join(warn) if warn else ""))
                        st.rerun()

    f1, f2, f3 = st.columns([1.2, 2, 2], vertical_alignment="bottom")
    today = date.today()
    preset = f1.selectbox("Period", ["This month", "Last month", "Project to date", "Custom"], key="lg_p")
    if preset == "This month":
        a, b = today.replace(day=1), today
    elif preset == "Last month":
        b = today.replace(day=1) - timedelta(days=1)
        a = b.replace(day=1)
    elif preset == "Project to date":
        a = _d(s["start_date"]) or date(2000, 1, 1)
        b = today
    else:
        rng = f2.date_input("From – to", (today.replace(day=1), today), format="DD/MM/YYYY", key="lg_c")
        a, b = (rng[0], rng[1]) if len(rng) == 2 else (today, today)
    lf = f3.selectbox("Budget line", [None] + [ln["id"] for ln in ls], key="lg_l",
                      format_func=lambda i: "All lines" if i is None else f"{lmap[i]['code']}  {lmap[i]['description']}")
    ex = money.expenses(a, b, lf)
    total = sum(x["amount"] for x in ex)
    st.caption(f"{a:%d %b %Y} to {b:%d %b %Y}: {len(ex)} entr{'y' if len(ex) == 1 else 'ies'}, "
               f"total {ui.money(total, cur)}.")
    if not ex:
        st.markdown('<div class="tt-empty-col">No expenses in this period.</div>', unsafe_allow_html=True)
        return
    running = 0.0
    recs = []
    for x in ex:
        running += x["amount"]
        recs.append({"id": x["id"], "Date": _d(x["day"]), "Line": x["code"], "Description": x["description"],
                     "Paid to": x["payee"], "Voucher": x["voucher"], "Paid by": x["method"],
                     f"Amount ({cur})": x["amount"], f"Running total ({cur})": round(running, 2),
                     "Entered by": x["entered_by"]})
    df = pd.DataFrame(recs)
    num = st.column_config.NumberColumn(format="%,.2f")
    ev = st.dataframe(df, hide_index=True, key="lg_table", on_select="rerun", selection_mode="single-row",
                      column_order=[c for c in df.columns if c != "id"],
                      column_config={"Date": st.column_config.DateColumn(format="ddd DD MMM YYYY"),
                                     "Description": st.column_config.TextColumn(width="large"),
                                     f"Amount ({cur})": num, f"Running total ({cur})": num},
                      height=min(35 * (len(df) + 1) + 3, 520))
    c1, c2 = st.columns([3, 1])
    c1.download_button("Download this ledger (CSV)", df.drop(columns=["id"]).to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"ledger_{a:%Y%m%d}_{b:%Y%m%d}.csv", mime="text/csv")
    sel = ev.selection.rows if ev and ev.selection else []
    if edit and sel:
        row = recs[sel[0]]
        with c2.popover("Delete selected entry", width="stretch"):
            st.write(f"Delete {row['Description']} ({ui.money(row[f'Amount ({cur})'], cur)}, {row['Date']:%d %b %Y})? "
                     "This can't be undone.")
            if st.button("Delete entry", type="primary", key="lg_del"):
                money.delete_expense(row["id"])
                flash("Entry deleted")
                st.rerun()

    st.subheader("Daily totals")
    daily = df.groupby("Date", as_index=False).agg(**{"Entries": ("id", "count"), f"Spent ({cur})": (f"Amount ({cur})", "sum")})
    daily[f"Cumulative ({cur})"] = daily[f"Spent ({cur})"].cumsum().round(2)
    st.dataframe(daily, hide_index=True, column_config={"Date": st.column_config.DateColumn(format="ddd DD MMM YYYY"),
                                                        f"Spent ({cur})": num, f"Cumulative ({cur})": num})


def invoices_tab(t: dict, s: dict, edit: bool) -> None:
    alt, cur = t["alt"], t["currency"]
    num = st.column_config.NumberColumn(format="%,.2f")
    st.subheader("Invoices and funds requests sent to the partner")
    inv = money.invoices()
    if edit:
        with st.expander("Record an invoice or funds request"):
            with st.form("inv", clear_on_submit=True):
                c1, c2, c3 = st.columns([1.2, 1.4, 1])
                number = c1.text_input("Number or reference")
                kind = c2.selectbox("Type", money.INVOICE_KINDS)
                sent = c3.date_input("Date sent", date.today(), format="DD/MM/YYYY")
                c4, c5, c6 = st.columns([2, 1.2, 1.2])
                period = c4.date_input("Period covered", (), format="DD/MM/YYYY")
                amount = c5.number_input(f"Amount ({alt})", min_value=0.0, step=100.0, format="%.2f")
                status = c6.selectbox("Status", money.INVOICE_STATUS)
                note = st.text_input("Note")
                if st.form_submit_button("Record", type="primary"):
                    if not number.strip() or (amount <= 0 and kind != "Financial report"):
                        st.error("Add the number and an amount above zero.")
                    else:
                        pf, pt = (period[0], period[1]) if len(period) == 2 else (None, None)
                        money.add_invoice(number, kind, sent, pf, pt, amount, status, note, me()["name"])
                        flash("Recorded")
                        st.rerun()
    if inv:
        df = pd.DataFrame([{"id": x["id"], "Sent": _d(x["sent_on"]), "Number": x["number"], "Type": x["kind"],
                            "Period": (f"{_d(x['period_from']):%d %b %Y} to {_d(x['period_to']):%d %b %Y}"
                                       if x["period_from"] and x["period_to"] else ""),
                            f"Amount ({alt})": x["amount"], "Status": x["status"], "Note": x["note"]} for x in inv])
        ev = st.dataframe(df, hide_index=True, key="inv_t", on_select="rerun", selection_mode="single-row",
                          column_order=[c for c in df.columns if c != "id"],
                          column_config={"Sent": st.column_config.DateColumn(format="DD MMM YYYY"), f"Amount ({alt})": num})
        st.caption(f"Total requested: {ui.money(t['invoiced'], alt)} (financial reports are not counted as requests).")
        sel = ev.selection.rows if ev and ev.selection else []
        if edit and sel:
            row = inv[sel[0]]
            c1, c2, c3 = st.columns([2, 1, 1], vertical_alignment="bottom")
            new = c1.selectbox(f"Status of {row['number']}", money.INVOICE_STATUS,
                               index=money.INVOICE_STATUS.index(row["status"]) if row["status"] in money.INVOICE_STATUS else 0,
                               key=f"is_{row['id']}")
            if c2.button("Update status", key=f"isb_{row['id']}", width="stretch"):
                money.set_invoice_status(row["id"], new)
                flash("Status updated")
                st.rerun()
            with c3.popover("Delete", width="stretch"):
                st.write("Delete this record? Linked instalments keep their amounts.")
                if st.button("Delete record", type="primary", key=f"idel_{row['id']}"):
                    money.delete_invoice(row["id"])
                    flash("Deleted")
                    st.rerun()
    else:
        st.markdown('<div class="tt-empty-col">Nothing sent to the partner yet.</div>', unsafe_allow_html=True)

    st.subheader("Instalments received")
    ins = money.instalments()
    if edit:
        with st.expander("Record an instalment received"):
            with st.form("ins", clear_on_submit=True):
                c1, c2 = st.columns([2, 1])
                label = c1.text_input("Instalment", placeholder="e.g. 1st instalment (pre-financing)")
                recv = c2.date_input("Date received", date.today(), format="DD/MM/YYYY")
                c3, c4, c5 = st.columns(3)
                amount = c3.number_input(f"Amount paid ({alt})", min_value=0.0, step=100.0, format="%.2f")
                credited = c4.number_input(f"Credited to bank ({cur})", min_value=0.0, step=100.0, format="%.2f",
                                           help="The amount that actually arrived in the account. Leave at 0 if not known yet.")
                link = c5.selectbox("For invoice/request", [None] + [x["id"] for x in inv],
                                    format_func=lambda i: "Not linked" if i is None else
                                    next(x["number"] for x in inv if x["id"] == i))
                c6, c7 = st.columns(2)
                ref = c6.text_input("Bank reference")
                note = c7.text_input("Note")
                if st.form_submit_button("Record instalment", type="primary"):
                    if not label.strip() or amount <= 0:
                        st.error("Add the instalment name and an amount above zero.")
                    else:
                        money.add_instalment(label, recv, amount, credited or None, link, ref, note, me()["name"])
                        flash("Instalment recorded")
                        st.rerun()
    if ins:
        df = pd.DataFrame([{"id": x["id"], "Received": _d(x["received_on"]), "Instalment": x["label"],
                            f"Amount ({alt})": x["amount"], f"Credited ({cur})": x["credited"],
                            "Invoice": x["invoice_number"] or "", "Bank ref.": x["reference"]} for x in ins])
        ev = st.dataframe(df, hide_index=True, key="ins_t", on_select="rerun", selection_mode="single-row",
                          column_order=[c for c in df.columns if c != "id"],
                          column_config={"Received": st.column_config.DateColumn(format="DD MMM YYYY"),
                                         f"Amount ({alt})": num, f"Credited ({cur})": num})
        st.caption(f"Total received: {ui.money(t['received'], alt)}; credited to the bank: {ui.money(t['credited'], cur)}.")
        sel = ev.selection.rows if ev and ev.selection else []
        if edit and sel:
            row = ins[sel[0]]
            with st.popover("Delete selected instalment"):
                if st.button("Delete instalment", type="primary", key=f"indel_{row['id']}"):
                    money.delete_instalment(row["id"])
                    flash("Deleted")
                    st.rerun()
    else:
        st.markdown('<div class="tt-empty-col">No instalments recorded yet.</div>', unsafe_allow_html=True)
