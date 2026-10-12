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
- Small, tested commits on the branch, pushed after each part. Never commit directly to `main`.
- **One PR per step, only when the whole step is finished** (no PRs for individual parts).
  Claude creates it with the gh CLI (`gh pr create --base main --head <branch> --title ...
  --body-file ...`), shows the user the summary, and **merges only after the user says "merge"**
  (`gh pr merge <n> --squash`, one commit per step on main, no `--delete-branch`).
  Then Claude runs `git checkout main; git pull`, tags main (e.g. `phase2-step3`), pushes the tag
  and creates the next step's branch. Branches are **kept** for later debugging.
- gh 2.102.0 is installed at `C:\Program Files\GitHub CLI\` and logged in as MostafaNassar1.
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
- App built by `create_app(settings)` in `app/main.py` (tests build their own copies).
- Protect a route with `user: CurrentUser` / `admin: CurrentAdmin` (`app/core/dependencies.py`):
  401 for missing/invalid/expired/wrong-type tokens, 403 for disabled accounts.
- Errors: every error is `{"error": {"code", "message", "details"}}`
  (`app/middleware/error_handlers.py`). Raise `AppError(status, "specific_code", "message")`
  (`app/core/exceptions.py`) when the client needs a specific code; plain HTTPException gets a code
  from its status. Validation errors never echo the input; crashes return a generic 500.
- Logging: one line per request (method, path without query string, status, ms, request id);
  every response has `X-Request-ID`; uvicorn's access log is silenced (it logs query strings).
- Security helpers in `app/core/security.py`: bcrypt (max 72 bytes), JWT HS256 (fixed in code,
  claims `sub`, `sub_type` user/admin), `generate_token()` + `hash_token()` (SHA-256) for
  refresh/email tokens. `JWT_SECRET` only in `.env`. `CORS_ORIGINS` is a JSON list, empty by default.
- Auth endpoints (users): `/auth/register` (unverified account + emailed code, no tokens),
  `/auth/verify-email` {email, password, code} → tokens, `/auth/resend-verification`
  {email, password}, `/auth/forgot-password` {email} (always the same 202),
  `/auth/reset-password` {email, code, new_password} → logs out all devices + tokens,
  `/auth/login` (403 `email_not_verified` if unverified), `/auth/refresh|logout|me`,
  `/auth/google` {id_token} → tokens + `is_new_user` (linking policy in
  `controllers/google_auth_controller.py`, token check in `services/google_auth_service.py`).
  Admins: `/admin/auth/login|refresh|logout|me`. Shared logic: `services/token_service.py`
  (issue / rotate with reuse detection / revoke), `services/auth_service.py`
  (`check_password_login`: same 401 `invalid_credentials` + dummy bcrypt for unknown emails),
  `services/email_code_service.py` (issue / check codes, resend wait), `services/email_service.py`
  + `email_templates.py` (emails sent via FastAPI BackgroundTasks after the response).
  Sessions: access 15 min; refresh 30 days (users) / 12 hours (admins). Passwords: 8+ chars
  (users), 12+ (admins), max 72 bytes. Error codes so far: `email_taken`, `email_undeliverable`,
  `invalid_credentials`, `email_not_verified`, `already_verified`, `invalid_code`
  (details.attempts_left), `code_expired`, `code_recently_sent` (429, details.retry_after),
  `account_disabled`, `invalid_refresh_token`, `unauthorized`, `validation_error`,
  `invalid_google_token`, `google_email_not_verified`, `google_account_mismatch`,
  `google_sign_in_unavailable` (503).
- Tests: an autouse `outbox` fixture catches every email; `tests/auth/conftest.py` has
  `sign_up`, `last_code(outbox)`, `verify`, `age_codes` and the `unverified` / `registered`
  (verified + logged in) fixtures. `fake_google` (tests/conftest.py + tests/google_fake.py)
  signs Google ID tokens with a generated RSA key for the real google-auth verification.
- Check email settings: `python -m app.scripts.send_test_email --to <address>`. The user's `.env`
  uses `EMAIL_BACKEND=smtp` (real Gmail): never sign up made-up addresses against the dev server.
- Create admins (the user runs it; password typed hidden):
  `python -m app.scripts.create_admin --name "..." --email ... [--role ... --clinic-id N]`.
- No login rate limiting (user's decision): list it as a known limitation in the report.
- Settings added in Step 5: `BCRYPT_ROUNDS` (default 12; tests use 4 for speed),
  `EMAIL_CHECK_DELIVERABILITY` (DNS domain check at sign-up, `services/email_domain_service.py`;
  off in tests, which never use the internet). Test env overrides live at the top of `tests/conftest.py`.
- Migrations: review every autogenerated file (autogenerate misses CHECK constraints; give
  constraints their full convention name with `op.f(...)`). `0003` = email_tokens.attempts +
  non-unique token_hash. Dev DB is at `0003`.
- Run: `cd backend; .venv\Scripts\activate; uvicorn app.main:app --reload` → http://127.0.0.1:8000/docs
- Tests: `cd backend; .venv\Scripts\activate; pytest`. `tests/conftest.py` recreates
  `skincare_app_test` (name must end in `_test`) with `alembic upgrade head` each run, drops it at
  the end; each test runs in a rolled-back transaction (fixtures `db`, `client`).
  Tests are organized in one folder per area (each with `__init__.py`): `tests/database/`
  (migrations, models, constraints), `tests/api/` (endpoints); new areas get their own folder
  (e.g. `tests/security/`, `tests/middleware/`, `tests/auth/`, `tests/scripts/`). Shared fixtures
  stay in `tests/conftest.py` (area fixtures in that folder's own conftest.py). The test session
  uses the same settings as `SessionLocal` (`expire_on_commit=False`, `autoflush=False`).

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
- **Sign-up/login = Instagram-style (decided 2026-10-12):** email/password (any real provider) OR
  "Continue with Google". Email sign-up creates an UNVERIFIED account and emails a 6-digit code;
  the user enters it in the app → verified + logged in. Login of an unverified account → 403
  `email_not_verified` (app shows the code screen, "Resend code"). Forgot password = code by email
  + new password. Codes: 10 min expiry, max 5 wrong attempts (needed: 6 digits = 1M options),
  stored hashed. Re-registering an UNVERIFIED email replaces that account (no email squatting).
  Plus a DNS domain check at sign-up (rejects e.g. user@exasad.com). Google users are verified by
  Google. NOT an allowlist of providers (blocks university/work emails, proves nothing).
- Email sender = **Gmail SMTP** with a dedicated Gmail account + App Password (free, ~500/day);
  the App Password lives only in `.env`.
- **Account linking (decided 2026-10-12, Step 6):** "Continue with Google" with a new email →
  new verified account (no password). Known google_sub → log in. Email of a VERIFIED password
  account → link automatically (both methods work). Email of an UNVERIFIED password account → the
  Google user takes it over and the unproven password is DELETED (prevents pre-account takeover).
  Google-only users may add a password through forgot-password (inbox proven by the code).
  Google tokens with email_verified=false are refused. Admins never use Google login.
- Open decisions: hosting, calendar type, Cloudinary upload flow;
  weather = Open-Meteo (recommended).
- The local DB password is the PostgreSQL default (same as the username): fine for local
  development only, **must be changed to a strong one before hosting**.

## Progress
- Phase 1 (database): done, then rebuilt as v2 on 2026-10-08.
- Phase 2 Step 1 (setup + DB connection + /health): done, commit e6c9746, pushed to
  github.com/MostafaNassar1/SkinCare-APP (**public** repo, kept public by the user's choice:
  never commit secrets; `.env` is git-ignored).
- Phase 2 Step 2 (models + Alembic + tests): done 2026-10-11, PR #2 squash-merged, tag `phase2-step2`.
  Models in `app/models/` (12 files, allowed values in `choices.py`), shared `Base` in
  `app/db/base.py` (PostgreSQL-default constraint names, eager_defaults for trigger-set
  `updated_at`, passive_deletes on owned children). Dev DB stamped at `0002`.
- Phase 2 Step 3 (security helpers + current-user dependencies + middleware): done 2026-10-11 on
  branch `mostafa/feature/phase2-step3-security`, 60 tests passing; PR #3 squash-merged, tag `phase2-step3`.
- Phase 2 Step 4 (register, login, refresh rotation + reuse detection, logout, /me, admin login,
  create_admin script): done 2026-10-11 on branch `mostafa/feature/phase2-step4-email-auth`,
  127 tests passing; PR #4 squash-merged, tag `phase2-step4`. The first super admin is not created yet
  (the user runs create_admin when needed).
- Phase 2 Step 5 (steps 5 and 6 swapped on 2026-10-12): Instagram-style email codes —
  verification at sign-up, resend, forgot/reset password, DNS domain check, Gmail SMTP sender
  (skincare.app.noreply1@gmail.com, tested OK). Done 2026-10-12 on branch
  `mostafa/feature/phase2-step5-email-verification`, 195 tests; PR #5 squash-merged, tag
  `phase2-step5`.
- Phase 2 Step 6 (Google sign-in + account linking + Google-only users add a password via
  forgot-password): done 2026-10-12 on branch `mostafa/feature/phase2-step6-google-auth`,
  222 tests; PR waiting for the user's manual Google test and "merge". Google Cloud project
  "SkinCare App", Web client id in `.env` (`GOOGLE_CLIENT_IDS`), JS origin http://localhost:5500,
  consent screen in Testing mode (only listed test users can sign in).
- **NEXT: Phase 2 Step 7**: profile APIs (profile, skin quiz, allergies, location, FCM devices).
- Later Phase 2 steps: 8 reference APIs ·
  9 routines/logs · 10 clinics/appointments/Overpass · 11 notifications/calendar.
  Tests (pytest) inside each step.
- Not yet assigned to a step: a background scheduler for reminders/weather/achievements
  (depends on hosting). It must also run `python -m app.scripts.cleanup_unverified` daily
  (deletes email sign-ups still unverified after 24 h; `--dry-run`, `--hours N`).
