# SkinCare-APP — AI Skincare Companion (Final Year Project, IUL University)

Solo FYP. The user takes a face photo; an AI model detects visible skin concerns
(acne, oiliness, dryness, redness, dark spots, wrinkles), and a rule-based engine builds a
personalized routine. NOT disease diagnosis, no medicine; serious cases are referred to
dermatologists through the clinic locator, with a visible disclaimer.

## How to work with the user
- Act as an FYP instructor/mentor: honest, push back with reasons, explain the *why* (the user must defend it to examiners).
- One step at a time; wait for confirmation before moving on. Max 1-2 questions at a time.
- Claude runs the commands and writes the code, but **explains what it will do before running anything**.
- Everything must be free (free tiers / open-source). No feature cuts; extra features only after the scope is done.
- At the end of each session, write a documentation summary for the FYP report
  (saved per day in `OneDrive\Desktop\Final Year Project\Documentation\Day N(date)\`).

## Git workflow (agreed 2026-10-11)
- One branch per step, created from an up-to-date `main`:
  `mostafa/<type>/phase<P>-step<S>-<short-desc>` (type = feature | bug | spike | docs | chore),
  e.g. `mostafa/feature/phase2-step2-models`.
- Small, tested commits on the branch. Never commit directly to `main`.
- When the step is done: Claude pushes the branch and gives the PR title + description →
  the user opens the PR on github.com and clicks **Squash and merge** (one commit per step on main)
  → Claude runs `git checkout main; git pull`, tags main (e.g. `phase2-step2`) and creates the
  next step's branch. Branches are **kept** (not deleted) for later debugging. No gh CLI needed.
- An early PR merge mid-step is fine: keep working on the same branch and open a new PR at the end.
- Bug found during a step: fix it in that step's branch. Bug in an already-merged step:
  its own `mostafa/bug/...` branch and PR.

## Stack
Flutter (mobile, Phase 4-6) · React admin (Phase 7) · FastAPI on Python 3.12 · PostgreSQL 16
(port 5433, database `skincare_app`, user `postgres`) · SQLAlchemy 2 + Alembic · Cloudinary ·
JWT access + refresh tokens · Google Sign-In + email/password (bcrypt) · FCM (push only) ·
OpenStreetMap/Overpass (clinics + pharmacies) · pretrained CNN fine-tuned on public datasets.

## Backend architecture (agreed)
`Middleware → routes/ (endpoints only, no logic) → controllers/ (logic per endpoint) →
services/ (shared logic + external APIs) → repositories/ (DB queries) → models/ → PostgreSQL`
- A controller never imports another controller; logic needed in two places goes to services/.
- Auth = FastAPI dependency `Depends(get_current_user)`, not middleware. Middleware = CORS, logging, errors.
- Settings in `backend/.env` (git-ignored) via `app/core/config.py`; `get_db()` lives in `app/core/dependencies.py`.
- Run: `cd backend; .venv\Scripts\activate; uvicorn app.main:app --reload` → http://127.0.0.1:8000/docs
- Tests: `cd backend; .venv\Scripts\activate; pytest`. `tests/conftest.py` recreates
  `skincare_app_test` (name must end in `_test`) with `alembic upgrade head` each run, drops it at
  the end; each test runs in a rolled-back transaction (fixtures `db`, `client`).
  Tests are organized in one folder per area (each with `__init__.py`): `tests/database/`
  (migrations, models, constraints), `tests/api/` (endpoints); new areas get their own folder
  (e.g. `tests/security/` in Step 3, `tests/auth/` in Step 4). Shared fixtures stay in `tests/conftest.py`.

## Key decisions (with reasons, for the report)
- Datasets: ACNE04 (acne + severity), FFHQ-Wrinkle, Roboflow CC-BY redness and pigmentation sets,
  Kaggle oily/dry set. Fitzpatrick17k/SD-198 dropped (disease datasets). Model: shared backbone,
  one sigmoid head per concern, masked loss. Licenses still to verify in Phase 3.
- Oiliness/dryness = **hybrid (Option A)**: the skin quiz is primary, the photo is a supporting signal.
- Recommendations = **product types + ingredient + concentration** from the rules engine. No brand
  tables, no LLM. "Find nearby pharmacy" uses live Overpass data.
- Schema v2 (26 tables) in `database/schema_v2.sql` + `seed_v2.sql`; the rules-engine algorithm is
  described in the seed file. Migration `0001` runs schema_v2.sql, `0002` runs seed_v2.sql
  (reference data the app needs). Both SQL files are **FROZEN**: every schema/data change is a new
  Alembic migration. Commands (from `backend/`): `alembic upgrade head`, `alembic current`,
  `alembic check` (models vs DB), `alembic revision --autogenerate -m "..."`.
- Recommended libraries: google-auth (Google ID tokens), PyJWT, bcrypt used directly (not passlib / python-jose).
- Open decisions: hosting, email sender (Gmail SMTP / Brevo), calendar type, Cloudinary upload flow,
  account-linking policy; weather = Open-Meteo (recommended).

## Progress
- Phase 1 (database): done, then rebuilt as v2 on 2026-10-08.
- Phase 2 Step 1 (setup + DB connection + /health): done, commit e6c9746, pushed to
  github.com/MostafaNassar1/SkinCare-APP (private, branch main).
- Phase 2 Step 2 (models + Alembic + tests): done on branch `mostafa/feature/phase2-step2-models`
  (2026-10-11), waiting for the PR squash-merge + tag `phase2-step2`.
  Models in `app/models/` (12 files, allowed values in `choices.py`), shared `Base` in
  `app/db/base.py` (PostgreSQL-default constraint names, eager_defaults for trigger-set
  `updated_at`, passive_deletes on owned children). Dev DB stamped at `0002`.
- **NEXT: Phase 2 Step 3**: security helpers (refresh/email tokens stored as SHA-256, not bcrypt)
  **+ middleware** (CORS, request logging, global error handlers with one JSON error format).
- Later Phase 2 steps: (refresh/email tokens stored as SHA-256, not bcrypt)
  4 email auth **+ admin login** (same JWT code, token marks user vs admin; needed by Step 10
  clinic managers) · 5 Google auth · 6 reset/verify email · 7 profile APIs · 8 reference APIs ·
  9 routines/logs · 10 clinics/appointments/Overpass · 11 notifications/calendar.
  Tests (pytest) inside each step.
- Not yet assigned to a step: a background scheduler for reminders/weather/achievements
  (depends on hosting).
