# Query & Cold-Start Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cut MongoDB round-trips on the hot pages (leaderboard, judge dashboard, admin lists) from O(teams × judges) to a constant handful, shrink serverless cold-start work, and make static assets cacheable — while fixing the three scoring bugs the rewrite touches.

**Architecture:** Pull the arithmetic in `services/results_calculator.py` into pure functions that take already-fetched documents, so one batch query per collection feeds every team. Add a tiny `utils/lookups.py` for `$in` batch lookups and a per-request `event_settings` cache on `flask.g`. Gate index creation behind an env flag / `init_db.py`, tune the `MongoClient` pool for serverless, and give static files long cache headers with content-hash cache-busting.

**Tech Stack:** Python 3.13, Flask 3.x, PyMongo 4.x, pytest 8 (already installed). No new dependencies. Unit tests use `unittest.mock.patch` on the `models.database.get_*_collection` getters — **no live MongoDB is required for any test in this plan.**

**Spec:** This plan is its own spec — there is no separate design doc. The requirements are the findings listed under "Baseline findings" below; each task cites the one it fixes.

## Global Constraints

- Do not change any URL, template variable name, or session key that templates already read (`team.evaluated`, `stats.*`, `coverage.*`, `rankings`, `judge_type_display`, etc.).
- Preserve the official scoring rules: 6 criteria weights (0.15/0.15/0.20/0.25/0.15/0.10), weighted total on 0–100, final = internal×0.40 + external×0.60, tie-break order complete → final_score → prototype_avg → technical_avg → innovation_avg, rank `'-'` for incomplete teams.
- Judge type is stored inconsistently in the DB (`'internal'`, `'INTERNAL_JUDGE'`, `'external'`, `'EXTERNAL_JUDGE'`). Every classification in this plan MUST go through `normalize_judge_type()` (Task 1). Rule: the string contains `'external'` (case-insensitive) → `'external'`, otherwise `'internal'` (same rule `routes/admin.py::judges_list` already uses).
- `team_id` and `judge_id` are stored as **strings** in `evaluations`; `_id` in `teams`/`users` is an `ObjectId`. Convert with `str()` / `ObjectId()` exactly where shown.
- Tests run from the repo root with `python -m pytest tests/<file> -v`. New test files must not import `app` (that requires `MONGO_URI`).
- Commit after every task with the message shown. Do not commit `.env`.

## Baseline findings (what we are fixing)

| # | Location | Problem | Fixed in |
|---|----------|---------|----------|
| F1 | `services/results_calculator.py::calculate_all_teams_scores` | For T teams: 1 `teams.find()` + T × `evaluations.find()` + (T×J) × `judges.find_one()`. Called by `/results/leaderboard`, `/admin/results-overview`, `/admin/export/results`, and **twice** by `/results/team/<id>`. | Task 1 |
| F2 | `results_calculator.py::calculate_team_score` line `if judge['judge_type'] == 'internal'` | Judges are stored as `'INTERNAL_JUDGE'` → every judge counted as external → `internal_average` always 0 and every team `INCOMPLETE`. **Correctness bug.** | Task 1 |
| F3 | `results_calculator.py::get_team_detailed_result` | Uses `get_users_collection()` which is never imported → `NameError` on `/results/team/<id>`. **Correctness bug.** | Task 1 |
| F4 | `results_calculator.py::get_evaluation_coverage` | Loops every submitted evaluation and does one `judges.find_one()` each. Runs on admin dashboard, super-admin dashboard, leaderboard, results overview. | Task 2 |
| F5 | `routes/judge.py::dashboard` | One `check_evaluation_exists()` query per team although `eval_map` already has the answer; reads `weighted_score`/`total_score` but the doc field is `weighted_total`, so `avg_score` is always 0.0. | Task 3 |
| F6 | `routes/admin.py::judges_list`, `evaluations_list`, `audit_logs`; `routes/super_admin.py::dashboard` | One `users.find_one()` / `teams.find_one()` per row. | Task 4 |
| F7 | `app.py::inject_globals` → `is_registration_open()`; `checkpoint_manager.get_judging_status`; admin routes | `event_settings` is read 1–3 times per request, on every page including 404s. | Task 5 |
| F8 | `models/database.py::initialize` | Every process start does `ping` + 22 `create_index` calls. On Vercel that is every cold start. No pool sizing. | Task 6 |
| F9 | `templates/base.html`, Flask static defaults | CSS/JS served with default `max-age` (Flask 3 default: no cache) and no cache-buster, so every page load re-fetches `main.css`, `app.css`, `main.js`. | Task 7 |

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `services/results_calculator.py` | Modify | Pure aggregation (`normalize_judge_type`, `aggregate_team_scores`, `rank_results`) + batch loaders (`load_judge_types`, `load_submitted_evaluations`). Public function names/signatures stay compatible. |
| `utils/lookups.py` | Create | `fetch_users_by_ids`, `fetch_teams_by_ids`, `fetch_judges_by_user_ids` — one `$in` query each, returns `dict[str, doc]`. |
| `services/settings.py` | Create | `get_event_settings()` cached on `flask.g` per request; `invalidate_event_settings()`. |
| `routes/judge.py` | Modify | Dashboard uses `eval_map` only; correct score key. |
| `routes/admin.py` | Modify | Batch lookups in three list views; use settings cache. |
| `routes/super_admin.py` | Modify | Batch actor lookup on dashboard. |
| `routes/teams.py` | Modify | `is_registration_open()` reads the cached settings. |
| `services/checkpoint_manager.py` | Modify | `get_judging_status()` reads cached settings; lock/unlock invalidate. |
| `app.py` | Modify | Static cache config, `static_url` template global. |
| `models/database.py` | Modify | Pool options; `ensure_indexes()` gated by env; no startup ping. |
| `init_db.py` | Modify | Calls `Database.ensure_indexes()` explicitly. |
| `.env.example` | Modify | Document `MONGO_ENSURE_INDEXES`. |
| `tests/test_results_aggregation.py` | Create | Pure-function tests for Task 1 + 2. |
| `tests/test_lookups.py` | Create | Task 4 helper tests (mocked collections). |
| `tests/test_settings_cache.py` | Create | Task 5 tests (bare Flask app, mocked collection). |
| `tests/test_database_init.py` | Create | Task 6 tests (mocked `MongoClient`). |
| `tests/test_static_cache.py` | Create | Task 7 tests (bare Flask app). |

---

### Task 1: Batch the leaderboard calculation and fix judge-type classification

**Fixes:** F1, F2, F3

**Files:**
- Modify: `services/results_calculator.py` (whole file rewritten below; public names preserved)
- Test: `tests/test_results_aggregation.py`

**Interfaces:**
- Consumes: `models.database.get_teams_collection / get_evaluations_collection / get_judges_collection / get_team_results_collection / get_users_collection`, `services.audit.log_audit` (unchanged).
- Produces (used by Tasks 2, 3, 4):
  - `normalize_judge_type(raw: str | None) -> str` — returns `'external'` or `'internal'`.
  - `load_judge_types(judges_col=None) -> dict[str, str]` — `{user_id: 'internal'|'external'}` in ONE query.
  - `load_submitted_evaluations(stage_id, evaluations_col=None) -> dict[str, list[dict]]` — `{team_id: [evaluation, ...]}` in ONE query.
  - `aggregate_team_scores(team_id: str, stage_id: str, evaluations: list[dict], judge_types: dict[str, str]) -> dict` — pure; same return shape `calculate_team_score` has today (keys `final_score`, `internal_average`, `external_average`, `internal_count`, `external_count`, `total_evaluations`, `is_complete`, `status`, `prototype_avg`, `technical_avg`, `innovation_avg`, `internal_details`, `external_details`, `internal_weight`, `external_weight`, `calculated_at`, `team_id`, `stage_id`) or `{'error': ..., 'final_score': 0, 'evaluations_count': 0}` when `evaluations` is empty.
  - `rank_results(results: list[dict]) -> list[dict]` — pure; sorts by the official tie-break and assigns `rank` (int or `'-'`).
  - `calculate_team_score(team_id, stage_id='final_presentation', evaluations=None, judge_types=None)` — same name as today; extra optional args let callers pass pre-fetched data.
  - `calculate_all_teams_scores(stage_id='final_presentation')`, `get_leaderboard(stage_id, limit=None)`, `get_team_detailed_result(team_id, stage_id)`, `save_team_result(...)`, `recalculate_all_results(...)`, `get_evaluation_coverage()` — unchanged signatures.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_results_aggregation.py`:

```python
"""Pure-function tests for services.results_calculator — no MongoDB needed."""
from datetime import datetime

import pytest

from services.results_calculator import (
    normalize_judge_type,
    aggregate_team_scores,
    rank_results,
)


def _ev(judge_id, total, prototype=8.0, technical=8.0, innovation=8.0):
    return {
        'judge_id': judge_id,
        'team_id': 'team-1',
        'stage_id': 'final_presentation',
        'status': 'submitted',
        'weighted_total': total,
        'submitted_at': datetime(2026, 8, 25, 10, 0, 0),
        'raw_scores': {
            'prototype': prototype,
            'technical_design': technical,
            'innovation': innovation,
        },
    }


@pytest.mark.parametrize('raw,expected', [
    ('internal', 'internal'),
    ('INTERNAL_JUDGE', 'internal'),
    ('external', 'external'),
    ('EXTERNAL_JUDGE', 'external'),
    ('External Jury', 'external'),
    (None, 'internal'),
    ('', 'internal'),
])
def test_normalize_judge_type(raw, expected):
    assert normalize_judge_type(raw) == expected


def test_aggregate_returns_error_when_no_evaluations():
    result = aggregate_team_scores('team-1', 'final_presentation', [], {})
    assert result['error'] == 'No evaluations found for this team'
    assert result['final_score'] == 0
    assert result['evaluations_count'] == 0


def test_aggregate_applies_40_60_weighting_with_db_style_judge_types():
    judge_types = {'j-int': 'internal', 'j-ext': 'external'}
    evaluations = [_ev('j-int', 80.0), _ev('j-ext', 90.0)]

    result = aggregate_team_scores('team-1', 'final_presentation', evaluations, judge_types)

    assert result['internal_average'] == 80.0
    assert result['external_average'] == 90.0
    assert result['final_score'] == 86.0          # 80*0.4 + 90*0.6
    assert result['internal_count'] == 1
    assert result['external_count'] == 1
    assert result['total_evaluations'] == 2
    assert result['is_complete'] is True
    assert result['status'] == 'COMPLETE'
    assert result['team_id'] == 'team-1'
    assert result['stage_id'] == 'final_presentation'
    assert [d['judge_id'] for d in result['internal_details']] == ['j-int']
    assert [d['judge_id'] for d in result['external_details']] == ['j-ext']


def test_aggregate_marks_incomplete_when_only_one_side_scored():
    result = aggregate_team_scores('team-1', 'final_presentation',
                                   [_ev('j-int', 70.0)], {'j-int': 'internal'})
    assert result['is_complete'] is False
    assert result['status'] == 'INCOMPLETE'
    assert result['external_average'] == 0
    assert result['final_score'] == 28.0          # 70*0.4 + 0*0.6


def test_aggregate_skips_evaluations_from_unknown_judges():
    result = aggregate_team_scores('team-1', 'final_presentation',
                                   [_ev('ghost', 100.0), _ev('j-ext', 60.0)],
                                   {'j-ext': 'external'})
    assert result['internal_count'] == 0
    assert result['external_count'] == 1
    assert result['external_average'] == 60.0


def test_aggregate_computes_criterion_averages_and_ignores_bad_values():
    evaluations = [
        _ev('j1', 80.0, prototype=9.0, technical=7.0, innovation=6.0),
        _ev('j2', 80.0, prototype=7.0, technical='n/a', innovation=8.0),
    ]
    result = aggregate_team_scores('team-1', 'final_presentation', evaluations,
                                   {'j1': 'internal', 'j2': 'external'})
    assert result['prototype_avg'] == 8.0
    assert result['technical_avg'] == 7.0        # 'n/a' skipped
    assert result['innovation_avg'] == 7.0


def _row(name, final, proto=8.0, tech=8.0, innov=8.0, complete=True):
    return {'team_name': name, 'final_score': final, 'prototype_avg': proto,
            'technical_avg': tech, 'innovation_avg': innov, 'is_complete': complete}


def test_rank_results_official_tiebreak_and_incomplete_dash():
    rows = [
        _row('Beta', 85.0, proto=8.5),
        _row('Alpha', 85.0, proto=9.0),
        _row('Gamma', 99.0, complete=False),
        _row('Delta', 70.0),
    ]
    ranked = rank_results(rows)
    assert [r['team_name'] for r in ranked] == ['Alpha', 'Beta', 'Delta', 'Gamma']
    assert [r['rank'] for r in ranked] == [1, 2, 3, '-']
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_results_aggregation.py -v`
Expected: FAIL at import — `ImportError: cannot import name 'normalize_judge_type' from 'services.results_calculator'`

- [ ] **Step 3: Rewrite `services/results_calculator.py`**

Replace the entire file with:

```python
"""
Results Calculator Service
Calculates final scores with Internal 40% + External 60% weighting.

Design: the arithmetic lives in pure functions (`aggregate_team_scores`,
`rank_results`) that take already-fetched documents. The loaders
(`load_judge_types`, `load_submitted_evaluations`) each issue exactly ONE
query, so building the whole leaderboard costs 3 round-trips regardless of
how many teams or judges exist.
"""

from collections import defaultdict
from datetime import datetime
from bson.objectid import ObjectId

from models.database import (
    get_teams_collection,
    get_evaluations_collection,
    get_judges_collection,
    get_team_results_collection,
    get_users_collection,
)
from services.audit import log_audit


# Official TechForge 3.0 Scoring Weights
INTERNAL_WEIGHT = 0.40
EXTERNAL_WEIGHT = 0.60

DEFAULT_STAGE = 'final_presentation'


# --------------------------------------------------------------------------
# Pure helpers (no database access)
# --------------------------------------------------------------------------

def normalize_judge_type(raw):
    """Map any stored judge_type ('internal', 'INTERNAL_JUDGE', 'External Jury', None…)
    to exactly 'internal' or 'external'."""
    return 'external' if 'external' in str(raw or '').lower() else 'internal'


def _avg(values):
    return sum(values) / len(values) if values else 0


def _float_or_none(value):
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def aggregate_team_scores(team_id, stage_id, evaluations, judge_types):
    """
    Pure aggregation for one team.

    Args:
        team_id: team id as string
        stage_id: stage identifier
        evaluations: list of submitted evaluation documents for this team/stage
        judge_types: {judge user_id (str): 'internal' | 'external'}

    Returns:
        dict with the full score breakdown, or an error dict when there are no evaluations.
    """
    if not evaluations:
        return {
            'error': 'No evaluations found for this team',
            'final_score': 0,
            'evaluations_count': 0,
        }

    internal_scores, external_scores = [], []
    internal_details, external_details = [], []
    prototype_scores, technical_scores, innovation_scores = [], [], []

    for evaluation in evaluations:
        judge_type = judge_types.get(evaluation['judge_id'])
        if judge_type is None:
            continue  # evaluation from a judge that no longer exists

        detail = {
            'judge_id': evaluation['judge_id'],
            'weighted_total': evaluation['weighted_total'],
            'submitted_at': evaluation['submitted_at'],
        }
        if judge_type == 'internal':
            internal_scores.append(evaluation['weighted_total'])
            internal_details.append(detail)
        else:
            external_scores.append(evaluation['weighted_total'])
            external_details.append(detail)

        raw = evaluation.get('raw_scores', {})
        for key, bucket in (('prototype', prototype_scores),
                            ('technical_design', technical_scores),
                            ('innovation', innovation_scores)):
            value = _float_or_none(raw.get(key))
            if value is not None:
                bucket.append(value)

    internal_avg = _avg(internal_scores)
    external_avg = _avg(external_scores)
    is_complete = bool(internal_scores) and bool(external_scores)
    final_score = internal_avg * INTERNAL_WEIGHT + external_avg * EXTERNAL_WEIGHT

    return {
        'team_id': str(team_id),
        'stage_id': stage_id,
        'final_score': round(final_score, 2),
        'internal_average': round(internal_avg, 2),
        'external_average': round(external_avg, 2),
        'internal_count': len(internal_scores),
        'external_count': len(external_scores),
        'total_evaluations': len(evaluations),
        'is_complete': is_complete,
        'status': 'COMPLETE' if is_complete else 'INCOMPLETE',
        'prototype_avg': round(_avg(prototype_scores), 2),
        'technical_avg': round(_avg(technical_scores), 2),
        'innovation_avg': round(_avg(innovation_scores), 2),
        'internal_details': internal_details,
        'external_details': external_details,
        'internal_weight': INTERNAL_WEIGHT,
        'external_weight': EXTERNAL_WEIGHT,
        'calculated_at': datetime.utcnow(),
    }


def rank_results(results):
    """
    Sort in place by the official tie-break order and assign `rank`.

    Order: complete first, then final_score, prototype_avg, technical_avg,
    innovation_avg — all descending. Incomplete teams get rank '-'.
    """
    results.sort(key=lambda x: (
        1 if x['is_complete'] else 0,
        x['final_score'],
        x['prototype_avg'],
        x['technical_avg'],
        x['innovation_avg'],
    ), reverse=True)

    rank_counter = 1
    for result in results:
        if result['is_complete']:
            result['rank'] = rank_counter
            rank_counter += 1
        else:
            result['rank'] = '-'
    return results


# --------------------------------------------------------------------------
# Batch loaders (exactly one query each)
# --------------------------------------------------------------------------

def load_judge_types(judges_col=None):
    """{judge user_id: 'internal' | 'external'} for every judge — one query."""
    judges_col = judges_col if judges_col is not None else get_judges_collection()
    return {
        judge['user_id']: normalize_judge_type(judge.get('judge_type'))
        for judge in judges_col.find({}, {'user_id': 1, 'judge_type': 1})
        if judge.get('user_id')
    }


def load_submitted_evaluations(stage_id=DEFAULT_STAGE, evaluations_col=None):
    """{team_id: [evaluation, ...]} for all submitted evaluations of a stage — one query."""
    evaluations_col = evaluations_col if evaluations_col is not None else get_evaluations_collection()
    grouped = defaultdict(list)
    for evaluation in evaluations_col.find({'stage_id': stage_id, 'status': 'submitted'}):
        grouped[evaluation['team_id']].append(evaluation)
    return grouped


# --------------------------------------------------------------------------
# Public API (signatures preserved)
# --------------------------------------------------------------------------

def calculate_team_score(team_id, stage_id=DEFAULT_STAGE, evaluations=None, judge_types=None):
    """
    Calculate the final score for one team.

    `evaluations` / `judge_types` may be passed by callers that already hold
    them (leaderboard); when omitted they are fetched (2 queries).
    """
    team_id = str(team_id)
    if evaluations is None:
        evaluations = list(get_evaluations_collection().find({
            'team_id': team_id,
            'stage_id': stage_id,
            'status': 'submitted',
        }))
    if judge_types is None:
        judge_types = load_judge_types()
    return aggregate_team_scores(team_id, stage_id, evaluations, judge_types)


def _team_row(team, score):
    return {
        'team_id': str(team['_id']),
        'team_code': team.get('team_code', ''),
        'team_name': team.get('team_name', ''),
        'leader_name': team.get('leader_name', ''),
        'theme_name': team.get('theme_name', ''),
        'final_score': score['final_score'],
        'internal_average': score['internal_average'],
        'external_average': score['external_average'],
        'internal_count': score['internal_count'],
        'external_count': score['external_count'],
        'total_evaluations': score['total_evaluations'],
        'is_complete': score['is_complete'],
        'status': score['status'],
        'prototype_avg': score['prototype_avg'],
        'technical_avg': score['technical_avg'],
        'innovation_avg': score['innovation_avg'],
    }


def calculate_all_teams_scores(stage_id=DEFAULT_STAGE):
    """
    Ranked results for every team that has at least one submitted evaluation.
    Exactly 3 queries: teams, evaluations, judges.
    """
    by_team = load_submitted_evaluations(stage_id)
    if not by_team:
        return []

    judge_types = load_judge_types()
    teams = get_teams_collection().find(
        {'_id': {'$in': [ObjectId(tid) for tid in by_team if ObjectId.is_valid(tid)]}},
        {'team_code': 1, 'team_name': 1, 'leader_name': 1, 'theme_name': 1},
    )

    results = []
    for team in teams:
        score = aggregate_team_scores(str(team['_id']), stage_id, by_team[str(team['_id'])], judge_types)
        if not score.get('error'):
            results.append(_team_row(team, score))

    return rank_results(results)


def save_team_result(team_id, stage_id=DEFAULT_STAGE, actor_id=None, evaluations=None, judge_types=None):
    """Calculate and upsert one team's result document."""
    results_col = get_team_results_collection()

    score_result = calculate_team_score(team_id, stage_id, evaluations=evaluations, judge_types=judge_types)
    if score_result.get('error'):
        return score_result

    updated = results_col.find_one_and_update(
        {'team_id': str(team_id), 'stage_id': stage_id},
        {'$set': score_result},
        upsert=True,
        return_document=True,
        projection={'_id': 1},
    )
    result_id = updated['_id']

    log_audit(actor_id, 'result_calculated', 'result', str(result_id),
              {'team_id': str(team_id), 'final_score': score_result['final_score']})

    return {'success': True, 'result_id': str(result_id), 'final_score': score_result['final_score']}


def recalculate_all_results(stage_id=DEFAULT_STAGE, actor_id=None):
    """Recalculate and save results for all teams (3 reads + 1 write per team)."""
    all_teams = list(get_teams_collection().find({}, {'team_name': 1}))
    by_team = load_submitted_evaluations(stage_id)
    judge_types = load_judge_types()

    successful, failed, errors = 0, 0, []
    for team in all_teams:
        tid = str(team['_id'])
        result = save_team_result(tid, stage_id, actor_id,
                                  evaluations=by_team.get(tid, []), judge_types=judge_types)
        if result.get('success'):
            successful += 1
        else:
            failed += 1
            errors.append(f"{team.get('team_name', tid)}: {result.get('error')}")

    return {'total_teams': len(all_teams), 'successful': successful, 'failed': failed, 'errors': errors}


def get_leaderboard(stage_id=DEFAULT_STAGE, limit=None):
    results = calculate_all_teams_scores(stage_id)
    return results[:limit] if limit else results


def get_team_detailed_result(team_id, stage_id=DEFAULT_STAGE):
    """Detailed breakdown for one team, including judge names. 4 queries."""
    team = get_teams_collection().find_one({'_id': ObjectId(team_id)})
    if not team:
        return {'error': 'Team not found'}

    evaluations = list(get_evaluations_collection().find({
        'team_id': str(team_id), 'stage_id': stage_id, 'status': 'submitted',
    }))
    judge_types = load_judge_types()

    score_result = aggregate_team_scores(str(team_id), stage_id, evaluations, judge_types)
    if score_result.get('error'):
        return score_result

    judge_ids = [ObjectId(e['judge_id']) for e in evaluations if ObjectId.is_valid(e['judge_id'])]
    users_by_id = {
        str(u['_id']): u
        for u in get_users_collection().find({'_id': {'$in': judge_ids}}, {'name': 1})
    }

    detailed_evaluations = []
    for evaluation in evaluations:
        user = users_by_id.get(evaluation['judge_id'])
        judge_type = judge_types.get(evaluation['judge_id'])
        if user and judge_type:
            detailed_evaluations.append({
                'judge_name': user['name'],
                'judge_type': judge_type,
                'weighted_total': evaluation['weighted_total'],
                'raw_scores': evaluation.get('raw_scores', {}),
                'comments': evaluation.get('comments', {}),
                'submitted_at': evaluation['submitted_at'],
            })

    return {
        'team': team,
        'score_result': score_result,
        'evaluations': detailed_evaluations,
        'leaderboard_position': None,
    }


def get_evaluation_coverage():
    """Coverage statistics — replaced in Task 2 (kept here so the module imports)."""
    teams_col = get_teams_collection()
    evaluations_col = get_evaluations_collection()
    judges_col = get_judges_collection()

    total_teams = teams_col.count_documents({})
    total_judges = judges_col.count_documents({})
    total_evaluations = evaluations_col.count_documents({'status': 'submitted'})

    teams_evaluated = len(evaluations_col.distinct('team_id'))
    teams_pending = total_teams - teams_evaluated

    judge_types = load_judge_types()
    internal_evaluations = external_evaluations = 0
    for ev in evaluations_col.find({'status': 'submitted'}, {'judge_id': 1}):
        judge_type = judge_types.get(ev.get('judge_id'))
        if judge_type == 'internal':
            internal_evaluations += 1
        elif judge_type == 'external':
            external_evaluations += 1

    completion_percentage = (teams_evaluated / total_teams * 100) if total_teams > 0 else 0

    return {
        'total_teams': total_teams,
        'teams_evaluated': teams_evaluated,
        'teams_pending': teams_pending,
        'total_judges': total_judges,
        'total_evaluations': total_evaluations,
        'internal_evaluations': internal_evaluations,
        'external_evaluations': external_evaluations,
        'completion_percentage': round(completion_percentage, 2),
    }
```

Note on `judge_type` in `get_team_detailed_result`: the template previously received the raw stored value (e.g. `'INTERNAL_JUDGE'`); it now receives `'internal'`/`'external'`. Check `templates/results/team_detail.html` — if it compares against `'INTERNAL_JUDGE'`, change that comparison to `'internal'`. Run `grep -n "judge_type" templates/results/team_detail.html` and update any literal.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_results_aggregation.py -v`
Expected: 13 passed (7 parametrized `normalize_judge_type` cases + 6 others).

Also run the existing pure test file to be sure nothing regressed:
Run: `python -m pytest tests/test_all_flows.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add services/results_calculator.py tests/test_results_aggregation.py templates/results/team_detail.html
git commit -m "perf(results): batch leaderboard queries to 3 round-trips; fix judge-type classification and missing import"
```

---

### Task 2: Make `get_evaluation_coverage` two fixed queries

**Fixes:** F4

**Files:**
- Modify: `services/results_calculator.py` (function `get_evaluation_coverage` only)
- Test: `tests/test_results_aggregation.py` (append)

**Interfaces:**
- Consumes: `load_judge_types` (Task 1).
- Produces: `summarize_coverage(total_teams, total_judges, submitted_evaluations, judge_types) -> dict` — pure, same keys as `get_evaluation_coverage` returns today. `get_evaluation_coverage()` becomes a thin wrapper.

Current cost after Task 1: 3 `count_documents` + 1 `distinct` + 1 judges find + 1 evaluations find = 6 queries. Target: 4 queries (2 counts, 1 judges find, 1 evaluations find with projection), and the loop work moves into a pure function that is tested.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_results_aggregation.py`:

```python
from services.results_calculator import summarize_coverage


def test_summarize_coverage_counts_teams_and_judge_sides():
    submitted = [
        {'team_id': 't1', 'judge_id': 'j-int'},
        {'team_id': 't1', 'judge_id': 'j-ext'},
        {'team_id': 't2', 'judge_id': 'j-int'},
        {'team_id': 't3', 'judge_id': 'ghost'},   # judge deleted → not counted per side
    ]
    judge_types = {'j-int': 'internal', 'j-ext': 'external'}

    cov = summarize_coverage(total_teams=4, total_judges=2,
                             submitted_evaluations=submitted, judge_types=judge_types)

    assert cov == {
        'total_teams': 4,
        'teams_evaluated': 3,
        'teams_pending': 1,
        'total_judges': 2,
        'total_evaluations': 4,
        'internal_evaluations': 2,
        'external_evaluations': 1,
        'completion_percentage': 75.0,
    }


def test_summarize_coverage_handles_zero_teams():
    cov = summarize_coverage(0, 0, [], {})
    assert cov['completion_percentage'] == 0
    assert cov['teams_pending'] == 0
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_results_aggregation.py -k coverage -v`
Expected: FAIL — `ImportError: cannot import name 'summarize_coverage'`

- [ ] **Step 3: Replace `get_evaluation_coverage` in `services/results_calculator.py`**

Delete the existing `get_evaluation_coverage` function (the last one in the file) and add:

```python
def summarize_coverage(total_teams, total_judges, submitted_evaluations, judge_types):
    """Pure coverage summary from already-fetched data."""
    teams_evaluated = len({ev['team_id'] for ev in submitted_evaluations})
    internal_evaluations = external_evaluations = 0
    for ev in submitted_evaluations:
        judge_type = judge_types.get(ev.get('judge_id'))
        if judge_type == 'internal':
            internal_evaluations += 1
        elif judge_type == 'external':
            external_evaluations += 1

    completion_percentage = (teams_evaluated / total_teams * 100) if total_teams > 0 else 0
    return {
        'total_teams': total_teams,
        'teams_evaluated': teams_evaluated,
        'teams_pending': max(0, total_teams - teams_evaluated),
        'total_judges': total_judges,
        'total_evaluations': len(submitted_evaluations),
        'internal_evaluations': internal_evaluations,
        'external_evaluations': external_evaluations,
        'completion_percentage': round(completion_percentage, 2),
    }


def get_evaluation_coverage():
    """Coverage statistics — 4 queries total."""
    submitted = list(get_evaluations_collection().find(
        {'status': 'submitted'}, {'team_id': 1, 'judge_id': 1}))
    return summarize_coverage(
        total_teams=get_teams_collection().count_documents({}),
        total_judges=get_judges_collection().count_documents({}),
        submitted_evaluations=submitted,
        judge_types=load_judge_types(),
    )
```

Behaviour note: `teams_evaluated` now counts teams with a **submitted** evaluation (the old `distinct('team_id')` also counted reopened ones). This matches the label "teams evaluated" and the `evaluations_completed` stat shown next to it.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_results_aggregation.py -v`
Expected: all passed (15).

- [ ] **Step 5: Commit**

```bash
git add services/results_calculator.py tests/test_results_aggregation.py
git commit -m "perf(results): compute evaluation coverage from a single projected query"
```

---

### Task 3: Judge dashboard — zero per-team queries, correct average

**Fixes:** F5

**Files:**
- Modify: `routes/judge.py:66-140` (`dashboard` function body)
- Test: `tests/test_judge_dashboard_summary.py`

**Interfaces:**
- Produces: `summarize_judge_progress(teams: list[dict], evaluations: list[dict]) -> tuple[int, int, float]` in `routes/judge.py` — pure; mutates each team dict to set `team['evaluated']`; returns `(completed, pending, avg_score)`. Template keys `team.evaluated`, `evaluations_count`, `pending_count`, `avg_score` are unchanged.

- [ ] **Step 1: Write the failing test**

Create `tests/test_judge_dashboard_summary.py`:

```python
"""Pure test for the judge dashboard progress summary — no DB, no app."""
from bson.objectid import ObjectId

from routes.judge import summarize_judge_progress


def test_summarize_judge_progress_flags_teams_and_averages_weighted_total():
    t1, t2, t3 = ObjectId(), ObjectId(), ObjectId()
    teams = [{'_id': t1}, {'_id': t2}, {'_id': t3}]
    evaluations = [
        {'team_id': str(t1), 'weighted_total': 80.0},
        {'team_id': str(t3), 'weighted_total': 70.0},
    ]

    completed, pending, avg = summarize_judge_progress(teams, evaluations)

    assert completed == 2
    assert pending == 1
    assert avg == 75.0
    assert [t['evaluated'] for t in teams] == [True, False, True]


def test_summarize_judge_progress_with_no_evaluations():
    teams = [{'_id': ObjectId()}]
    completed, pending, avg = summarize_judge_progress(teams, [])
    assert (completed, pending, avg) == (0, 1, 0.0)
    assert teams[0]['evaluated'] is False
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_judge_dashboard_summary.py -v`
Expected: FAIL — `ImportError: cannot import name 'summarize_judge_progress'`

(`routes/judge.py` imports `routes.auth`, `models.database`, `services.*` — none touch the DB at import time, so this import is safe without `MONGO_URI`.)

- [ ] **Step 3: Add the helper and use it in `dashboard`**

In `routes/judge.py`, add above `judge_bp = Blueprint(...)`:

```python
def summarize_judge_progress(teams, evaluations):
    """
    Mark each team with `evaluated` and return (completed, pending, avg_score)
    using only the judge's already-fetched evaluations — no extra queries.
    """
    eval_map = {str(e.get('team_id')): e for e in evaluations}
    completed = 0
    total = 0.0
    for team in teams:
        ev = eval_map.get(str(team['_id']))
        team['evaluated'] = ev is not None
        if ev is not None:
            completed += 1
            total += float(ev.get('weighted_total') or 0)
    pending = max(0, len(teams) - completed)
    avg_score = round(total / completed, 1) if completed else 0.0
    return completed, pending, avg_score
```

Then in `dashboard()`, replace everything from `# 2. Every registered team is open to every judge` down to (and including) the line `avg_score = round(...)` with:

```python
    # 2. Every registered team is open to every judge
    all_teams = list(get_teams_collection().find().sort('team_name', 1))

    # 3. This judge's submitted evaluations (one query) drive every per-team flag
    evaluations = get_judge_evaluations(user_id, stage_id='final_presentation')
    completed_evals, pending_evals, avg_score = summarize_judge_progress(all_teams, evaluations)
```

Remove `check_evaluation_exists` from the `from services.scoring import (...)` list in `routes/judge.py` **only if** it is no longer referenced — it is still used in `evaluate_team`, so keep the import.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_judge_dashboard_summary.py -v`
Expected: 2 passed.

Manual check (needs a running DB): log in as a judge, open `/judge/dashboard`, confirm evaluated teams show as evaluated and "Average score" is non-zero once you have submitted one.

- [ ] **Step 5: Commit**

```bash
git add routes/judge.py tests/test_judge_dashboard_summary.py
git commit -m "perf(judge): build dashboard progress from one evaluations query; fix average using weighted_total"
```

---

### Task 4: Batch lookups for admin & super-admin list pages

**Fixes:** F6

**Files:**
- Create: `utils/lookups.py`
- Modify: `routes/admin.py` (`judges_list`, `audit_logs`, `evaluations_list`, `send_credentials_all`)
- Modify: `routes/super_admin.py` (`dashboard` recent-logs loop)
- Test: `tests/test_lookups.py`

**Interfaces:**
- Produces (`utils/lookups.py`):
  - `to_object_ids(ids: Iterable) -> list[ObjectId]` — drops values that are not valid ObjectIds.
  - `fetch_users_by_ids(ids, projection=None) -> dict[str, dict]` — one `users.find({'_id': {'$in': ...}})`.
  - `fetch_teams_by_ids(ids, projection=None) -> dict[str, dict]` — same for `teams`.
  - `fetch_judges_by_user_ids(user_ids) -> dict[str, dict]` — one `judges.find({'user_id': {'$in': [...]}})`, keyed by `user_id`.
  - `actor_name_map(actor_ids) -> dict[str, str]` — `{actor_id: name}`; missing → not present (callers default to `'Unknown'` / `'System'`).
- Consumes: `models.database.get_users_collection / get_teams_collection / get_judges_collection`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_lookups.py`:

```python
"""utils.lookups tests — collections are mocked, no MongoDB needed."""
from unittest.mock import MagicMock, patch

from bson.objectid import ObjectId

import utils.lookups as lookups


def test_to_object_ids_drops_invalid_values():
    valid = ObjectId()
    assert lookups.to_object_ids([str(valid), 'nope', None, valid]) == [valid, valid]


def test_fetch_users_by_ids_issues_one_in_query_and_keys_by_str_id():
    u1, u2 = ObjectId(), ObjectId()
    users_col = MagicMock()
    users_col.find.return_value = [{'_id': u1, 'name': 'A'}, {'_id': u2, 'name': 'B'}]

    with patch.object(lookups, 'get_users_collection', return_value=users_col):
        result = lookups.fetch_users_by_ids([str(u1), str(u2), 'garbage'], projection={'name': 1})

    users_col.find.assert_called_once_with({'_id': {'$in': [u1, u2]}}, {'name': 1})
    assert result == {str(u1): {'_id': u1, 'name': 'A'}, str(u2): {'_id': u2, 'name': 'B'}}


def test_fetch_users_by_ids_with_no_valid_ids_skips_the_query():
    users_col = MagicMock()
    with patch.object(lookups, 'get_users_collection', return_value=users_col):
        assert lookups.fetch_users_by_ids(['x', None]) == {}
    users_col.find.assert_not_called()


def test_fetch_judges_by_user_ids_keys_by_user_id():
    judges_col = MagicMock()
    judges_col.find.return_value = [{'user_id': 'u1', 'judge_type': 'INTERNAL_JUDGE'}]
    with patch.object(lookups, 'get_judges_collection', return_value=judges_col):
        result = lookups.fetch_judges_by_user_ids(['u1', 'u2'])
    judges_col.find.assert_called_once_with({'user_id': {'$in': ['u1', 'u2']}})
    assert result == {'u1': {'user_id': 'u1', 'judge_type': 'INTERNAL_JUDGE'}}


def test_actor_name_map():
    u1 = ObjectId()
    users_col = MagicMock()
    users_col.find.return_value = [{'_id': u1, 'name': 'Priya'}]
    with patch.object(lookups, 'get_users_collection', return_value=users_col):
        assert lookups.actor_name_map([str(u1), None]) == {str(u1): 'Priya'}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_lookups.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'utils.lookups'`

- [ ] **Step 3: Create `utils/lookups.py`**

```python
"""
Batch lookup helpers: replace per-row `find_one` loops with one `$in` query.
Each function returns a dict keyed by the string id the caller already holds.
"""
from bson.objectid import ObjectId

from models.database import (
    get_users_collection,
    get_teams_collection,
    get_judges_collection,
)


def to_object_ids(ids):
    """Convert an iterable of str/ObjectId to ObjectIds, silently dropping invalid values."""
    result = []
    for value in ids:
        if isinstance(value, ObjectId):
            result.append(value)
        elif isinstance(value, str) and ObjectId.is_valid(value):
            result.append(ObjectId(value))
    return result


def _fetch_by_object_ids(collection, ids, projection=None):
    object_ids = to_object_ids(ids)
    if not object_ids:
        return {}
    cursor = collection.find({'_id': {'$in': object_ids}}, projection) if projection is not None \
        else collection.find({'_id': {'$in': object_ids}})
    return {str(doc['_id']): doc for doc in cursor}


def fetch_users_by_ids(ids, projection=None):
    return _fetch_by_object_ids(get_users_collection(), ids, projection)


def fetch_teams_by_ids(ids, projection=None):
    return _fetch_by_object_ids(get_teams_collection(), ids, projection)


def fetch_judges_by_user_ids(user_ids):
    user_ids = [u for u in user_ids if u]
    if not user_ids:
        return {}
    return {doc['user_id']: doc for doc in get_judges_collection().find({'user_id': {'$in': user_ids}})}


def actor_name_map(actor_ids):
    """{actor_id: name} for the given user ids; ids without a user are absent."""
    users = fetch_users_by_ids([a for a in actor_ids if a], projection={'name': 1})
    return {uid: user.get('name', 'Unknown') for uid, user in users.items()}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_lookups.py -v`
Expected: 5 passed.

- [ ] **Step 5: Use the helpers in `routes/admin.py`**

Add to the imports at the top of `routes/admin.py`:

```python
from utils.lookups import fetch_users_by_ids, fetch_teams_by_ids, fetch_judges_by_user_ids, actor_name_map
```

**`judges_list`** — replace the `for judge in all_judges:` loop (from `for judge in all_judges:` through `judge['kind'] = ...`) with:

```python
    all_judges = list(judges_col.find().sort('created_at', -1))
    users_by_id = fetch_users_by_ids([j.get('user_id') for j in all_judges])
    for judge in all_judges:
        user = users_by_id.get(str(judge.get('user_id')))
        if user:
            judge['name'] = user['name']
            judge['email'] = user['email']
            judge['credentials_sent'] = user.get('credentials_sent', judge.get('credentials_sent'))
            judge['credentials_sent_at'] = user.get('credentials_sent_at', judge.get('credentials_sent_at'))
            judge['credentials_sent_to'] = user.get('credentials_sent_to', judge.get('credentials_sent_to'))
        judge['kind'] = 'external' if 'external' in str(judge.get('judge_type', '')).lower() else 'internal'
```

Also delete the now-unused `users_col = get_users_collection()` line in that function.

**`send_credentials_all`** — replace the `targets = []` loop with:

```python
    all_judges = list(judges_col.find())
    users_by_id = fetch_users_by_ids([j.get('user_id') for j in all_judges])
    targets = []
    for judge in all_judges:
        kind = 'external' if 'external' in str(judge.get('judge_type', '')).lower() else 'internal'
        if tab in ('internal', 'external') and kind != tab:
            continue
        if str(judge.get('status', 'active')).lower() != 'active':
            continue
        user = users_by_id.get(str(judge.get('user_id')))
        already = (user or judge).get('credentials_sent', False)
        if already and not include_sent:
            continue
        targets.append(judge)
```

Delete the now-unused `users_col = get_users_collection()` line in that function.

**`audit_logs`** — replace the `# Add actor names` loop with:

```python
    # Add actor names (one query for the whole page)
    names = actor_name_map([log.get('actor_id') for log in logs])
    for log in logs:
        if log.get('actor_id'):
            log['actor_name'] = names.get(log['actor_id'], 'Unknown')
        else:
            log['actor_name'] = 'System'
```

Delete the now-unused `users_col = get_users_collection()` line in that function.

**`evaluations_list`** — replace the `for ev in evaluations:` loop with:

```python
    judge_ids = [ev.get('judge_id', '') for ev in evaluations]
    judges_by_user = fetch_judges_by_user_ids(judge_ids)
    users_by_id = fetch_users_by_ids(judge_ids, projection={'name': 1})
    teams_by_id = fetch_teams_by_ids([ev.get('team_id') for ev in evaluations], projection={'team_name': 1})
    for ev in evaluations:
        judge = judges_by_user.get(ev.get('judge_id', ''))
        user = users_by_id.get(ev.get('judge_id', ''))
        ev['judge_name'] = user['name'] if (judge and user) else 'Unknown'
        ev['judge_type'] = judge['judge_type'] if judge else 'unknown'
        team = teams_by_id.get(ev.get('team_id', ''))
        ev['team_name'] = team['team_name'] if team else 'Unknown'
```

Delete the now-unused `judges_col`, `users_col`, `teams_col` assignments at the top of that function.

- [ ] **Step 6: Use the helpers in `routes/super_admin.py::dashboard`**

Add import:

```python
from utils.lookups import fetch_users_by_ids
```

Replace the `for log in recent_logs:` loop with:

```python
    recent_logs = list(audit_col.find().sort('created_at', -1).limit(10))
    actors = fetch_users_by_ids([log.get('actor_id') for log in recent_logs], projection={'name': 1, 'role': 1})
    for log in recent_logs:
        actor = actors.get(str(log.get('actor_id') or ''))
        log['actor_name'] = actor['name'] if actor else 'System / Guest'
        log['actor_role'] = actor.get('role', 'N/A') if actor else 'N/A'
```

(The old code fell back to `find_one({'email': actor_id})` when the id was not an ObjectId. Audit logs written by this codebase always store `str(user['_id'])` or `None` as `actor_id`, so the fallback is dead code; drop it.)

- [ ] **Step 7: Verify imports still resolve**

Run: `python -c "import routes.admin, routes.super_admin; print('ok')"`
Expected: `ok`

Run: `python -m pyflakes routes/admin.py routes/super_admin.py 2>/dev/null || python -m py_compile routes/admin.py routes/super_admin.py && echo compiled`
Expected: no `undefined name` output; `compiled`.

- [ ] **Step 8: Commit**

```bash
git add utils/lookups.py routes/admin.py routes/super_admin.py tests/test_lookups.py
git commit -m "perf(admin): replace per-row find_one loops with \$in batch lookups"
```

---

### Task 5: Per-request cache for `event_settings`

**Fixes:** F7

**Files:**
- Create: `services/settings.py`
- Modify: `routes/teams.py` (`is_registration_open`)
- Modify: `services/checkpoint_manager.py` (`get_judging_status`, `lock_judging`, `unlock_judging`)
- Modify: `routes/admin.py` (`dashboard`, `judges_list`, `settings`, `send_credentials_all`, `results_overview` — read via cache; toggles invalidate)
- Test: `tests/test_settings_cache.py`

**Interfaces:**
- Produces (`services/settings.py`):
  - `get_event_settings() -> dict` — the single `event_settings` document or `{}`; cached on `flask.g` for the current request/app context; safe to call with no app context (falls through to a query).
  - `invalidate_event_settings() -> None` — clears the cached copy (call after any write).
- Consumes: `models.database.get_event_settings_collection`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_settings_cache.py`:

```python
"""services.settings per-request cache — bare Flask app, mocked collection."""
from unittest.mock import MagicMock, patch

from flask import Flask

import services.settings as settings


def _app():
    return Flask('settings-test')


def test_get_event_settings_queries_once_per_request():
    col = MagicMock()
    col.find_one.return_value = {'_id': 1, 'registration_open': False}
    with patch.object(settings, 'get_event_settings_collection', return_value=col):
        with _app().test_request_context('/'):
            first = settings.get_event_settings()
            second = settings.get_event_settings()
    assert first is second
    assert first['registration_open'] is False
    col.find_one.assert_called_once_with({})


def test_get_event_settings_returns_empty_dict_when_missing():
    col = MagicMock()
    col.find_one.return_value = None
    with patch.object(settings, 'get_event_settings_collection', return_value=col):
        with _app().test_request_context('/'):
            assert settings.get_event_settings() == {}


def test_invalidate_forces_refetch():
    col = MagicMock()
    col.find_one.side_effect = [{'judging_locked': False}, {'judging_locked': True}]
    with patch.object(settings, 'get_event_settings_collection', return_value=col):
        with _app().test_request_context('/'):
            assert settings.get_event_settings()['judging_locked'] is False
            settings.invalidate_event_settings()
            assert settings.get_event_settings()['judging_locked'] is True
    assert col.find_one.call_count == 2


def test_cache_does_not_leak_between_requests():
    col = MagicMock()
    col.find_one.side_effect = [{'v': 1}, {'v': 2}]
    app = _app()
    with patch.object(settings, 'get_event_settings_collection', return_value=col):
        with app.test_request_context('/'):
            assert settings.get_event_settings()['v'] == 1
        with app.test_request_context('/'):
            assert settings.get_event_settings()['v'] == 2


def test_works_without_app_context():
    col = MagicMock()
    col.find_one.return_value = {'x': 1}
    with patch.object(settings, 'get_event_settings_collection', return_value=col):
        assert settings.get_event_settings() == {'x': 1}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_settings_cache.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'services.settings'`

- [ ] **Step 3: Create `services/settings.py`**

```python
"""
Event settings access with a per-request cache.

`event_settings` is a single document read by the context processor on every
page, by the judging-lock check, and by several admin views — often 2–3 times
in one request. Cache it on `flask.g` so each request pays for it once.
"""
from flask import g, has_app_context

from models.database import get_event_settings_collection

_CACHE_KEY = '_event_settings_cache'


def get_event_settings():
    """Return the event_settings document (or {}), cached for the current request."""
    if has_app_context() and _CACHE_KEY in g:
        return g.get(_CACHE_KEY)

    doc = get_event_settings_collection().find_one({}) or {}

    if has_app_context():
        setattr(g, _CACHE_KEY, doc)
    return doc


def invalidate_event_settings():
    """Drop the cached copy — call after writing to event_settings."""
    if has_app_context():
        g.pop(_CACHE_KEY, None)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_settings_cache.py -v`
Expected: 5 passed.

- [ ] **Step 5: Wire the readers**

`routes/teams.py` — replace `is_registration_open`:

```python
from services.settings import get_event_settings


def is_registration_open():
    """Admin/Super Admin switch 'registration_open' in event_settings (default: open)."""
    try:
        settings = get_event_settings()
    except Exception:
        return True
    return bool(settings.get('registration_open', True))
```

Remove `get_event_settings_collection` from the `from models.database import (...)` line in `routes/teams.py` (it is no longer used there).

`services/checkpoint_manager.py` — change the import line to:

```python
from models.database import get_event_settings_collection
from services.settings import get_event_settings, invalidate_event_settings
from services.audit import log_audit
```

Replace `get_judging_status`:

```python
def get_judging_status():
    """Current judging status (locked/unlocked), read from the per-request settings cache."""
    settings = get_event_settings()
    return {
        'is_locked': settings.get('judging_locked', False),
        'locked_at': settings.get('judging_locked_at'),
        'locked_by': settings.get('judging_locked_by'),
        'lock_reason': settings.get('judging_lock_reason'),
    }
```

In `lock_judging` and `unlock_judging`, add `invalidate_event_settings()` as the first line after the `settings_col.update_one(...)`/`insert_one(...)` block (i.e. immediately before `# Log audit`).

`routes/admin.py` — add import:

```python
from services.settings import get_event_settings, invalidate_event_settings
```

Then:
- `dashboard`: replace `event_settings = settings.find_one({})` with `event_settings = get_event_settings()`; delete `settings = get_event_settings_collection()`.
- `judges_list`: replace `settings = get_event_settings_collection().find_one({}) or {}` with `settings = get_event_settings()`.
- `settings` view: replace `event_settings = settings_col.find_one({})` with `event_settings = get_event_settings()` and change the `if not event_settings:` block to build the defaults dict as today (it still works because `{}` is falsy). Delete `settings_col = get_event_settings_collection()` in that function.
- `send_credentials_all`: replace `settings = get_event_settings_collection().find_one({}) or {}` with `settings = get_event_settings()`.
- `results_overview`: replace the two lines `settings_col = ...` / `event_settings = settings_col.find_one({}) or {}` with `event_settings = get_event_settings()`.
- `toggle_judging`, `toggle_results`, `toggle_registration`: add `invalidate_event_settings()` immediately after each `settings_col.update_one(...)` call.

- [ ] **Step 6: Verify**

Run: `python -c "import routes.admin, routes.teams, services.checkpoint_manager; print('ok')"`
Expected: `ok`

Run: `python -m pytest tests/test_settings_cache.py tests/test_results_aggregation.py tests/test_lookups.py tests/test_judge_dashboard_summary.py -q`
Expected: all passed.

- [ ] **Step 7: Commit**

```bash
git add services/settings.py routes/teams.py services/checkpoint_manager.py routes/admin.py tests/test_settings_cache.py
git commit -m "perf(settings): cache event_settings per request; invalidate on write"
```

---

### Task 6: Cheaper cold start — pool options, no startup ping, gated index creation

**Fixes:** F8

**Files:**
- Modify: `models/database.py` (`Database.initialize`, rename `_create_indexes` → `ensure_indexes`)
- Modify: `init_db.py`
- Modify: `.env.example`
- Test: `tests/test_database_init.py`

**Interfaces:**
- Produces:
  - `Database.initialize(app)` — same call site in `app.py`. Reads `app.config['MONGO_MAX_POOL_SIZE']` (default 10) and `app.config['MONGO_ENSURE_INDEXES']` (default `True` in development, `False` in production).
  - `Database.ensure_indexes()` — public; idempotent; callable from `init_db.py`.
- Consumes: `config.Config` gains two attributes:

```python
    # MongoDB client tuning (serverless-friendly defaults)
    MONGO_MAX_POOL_SIZE = int(os.environ.get('MONGO_MAX_POOL_SIZE', 10))
    # Index creation costs ~20 round-trips; on Vercel that is every cold start.
    # Default on in development, off in production; `python init_db.py` always runs it.
    MONGO_ENSURE_INDEXES = os.environ.get('MONGO_ENSURE_INDEXES', '').lower() in ('1', 'true', 'yes')
```

and `DevelopmentConfig` sets `MONGO_ENSURE_INDEXES = os.environ.get('MONGO_ENSURE_INDEXES', 'true').lower() in ('1', 'true', 'yes')` (i.e. default **on** in dev, **off** in prod).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_database_init.py`:

```python
"""Database.initialize behaviour with MongoClient mocked — no MongoDB needed."""
from unittest.mock import MagicMock, patch

from flask import Flask

from models.database import Database


def _app(**overrides):
    app = Flask('db-test')
    app.config.update({
        'MONGO_URI': 'mongodb://example.invalid:27017',
        'MONGO_DB_NAME': 'testdb',
        'MONGO_MAX_POOL_SIZE': 7,
        'MONGO_ENSURE_INDEXES': False,
    })
    app.config.update(overrides)
    return app


def _reset():
    Database.client = None
    Database.db = None


def test_initialize_passes_pool_options_and_does_not_ping():
    _reset()
    client = MagicMock()
    with patch('models.database.MongoClient', return_value=client) as mongo_client:
        Database.initialize(_app())

    args, kwargs = mongo_client.call_args
    assert args == ('mongodb://example.invalid:27017',)
    assert kwargs['maxPoolSize'] == 7
    assert kwargs['serverSelectionTimeoutMS'] == 5000
    assert kwargs['connectTimeoutMS'] == 5000
    assert kwargs['retryWrites'] is True
    client.admin.command.assert_not_called()
    assert Database.db is client['testdb']


def test_initialize_skips_indexes_when_disabled():
    _reset()
    with patch('models.database.MongoClient', return_value=MagicMock()), \
         patch.object(Database, 'ensure_indexes') as ensure:
        Database.initialize(_app(MONGO_ENSURE_INDEXES=False))
    ensure.assert_not_called()


def test_initialize_creates_indexes_when_enabled():
    _reset()
    with patch('models.database.MongoClient', return_value=MagicMock()), \
         patch.object(Database, 'ensure_indexes') as ensure:
        Database.initialize(_app(MONGO_ENSURE_INDEXES=True))
    ensure.assert_called_once_with()


def test_ensure_indexes_creates_the_unique_evaluation_index():
    _reset()
    Database.db = MagicMock()
    Database.ensure_indexes()
    Database.db.evaluations.create_index.assert_any_call(
        [('judge_id', 1), ('team_id', 1), ('stage_id', 1)], unique=True)
    Database.db.evaluations.create_index.assert_any_call([('stage_id', 1), ('status', 1), ('team_id', 1)])
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_database_init.py -v`
Expected: FAIL — first test fails on `kwargs['maxPoolSize']` (`KeyError`) / `client.admin.command.assert_not_called()`; last test fails with `AttributeError: type object 'Database' has no attribute 'ensure_indexes'`.

- [ ] **Step 3: Update `config/__init__.py`**

In `class Config`, directly after the `MONGO_DB_NAME = ...` line, add:

```python
    # MongoDB client tuning (serverless-friendly defaults)
    MONGO_MAX_POOL_SIZE = int(os.environ.get('MONGO_MAX_POOL_SIZE', 10))
    # Index creation costs ~20 round-trips; on Vercel that is every cold start.
    # Default: on in development, off in production. `python init_db.py` always runs it.
    MONGO_ENSURE_INDEXES = os.environ.get('MONGO_ENSURE_INDEXES', '').lower() in ('1', 'true', 'yes')
```

In `class DevelopmentConfig(Config)`, add:

```python
    MONGO_ENSURE_INDEXES = os.environ.get('MONGO_ENSURE_INDEXES', 'true').lower() in ('1', 'true', 'yes')
```

- [ ] **Step 4: Rewrite `Database.initialize` and rename `_create_indexes`**

In `models/database.py`, replace the `initialize` method and the `_create_indexes` method header with:

```python
    @staticmethod
    def initialize(app):
        """
        Create the MongoClient. Connection is lazy (PyMongo connects on first
        operation), so startup does no network I/O. Index creation is opt-in
        via MONGO_ENSURE_INDEXES — run `python init_db.py` after deploying
        schema changes instead of paying for it on every cold start.
        """
        Database.client = MongoClient(
            app.config['MONGO_URI'],
            maxPoolSize=app.config.get('MONGO_MAX_POOL_SIZE', 10),
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=5000,
            retryWrites=True,
        )
        Database.db = Database.client[app.config['MONGO_DB_NAME']]
        logger.info("MongoDB client ready for database: %s", app.config['MONGO_DB_NAME'])

        if app.config.get('MONGO_ENSURE_INDEXES', False):
            Database.ensure_indexes()

    @staticmethod
    def ensure_indexes():
        """Create database indexes for performance and constraints (idempotent)."""
```

Keep the existing body of the old `_create_indexes` (the `try:` block with all the `create_index` calls) under the new `ensure_indexes` header. Inside that body, in the `# Evaluations collection` group, add one compound index that serves `load_submitted_evaluations` and `get_evaluation_coverage` directly:

```python
            Database.db.evaluations.create_index([('stage_id', 1), ('status', 1), ('team_id', 1)])
```

Remove the now-unused `from pymongo.errors import ConnectionFailure` and `from flask import current_app` imports at the top of the file.

- [ ] **Step 5: Make `init_db.py` create indexes explicitly**

Replace the body of `init_db.py`'s `if __name__ == '__main__':` block:

```python
if __name__ == '__main__':
    app = create_app()
    with app.app_context():
        Database.ensure_indexes()
        init_database()
```

and add `from models.database import Database` to its imports.

- [ ] **Step 6: Document the flags in `.env.example`**

Append:

```
# MongoDB client tuning
MONGO_MAX_POOL_SIZE=10
# Create indexes on app start (default: true in development, false in production).
# In production run `python init_db.py` once after deploy instead.
MONGO_ENSURE_INDEXES=false
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `python -m pytest tests/test_database_init.py -v`
Expected: 4 passed.

Run: `python -c "import ast,sys; ast.parse(open('models/database.py').read()); print('syntax ok')"`
Expected: `syntax ok`

- [ ] **Step 8: Commit**

```bash
git add models/database.py config/__init__.py init_db.py .env.example tests/test_database_init.py
git commit -m "perf(db): lazy connect with pool options; gate index creation behind MONGO_ENSURE_INDEXES"
```

---

### Task 7: Cacheable static assets with content-hash busting

**Fixes:** F9

**Files:**
- Modify: `app.py` (`create_app`: config + `static_url` template global)
- Modify: `templates/base.html` (3 `url_for('static', …)` → `static_url(...)`), `templates/landing.html` (1)
- Test: `tests/test_static_cache.py`

**Interfaces:**
- Produces: Jinja global `static_url(filename: str) -> str` — returns `/static/<filename>?v=<8-hex-chars of the file's md5>`; falls back to a plain `/static/<filename>` when the file is missing. Hashes are memoised for the process lifetime (fine on Vercel: a new deploy is a new process).
- Config: `SEND_FILE_MAX_AGE_DEFAULT = 31536000` (one year) — safe **only** because every reference carries a content hash.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_static_cache.py`:

```python
"""static_url helper + cache headers — bare Flask app pointing at a temp static dir."""
import hashlib
from pathlib import Path

from flask import Flask

from app import configure_static_caching


def _app(tmp_path):
    static_dir = tmp_path / 'static'
    static_dir.mkdir()
    (static_dir / 'a.css').write_bytes(b'body{color:red}')
    app = Flask('static-test', static_folder=str(static_dir))
    configure_static_caching(app)
    return app, static_dir


def test_static_url_appends_content_hash(tmp_path):
    app, static_dir = _app(tmp_path)
    expected = hashlib.md5(b'body{color:red}').hexdigest()[:8]
    with app.test_request_context('/'):
        assert app.jinja_env.globals['static_url']('a.css') == f'/static/a.css?v={expected}'


def test_static_url_changes_when_content_changes(tmp_path):
    app, static_dir = _app(tmp_path)
    with app.test_request_context('/'):
        first = app.jinja_env.globals['static_url']('a.css')
    (static_dir / 'a.css').write_bytes(b'body{color:blue}')
    configure_static_caching(app)          # new process == fresh memo
    with app.test_request_context('/'):
        second = app.jinja_env.globals['static_url']('a.css')
    assert first != second


def test_static_url_missing_file_has_no_version(tmp_path):
    app, _ = _app(tmp_path)
    with app.test_request_context('/'):
        assert app.jinja_env.globals['static_url']('missing.css') == '/static/missing.css'


def test_static_files_get_one_year_cache_header(tmp_path):
    app, _ = _app(tmp_path)
    resp = app.test_client().get('/static/a.css?v=abc')
    assert resp.status_code == 200
    assert 'max-age=31536000' in resp.headers['Cache-Control']
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_static_cache.py -v`
Expected: FAIL — `ImportError: cannot import name 'configure_static_caching' from 'app'`.

Note: importing `app` executes `app = create_app()` at module bottom, which calls `Database.initialize`. After Task 6 that no longer performs network I/O, and `MONGO_URI` defaults to `""` which `MongoClient("")` rejects. To keep this test DB-free, **guard the module-level instantiation**: change the bottom of `app.py` to

```python
if os.environ.get('SKIP_APP_INIT') != '1':
    app = create_app()
```

and run this test file with `SKIP_APP_INIT=1 python -m pytest tests/test_static_cache.py -v`. (Vercel imports `app` from `api/index.py`, which never sets that variable, so production is unaffected.)

- [ ] **Step 3: Implement in `app.py`**

Add near the top (after the `from models.database import Database` import):

```python
import hashlib
from functools import lru_cache
from flask import url_for


def configure_static_caching(app):
    """
    Long-lived cache headers for /static plus a `static_url()` Jinja global
    that appends a content hash, so a deploy busts the cache and unchanged
    files are served from the browser cache for a year.
    """
    app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 31536000  # 1 year, in seconds
    static_root = app.static_folder

    @lru_cache(maxsize=256)
    def _digest(filename):
        try:
            with open(os.path.join(static_root, filename), 'rb') as fh:
                return hashlib.md5(fh.read()).hexdigest()[:8]
        except OSError:
            return None

    def static_url(filename):
        digest = _digest(filename)
        if digest:
            return url_for('static', filename=filename, v=digest)
        return url_for('static', filename=filename)

    app.jinja_env.globals['static_url'] = static_url
```

In `create_app()`, add `configure_static_caching(app)` right after `app.config.from_object(get_config())`.

Replace the bottom of the file as described in Step 2.

- [ ] **Step 4: Update templates**

`templates/base.html` — change these three lines:

```html
    <link rel="icon" type="image/png" href="{{ static_url('images/favicon.png') }}">
```
```html
    {% block legacy_css %}<link rel="stylesheet" href="{{ static_url('css/main.css') }}">{% endblock %}
    <link rel="stylesheet" href="{{ static_url('css/app.css') }}">
```
```html
    <script src="{{ static_url('js/main.js') }}"></script>
```

`templates/landing.html` line 6:

```html
<link rel="stylesheet" href="{{ static_url('css/landing.css') }}">
```

Then find any remaining static references in templates and convert them the same way:

Run: `grep -rn "url_for('static'" templates`
Expected after edits: no output. (Convert each hit to `static_url('<same filename>')`.)

- [ ] **Step 5: Run the tests to verify they pass**

Run: `SKIP_APP_INIT=1 python -m pytest tests/test_static_cache.py -v`
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add app.py templates tests/test_static_cache.py
git commit -m "perf(static): one-year cache headers with content-hash cache busting"
```

---

### Task 8: Full verification pass

**Files:** none modified (fix-forward only if something fails).

- [ ] **Step 1: Run every DB-free test**

Run: `SKIP_APP_INIT=1 python -m pytest tests/test_all_flows.py tests/test_results_aggregation.py tests/test_judge_dashboard_summary.py tests/test_lookups.py tests/test_settings_cache.py tests/test_database_init.py tests/test_static_cache.py -q`
Expected: all passed, 0 failed.

- [ ] **Step 2: Compile everything**

Run: `python -m compileall -q app.py config models routes services utils && echo OK`
Expected: `OK`

- [ ] **Step 3: Smoke test against a real database (requires `.env` with `MONGO_URI`)**

Run: `FLASK_ENV=development python app.py` in one terminal; in another:

```bash
curl -s -o /dev/null -w "%{http_code} %{time_total}s\n" http://localhost:5002/
curl -s -I http://localhost:5002/static/css/app.css | grep -i cache-control
```
Expected: `200 …`, and `Cache-Control: … max-age=31536000`.

Then log in as an admin in a browser and open `/admin/results-overview`, `/admin/judges`, `/admin/evaluations-list`, `/admin/audit-logs`, `/results/team/<any team id>` — each should render and the leaderboard should now show a non-zero **Internal Average** for teams that have internal-judge evaluations (F2 fixed).

- [ ] **Step 4: Re-create indexes once (production only, one-off)**

Run: `python init_db.py`
Expected: log line `Database indexes created successfully`. This adds the new `(stage_id, status, team_id)` index; subsequent deploys skip index creation.

- [ ] **Step 5: Commit any fix-ups**

```bash
git add -A -- ':!.env'
git commit -m "chore: verification fix-ups for query/cold-start optimization"
```
(Skip if the working tree is clean.)

---

## Self-Review

**Spec coverage:** F1/F2/F3 → Task 1; F4 → Task 2; F5 → Task 3; F6 → Task 4; F7 → Task 5; F8 → Task 6; F9 → Task 7. Every baseline finding has a task.

**Placeholder scan:** every code step shows the code; no "TBD"/"similar to". The one deferred-verification item (Task 8 Step 3) requires a live DB and is labelled as such.

**Type consistency:**
- `normalize_judge_type` returns `'internal' | 'external'` and `load_judge_types` values are exactly those strings; `aggregate_team_scores` and `summarize_coverage` compare against them — consistent.
- `calculate_team_score(team_id, stage_id, evaluations=None, judge_types=None)` is the signature used by `save_team_result`; `recalculate_all_results` passes both kwargs — consistent.
- `utils.lookups` functions return `dict[str, doc]`; all callers index with `str(...)` — consistent.
- `configure_static_caching(app)` is imported by `tests/test_static_cache.py` and called in `create_app` — consistent.
- `Database.ensure_indexes()` is called with no args in `initialize` and `init_db.py`; test asserts `assert_called_once_with()` — consistent.

**Expected impact (typical event: 30 teams, 25 judges, ~300 evaluations):**
- `/results/leaderboard`: ~30 + 300 + 6 ≈ 336 queries → 7 (3 leaderboard + 4 coverage).
- `/results/team/<id>`: ~2× that + N+1 detail → ~11.
- `/judge/dashboard`: 30 + 4 → 4.
- `/admin/judges` (25 judges): 27 → 3. `/admin/evaluations-list` (25 rows): 76 → 5.
- Cold start: 23 round-trips (ping + 22 indexes) → 0 before the first real query.
- Repeat page views: 3 CSS/JS fetches → 0 (browser cache).
