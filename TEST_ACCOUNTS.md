# Test Accounts — TechForge 3.0

Default accounts for local / staging testing. Each role has its own sign-in page.

| Role | Panel | Email | Password |
|---|---|---|---|
| Super Admin (developer) | `/super-admin` | `superadmin@srhu.edu.in` | `superadmin123` |
| Admin (operations team) | `/admin` | `admin@srhu.edu.in` | `admin123` |

## How they get created

```bash
python admin_seed.py         # creates the Admin from ADMIN_* in .env (defaults above); --reset to change its password
python seed_super_admin.py   # creates the Super Admin from SUPER_ADMIN_* in .env
```

Both scripts are idempotent — re-running them does not reset an existing password.
The Super Admin values come from `.env` (`SUPER_ADMIN_EMAIL`, `SUPER_ADMIN_PASSWORD`);
the Admin values come from `ADMIN_EMAIL` / `ADMIN_PASSWORD` (defaults shown above).

## Before the event

- **Change both passwords.** These defaults are in the repo and are effectively public.
  Super Admin: set a new `SUPER_ADMIN_PASSWORD` in `.env` / Vercel and re-run `seed_super_admin.py`,
  or reset it from `/super-admin/admins`. Admin: reset it from `/super-admin/admins`.
- Create real operations-team accounts from `/super-admin/admins` and deactivate `admin@srhu.edu.in`.
