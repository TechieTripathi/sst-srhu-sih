# TechForge 3.0 — UI Redesign Plan (Tailwind CSS + SRHU brand)

> **Status (25 Aug 2026): Phases 1–6 implemented.** Remaining: swap in the official high-res SRHU logo; confirm the saffron accent with SRHU comms.

Order of work, as requested: **Foundation → Public/Teams → Jury → Admin → Super Admin (last)**.
Each phase ships independently; the app keeps working between phases because old CSS
and new Tailwind classes coexist until Phase 6 removes the legacy files.

---

## 0. Brand facts (verified) and open items

| Item | Status |
|---|---|
| Logo | Navy wordmark **SRHU** with a mountain-peak motif, "Swami Rama Himalayan University" beneath, NAAC A+ badge. Sampled from the public logo file: dominant **#183878** (≈45 %), shades #184888 / #082868, white. |
| Primary colour | **Navy #183878** — taken directly from the logo. |
| Accent colour | *Not verifiable*: srhu.edu.in sits behind a Cloudflare bot-check and refused every fetch. Recommendation below uses **saffron/gold** (already used as `--gold` on the landing page and culturally apt for an Indian university); confirm with SRHU communications or swap the single token. |
| Logo asset | Only an 80×75 px public copy exists → `static/images/srhu-logo-placeholder.png`. **Ask SRHU for the official SVG/PNG (≥ 512 px, transparent)** and save as `static/images/srhu-logo.svg` before Phase 2. The templates will reference that path from day one. |
| Fonts | Institutional site fonts unknown (blocked). Use **Inter** (UI) + **Sora** or **Plus Jakarta Sans** (display) via Google Fonts, both free. |

### Design tokens (Tailwind theme)
```
brand.navy      #183878   primary — nav, sidebar, primary buttons, links
brand.navy-700  #12305f   hover / active
brand.navy-900  #0b1f4b   dark headers, footer
brand.navy-100  #e6ecf7   tinted backgrounds, selected rows
brand.saffron   #f2a900   accent — CTAs on dark, highlights, "Register" (confirm)
brand.saffron-600 #d99400 accent hover
brand.snow      #f6f8fb   page background
brand.ink       #1a1f36   body text
crimson  #c41e3a  danger only (locked judging, deactivate, destructive) — keep from current theme
success  #16a34a · warning #d97706 · info #2563eb
```
Role tint (subtle, top bar only, so users always know where they are):
Teams = navy · Jury = navy + saffron stripe · Admin = navy-900 · Super Admin = navy-900 + crimson stripe.

---

## 1. Toolchain (no Node needed on Vercel)

- `npm i -D tailwindcss @tailwindcss/cli @tailwindcss/forms` (Node 22 is installed locally).
- `tailwind.config.js`: `content: ["templates/**/*.html", "static/js/**/*.js"]`, brand colours above, fonts, `@tailwindcss/forms`.
- `static/css/src/app.css` → build to **`static/css/app.css` and commit the built file**. Vercel's Python preset never runs npm, so committing the output is the deployment-safe choice.
- npm scripts: `build:css` (minified) and `watch:css`. Document in README.
- `templates/base.html`: load `app.css`, Google Fonts, favicon = logo. Keep `main.css` etc. loaded until Phase 6.
- Component layer (`@layer components`) for the ~10 primitives so templates stay readable:
  `btn btn-primary|secondary|danger|ghost`, `card`, `badge-*`, `table-base`, `input`, `select`,
  `alert-*`, `stat-card`, `tab`, `sidebar-link`. Jinja macros in `templates/partials/ui.html`
  (`{% from 'partials/ui.html' import btn, badge, stat %}`) so markup isn't repeated 30 times.

---

## 2. Phases

### Phase 1 — Foundation (all roles)
`base.html`, `partials/flash.html` (toast → non-auto-dismissing alert for warnings), `errors/error.html`,
`partials/ui.html` macros, header/footer with **logo + "School of Science & Technology"**, favicon.
Definition of done: every page renders inside the new shell without visual breakage; no route changes.

### Phase 2 — Public & Teams
`landing.html` (hero with logo, event dates, single saffron **Register Team** CTA; Registration-Closed state),
`teams/register.html`, `registration_success.html` (team code as a copyable card), `registration_closed.html`,
`results/leaderboard.html`, `results/team_detail.html` (public when published).
Mobile-first: these are the pages students open on phones.

### Phase 3 — Jury
`judge/login.html`, `judge/dashboard.html` (all teams; evaluated/pending filter chips, progress ring),
`judge/evaluate.html` — the most important screen: 6 criteria as cards with 0–10 slider + number input,
live weighted total (existing `/api/evaluations/preview`), comments collapsed, sticky submit bar,
clear **judging-locked** banner. Keyboard-operable; 44 px touch targets.

### Phase 4 — Admin
`admin/base_admin.html` (collapsible sidebar, logo, role chip "Operations"), dashboard (coverage stats),
teams + team_detail, **judges** (tabs All/Internal/External, credentials panel, bulk send),
create_judge (delivery radio group), settings (three switches), evaluations_list, results_overview, audit_logs.
Tables → responsive (stack on mobile), consistent empty states.

### Phase 5 — Super Admin (final)
`super_admin/base_super_admin.html` (same shell, crimson stripe + "Developer" chip), dashboard,
admins (create/deactivate/reset modals), settings (4 switches incl. bulk-send gate), audit_logs.
Deliberately restrained: same components, denser layout, no marketing polish.

### Phase 6 — Cleanup & hardening
Delete `static/css/{base,layout,components,pages,landing,variables,main}.css` once no template references them;
remove inline `style=` blocks; `web-accessibility` pass (WCAG 2.2 AA: contrast on navy/saffron, focus rings,
labels, aria-live for flash); `web-core-web-vitals`/`web-perf` pass (fonts `display=swap`, logo as SVG,
no render-blocking legacy CSS); Playwright screenshot regression of all 29 templates.

---

## 2a. Ease-of-use rules (decided — apply to every phase)

Audience: students registering once on a phone, faculty/industry jury who see the tool for the first time
on event day, an operations team that must not make mistakes under time pressure. Every choice below
optimises for *first use without training*.

| Rule | Concrete decision |
|---|---|
| One primary action per screen | Exactly one saffron button per page (Register / Sign in / Submit evaluation / Save). Everything else is secondary/ghost. |
| Plain language, no jargon | "Sign in" not "Authenticate"; "Score this team" not "Evaluate entity"; "Team code" not "team_code". Error text says what to do next. |
| Show where I am and what's next | Step indicator on registration (Details → Done); progress ring on jury dashboard (3 of 12 scored); breadcrumb in admin. |
| Big, obvious inputs | Score entry = **six large 0–10 number buttons (segmented control)**, not a slider — sliders are imprecise on phones and unclear to first-time jurors. Live total always visible. |
| Never lose work | Evaluate form autosaves to `localStorage` per team; warns before leaving with unsaved scores; "already submitted" state is unmistakable. |
| Confirm only what's destructive | Confirm dialogs for submit-evaluation, lock judging, deactivate, bulk send. No confirms for navigation. |
| Status at a glance | Colour + icon + word together (never colour alone): ✅ Scored · ⏳ Pending · 🔒 Locked. Badges have text. |
| Mobile-first for students & jury | 375 px layouts designed first; tables collapse to cards; 44 px tap targets; sticky bottom submit bar on evaluate. |
| Zero-empty-state confusion | Every empty list explains why and what to do ("No teams yet — registration opens 26 Aug"). |
| Help where the doubt is | Inline helper text under fields (e.g. "Use the email you check daily — your team code is sent there"); a one-line "How judging works: Internal 40 % + External 60 %" on the jury dashboard. |
| Accessibility = usability | WCAG 2.2 AA contrast on navy/saffron, visible focus rings, labels on every input, `aria-live` for flash messages, no information in hover-only tooltips. |
| Consistency | Same shell, same button styles, same table pattern across Teams / Jury / Admin / Super Admin — learn once, use everywhere. |

Per-stakeholder first-screen goals:
- **Student**: lands on `/` → understands event + dates in 5 s → registers in < 2 min → sees team code and knows to save it.
- **Jury**: opens emailed link → signs in → sees list of teams with clear "Score" buttons → scores one team in < 3 min → sees it marked done.
- **Admin**: dashboard answers "how many teams, how many scored, is judging locked, are results published" without clicking.
- **Super Admin**: settings page is a short list of switches with one-line consequences; nothing else competes for attention.

---

## 3. Skills to use (installed in `.claude/skills/`)

| Phase | Skill | Why |
|---|---|---|
| 0–1 | `frontend-design` (built-in), `theme-factory` | lock aesthetic direction + generate the token set once |
| 1–5 | `frontend-design-review` | review each phase's PR against the three pillars before moving on |
| 2–5 | `webapp-testing` / `playwright-interactive` | screenshot every page at 375 / 768 / 1280 px, catch regressions |
| 3 | `web-accessibility` | evaluate form is keyboard/screen-reader critical |
| 6 | `web-core-web-vitals`, `web-perf`, `web-best-practices` | final quality gate |
| any | `brainstorming` before Phase 3's evaluate screen — the one screen worth exploring alternatives for |

---

## 4. Estimated effort (one developer, with Claude)
Phase 1 ½ day · Phase 2 1 day · Phase 3 1 day · Phase 4 1½ days · Phase 5 ½ day · Phase 6 ½ day ≈ **5 days**.
Deploy after each phase; the Vercel preview URL is the review surface.

## 5. Blockers to clear first
1. Official high-res SRHU logo (SVG preferred) → `static/images/srhu-logo.svg`.
2. Confirm accent colour (saffron proposed) — or send a screenshot of srhu.edu.in's header and it will be matched.
3. Commit + push the current staged work so the redesign starts from a deployed baseline.
