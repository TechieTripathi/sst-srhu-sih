# TechForge 3.0 — Hackathon Jury & Evaluation Platform

Judging platform for **TechForge 3.0**, the 36-hour internal hackathon of the School of Science & Technology, Swami Rama Himalayan University (institutional round for SIH 2026).

**Stack:** Flask 3 · MongoDB Atlas (PyMongo) · Jinja2 · vanilla JS · deployed on Vercel.

## Roles

| Role | Login | Does |
|---|---|---|
| Team leader | `/teams/register` | Registers a team |
| Jury (internal / external) | `/judge/login` — email + password (credentials emailed by admin or `seed_judges.py`) | Scores every registered team |
| Admin (operations team) | `/admin` | Teams, judges (create + email credentials), lock judging, publish results, evaluations, audit logs, CSV export |
| Super Admin (developer) | `/super-admin` | Admin account provisioning, system settings, full audit trail, system health |

## Scoring

Six criteria, each scored 0–10:
Problem Understanding 15% · Innovation 15% · Technical Design 20% · Prototype 25% · Impact 15% · Presentation 10%.

**Final = Internal jury avg × 40% + External jury avg × 60%.** Computed server-side in `services/results_calculator.py`.
Full rules, tie-breaks and a worked example: [docs/SCORING.md](docs/SCORING.md).

## Run locally

```bash
git clone https://github.com/TechieTripathi/sst-srhu-sih.git && cd sst-srhu-sih
python -m venv venv && source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                 # fill in MONGO_URI, SECRET_KEY, SMTP_*
python init_db.py                                    # criteria + event settings
python admin_seed.py                                 # operations admin from ADMIN_* env (--reset to change password)
python seed_super_admin.py                           # super admin from SUPER_ADMIN_* env
python seed_judges.py                                # 25 pre-authorised jury members (DB only; add --email to send passwords)
python app.py                                        # http://localhost:5002
```

Change the default admin password after first login.

## Environment variables

See `.env.example`. Required: `MONGO_URI`, `MONGO_DB_NAME`, `SECRET_KEY`.
`FRONTEND_URL` = the public base URL (e.g. `https://sst.aicentre.org`) — every link in credential emails is built from it, so set it per environment.
`FLASK_ENV=production` enables secure cookies. `SMTP_*` is needed to email judges their login credentials (without it the password is shown once on screen). Never commit `.env`.

## Deploy (Vercel)

No `vercel.json` needed — Vercel auto-detects the Flask app in `app.py`.

1. Import the GitHub repo in Vercel.
2. Add every variable from `.env.example` under **Settings → Environment Variables** (missing `MONGO_URI` crashes the function on cold start).
3. In MongoDB Atlas → **Network Access**, allow `0.0.0.0/0` (Vercel has no fixed IPs).
4. Push to `main` → auto-deploys.

## Front-end (Tailwind CSS)

Templates use Tailwind v4 with SRHU brand tokens (`static/css/src/app.css`). The built stylesheet
`static/css/app.css` **is committed** — Vercel never runs npm. After editing templates or tokens:

```bash
npm install            # once (Node 18+)
npm run build:css      # rebuild static/css/app.css, then commit it
npm run watch:css      # while developing
```

Logo: replace `static/images/srhu-logo.png` with the official high-resolution SRHU logo (same filename).

## Tests

```bash
python -m unittest discover tests        # needs a reachable MONGO_URI
```

## Layout

```
app.py              app factory, root routes, error handlers
config/             settings from env; evaluation criteria & weights
models/database.py  Mongo connection, indexes, collection helpers
routes/             auth · admin · super_admin · judge · teams · evaluations · results · api
services/           jury auth, email, scoring, results, judging lock, judge mgmt, audit, seeding
templates/ static/  Jinja pages by role (partials/ui.html = shared macros); Tailwind source + built CSS; main.js
tests/              unittest suites
init_db.py, admin_seed.py, seed_super_admin.py, seed_judges.py, seed_test_judge.py, inspect_db.py, clean_dummy_data.py
```
