"""Project Tracker: activities, schedule and budget for one project.

Run on your own computer:
    streamlit run app.py
"""
import streamlit as st

st.set_page_config(page_title="Project Tracker", page_icon="assets/icon.svg", layout="wide")

from core import admin, auth, db, finance, seed, ui, work  # noqa: E402


@st.cache_resource
def _startup() -> str | None:
    """Prepare the database once per server start. Returns a problem message, or None."""
    if db.init():
        try:
            data = seed.read_seed()
        except seed.SeedLocked as exc:
            return str(exc)
        seed.load_project(data)
    return None


problem = _startup()
ui.inject_css()
if problem:
    _startup.clear()
    ui.gate("The app can't start yet", problem)
    st.stop()
me = auth.current_person()
st.session_state["me"] = me
role = me["role"]

P = st.Page
dashboard = P(work.page_dashboard, title="Dashboard", icon=":material/space_dashboard:", url_path="dashboard")
schedule = P(work.page_schedule, title="Schedule", icon=":material/calendar_month:", url_path="schedule")
activities = P(work.page_activities, title="Activities", icon=":material/table_rows:", url_path="activities")
mine = P(work.page_mine, title="My activities", icon=":material/person_check:", url_path="mine")
budget = P(finance.page_budget, title="Budget and finance", icon=":material/account_balance:", url_path="budget")
overview = P(admin.page_management, title="Management overview", icon=":material/insights:", url_path="overview")
people = P(admin.page_people, title="People", icon=":material/group:", url_path="people")
settings = P(admin.page_settings, title="Project settings", icon=":material/settings:", url_path="settings")


if role == "coordinator":
    pages = {"Work": [P(work.page_dashboard, title="Dashboard", icon=":material/space_dashboard:", default=True),
                      schedule, activities, mine],
             "Finance": [budget], "Reports": [overview], "Manage": [people, settings]}
elif role == "finance":
    pages = {"Finance": [P(finance.page_budget, title="Budget and finance", icon=":material/account_balance:",
                           default=True)],
             "Work": [mine, schedule, activities, dashboard]}
elif role == "management":
    pages = {"Overview": [P(admin.page_management, title="Management overview", icon=":material/insights:",
                            default=True), schedule, budget]}
else:
    pages = {"Work": [P(work.page_mine, title="My activities", icon=":material/person_check:", default=True),
                      schedule, activities, dashboard]}

st.logo("assets/logo.svg", size="large", icon_image="assets/icon.svg")
nav = st.navigation(pages, position="sidebar", expanded=True)

with st.sidebar:
    s = db.settings()
    st.markdown(
        f'<div class="tt-me"><b>{ui.e(s["project_name"])}</b><span>{ui.e(s["project_code"])}</span></div>'
        f'<div class="tt-me"><b>{ui.e(me["name"])}</b><span>{ui.e(db.ROLES[me["role"]])}</span></div>',
        unsafe_allow_html=True,
    )
    label = "Sign out" if auth.AUTH_MODE == "microsoft" else "Switch person"
    if st.button(label, width="stretch"):
        auth.sign_out()
        st.rerun()

nav.run()
