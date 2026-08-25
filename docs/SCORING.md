# TechForge 3.0 — How scoring works

## 1. One judge scores one team

Six criteria, each scored **0–10** (whole numbers on the form).

| Criterion | Weight |
|---|---|
| Problem Understanding & Relevance | 15 % |
| Innovation & Differentiation | 15 % |
| Technical Design & Feasibility | 20 % |
| Prototype & Implementation | 25 % |
| Impact, Scalability & Sustainability | 15 % |
| Presentation & Team Response | 10 % |

**Evaluation total (out of 100)** = Σ (criterion score × weight × 10)

Example: 7, 8, 6, 9, 7, 8 → 7×1.5 + 8×1.5 + 6×2.0 + 9×2.5 + 7×1.5 + 8×1.0 = **75.5 / 100**

Rules: every criterion must be scored; a judge can submit **once per team**; submissions are final
(an admin can *reopen* one, then the judge scores again). Nothing can be submitted while judging is locked.

## 2. A team's final score

Only **submitted** evaluations count.

1. Average the evaluation totals of all **internal** judges → *Internal average*
2. Average the evaluation totals of all **external** judges → *External average*
3. **Final score = Internal average × 40 % + External average × 60 %**

Example: internal judges gave 75.5 and 80.5 (avg 78.0); one external judge gave 70.0
→ 78.0 × 0.4 + 70.0 × 0.6 = **73.2 / 100**

A team is **complete** only when it has at least one internal *and* one external evaluation.
An incomplete team still shows a number, but it isn't comparable (a missing jury side counts as 0).

## 3. Ranking

Teams are ordered by:

1. **Complete** teams first, incomplete teams below them (shown with rank `-`)
2. **Final score**, highest first
3. Tie → higher average **Prototype & Implementation** score (0–10, all judges)
4. Still tied → higher average **Technical Design & Feasibility**
5. Still tied → higher average **Innovation & Differentiation**
6. Still tied → order of registration (no shared ranks)

Ranks are 1, 2, 3… for complete teams only. Medals on the leaderboard are the top three complete teams.

## 4. What the CSV export contains

`Admin → Export results (CSV)` writes exactly the ranking above, one row per team that has at least one evaluation:

Rank · Team Code · Team Name · Leader · Internal Average · External Average · Final Score · Internal Evaluations · External Evaluations · Stage

## 5. Who sees what, when

- **Judges** see their own scoring status (scored / to score) on their dashboard, never other judges' numbers.
- **Admins / Super Admin** see live rankings at any time (`Admin → Rankings`).
- The **leaderboard** (`/results/leaderboard`) requires sign-in and is visible to admins **and judges**, at all times.
- Students and the public cannot see any scores; there is no public results page.

> ⚠️ **Known gap:** the **Publish results** switch is stored and shown as a status badge, but nothing currently
> reads it — the leaderboard is not hidden while results are unpublished, and it is not opened to the public when
> they are. If you want publish/unpublish to control visibility (e.g. hide from judges until published, or open a
> public page after publishing), that is a small follow-up change in `routes/results.py`.

## 6. Where this lives in the code

- Weights & criteria: `config/__init__.py` (`EVALUATION_CRITERIA`), `services/scoring.py` (`OFFICIAL_CRITERIA`, `calculate_weighted_score`)
- Team score & ranking: `services/results_calculator.py` (`calculate_team_score`, `calculate_all_teams_scores`)
- CSV: `routes/admin.py` (`export_results`)
