"""
Jury Panel Service — panel rosters, team assignment and scoring progress.

Panel membership is a scalar `panel_no` on the judges document and on the teams
document. There is deliberately no panel collection holding an array of team ids:
an array cannot structurally stop two panels claiming the same team, this
codebase has no transactions, and moving a team would be a non-atomic $pull plus
$push with a window where the team belongs to zero or two panels. A scalar is
single-valued by construction, which is exactly the invariant the event needs.
"""

import math
from datetime import datetime

from bson.objectid import ObjectId

from models.database import (
    get_evaluations_collection,
    get_judges_collection,
    get_teams_collection,
)
from services.audit import log_audit
from services.jury_scope import (
    FILTER_EXCEPTION,
    FILTER_GROUP,
    PANEL_COUNT,
    PANEL_NUMBERS,
    SCOPE_ALL,
    SCOPE_ASSIGNED,
    is_exception_jury,
    judge_panel_no,
    panel_judge_counts,
    judge_user_ids_by_panel,
)

DEFAULT_STAGE = 'final_presentation'


# --------------------------------------------------------------------------- #
# Reads
# --------------------------------------------------------------------------- #

def panel_teams(panel_no):
    return list(get_teams_collection().find({'panel_no': int(panel_no)}).sort('team_name', 1))


def panel_judges(panel_no):
    return list(
        get_judges_collection().find({'panel_no': int(panel_no), **FILTER_GROUP}).sort('name', 1)
    )


def exception_judges():
    return list(get_judges_collection().find(FILTER_EXCEPTION).sort('name', 1))


def unassigned_teams():
    """Teams with no panel. Only exception jury can score these.

    $nin also matches documents where the field is absent or null, so this one
    query covers never-assigned, cleared and malformed values alike.
    """
    return list(
        get_teams_collection()
        .find({'panel_no': {'$nin': list(PANEL_NUMBERS)}})
        .sort([('created_at', 1), ('_id', 1)])
    )


def list_panels(stage_id=DEFAULT_STAGE):
    """All five panels with their rosters, teams and scoring progress."""
    counts = panel_judge_counts()
    by_panel_users = judge_user_ids_by_panel()
    evaluations_col = get_evaluations_collection()

    panels = []
    for n in PANEL_NUMBERS:
        teams = panel_teams(n)
        team_ids = [str(t['_id']) for t in teams]
        user_ids = by_panel_users.get(n, [])

        expected = len(user_ids) * len(teams)
        submitted = 0
        if user_ids and team_ids:
            submitted = evaluations_col.count_documents({
                'judge_id': {'$in': user_ids},
                'team_id': {'$in': team_ids},
                'stage_id': stage_id,
                'status': 'submitted',
            })

        panels.append({
            'panel_no': n,
            'judge_count': counts.get(n, 0),
            'team_count': len(teams),
            'judges': panel_judges(n),
            'teams': teams,
            'submitted': submitted,
            'expected': expected,
            'pct': round(submitted / expected * 100) if expected else 0,
        })
    return panels


def panel_detail(panel_no, stage_id=DEFAULT_STAGE):
    for panel in list_panels(stage_id=stage_id):
        if panel['panel_no'] == int(panel_no):
            return panel
    return None


def roster_overview(stage_id=DEFAULT_STAGE):
    """Counts for the panels landing page and the admin dashboard tile."""
    teams_col = get_teams_collection()
    judges_col = get_judges_collection()

    total_teams = teams_col.count_documents({})
    assigned = teams_col.count_documents({'panel_no': {'$in': list(PANEL_NUMBERS)}})

    return {
        'judges': judges_col.count_documents({}),
        'exception': judges_col.count_documents(FILTER_EXCEPTION),
        'group': judges_col.count_documents(FILTER_GROUP),
        'total_teams': total_teams,
        'assigned': assigned,
        'unassigned': total_teams - assigned,
    }


def judge_submitted_count(judge, stage_id=DEFAULT_STAGE):
    """How many evaluations this judge has already submitted.

    Used to warn an admin before moving someone between panels.
    """
    user_id = (judge or {}).get('user_id')
    if not user_id:
        return 0
    return get_evaluations_collection().count_documents({
        'judge_id': user_id,
        'stage_id': stage_id,
        'status': 'submitted',
    })


# --------------------------------------------------------------------------- #
# Writes
# --------------------------------------------------------------------------- #

def _normalise_panel(panel_no):
    """None for 'no panel'; otherwise an int in 1..5. Raises on anything else."""
    if panel_no in (None, '', 'none', 'None'):
        return None
    panel = int(panel_no)
    if panel not in PANEL_NUMBERS:
        raise ValueError(f'panel_no must be 1..{PANEL_COUNT}, got {panel_no!r}')
    return panel


def set_team_panel(team_id, panel_no, actor_id=None):
    """Assign or clear one team's panel. Returns True if anything changed."""
    panel = _normalise_panel(panel_no)
    teams_col = get_teams_collection()

    try:
        oid = ObjectId(team_id)
    except Exception:
        return False

    team = teams_col.find_one({'_id': oid})
    if not team:
        return False

    before = team.get('panel_no')
    if before == panel:
        return False

    if panel is None:
        teams_col.update_one(
            {'_id': oid},
            {'$unset': {'panel_no': '', 'panel_assigned_at': '', 'panel_assigned_by': ''}},
        )
        log_audit(actor_id, 'team_panel_cleared', 'team', str(oid),
                  {'from': before, 'team_name': team.get('team_name')})
    else:
        teams_col.update_one({'_id': oid}, {'$set': {
            'panel_no': panel,
            'panel_assigned_at': datetime.utcnow(),
            'panel_assigned_by': actor_id,
        }})
        log_audit(actor_id, 'team_panel_updated', 'team', str(oid),
                  {'from': before, 'to': panel, 'team_name': team.get('team_name')})
    return True


def set_judge_panel(judge_id, panel_no, actor_id=None):
    """Move a judge onto a panel (group jury) or to the exception jury.

    `panel_no=None` means exception jury: scope flips to all_teams and panel_no
    is unset. Scope and membership are written together so the two can never
    disagree.
    """
    panel = _normalise_panel(panel_no)
    judges_col = get_judges_collection()

    try:
        oid = ObjectId(judge_id)
    except Exception:
        return False

    judge = judges_col.find_one({'_id': oid})
    if not judge:
        return False

    before_scope = judge.get('jury_scope')
    before_panel = judge.get('panel_no')

    if panel is None:
        if before_scope == SCOPE_ALL and before_panel is None:
            return False
        judges_col.update_one({'_id': oid}, {
            '$set': {'jury_scope': SCOPE_ALL, 'updated_at': datetime.utcnow()},
            '$unset': {'panel_no': ''},
        })
        log_audit(actor_id, 'judge_scope_updated', 'judge', str(oid), {
            'from': before_scope, 'to': SCOPE_ALL,
            'from_panel': before_panel, 'name': judge.get('name'),
        })
    else:
        if before_scope == SCOPE_ASSIGNED and before_panel == panel:
            return False
        judges_col.update_one({'_id': oid}, {'$set': {
            'jury_scope': SCOPE_ASSIGNED,
            'panel_no': panel,
            'updated_at': datetime.utcnow(),
        }})
        action = ('judge_scope_updated' if before_scope != SCOPE_ASSIGNED
                  else 'judge_panel_updated')
        log_audit(actor_id, action, 'judge', str(oid), {
            'from_scope': before_scope, 'to_scope': SCOPE_ASSIGNED,
            'from_panel': before_panel, 'to_panel': panel,
            'name': judge.get('name'),
        })
    return True


def auto_assign_teams(mode='blocks', overwrite=False, actor_id=None):
    """Distribute teams across the five panels.

    Sizes come from ceil(total / PANEL_COUNT), never a hardcoded 10 — teams are
    still registering, and a fixed 10 leaves the tail unassigned at any count
    that is not a multiple of five.

    overwrite=False (the default) touches only teams that have no panel, so the
    button is safe to press again after late registrations. Those late teams go
    to the panel holding the fewest teams rather than the next slot in sequence,
    which would otherwise pile them onto a panel that is already full.
    """
    teams_col = get_teams_collection()
    # _id as tie-break keeps the ordering stable across runs.
    teams = list(teams_col.find().sort([('created_at', 1), ('_id', 1)]))

    if overwrite:
        targets = teams
    else:
        targets = [t for t in teams if not t.get('panel_no')]

    per_panel = {n: 0 for n in PANEL_NUMBERS}
    if not overwrite:
        for t in teams:
            panel = t.get('panel_no')
            if panel in per_panel:
                per_panel[panel] += 1

    assigned = 0
    if overwrite:
        size = max(1, math.ceil(len(targets) / PANEL_COUNT))
        for index, team in enumerate(targets):
            if mode == 'round_robin':
                panel = (index % PANEL_COUNT) + 1
            else:
                panel = min(PANEL_COUNT, index // size + 1)
            if team.get('panel_no') != panel:
                teams_col.update_one({'_id': team['_id']}, {'$set': {
                    'panel_no': panel,
                    'panel_assigned_at': datetime.utcnow(),
                    'panel_assigned_by': actor_id,
                }})
                assigned += 1
            per_panel[panel] = per_panel.get(panel, 0) + 1
    else:
        for team in targets:
            # Smallest panel first, ties resolved by lowest panel number.
            panel = min(PANEL_NUMBERS, key=lambda n: (per_panel[n], n))
            teams_col.update_one({'_id': team['_id']}, {'$set': {
                'panel_no': panel,
                'panel_assigned_at': datetime.utcnow(),
                'panel_assigned_by': actor_id,
            }})
            per_panel[panel] += 1
            assigned += 1

    # per_panel is keyed by int, and BSON documents only accept string keys -
    # storing it raw raises InvalidDocument.
    log_audit(actor_id, 'team_panels_auto_assigned', 'jury_panel', mode, {
        'mode': mode, 'overwrite': overwrite,
        'assigned': assigned, 'skipped': len(teams) - len(targets),
        'per_panel': {str(k): v for k, v in per_panel.items()},
    })

    return {
        'assigned': assigned,
        'skipped': len(teams) - len(targets),
        'per_panel': per_panel,
    }


def clear_assignments(actor_id=None):
    """Remove every team's panel. Destructive; confirm before calling."""
    result = get_teams_collection().update_many(
        {'panel_no': {'$exists': True}},
        {'$unset': {'panel_no': '', 'panel_assigned_at': '', 'panel_assigned_by': ''}},
    )
    log_audit(actor_id, 'team_panels_reset', 'jury_panel', 'all',
              {'cleared': result.modified_count})
    return {'cleared': result.modified_count}
