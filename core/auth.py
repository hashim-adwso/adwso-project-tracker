"""Who is using the app, and what they may do.

Two modes, set with the AUTH_MODE setting:
- "open" (default, for testing): the person chooses their name from the People list. An optional
  APP_PASSWORD keeps the test version away from casual visitors.
- "microsoft" (production): sign-in with an organization Microsoft account. Only people on the
  People list (matched by email) get in, with the role recorded there.
"""
from __future__ import annotations

import hmac

import streamlit as st

from core import db, ui
from core.db import _secret

AUTH_MODE = _secret("AUTH_MODE", "open").strip().lower() or "open"
APP_PASSWORD = _secret("APP_PASSWORD").strip()


def microsoft_configured() -> bool:
    try:
        return "auth" in st.secrets
    except Exception:
        return False


def _password_gate() -> None:
    if not APP_PASSWORD or st.session_state.get("_pw_ok"):
        return
    ui.gate("Project Tracker", "This is a test version. Enter the access password you were given.")
    _, mid, _ = st.columns([1, 1.2, 1])
    with mid.form("pw"):
        pw = st.text_input("Access password", type="password")
        if st.form_submit_button("Continue", type="primary", width="stretch"):
            if hmac.compare_digest(pw.encode(), APP_PASSWORD.encode()):
                st.session_state["_pw_ok"] = True
                st.rerun()
            st.error("That password is not correct.")
    st.stop()


def current_person() -> dict:
    if AUTH_MODE == "microsoft":
        return _microsoft_person()
    _password_gate()
    pid = st.session_state.get("pid")
    p = db.person(pid) if pid else None
    if p and p["active"]:
        return p
    team = db.people()
    s = db.settings()
    ui.gate(s["project_name"], "Choose your name to continue. In this test version anyone can choose any name; "
            "after approval, people will sign in with their ADWSO Microsoft account instead.")
    _, mid, _ = st.columns([1, 1.2, 1])
    with mid:
        if not team:
            st.error("The People list is empty. Ask the administrator to add the team.")
            st.stop()
        choice = st.selectbox("Your name", [p["id"] for p in team],
                              format_func=lambda i: next(f"{p['name']} ({db.ROLES[p['role']]})" for p in team if p["id"] == i),
                              index=None, placeholder="Select your name")
        if st.button("Continue", type="primary", width="stretch", disabled=choice is None):
            st.session_state["pid"] = choice
            st.rerun()
    st.stop()


def _microsoft_person() -> dict:
    if not microsoft_configured():
        ui.gate("Sign-in is not set up", "AUTH_MODE is 'microsoft', but the Microsoft sign-in settings are missing. "
                "See the README.")
        st.stop()
    if not st.user.is_logged_in:
        s = db.settings()
        ui.gate(s["project_name"], "Sign in with your ADWSO Microsoft account to continue.")
        _, mid, _ = st.columns([1, 1.2, 1])
        mid.button("Sign in with Microsoft", type="primary", width="stretch", on_click=st.login)
        st.stop()
    email = (st.user.get("email") or st.user.get("preferred_username") or "").strip().lower()
    p = db.person_by_email(email) if email else None
    if not p:
        ui.gate("You're not on this project's team list",
                f"You signed in as {email}. Ask the project coordinator to add this email on the People page.")
        _, mid, _ = st.columns([1, 1.2, 1])
        mid.button("Sign out", width="stretch", on_click=st.logout)
        st.stop()
    return p


def sign_out() -> None:
    if AUTH_MODE == "microsoft":
        st.logout()
    else:
        st.session_state.pop("pid", None)


# --------------------------------------------------------------------------- permissions
def can(p: dict, action: str, activity: dict | None = None) -> bool:
    role = p["role"]
    if action in ("edit_activities", "manage_people", "settings"):
        return role == "coordinator"
    if action == "update_progress":
        if role == "coordinator":
            return True
        return role in ("team", "finance") and activity is not None and p["id"] in activity["people_ids"]
    if action == "view_finance":
        return role in ("coordinator", "finance", "management")
    if action == "edit_finance":
        return role == "finance"
    if action == "view_all_activities":
        return role in ("coordinator", "finance", "team", "management")
    return False
