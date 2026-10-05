# AdaptoLearn

AdaptoLearn is a Flask learning platform with a SQLite data store, HTML templates, CSS, and plain JavaScript. The application starts at `run.py`; student and administrator workspaces have separate templates, scripts, routes, and server-side access controls. No frontend build step is required.

The Python modules at the project root contain application services, routes, database access, and domain rules. `templates/` and `static/` contain the UI shells and frontend assets; `tests/` contains Python integration/browser tests and Node tests; `scripts/` contains maintenance utilities.

## Local setup

Use Python 3.13 or newer. Node.js is needed for frontend checks, linting, and formatting.

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
# Set SECRET_KEY and configure a mail provider in .env.
.\.venv\Scripts\python run.py
```

Open http://127.0.0.1:5000. HTML, CSS, and JavaScript changes do not require a build.

## Environment variables

### Resend HTTP delivery

Set these server-only values in `.env`, then restart `run.py`:

```dotenv
MAIL_PROVIDER=resend
RESEND_API_KEY=re_your_api_key
```

The default workflow uses `requests.post('https://api.resend.com/emails', ...)`, with no SMTP, Microsoft tenant credentials, or university admin permissions. The sender is `Registration System <onboarding@resend.dev>`. **Resend restricts this testing sender to your Resend account email.** Use your university email for your Resend account to test that recipient. Sending to other students requires a verified domain you control and a different sender. See [Resend's restriction](https://resend.com/docs/knowledge-base/403-error-resend-dev-domain).

Verification codes are generated with Python `secrets`, stored as bcrypt hashes, expire after **15 minutes**, allow five attempts, and are single-use. Resends invalidate older codes. Delivery failure rolls back registration; HTTP calls have timeouts and safe errors. Password recovery codes expire after ten minutes.

`POST /api/register` takes the existing signup fields: email, password, name, institution_id, programme, year. It validates the official university email domain and sends the code. `POST /api/verify` takes `{ "email": "221234567@dut4life.ac.za", "code": "123456" }` in the pending registration session. Email is optional for the existing UI; if supplied, it must match that session. Both endpoints require the CSRF token from `/api/bootstrap`. Verification marks the student active and establishes their session.

Legacy SMTP utilities are unused unless explicitly selecting `MAIL_PROVIDER=smtp`.


| Variable | Purpose |
| --- | --- |
| `SECRET_KEY` | Required persistent Flask session secret. Generate with `secrets.token_hex(32)`. |
| `DATABASE_PATH` | SQLite database location; defaults to `instance/adaptolearn.sqlite3`. |
| `HOST`, `PORT` | Local listening address and port, default `127.0.0.1:5000`. |
| `COOKIE_SECURE` | Set `1` for HTTPS deployments; leave `0` locally. |
| `MAIL_PROVIDER`, `RESEND_API_KEY` | Default `resend`; server-only API key. |
| `SMTP_HOST`, `SMTP_PORT` | SMTP server and port; port defaults to 587. |
| `SMTP_SECURITY` | `starttls` (default), `ssl`, or `none` for a trusted local relay. |
| `SMTP_USERNAME`, `SMTP_PASSWORD` | Mail service credentials. Username may be empty for a trusted local relay. |
| `SMTP_FROM` | Authorized sender address for verification messages. |
| `SMTP_AUTH` | `password` for other SMTP providers, or `microsoft_oauth` for Microsoft 365. |
| `MICROSOFT_TENANT_ID`, `MICROSOFT_CLIENT_ID` | Microsoft directory and app registration GUIDs for delegated SMTP OAuth. |
| `MICROSOFT_TOKEN_CACHE` | Encrypted MSAL cache, defaults to `instance/microsoft-mail-cache.bin`. |
| `ADMIN_INITIAL_PASSWORD` | Initial admin password used only by the setup script; 10–128 characters. Remove after first-login reset. |
| `ADMIN_OLD_EMAIL` | Select an existing admin if multiple admins exist. Not needed for a single admin. |
| `ANNOUNCEMENT_WORKER` | `1` (default) dispatches scheduled notices every 20 seconds. Set `0` when using an external scheduler instead. |

Do not place passwords or email credentials in templates, JavaScript, source, command-line arguments, or version control.

## Student registration and verification

“Forgot password?” appears next to Sign in. Both students and administrators can request a six-digit password reset code by email, enter it with a new password, and then sign in again. Codes are bcrypt-hashed, expire after ten minutes, permit five attempts, and are single-use. Resends invalidate prior codes, enforce a 60-second cooldown, and are limited to five per email per hour. Successful recovery invalidates existing sessions and preserves the account's role and verification status. The request response is identical for unknown accounts and email-delivery failures. Resend must be configured for delivery; check server logs for the generic delivery-failure notice if no email arrives.

The registry contains all 26 public institutions and the owner-supplied student domains. DUT is selected initially. Student IDs type only the email local part; the selected institution domain is a locked suffix. Changing institution preserves the local part. The server revalidates the normalized full address against the current institution registry, rejects mismatched/public email domains, and checks registration availability.

Accounts start with `email_verified=0` and `PENDING_VERIFICATION`. Successful password authentication for a pending account opens verification only; it does not grant access to student APIs. A cryptographically generated six-digit code is emailed to the institutional address, stored only as a bcrypt hash, and expires after 15 minutes. Five failed attempts exhaust the code. All failures use “Invalid or expired code”.

The six input fields support paste, automatic focus advancement, arrows, backspace, labels, and keyboard access. Resends have a server-side 60-second cooldown and a maximum of five per user per hour. User and IP limits also protect verification/resend endpoints. Issuing a new code invalidates older codes. Successful verification consumes every outstanding code and activates the account.

Code, SMTP, and login secrets are never written to application logs. Automated tests capture mail only through a testing-only in-memory transport. Production has no test inbox or bypass.

## Administration and maintenance

```powershell
.\.venv\Scripts\python scripts/manage.py cleanup-demo
.\.venv\Scripts\python scripts/manage.py setup-admin
.\.venv\Scripts\python scripts/manage.py dispatch-announcements
```

`setup-admin` initializes or migrates an administrator using the server-only `ADMIN_INITIAL_PASSWORD` setting; an existing administrator can be selected with `ADMIN_OLD_EMAIL`. The command requires a database created by starting the app and makes a timestamped backup before changing account data. No administrator is created automatically at startup.

`cleanup-demo` removes only the known legacy demo accounts and also backs up the database first. Review the command output and backup location before using maintenance commands against a non-test database. `seed-test-admin` is for local testing only and must never be run against production data.

## Administration

The login form requires a Student/Admin selector, defaulting to Student. The server compares it with the stored account role and responds with “Invalid email or password” for an unknown account, wrong password, or role mismatch. Public signup remains student-only and refuses the reserved administrator email or any address already belonging to an admin.

For local testing only, a test administrator can be seeded explicitly:

```powershell
.\.venv\Scripts\python scripts/manage.py seed-test-admin
```

The seed is idempotent and intended only for disposable development databases. It is never run automatically and must not be used in production. Production administration should use `setup-admin`.

Sign in through the normal login page. Administrators are routed to `/admin/overview`. Students receive 403 on admin pages/APIs; unauthenticated admin-page requests redirect to login. Administrators receive 403 on student workspace APIs. Admin JavaScript is loaded only by the guarded admin template.

- `/admin/overview`: student totals, pending/verified counts, active institution counts, recent sign-ups.
- `/admin/students`: search/filter, read-only detail, verify/unverify, suspend/reactivate, delete.
- `/admin/verifications`: pending accounts, verification controls, code resend.
- `/admin/institutions`: enable/disable registrations and edit student domains. Overrides persist in SQL and feed all signup and server-validation paths.
- `/admin/admins`: super-admin-only privilege assignment and deactivation. Account creation is available only through setup scripts.
- `/admin/announcements`: immediate/scheduled in-app notices, optionally limited to an institution.
- `/admin/audit`: actor, action, target, timestamp, and non-secret change details.

Suspension, role/privilege changes, unverification, password changes, and migration invalidate old authenticated sessions through `auth_version`. Administrative student controls never edit learning profiles. Admins cannot deactivate/demote themselves.

Scheduled notices are delivered by the background dispatcher when their due time arrives. Delivery and marking the notice sent happen in one SQL transaction, preventing duplicate deliveries. For external scheduling, disable `ANNOUNCEMENT_WORKER` and periodically run:

```powershell
.\.venv\Scripts\python scripts/manage.py dispatch-announcements
```

## Student learning features

Verified students retain editable modules, strengths, priority-weighted learning needs, interests, methods, and availability; ranked peers and match explanations; connection requests; sessions and status/history; feedback-driven recommendations; and in-app notifications. Institution changes on a verified profile must still match the student's email.

Matching weights: needs 40%, reciprocal assistance 10%, modules 20%, availability 15%, methods 10%, interests 5%. Pair feedback adjusts by -10 to +10 points; scores stay in 0–100. Topic matching ignores case and otherwise uses exact text. All session/availability times are SAST (UTC+2). Reminders are checked when activity is loaded. No student email verification is inferred from an academic profile or an institution domain alone.

## File map

| File | Responsibility |
| --- | --- |
| `institutions.py` | Typed 26-institution registry and stable IDs; no duplicated domains in UI/routes. |
| `database.py`, `migrations.py`, `schema.sql` | Data access, transactions, additive SQL upgrades, base learning tables. |
| `schemas.json`, `validation.py`, `errors.py` | Shared JSON schemas, authoritative server validation, safe typed errors. |
| `auth_service.py`, `access.py` | Registration/authentication/reset services and server role/session guards. |
| `verification.py`, `mailer.py` | Hashed verification lifecycle, limits, responsive HTML and Resend HTTP delivery. |
| `admin_service.py`, `admin_routes.py` | Admin operations, auditing, and guarded page/API controllers. |
| `maintenance.py`, `scripts/manage.py` | Scoped demo cleanup, admin email migration, backups, dispatch CLI. |
| `test_users.py`, `seed_service.py`, `password_hashing.py` | Server-only test-admin config, idempotent bcrypt seeding, compatible password verification. |
| `password_recovery.py` | Hashed expiring reset codes, generic request responses, limits, and session invalidation. |
| `scheduler.py`, `run.py` | Scheduled notice dispatcher and local/WSGI entry point. |
| `requirements.txt`, `requirements-dev.txt`, `pyproject.toml` | Runtime/development Python dependencies and Ruff rules. |
| `package.json`, `eslint.config.mjs`, `.prettierrc.json` | Node tests, syntax checks, lint, and formatting commands. |
| `static/shared.js`, `domain.js` | API/forms/schema utilities and pure institution-domain logic. |
| `static/auth.js`, `app.js`, `admin.js` | Accessible verification/signup, student workspace, separate admin workspace. |
| `templates/index.html`, `templates/admin.html` | Separate student/auth and admin document shells. |
| `static/style.css` | Responsive layouts, input styles, and motion with reduced-motion support. |
| `tests/test_app.py`, `test_security.py`, `test_browser.py` | Student regression, security/migration, and real desktop/mobile browser tests. |
| `tests/conftest.py` | Shared isolated Flask test application fixture. |
| `tests/frontend.test.mjs` | Pure institution domain/auto-fill tests against the JavaScript source. |

## Tests and quality checks

```powershell
npm run check
npm run lint
npm test
npm run format:check
.\.venv\Scripts\python -m pytest -q
.\.venv\Scripts\python -m ruff check .
.\.venv\Scripts\python -m ruff format --check .
```

Browser tests additionally need Playwright and a browser: Windows uses installed Microsoft Edge; other platforms require Playwright Chromium (`python -m playwright install chromium`). Tests use isolated temporary SQL databases and in-memory email capture; they do not send real emails. Browser screenshots are written under `artifacts/`.

Install only runtime dependencies in production with `pip install -r requirements.txt`. Development dependencies, including Ruff, are listed in `requirements-dev.txt`.

## Deployment

The Dockerfile and Gunicorn entry point are prepared; no public hosting URL has been deployed. Set the environment variables above on the host, mount persistent SQLite storage at `/data`, use HTTPS and `COOKIE_SECURE=1`, and keep the SQL volume and session secret across deployments. HTML, CSS, and JavaScript files are included directly; `.env` and local account backups are excluded from Docker builds. `/health` checks the database. Use one replica for this SQLite configuration; server SQL is needed for horizontal scaling.

The project owner's domain list is application configuration, not an independently certified list of current university email policies. Institution names were originally sourced from [Universities South Africa](https://usaf.ac.za/prospective-students/).
