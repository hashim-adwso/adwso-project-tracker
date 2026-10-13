"""Management overview, People, and Project settings pages."""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from core import acts, auth, db, money, seed, ui
from core.finance import summary
from core.ui import e
from core.work import _select_open, can, flash, me, open_pending, show_flash


# =========================================================================== management
def page_management() -> None:
    show_flash()
    open_pending()
    s = db.settings()
    ui.page_head(s["project_name"], f"{s['project_code']}. {s['donor']}. "
                 f"{ui.fmt_day(s['start_date'])} to {ui.fmt_day(s['end_date'])}.")
    all_acts = [a for a in acts.load_all() if a["key_activity"]]
    open_ = [a for a in all_acts if a["status"] != "Cancelled"]
    done = sum(1 for a in open_ if a["status"] == "Completed")
    overdue = [a for a in open_ if a["status"] == "Overdue"]
    blocked = [a for a in open_ if a["status"] == "Blocked"]
    avg = round(sum(a["pct"] for a in open_) / len(open_)) if open_ else 0
    t = date.today()
    reports = sorted([a for a in open_ if a["title"].startswith("Submit") and a["is_open"] and a["next_date"]],
                     key=lambda a: a["next_date"])
    nxt = reports[0] if reports else None
    days_left = (date.fromisoformat(nxt["next_date"]) - t).days if nxt else None
    st.markdown(
        '<div class="tt-stats">'
        f'<div class="tt-stat"><b>{avg}%</b><span>Average progress of {len(open_)} key activities</span></div>'
        f'<div class="tt-stat"><b>{done}</b><span>Key activities completed</span></div>'
        f'<div class="tt-stat {"warn" if overdue or blocked else ""}"><b>{len(overdue) + len(blocked)}</b>'
        f'<span>Overdue or blocked</span></div>'
        f'<div class="tt-stat"><b>{days_left if days_left is not None else "–"}</b><span>'
        f'{"Days to " + e(nxt["title"].replace("Submit ", "")) if nxt else "No report due"}</span></div>'
        '</div>', unsafe_allow_html=True)

    if overdue or blocked:
        st.subheader("Needs attention")
        for a in overdue + blocked:
            why = ("marked as blocked (see its updates for the reason)" if a["status"] == "Blocked"
                   else f"overdue since {ui.fmt_day(a['overdue_dates'][0])}")
            st.markdown(f"{ui.status_pill(a['status'])} **{e(a['ref'] or '')} {e(a['title'])}**, {e(why)}. "
                        f"Lead: {e(a['lead_name'] or 'not set')}.", unsafe_allow_html=True)

    st.subheader("Key activities")
    df = pd.DataFrame([{"id": a["id"], "Ref.": a["ref"] or "", "Activity": a["title"], "When": acts.when_text(a),
                        "Lead": a["lead_name"] or "", "Status": a["status"], "Progress": a["pct"]} for a in all_acts])
    if not df.empty:
        ev = st.dataframe(df, hide_index=True, key="mg_t", on_select="rerun", selection_mode="single-row",
                          column_order=["Ref.", "Activity", "When", "Lead", "Status", "Progress"],
                          column_config={"Activity": st.column_config.TextColumn(width="large"),
                                         "Progress": st.column_config.ProgressColumn(min_value=0, max_value=100,
                                                                                     format="%d%%")},
                          height=min(35 * (len(df) + 1) + 3, 560))
        _select_open(df, ev, "mg_t")
        st.caption("Key activities are the ones the project coordinator marks for management. Select one for details.")

    st.subheader("Coming up in the next 60 days")
    soon = acts.pending_items(all_acts, t, t + timedelta(days=60), None, include_earlier_overdue=False)
    if soon:
        st.markdown("".join(
            f'<div class="tt-run-row"><div><b>{e((i["activity"]["ref"] + " ") if i["activity"]["ref"] else "")}'
            f'{e(i["activity"]["title"])}</b><br><small>{e(i["activity"]["lead_name"] or "No lead")}</small></div>'
            f'<div>{"Ends " if i["label"] == "Ends" else ""}{i["day"]:%a %d %b %Y}</div>'
            f'<div>{ui.status_pill(i["activity"]["status"])}</div></div>' for i in soon), unsafe_allow_html=True)
    else:
        st.caption("No key deadlines in the next 60 days.")

    if can("view_finance"):
        st.subheader("Financial position")
        summary(money.totals(), s, compact=True)


# =========================================================================== people
def page_people() -> None:
    show_flash()
    ui.page_head("People", "The team list. These names appear when assigning activities. After approval, the "
                 "email decides who can sign in, and the role decides what they see.")
    ppl = db.people(active_only=False)
    roles = list(db.ROLES)
    df = pd.DataFrame([{"id": p["id"], "Name": p["name"], "Email": p["email"] or "", "Job title": p["title"] or "",
                        "Role in the app": p["role"], "Active": bool(p["active"])} for p in ppl])
    edited = st.data_editor(
        df, hide_index=True, key="ppl_ed", column_order=["Name", "Email", "Job title", "Role in the app", "Active"],
        column_config={"Role in the app": st.column_config.SelectboxColumn(
            options=roles, required=True, format_func=db.ROLES.get,
            help="Coordinator: manages activities and people. Finance: records the budget. "
                 "Management: overview only. Team member: updates their own activities."),
            "Active": st.column_config.CheckboxColumn(help="Untick when someone leaves; their history is kept.")})
    if st.button("Save changes", type="primary", key="ppl_save"):
        n, problems = 0, []
        for (_, new), (_, old) in zip(edited.iterrows(), df.iterrows()):
            if new.equals(old):
                continue
            if not str(new["Name"]).strip():
                problems.append("A name can't be empty.")
                continue
            if int(new["id"]) == me()["id"] and (new["Role in the app"] != "coordinator" or not new["Active"]):
                problems.append("You can't remove your own coordinator role or deactivate yourself.")
                continue
            db.save_person(int(new["id"]), str(new["Name"]), str(new["Email"]), str(new["Job title"]),
                           new["Role in the app"], bool(new["Active"]))
            n += 1
        if problems:
            st.error(" ".join(problems))
        else:
            flash(f"Saved {n} change{'s' if n != 1 else ''}" if n else "Nothing changed")
            st.rerun()

    st.subheader("Add a person")
    with st.form("add_p", clear_on_submit=True):
        c1, c2 = st.columns(2)
        name = c1.text_input("Full name")
        email = c2.text_input("Email", placeholder="name@adwso.org")
        c3, c4 = st.columns(2)
        title = c3.text_input("Job title")
        role = c4.selectbox("Role in the app", roles, index=roles.index("team"), format_func=db.ROLES.get)
        if st.form_submit_button("Add person", type="primary"):
            if not name.strip():
                st.error("Enter the person's name.")
            elif email.strip() and "@" not in email:
                st.error("Enter a full email address, or leave it empty for now.")
            elif email.strip() and any((p["email"] or "").lower() == email.strip().lower() for p in ppl):
                st.error("Someone with this email is already on the list.")
            else:
                db.save_person(None, name, email, title, role)
                flash(f"Added {name.strip()}")
                st.rerun()


# =========================================================================== settings
def page_settings() -> None:
    show_flash()
    ui.page_head("Project settings", "Project details, and where the data is kept.")
    s = db.settings()
    with st.form("settings"):
        c1, c2 = st.columns([2, 1])
        name = c1.text_input("Project name", s["project_name"])
        code = c2.text_input("Project or agreement code", s["project_code"])
        c3, c4 = st.columns(2)
        donor = c3.text_input("Donor", s["donor"])
        partner = c4.text_input("Partner we report to", s["partner"])
        c5, c6 = st.columns(2)
        start = c5.date_input("Start date", date.fromisoformat(s["start_date"]) if s["start_date"] else None,
                              format="DD/MM/YYYY")
        end = c6.date_input("End date", date.fromisoformat(s["end_date"]) if s["end_date"] else None,
                            format="DD/MM/YYYY")
        c7, c8, c9 = st.columns(3)
        cur = c7.text_input("Ledger currency", s["currency"], max_chars=3)
        alt = c8.text_input("Agreement currency", s["alt_currency"], max_chars=3)
        rate = c9.number_input(f"1 {s['alt_currency']} = … {s['currency']}", value=float(s["alt_rate"] or 1),
                               min_value=0.0001, format="%.4f",
                               help="Used only where the two currencies are compared, e.g. converting the budget.")
        locs = st.text_area("Locations offered when creating activities (comma-separated)", s["locations"], height=80)
        terms = st.text_area("Payment terms shown on the budget summary", s.get("payment_terms", ""), height=150)
        if st.form_submit_button("Save settings", type="primary"):
            if start and end and end < start:
                st.error("The end date is before the start date.")
            else:
                db.save_settings({"project_name": name, "project_code": code, "donor": donor, "partner": partner,
                                  "start_date": db.d(start), "end_date": db.d(end), "currency": cur.upper(),
                                  "alt_currency": alt.upper(), "alt_rate": rate, "locations": locs,
                                  "payment_terms": terms})
                flash("Settings saved")
                st.rerun()

    st.subheader("Data and backup")
    b = db.backup
    if b.enabled:
        st.success(f"Every change is copied to the private dataset **{b.repo}** within a few seconds.")
        st.write(f"Last successful backup: {b.last_ok or 'none yet in this session'}")
        if b.last_error:
            st.warning(b.last_error)
    else:
        st.warning("Backups are off. The hosting service erases the app's disk when it restarts, so entries will be "
                   "lost. Add HF_TOKEN and DATA_REPO to the app's secrets (see the README).")
    with open(db.DB_PATH, "rb") as f:
        st.download_button("Download a copy of the database", f, file_name=f"tracker_{date.today():%Y%m%d}.db")

    st.subheader("Demo financial entries")
    st.write("Load a small set of sample expenses, a funds request and an instalment, so the Budget pages can be "
             "shown to management before real figures are recorded. Every demo entry starts with [Demo] and can be "
             "removed in one step.")
    n = money.totals()["demo_rows"]
    c1, c2 = st.columns(2)
    if c1.button("Load demo entries", disabled=n > 0, key="demo_load"):
        k = seed.load_demo_finance(me()["name"])
        flash(f"Loaded {k} demo entries")
        st.rerun()
    if c2.button(f"Remove demo entries ({n})", disabled=n == 0, key="demo_clear"):
        k = money.clear_demo()
        flash(f"Removed {k} demo entries")
        st.rerun()
    st.caption(f"Signed-in mode: {auth.AUTH_MODE}. Access password {'on' if auth.APP_PASSWORD else 'off'}.")
