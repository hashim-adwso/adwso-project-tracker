---
title: Project Tracker
emoji: ✅
colorFrom: blue
colorTo: yellow
sdk: docker
app_port: 8501
pinned: false
---

# Project Tracker – ECHO HIP 2026 (PIN partnership)

A tracker for one project: its activities, schedule, team, budget and payments.
The first version is set up for ADWSO's ECHO HIP 2026 partnership with People in Need (PIN),
1 Oct 2026 – 30 Sep 2027.

## What it does

**Activities, in four types**

| Type | What you enter | How progress is measured |
|---|---|---|
| One-time | One date | Done when that date is marked done |
| Selected dates | Several specific dates | Each date is ticked off; progress = dates done ÷ dates planned |
| Date range (e.g. a campaign) | Start and end date | The person updates the percentage by hand. If the end date passes before 100%, the activity is flagged as overdue |
| Recurring (weekly, monthly, quarterly) | One date, several dates, or a range | As above, plus a "Recurring" label. "Create next occurrence" plans the next one |

Each activity has a lead person, optional support people, priority, location, workplan reference,
description and an update log. Any activity can be marked as blocked (with a reason) or cancelled.
"Key activities" are the ones shown to management.

**Pages**

- **Dashboard:** pending and overdue work, and progress, for any person and any period (this week,
  next 7 days, this month, next 30 days, or custom dates). Downloads to Excel (CSV).
- **Schedule:** a week view (Saturday to Friday) with "Mark done" on each card, and a month calendar.
- **Activities:** the full list with search and filters; create and edit activities here.
- **My activities:** the signed-in person's overdue, this-week and upcoming work.
- **Budget and finance:** summary (budget, spending, cash in hand, payments from the partner, spending pace),
  budget lines with spending to date, the daily ledger with daily totals, and invoices/funds requests and
  instalments received.
- **Management overview:** key activities, what needs attention, upcoming deadlines, days to the next report,
  and the financial position.
- **People** and **Project settings** (coordinator only).

**Roles**

| Role | Sees | Can change |
|---|---|---|
| Project coordinator | Everything | Activities, people, settings; progress on any activity |
| Finance focal point | Budget first, plus activities | Budget entries, invoices, instalments; progress on activities they are part of |
| Management | Management overview, schedule, budget | Nothing |
| Team member | Their activities, schedule, list | Progress on activities they are part of |

## Starting data

On first start the app loads the project's starting data: the 33 activities from the
workplan (including the PIN and ECHO reporting deadlines), the Annex C budget lines, and the project team.
Where the workplan gives only a month, the date is a month-end placeholder, and the description says so.

Because this repository is public, the starting data is stored encrypted in `seed/project.enc`.
The app unlocks it with the `SEED_KEY` secret. Without the key the app shows a message and does not start.
(For local work, a plain `seed/project.json` is used instead when present; it is never published.)

The ledger currency is USD; partner invoices and instalments are recorded in EUR, the agreement currency.

## Test version (now): Streamlit Community Cloud

There is no Microsoft sign-in in the test version. People choose their name from the People list.

App secrets (Streamlit Community Cloud → the app → **Settings → Secrets**), in this format:

```toml
APP_PASSWORD = "a password you share with the reviewers"
SEED_KEY = "the key that unlocks the starting data"
HF_TOKEN = "hf_..."                       # Hugging Face token with write access
DATA_REPO = "your-hf-name/pin-tracker-data" # a PRIVATE Hugging Face dataset
```

- `APP_PASSWORD` is optional but recommended, because the app shows the real budget and staff names.
- `SEED_KEY` is required; keep it private and never share it in the repository.
- `HF_TOKEN` and `DATA_REPO` keep the data. Streamlit Community Cloud erases the app's disk whenever the app
  restarts or wakes from sleep; with these two settings every change is copied to the private dataset within
  seconds and restored on start-up. Without them, all entries are lost on each restart.

**Demo financial entries:** Project settings → "Load demo entries" adds 12 sample expenses, one funds request
and one instalment, all labelled `[Demo]`, so the Budget pages can be presented. "Remove demo entries"
deletes exactly those rows.

## After approval: Hugging Face with Microsoft sign-in

1. Register the app in Microsoft Entra (single tenant), redirect URI
   `https://OWNER-SPACE.hf.space/oauth2callback`, and create a client secret.
2. Create a Docker Space and connect GitHub with `.github/workflows/sync-to-huggingface.yml`
   (repository secret `HF_TOKEN`, repository variable `HF_SPACE`).
3. Space secrets: `AUTH_MODE=microsoft`, `SEED_KEY`, `MS_TENANT_ID`, `MS_CLIENT_ID`, `MS_CLIENT_SECRET`,
   `APP_URL=https://OWNER-SPACE.hf.space`, `COOKIE_SECRET` (long random text), `HF_TOKEN`, `DATA_REPO`.
4. Make sure everyone has their ADWSO email on the People page. With `AUTH_MODE=microsoft`, only people on
   that list can sign in, with the role recorded there.

`start.py` turns the Space secrets into Streamlit's sign-in settings.

## Run on your own computer

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Files

| File | Purpose |
|---|---|
| `app.py` | Start-up, sign-in, menu by role |
| `core/acts.py` | Activity types, progress, status, period queries, recurring occurrences |
| `core/money.py` | Budget lines, ledger, invoices, instalments, totals |
| `core/work.py` | Dashboard, schedule, activity list, activity window |
| `core/finance.py` | Budget pages |
| `core/admin.py` | Management overview, people, settings |
| `core/db.py` | Database and backup |
| `core/auth.py` | Test and Microsoft sign-in, roles and permissions |
| `core/seed.py`, `seed/project.enc` | Starting data (encrypted) and demo entries |
| `Dockerfile`, `start.py` | Hugging Face deployment |
