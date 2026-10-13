"""Activity pages: dashboard, schedule, activity list, my activities, and the activity window."""
from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta

import pandas as pd
import streamlit as st

from core import acts, auth, db, ui
from core.ui import e

WEEK_START = 5  # Saturday; the Afghan working week runs Saturday to Thursday
DAY_OFF = 4     # Friday


def me() -> dict:
    return st.session_state["me"]


def can(action: str, a: dict | None = None) -> bool:
    return auth.can(me(), action, a)


def flash(msg: str) -> None:
    st.session_state["_flash"] = msg


def show_flash() -> None:
    msg = st.session_state.pop("_flash", None)
    if msg:
        st.toast(msg)


def _d(v) -> date | None:
    return date.fromisoformat(str(v)[:10]) if v else None


def _when(ts: str) -> str:
    try:
        return datetime.fromisoformat(ts).astimezone().strftime("%d %b %Y, %H:%M")
    except (ValueError, TypeError):
        return ts or ""


def people_names() -> dict[int, str]:
    return {p["id"]: p["name"] for p in db.people(active_only=False)}


def people_line(a: dict) -> str:
    lead = a["lead_name"] or "No lead set"
    sup = ", ".join(s["name"] for s in a["support"])
    return f"{lead}" + (f" (with {sup})" if sup else "")


def week_start(dd: date) -> date:
    return dd - timedelta(days=(dd.weekday() - WEEK_START) % 7)


PERIODS = ["This week", "Next 7 days", "This month", "Next 30 days", "Custom"]


def period_range(choice: str, custom=None) -> tuple[date, date]:
    t = date.today()
    if choice == "This week":
        s = week_start(t)
        return s, s + timedelta(days=6)
    if choice == "Next 7 days":
        return t, t + timedelta(days=6)
    if choice == "This month":
        return t.replace(day=1), t.replace(day=calendar.monthrange(t.year, t.month)[1])
    if choice == "Next 30 days":
        return t, t + timedelta(days=29)
    if custom and len(custom) == 2 and custom[0] and custom[1]:
        return custom[0], custom[1]
    return t, t + timedelta(days=29)


# =========================================================================== activity window
@st.dialog("Activity", width="large", on_dismiss="rerun")
def activity_dialog(aid: int) -> None:
    a = acts.load(aid)
    if not a:
        st.error("This activity no longer exists.")
        return
    ref = f'<span class="tt-ref">{e(a["ref"])}</span>' if a["ref"] else ""
    st.markdown(f'<div class="tt-card-title" style="font-size:1.25rem">{ref}{e(a["title"])}</div>'
                f'<div class="tt-meta">{ui.type_tag(a)} {ui.status_pill(a["status"])} {ui.key_tag(a)} '
                f'{ui.priority_chip(a["priority"])}</div>', unsafe_allow_html=True)
    st.markdown(f'<p class="tt-who" style="margin:.5rem 0 0">{e(acts.when_text(a))}. '
                f'{e(people_line(a))}.{" " + e(a["location"]) + "." if a["location"] else ""}</p>',
                unsafe_allow_html=True)

    tabs = ["Progress", "Details", f"Updates ({len(acts.log(aid))})"]
    t_prog, t_det, t_log = st.tabs(tabs)
    with t_prog:
        _progress_tab(a)
    with t_det:
        if can("edit_activities"):
            activity_form(a, key=f"edit{aid}")
        else:
            st.markdown(e(a["description"] or "No description.").replace("\n", "<br>"), unsafe_allow_html=True)
            if a["workplan_ref"]:
                st.caption(f"Workplan reference: {a['workplan_ref']}")
    with t_log:
        with st.form(f"note{aid}", clear_on_submit=True, border=False):
            note = st.text_area("Post an update", height=90,
                                placeholder="What happened? Mention results, problems and next steps.")
            if st.form_submit_button("Post update", type="primary"):
                if note.strip():
                    acts.add_note(aid, me()["name"], note)
                    st.rerun(scope="fragment")
                else:
                    st.error("Write something before posting.")
        items = "".join(
            f'<div class="tt-log-item {x["kind"]}"><small>{e(x["by_name"] or "")} on {e(_when(x["at"]))}</small>'
            f'<p>{e(x["note"])}</p></div>' for x in acts.log(aid))
        st.markdown(f'<div class="tt-log">{items}</div>', unsafe_allow_html=True)


def _progress_tab(a: dict) -> None:
    aid = a["id"]
    may = can("update_progress", a)
    if not may:
        st.caption("You can see this activity. Only its lead, support people and the project coordinator can update it.")

    if a["kind"] == "date_range":
        if a["overdue_dates"]:
            st.error(f"The end date ({ui.fmt_day(a['end_date'])}) has passed and progress is {a['pct']}%. "
                     "Update the progress, or ask the coordinator to change the end date.")
        st.markdown(ui.progress_bar(a["pct"], ui.STATUS_STYLE[a["status"]]["dot"]), unsafe_allow_html=True)
        if may and a["status"] != "Cancelled":
            with st.form(f"prog{aid}", border=False):
                pct = st.slider("How much of the work is done?", 0, 100, int(a["pct"]), step=5, format="%d%%")
                note = st.text_input("Short note (optional)", placeholder="e.g. 140 of 520 children registered")
                c1, c2 = st.columns(2)
                save = c1.form_submit_button("Save progress", type="primary", width="stretch")
                done = c2.form_submit_button("Mark complete", width="stretch")
            if save or done:
                acts.set_progress(aid, 100 if done else pct, me()["name"], note)
                st.rerun(scope="fragment")
        else:
            st.write(f"Progress: **{a['pct']}%**")
    else:
        total = a["total_count"]
        st.markdown(f"**{a['done_count']} of {total}** scheduled date{'s' if total != 1 else ''} complete "
                    f"({a['pct']}%).")
        st.markdown(ui.progress_bar(a["pct"], ui.STATUS_STYLE[a["status"]]["dot"]), unsafe_allow_html=True)
        today = date.today()
        for x in a["dates"]:
            dd = _d(x["day"])
            with st.container(border=True):
                c1, c2 = st.columns([3, 1.3], vertical_alignment="center")
                if x["done"]:
                    who = f"Done, marked by {x['done_by']} on {_when(x['done_at'])}"
                    c1.markdown(f'<div class="tt-tick"><b>✓ {dd:%a %d %b %Y}</b></div>'
                                f'<small class="tt-who">{e(who)}</small>'
                                + (f'<p style="margin:.2rem 0 0;font-size:.88rem">{e(x["note"])}</p>' if x["note"] else ""),
                                unsafe_allow_html=True)
                    if may and c2.button("Reopen", key=f"re{x['id']}", width="stretch"):
                        acts.mark_date(x["id"], False, me()["name"])
                        st.rerun(scope="fragment")
                else:
                    late = dd < today
                    label = "Overdue" if late else ("Today" if dd == today else "Planned")
                    color = ui.POMEGRANATE if late else ui.SLATE
                    c1.markdown(f'<div class="tt-tick"><b>{dd:%a %d %b %Y}</b>'
                                f'<small style="color:{color};font-weight:700">{label}</small></div>',
                                unsafe_allow_html=True)
                    if may and a["status"] != "Cancelled":
                        note = c1.text_input("Note", key=f"n{x['id']}", label_visibility="collapsed",
                                             placeholder="Optional note, e.g. number of participants")
                        if c2.button("Mark done", key=f"d{x['id']}", type="primary", width="stretch"):
                            acts.mark_date(x["id"], True, me()["name"], note)
                            st.rerun(scope="fragment")

    # Blocked / cancelled
    if may:
        with st.expander("Report a problem or cancel"):
            if a["flag"]:
                st.write(f"This activity is marked **{a['flag']}**.")
                if st.button("Clear this flag", key=f"cf{aid}"):
                    acts.set_flag(aid, None, me()["name"])
                    st.rerun(scope="fragment")
            else:
                reason = st.text_input("Reason", key=f"fr{aid}", placeholder="What is stopping the work?")
                c1, c2 = st.columns(2)
                if c1.button("Mark as blocked", key=f"fb{aid}", width="stretch"):
                    acts.set_flag(aid, "blocked", me()["name"], reason)
                    st.rerun(scope="fragment")
                if can("edit_activities") and c2.button("Cancel activity", key=f"fc{aid}", width="stretch"):
                    acts.set_flag(aid, "cancelled", me()["name"], reason)
                    st.rerun(scope="fragment")

    # Recurring
    if a["recurring"]:
        st.markdown("---")
        freq = acts.FREQUENCIES.get(a["frequency"], "").lower()
        if acts.has_next_occurrence(a):
            st.info(f"This is a {freq} activity. The next occurrence has already been created.")
        else:
            nxt = acts.next_occurrence_preview(a)
            when = (f"{ui.fmt_day(nxt['start_date'])} to {ui.fmt_day(nxt['end_date'])}" if a["kind"] == "date_range"
                    else ", ".join(ui.fmt_day(x) for x in nxt["days"]))
            st.write(f"This activity repeats {freq}. The next occurrence would be scheduled for **{when}**.")
            if can("edit_activities") and st.button("Create next occurrence", key=f"no{aid}", type="primary"):
                acts.create_next_occurrence(a, me()["name"])
                flash("Next occurrence created")
                st.rerun()


# =========================================================================== create / edit
def activity_form(a: dict | None, key: str) -> None:
    team = db.people()
    tid = [p["id"] for p in team]
    names = people_names()
    s = db.settings()
    locs = [x.strip() for x in (s["locations"] or "").split(",") if x.strip()]

    title = st.text_input("Title", a["title"] if a else "", key=f"{key}_t", max_chars=200,
                          placeholder="e.g. Case management training for CSC facilitators")
    c1, c2 = st.columns([1, 3])
    ref = c1.text_input("Ref.", a["ref"] if a and a["ref"] else "", key=f"{key}_r", placeholder="e.g. B.3")
    if a:
        tdefault = "Recurring" if a["recurring"] else acts.KINDS[a["kind"]]
    else:
        tdefault = "One-time"
    tchoice = c2.segmented_control("Type of activity", acts.TYPE_CHOICES, default=tdefault, key=f"{key}_ty",
                                   required=True)
    recurring = tchoice == "Recurring"
    if recurring:
        r1, r2 = st.columns(2)
        freqs = list(acts.FREQUENCIES)
        freq = r1.selectbox("Repeats", freqs, format_func=acts.FREQUENCIES.get, key=f"{key}_fq",
                            index=freqs.index(a["frequency"]) if a and a["frequency"] in freqs else 1)
        base_opts = {"One date": "one_time", "Several dates": "selected_dates", "A date range": "date_range"}
        inv = {v: k for k, v in base_opts.items()}
        base = r2.selectbox("Each occurrence is scheduled as", list(base_opts),
                            index=list(base_opts).index(inv[a["kind"]]) if a and a["recurring"] else 0, key=f"{key}_bs")
        kind = base_opts[base]
        st.caption("The activity is labelled as recurring. When one occurrence is done, use "
                   "'Create next occurrence' in its window to plan the next one.")
    else:
        freq = None
        kind = {"One-time": "one_time", "Selected dates": "selected_dates", "Date range": "date_range"}[tchoice]

    days, start, end = [], None, None
    existing_days = [_d(x["day"]) for x in a["dates"]] if a else []
    if kind == "one_time":
        dflt = existing_days[0] if existing_days else (_d(a["start_date"]) if a and a["start_date"] else None)
        one = st.date_input("Date", dflt, format="DD/MM/YYYY", key=f"{key}_od")
        days = [one] if one else []
    elif kind == "selected_dates":
        sk = f"{key}_days"
        if sk not in st.session_state:
            st.session_state[sk] = sorted(set(existing_days))
        cur = st.session_state[sk]
        with st.form(f"{key}_addf", clear_on_submit=True, border=False):
            a1, a2 = st.columns([2, 1], vertical_alignment="bottom")
            newd = a1.date_input("Add a date", None, format="DD/MM/YYYY")
            if a2.form_submit_button("Add date", width="stretch") and newd:
                st.session_state[sk] = sorted(set(st.session_state[sk]) | {newd})
        cur = st.session_state[sk]
        with st.expander("Add the same weekdays across a period"):
            w1, w2 = st.columns(2)
            per = w1.date_input("Period", (), format="DD/MM/YYYY", key=f"{key}_wp")
            wds = w2.multiselect("Weekdays", ["Sat", "Sun", "Mon", "Tue", "Wed", "Thu", "Fri"], key=f"{key}_wd")
            if st.button("Add these dates", key=f"{key}_wa"):
                if len(per) == 2 and wds:
                    wanted = {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].index(w) for w in wds}
                    span = [per[0] + timedelta(days=i) for i in range((per[1] - per[0]).days + 1)]
                    st.session_state[sk] = sorted(set(cur) | {x for x in span if x.weekday() in wanted})
                    st.rerun(scope="fragment")
                else:
                    st.error("Choose a start and end date, and at least one weekday.")
        cur = st.session_state[sk]
        kept = st.multiselect("Scheduled dates (remove one with its ×)", cur, default=cur,
                              format_func=lambda x: x.strftime("%a %d %b %Y"), key=f"{key}_ms_{len(cur)}")
        days = kept
        done_days = {_d(x["day"]) for x in a["dates"] if x["done"]} if a else set()
        if done_days - set(kept):
            st.warning("You removed a date that was already marked done. Its completion record will be deleted.")
    else:
        r1, r2 = st.columns(2)
        start = r1.date_input("Start date", _d(a["start_date"]) if a else None, format="DD/MM/YYYY", key=f"{key}_sd")
        end = r2.date_input("End date", _d(a["end_date"]) if a else None, format="DD/MM/YYYY", key=f"{key}_ed")
        st.caption("Progress for a date range is updated by hand. If the end date passes before it reaches 100%, "
                   "the activity is flagged as overdue.")

    p1, p2 = st.columns(2)
    lead = p1.selectbox("Lead person", [None, *tid], format_func=lambda i: "No lead yet" if i is None else names[i],
                        index=([None, *tid].index(a["lead_id"]) if a and a["lead_id"] in tid else 0), key=f"{key}_ld")
    support = p2.multiselect("Support people", [i for i in tid if i != lead],
                             default=[s_["id"] for s_ in a["support"] if s_["id"] in tid and s_["id"] != lead] if a else [],
                             format_func=names.get, key=f"{key}_sp_{lead}")
    q1, q2, q3 = st.columns(3)
    priority = q1.selectbox("Priority", acts.PRIORITIES, index=acts.PRIORITIES.index(a["priority"]) if a else 1,
                            key=f"{key}_pr")
    cur_loc = a["location"] if a and a["location"] else None
    loc_opts = locs + ([cur_loc] if cur_loc and cur_loc not in locs else [])
    location = q2.selectbox("Location", loc_opts, index=loc_opts.index(cur_loc) if cur_loc else None,
                            accept_new_options=True, placeholder="Choose or type", key=f"{key}_lc")
    wref = q3.text_input("Workplan reference", a["workplan_ref"] if a else "", key=f"{key}_wr")
    desc = st.text_area("Description", a["description"] if a else "", height=120, key=f"{key}_de",
                        placeholder="What happens, the target, and what counts as done")
    key_act = st.checkbox("Key activity: show it to management", bool(a["key_activity"]) if a else False, key=f"{key}_ka")

    label = "Save changes" if a else "Create activity"
    b1, b2 = st.columns([1, 1])
    if b1.button(label, type="primary", key=f"{key}_save"):
        problems = []
        if not title.strip():
            problems.append("Add a title.")
        if kind == "one_time" and not days:
            problems.append("Choose the date.")
        if kind == "selected_dates" and not days:
            problems.append("Add at least one date.")
        if kind == "date_range" and (not start or not end):
            problems.append("Choose a start and an end date.")
        if kind == "date_range" and start and end and end < start:
            problems.append("The end date is before the start date.")
        if problems:
            st.error(" ".join(problems))
            return
        aid = acts.save({
            "ref": ref.strip(), "title": title, "description": desc, "kind": kind, "recurring": recurring,
            "frequency": freq, "days": days, "start_date": start, "end_date": end, "lead_id": lead,
            "support_ids": support, "priority": priority, "location": location or "", "workplan_ref": wref,
            "key_activity": key_act,
        }, me()["name"], a["id"] if a else None)
        st.session_state.pop(f"{key}_days", None)
        flash("Changes saved" if a else "Activity created")
        if not a:
            st.session_state["_open_after"] = aid
        st.rerun()
    if a:
        with b2.popover("Delete activity"):
            st.write("This deletes the activity, its dates and its updates. It can't be undone. "
                     "To keep the record, cancel the activity instead.")
            if st.button("Delete permanently", type="primary", key=f"{key}_del"):
                acts.delete(a["id"])
                flash("Activity deleted")
                st.rerun()


@st.dialog("New activity", width="large")
def new_activity_dialog() -> None:
    activity_form(None, key="new")


def new_button(where: str) -> None:
    if can("edit_activities"):
        if st.button("New activity", type="primary", width="stretch", key=f"new_{where}"):
            st.session_state.pop("new_days", None)
            new_activity_dialog()


def open_pending() -> None:
    aid = st.session_state.pop("_open_after", None)
    if aid:
        activity_dialog(aid)


# =========================================================================== pieces
def item_card(a: dict, key: str, day: date | None = None, date_id: int | None = None, show_day: bool = True) -> None:
    with st.container(key=f"card_{key}"):
        ref = f'<span class="tt-ref">{e(a["ref"])}</span>' if a["ref"] else ""
        when = ""
        if a["kind"] == "date_range":
            when = f'{ui.fmt_day(a["start_date"])} to {ui.fmt_day(a["end_date"])}'
        elif show_day and day:
            late = day < date.today()
            when = (f'<span class="tt-due-over">Overdue since {day:%d %b}</span>' if late
                    else f"{day:%a %d %b}")
        meta = [ui.type_tag(a), when, e(a["lead_name"] or "No lead"), ui.status_pill(a["status"])]
        st.markdown(f'<div class="tt-card-title">{ref}{e(a["title"])}</div>'
                    f'<div class="tt-meta">{"".join(f"<span>{m}</span>" for m in meta if m)}</div>'
                    f'{ui.progress_bar(a["pct"], ui.STATUS_STYLE[a["status"]]["dot"])}',
                    unsafe_allow_html=True)
        b1, b2 = st.columns(2)
        if b1.button("Open", key=f"o_{key}", type="tertiary"):
            activity_dialog(a["id"])
        if date_id and can("update_progress", a) and a["is_open"]:
            if b2.button("Mark done", key=f"m_{key}", type="tertiary"):
                acts.mark_date(date_id, True, me()["name"])
                flash(f"Marked {day:%d %b} done")
                st.rerun()


def _person_filter(key: str, default_me: bool = False) -> int | None:
    team = db.people()
    ids = [None] + [p["id"] for p in team]
    names = {p["id"]: p["name"] for p in team}
    idx = ids.index(me()["id"]) if default_me and me()["id"] in ids else 0
    return st.selectbox("Person", ids, index=idx, key=key,
                        format_func=lambda i: "Everyone" if i is None else names[i])


def _select_open(df: pd.DataFrame, event, key: str) -> None:
    sel = event.selection.rows if event and event.selection else []
    sid = int(df.iloc[sel[0]]["id"]) if sel else None
    if sid != st.session_state.get(f"{key}_last"):
        st.session_state[f"{key}_last"] = sid
        if sid is not None:
            activity_dialog(sid)


# =========================================================================== pages
def page_dashboard() -> None:
    show_flash()
    open_pending()
    s = db.settings()
    h1, h2 = st.columns([4, 1], vertical_alignment="bottom")
    with h1:
        ui.page_head("Dashboard", f"{s['project_name']}. Pending work and progress for any person and period.")
    with h2:
        new_button("dash")

    f1, f2 = st.columns([1, 2.4], vertical_alignment="bottom")
    with f1:
        pid = _person_filter("dash_person", default_me=me()["role"] == "team")
    with f2:
        choice = st.segmented_control("Period", PERIODS, default="This week", key="dash_period", required=True)
    custom = None
    if choice == "Custom":
        with f1:
            custom = st.date_input("From – to", (date.today(), date.today() + timedelta(days=13)),
                                   format="DD/MM/YYYY", key="dash_custom")
    start, end = period_range(choice, custom)
    earlier = st.toggle("Also show overdue work from before this period", True, key="dash_earlier")

    all_acts = acts.load_all()
    items = acts.pending_items(all_acts, start, end, pid, include_earlier_overdue=earlier)
    overdue_n = sum(1 for i in items if i["overdue"])
    done_n = acts.completed_in(all_acts, start, end, pid)
    blocked_n = sum(1 for a in all_acts if a["status"] == "Blocked" and acts.involves(a, pid))
    who = "everyone" if pid is None else people_names()[pid]
    st.caption(f"{start:%d %b %Y} to {end:%d %b %Y}, for {who}.")
    st.markdown(
        '<div class="tt-stats">'
        f'<div class="tt-stat"><b>{len(items) - overdue_n}</b><span>Pending in this period</span></div>'
        f'<div class="tt-stat {"warn" if overdue_n else ""}"><b>{overdue_n}</b><span>Overdue</span></div>'
        f'<div class="tt-stat"><b>{done_n}</b><span>Completed in this period</span></div>'
        f'<div class="tt-stat {"warn" if blocked_n else ""}"><b>{blocked_n}</b><span>Blocked activities</span></div>'
        '</div>', unsafe_allow_html=True)

    st.subheader("Pending work")
    if not items:
        st.markdown('<div class="tt-empty-col">Nothing is pending in this period.</div>', unsafe_allow_html=True)
    else:
        df = pd.DataFrame([{
            "id": i["activity"]["id"],
            "Date": i["day"],
            "": "Overdue" if i["overdue"] else ("Running until" if i["label"] == "Ends" else "Scheduled"),
            "Ref.": i["activity"]["ref"] or "",
            "Activity": i["activity"]["title"],
            "Type": acts.type_label(i["activity"]),
            "Lead": i["activity"]["lead_name"] or "",
            "Status": i["activity"]["status"],
            "Progress": i["activity"]["pct"],
        } for i in items])
        ev = st.dataframe(df, hide_index=True, key="dash_pending", on_select="rerun", selection_mode="single-row",
                          column_order=["", "Date", "Ref.", "Activity", "Type", "Lead", "Status", "Progress"],
                          column_config={"Date": st.column_config.DateColumn(format="ddd DD MMM YYYY"),
                                         "": st.column_config.TextColumn(width=110),
                                         "Activity": st.column_config.TextColumn(width="medium"),
                                         "Progress": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%d%%")},
                          height=min(35 * (len(df) + 1) + 3, 460))
        _select_open(df, ev, "dash_pending")
        st.caption("Select a row to open the activity and mark work done. A date range activity appears once, "
                   "with its end date, for as long as it is running.")

    st.subheader("Progress of activities in this period")
    in_period = [a for a in all_acts if acts.overlaps(a, start, end) and acts.involves(a, pid)]
    if not in_period:
        st.markdown('<div class="tt-empty-col">No activities are scheduled in this period.</div>', unsafe_allow_html=True)
        return
    rows = []
    for a in in_period:
        dn, sc = acts.period_progress(a, start, end)
        rows.append({"id": a["id"], "Ref.": a["ref"] or "", "Activity": a["title"], "Type": acts.type_label(a),
                     "Lead": a["lead_name"] or "", "Status": a["status"],
                     "In this period": f"{dn} of {sc} dates done" if sc is not None else "Runs through this period",
                     "Overall progress": a["pct"]})
    df2 = pd.DataFrame(rows)
    ev2 = st.dataframe(df2, hide_index=True, key="dash_prog", on_select="rerun", selection_mode="single-row",
                       column_order=["Ref.", "Activity", "Type", "Lead", "Status", "In this period", "Overall progress"],
                       column_config={"Activity": st.column_config.TextColumn(width="medium"),
                                      "Overall progress": st.column_config.ProgressColumn(min_value=0, max_value=100,
                                                                                          format="%d%%")},
                       height=min(35 * (len(df2) + 1) + 3, 520))
    _select_open(df2, ev2, "dash_prog")
    export = df2.drop(columns=["id"])
    st.download_button("Download this table (CSV, opens in Excel)", export.to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"progress_{start:%Y%m%d}_{end:%Y%m%d}.csv", mime="text/csv")


def page_schedule() -> None:
    show_flash()
    open_pending()
    h1, h2 = st.columns([4, 1], vertical_alignment="bottom")
    with h1:
        ui.page_head("Schedule", "What is planned, day by day. The working week runs Saturday to Thursday.")
    with h2:
        new_button("sched")
    f1, f2, f3 = st.columns([1, 1.3, 1.4], vertical_alignment="bottom")
    with f1:
        view = st.segmented_control("View", ["Week", "Month"], default="Week", key="sched_view", required=True)
    with f2:
        pid = _person_filter("sched_person", default_me=me()["role"] == "team")
    with f3:
        key_only = st.toggle("Key activities only", me()["role"] == "management", key="sched_key")

    all_acts = [a for a in acts.load_all(include_cancelled=False)
                if acts.involves(a, pid) and (a["key_activity"] or not key_only)]
    anchor = st.session_state.setdefault("sched_anchor", date.today())

    n1, n2, n3, n4 = st.columns([1, 1, 1, 4], vertical_alignment="center")
    step = 7 if view == "Week" else 31
    if n1.button("◀ Previous", key="sched_prev", width="stretch"):
        anchor = anchor - timedelta(days=step) if view == "Week" else (anchor.replace(day=1) - timedelta(days=1))
        st.session_state["sched_anchor"] = anchor
    if n2.button("Today", key="sched_today", width="stretch"):
        anchor = date.today()
        st.session_state["sched_anchor"] = anchor
    if n3.button("Next ▶", key="sched_next", width="stretch"):
        anchor = anchor + timedelta(days=step) if view == "Week" else (anchor.replace(day=28) + timedelta(days=5))
        st.session_state["sched_anchor"] = anchor

    if view == "Week":
        _week_view(all_acts, week_start(anchor), n4)
    else:
        _month_view(all_acts, anchor, n4)


def _running(all_acts: list[dict], start: date, end: date, title: str) -> None:
    running = [a for a in all_acts if a["kind"] == "date_range" and acts.overlaps(a, start, end)]
    if not running:
        return
    rows = "".join(
        f'<div class="tt-run-row"><div><b>{e((a["ref"] + " ") if a["ref"] else "")}{e(a["title"])}</b><br>'
        f'<small>{ui.fmt_day(a["start_date"])} to {ui.fmt_day(a["end_date"])}. {e(a["lead_name"] or "No lead")}</small></div>'
        f'<div>{ui.progress_bar(a["pct"], ui.STATUS_STYLE[a["status"]]["dot"])}{ui.status_pill(a["status"])}</div>'
        f'<div style="text-align:right;font-weight:800">{a["pct"]}%</div></div>'
        for a in running)
    st.markdown(f'<div class="tt-running"><h4>{e(title)} ({len(running)})</h4>{rows}</div>', unsafe_allow_html=True)
    opts = {a["id"]: f'{(a["ref"] + " ") if a["ref"] else ""}{a["title"]}' for a in running}
    c1, c2 = st.columns([4, 1], vertical_alignment="bottom")
    pick = c1.selectbox("Open a running activity to update its progress", list(opts), format_func=opts.get,
                        index=None, placeholder="Choose an activity", key=f"run_{start}")
    if c2.button("Open", key=f"runo_{start}", width="stretch", disabled=pick is None):
        activity_dialog(pick)


def _week_view(all_acts: list[dict], ws: date, label_col) -> None:
    we = ws + timedelta(days=6)
    label_col.markdown(f"**{ws:%d %b} to {we:%d %b %Y}**")
    by_day: dict[date, list] = {}
    for a in all_acts:
        if a["kind"] == "date_range":
            continue
        for x in a["dates"]:
            dd = _d(x["day"])
            if ws <= dd <= we:
                by_day.setdefault(dd, []).append((a, x))
    cols = st.columns(7, gap="small")
    today = date.today()
    for i, col in enumerate(cols):
        dd = ws + timedelta(days=i)
        cls = "today" if dd == today else ("off" if dd.weekday() == DAY_OFF else "")
        with col:
            st.markdown(f'<div class="tt-day-head {cls}"><b>{dd:%a}</b><span>{dd:%d %b}</span></div>',
                        unsafe_allow_html=True)
            items = by_day.get(dd, [])
            if not items:
                st.markdown('<div class="tt-empty-col" style="padding:.6rem;font-size:.78rem">Nothing planned</div>',
                            unsafe_allow_html=True)
            for a, x in items:
                _day_card(a, x, dd)
    st.write("")
    _running(all_acts, ws, we, "Date-range activities running this week")


def _day_card(a: dict, x: dict, dd: date) -> None:
    done = bool(x["done"])
    late = not done and dd < date.today()
    with st.container(key=f"card_w_{x['id']}"):
        mark = "✓ " if done else ""
        color = ui.LEAF if done else (ui.POMEGRANATE if late else ui.INK)
        recur = ' <span class="tt-recur">↻</span>' if a["recurring"] else ""
        st.markdown(f'<div class="tt-card-title" style="font-size:.86rem;color:{color}">{mark}'
                    f'{e((a["ref"] + " ") if a["ref"] else "")}{e(a["title"])}{recur}</div>'
                    f'<div class="tt-meta" style="font-size:.74rem">{e(a["lead_name"] or "No lead")}'
                    f'{"<span class=tt-due-over>Overdue</span>" if late else ""}</div>', unsafe_allow_html=True)
        if st.button("Open", key=f"wo_{x['id']}", type="tertiary"):
            activity_dialog(a["id"])
        if not done and a["is_open"] and can("update_progress", a):
            if st.button("Mark done", key=f"wm_{x['id']}", type="tertiary"):
                acts.mark_date(x["id"], True, me()["name"])
                flash(f"Marked {dd:%d %b} done")
                st.rerun()


def _month_view(all_acts: list[dict], anchor: date, label_col) -> None:
    first = anchor.replace(day=1)
    last = first.replace(day=calendar.monthrange(first.year, first.month)[1])
    label_col.markdown(f"**{first:%B %Y}**")
    by_day: dict[date, list] = {}
    for a in all_acts:
        if a["kind"] == "date_range":
            continue
        for x in a["dates"]:
            dd = _d(x["day"])
            if first <= dd <= last:
                by_day.setdefault(dd, []).append((a, x))
    gs = week_start(first)
    ge = week_start(last) + timedelta(days=6)
    head = "".join(f'<div class="h">{(gs + timedelta(days=i)):%a}</div>' for i in range(7))
    cells = []
    today = date.today()
    dd = gs
    while dd <= ge:
        evs = ""
        for a, x in by_day.get(dd, [])[:4]:
            if x["done"]:
                st_ = ui.STATUS_STYLE["Completed"]
            elif dd < today:
                st_ = ui.STATUS_STYLE["Overdue"]
            else:
                st_ = ui.STATUS_STYLE["In progress" if a["pct"] else "Not started"]
            tick = "✓ " if x["done"] else ""
            evs += (f'<span class="ev" style="background:{st_["bg"]};color:{st_["fg"]}" '
                    f'title="{e(a["title"])}">{tick}{e((a["ref"] + " ") if a["ref"] else "")}{e(a["title"])}</span>')
        more = len(by_day.get(dd, [])) - 4
        if more > 0:
            evs += f'<span class="tt-who">+{more} more</span>'
        cls = "c" + (" out" if dd.month != first.month else "") + (" today" if dd == today else "")
        cells.append(f'<div class="{cls}"><span class="n">{dd.day}</span>{evs}</div>')
        dd += timedelta(days=1)
    st.markdown(f'<div class="tt-month">{head}{"".join(cells)}</div>', unsafe_allow_html=True)
    st.write("")
    month_items = [(dd_, a) for dd_, lst in sorted(by_day.items()) for a, _ in lst]
    if month_items:
        opts = {}
        for dd_, a in month_items:
            opts.setdefault(a["id"], f'{dd_:%d %b}: {(a["ref"] + " ") if a["ref"] else ""}{a["title"]}')
        c1, c2 = st.columns([4, 1], vertical_alignment="bottom")
        pick = c1.selectbox("Open an activity from this month", list(opts), format_func=opts.get, index=None,
                            placeholder="Choose an activity", key=f"mon_{first}")
        if c2.button("Open", key=f"mono_{first}", width="stretch", disabled=pick is None):
            activity_dialog(pick)
    _running(all_acts, first, last, "Date-range activities running this month")


def page_activities() -> None:
    show_flash()
    open_pending()
    h1, h2 = st.columns([4, 1], vertical_alignment="bottom")
    with h1:
        ui.page_head("Activities", "Every activity in the project. Select one to open it.")
    with h2:
        new_button("list")
    all_acts = acts.load_all()
    f1, f2, f3, f4 = st.columns([2, 1.4, 1.4, 1.2], vertical_alignment="bottom")
    q = f1.text_input("Search", placeholder="Search titles, references and descriptions", key="al_q")
    status = f2.multiselect("Status", acts.STATUSES, placeholder="Any status", key="al_status")
    types = f3.multiselect("Type", acts.TYPE_CHOICES, placeholder="Any type", key="al_type")
    with f4:
        pid = _person_filter("al_person")
    key_only = st.toggle("Key activities only", False, key="al_key")

    out = all_acts
    if q:
        ql = q.lower()
        out = [a for a in out if ql in a["title"].lower() or ql in (a["ref"] or "").lower()
               or ql in (a["description"] or "").lower()]
    if status:
        out = [a for a in out if a["status"] in status]
    if types:
        out = [a for a in out if ("Recurring" if a["recurring"] else acts.KINDS[a["kind"]]) in types]
    out = [a for a in out if acts.involves(a, pid) and (a["key_activity"] or not key_only)]
    if not out:
        st.markdown('<div class="tt-empty-col">No activities match these filters.</div>', unsafe_allow_html=True)
        return
    df = pd.DataFrame([{
        "id": a["id"], "Ref.": a["ref"] or "", "Activity": a["title"], "Type": acts.type_label(a),
        "When": acts.when_text(a), "Lead": a["lead_name"] or "", "Status": a["status"], "Progress": a["pct"],
        "Key": "Yes" if a["key_activity"] else "", "Location": a["location"] or "",
    } for a in out])
    ev = st.dataframe(df, hide_index=True, key="al_table", on_select="rerun", selection_mode="single-row",
                      column_order=["Ref.", "Activity", "Type", "When", "Lead", "Status", "Progress", "Key", "Location"],
                      column_config={"Activity": st.column_config.TextColumn(width="medium"),
                                     "Progress": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%d%%")},
                      height=min(35 * (len(df) + 1) + 3, 640))
    _select_open(df, ev, "al_table")
    st.caption(f"{len(df)} activit{'y' if len(df) == 1 else 'ies'}. Select a row to open it.")
    st.download_button("Download as CSV (opens in Excel)", df.drop(columns=["id"]).to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"activities_{date.today():%Y%m%d}.csv", mime="text/csv")


def page_mine() -> None:
    show_flash()
    open_pending()
    ui.page_head("My activities", "Work where you are the lead or a support person.")
    all_acts = acts.load_all()
    pid = me()["id"]
    t = date.today()
    items = acts.pending_items(all_acts, t, t + timedelta(days=30), pid, include_earlier_overdue=True)
    overdue = [i for i in items if i["overdue"]]
    week_end = week_start(t) + timedelta(days=6)
    this_week = [i for i in items if not i["overdue"] and i["day"] and i["day"] <= week_end]
    later = [i for i in items if not i["overdue"] and i not in this_week]
    if not items:
        st.markdown('<div class="tt-empty-col">Nothing is pending for you in the next 30 days.</div>',
                    unsafe_allow_html=True)
    for title, group in (("Overdue", overdue), ("This week", this_week), ("Next 30 days", later)):
        if not group:
            continue
        st.subheader(f"{title} ({len(group)})")
        cols = st.columns(3, gap="medium")
        for n, i in enumerate(group):
            with cols[n % 3]:
                item_card(i["activity"], f"mine_{title}_{n}", i["day"], i.get("date_id"))
