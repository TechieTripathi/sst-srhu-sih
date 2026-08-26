"""
Jury Scope Service — who may evaluate which team, and which weight their score carries.

TechForge 3.0 runs two kinds of jury:

  * Group jury      (jury_scope='assigned_only') sit on one of five panels and may
                    only score the teams assigned to that panel. Weight 60%.
  * Exception jury  (jury_scope='all_teams')     sit outside every panel, may score
                    every team, and may keep scoring while judging is locked.
                    Weight 40%.

This axis is deliberately independent of `judge_type` (INTERNAL_JUDGE /
EXTERNAL_JUDGE), which now means only "does this person have a real mailbox and
how are their credentials delivered". An outside guest can sit on a panel; a
member of staff can be exception jury.

This module is the single source of truth for that distinction. It is a leaf —
it imports nothing from this package except models.database — so routes,
checkpoint_manager, scoring and results_calculator can all depend on it without
import cycles.

Nothing outside this module should read `judge['jury_scope']` or compare against
the literals directly. `judge_type` was handled that way and the substring test
`'internal' in judge_type.lower()` ended up copied into eight different files,
each free to drift.
"""

from bson.objectid import ObjectId

from models.database import (
    get_judges_collection,
    get_teams_collection,
    get_users_collection,
)


SCOPE_ALL = 'all_teams'
SCOPE_ASSIGNED = 'assigned_only'

# Fail closed. A judge whose document missed the migration can score NOTHING and
# says so within thirty seconds; the alternative default would silently hand them
# every team plus a bypass of the judging lock, granted by absence of data.
DEFAULT_SCOPE = SCOPE_ASSIGNED

PANEL_COUNT = 5
PANEL_NUMBERS = tuple(range(1, PANEL_COUNT + 1))

BUCKET_EXCEPTION = 'exception'
BUCKET_GROUP = 'group'

# Query fragment for "is group jury", tolerating documents written before the
# migration. Exposed so admin count_documents() calls build their filter from
# this name instead of each inventing its own $in / $exists clause.
FILTER_EXCEPTION = {'jury_scope': SCOPE_ALL}
FILTER_GROUP = {'jury_scope': {'$ne': SCOPE_ALL}}


def jury_scope(judge):
    """The judge's scope, with the only fallback in the codebase.

    Every other predicate here is defined in terms of this function, so the
    default lives in exactly one place.
    """
    value = (judge or {}).get('jury_scope')
    return value if value in (SCOPE_ALL, SCOPE_ASSIGNED) else DEFAULT_SCOPE


def is_exception_jury(judge):
    """True for at-large jury: every team, and immune to the judging lock."""
    return jury_scope(judge) == SCOPE_ALL


def judge_bucket(judge):
    """Which side of the 40/60 split this judge's score falls on."""
    return BUCKET_EXCEPTION if is_exception_jury(judge) else BUCKET_GROUP


def judge_panel_no(judge):
    """Panel number 1..5, or None for exception jury / unassigned group jury."""
    if is_exception_jury(judge):
        return None
    panel = (judge or {}).get('panel_no')
    try:
        panel = int(panel)
    except (TypeError, ValueError):
        return None
    return panel if panel in PANEL_NUMBERS else None


def panel_label(panel_no):
    """Display string for a panel, used by templates via the Jinja global."""
    try:
        panel_no = int(panel_no)
    except (TypeError, ValueError):
        return 'No panel'
    return f'Panel {panel_no}' if panel_no in PANEL_NUMBERS else 'No panel'


def scope_label(judge):
    """Human-readable role, for admin tables and the judge's own dashboard."""
    if is_exception_jury(judge):
        return 'Exception jury'
    panel = judge_panel_no(judge)
    return panel_label(panel) if panel else 'No panel'


def load_judge_for_session(user_id, email=None):
    """Resolve the judges document for a signed-in session.

    Tries user_id, then the user document's email, then the session email. This
    replaces three separately open-coded variants of the same lookup; one of them
    (results_calculator) used only user_id and silently dropped submitted scores
    when it missed.
    """
    judges_col = get_judges_collection()

    judge = judges_col.find_one({'user_id': user_id})
    if judge:
        return judge

    user = None
    if user_id:
        try:
            user = get_users_collection().find_one({'_id': ObjectId(user_id)})
        except Exception:
            user = None

    if user and user.get('email'):
        judge = judges_col.find_one({'email': str(user['email']).lower()})
        if judge:
            return judge

    if email:
        judge = judges_col.find_one({'email': str(email).lower()})
        if judge:
            return judge

    return None


def teams_for_judge(judge):
    """The teams this judge is entitled to see and score, name-sorted.

    Exception jury get everything. Group jury get their panel only — and a group
    judge with no panel gets an empty list, not everything.
    """
    teams_col = get_teams_collection()

    if is_exception_jury(judge):
        return list(teams_col.find().sort('team_name', 1))

    panel = judge_panel_no(judge)
    if not panel:
        return []
    return list(teams_col.find({'panel_no': panel}).sort('team_name', 1))


def can_evaluate(judge, team):
    """The single entitlement predicate. Fails closed on missing data."""
    if is_exception_jury(judge):
        return True
    panel = judge_panel_no(judge)
    return bool(panel) and (team or {}).get('panel_no') == panel


def bypasses_judging_lock(judge):
    """Exception jury keep scoring after the organisers lock judging."""
    return is_exception_jury(judge)


def panel_judge_counts():
    """{panel_no: judge_count} — the denominator for panel completeness.

    Deliberately does NOT filter on status. `status` is written as 'ACTIVE' by
    the seed script and 'active' by the admin form, so a naive filter returns
    zero for every seeded judge and would mark every team permanently
    incomplete with no error anywhere. Beyond that, deactivating one judge
    mid-event should not silently flip ten teams from COMPLETE back to
    incomplete.
    """
    counts = {n: 0 for n in PANEL_NUMBERS}
    cursor = get_judges_collection().find(
        FILTER_GROUP, {'panel_no': 1}
    )
    for judge in cursor:
        panel = judge.get('panel_no')
        try:
            panel = int(panel)
        except (TypeError, ValueError):
            continue
        if panel in counts:
            counts[panel] += 1
    return counts


def judge_user_ids_by_panel():
    """{panel_no: [users._id strings]} for progress queries.

    Note the field: evaluations.judge_id holds the *users* _id string, never
    judges._id. Matching on str(judge['_id']) instead renders 0/50 forever with
    no error.
    """
    by_panel = {n: [] for n in PANEL_NUMBERS}
    cursor = get_judges_collection().find(
        FILTER_GROUP, {'panel_no': 1, 'user_id': 1}
    )
    for judge in cursor:
        panel = judge.get('panel_no')
        try:
            panel = int(panel)
        except (TypeError, ValueError):
            continue
        if panel in by_panel and judge.get('user_id'):
            by_panel[panel].append(judge['user_id'])
    return by_panel


def exception_jury_user_ids():
    """users._id strings for every exception juror."""
    return [
        j['user_id']
        for j in get_judges_collection().find(FILTER_EXCEPTION, {'user_id': 1})
        if j.get('user_id')
    ]
