"""
Results Calculator Service

Final score = exception-jury average x 40% + group-jury average x 60%.

The buckets follow the jury *scope* axis (services.jury_scope), not judge_type.
Exception jury roam every team; group jury score only their own panel's teams.
judge_type (INTERNAL_JUDGE / EXTERNAL_JUDGE) is retained purely for display and
for how credentials are delivered.
"""

import logging
from datetime import datetime
from bson.objectid import ObjectId

from models.database import (
    get_teams_collection,
    get_evaluations_collection,
    get_judges_collection,
    get_team_results_collection,
    get_users_collection
)
from services.audit import log_audit
from services.jury_scope import (
    BUCKET_EXCEPTION,
    judge_bucket,
    judge_panel_no,
    panel_judge_counts,
)

logger = logging.getLogger(__name__)


# Official TechForge 3.0 Scoring Weights, on the jury-scope axis.
# These are the only copy - templates read them off the returned score dict.
EXCEPTION_WEIGHT = 0.40
GROUP_WEIGHT = 0.60

# How many exception jurors must have scored a team before it can rank.
# A quorum, not "all of them": requiring all three would mean 150 hand
# evaluations before any team could be ranked.
EXCEPTION_QUORUM = 1

# How many *panel* jurors must have scored a team before it can rank.
# Not every panel judge reaches every team, so a team is ranked on the average
# of whichever panel judges actually scored it (2, 3, 4 or 5). Coverage is still
# reported as group_count / group_expected so thin panels remain visible.
GROUP_QUORUM = 1


def _is_internal(judge):
    """Display only. judge_type no longer decides access or scoring weight."""
    return 'internal' in str((judge or {}).get('judge_type', '')).lower()


def judge_kind(judge):
    return 'internal' if _is_internal(judge) else 'external'


def _evaluation_bucket(evaluation, judge):
    """Which side of the 40/60 split an evaluation counts towards.

    Prefers the bucket frozen onto the evaluation at submission time, so moving
    a judge between panels afterwards never retroactively re-weights scores they
    have already given. Falls back to the judge's current document for rows
    written before stamping existed.
    """
    stamped = (evaluation or {}).get('judge_bucket')
    if stamped in (BUCKET_EXCEPTION, 'group'):
        return stamped
    return judge_bucket(judge)


def calculate_team_score(team_id, stage_id='final_presentation', panel_counts=None, team=None):
    """
    Calculate a team's final score: exception jury 40% + group jury 60%.

    Args:
        team_id: Team's ObjectId (string)
        stage_id: Evaluation stage identifier
        panel_counts: Optional {panel_no: judge_count} map. Pass this when
            scoring many teams so the panel roster is counted once per render
            rather than once per team.
        team: Optional team document, to save a lookup for the panel number.

    Returns:
        dict: final_score, the two bucket averages, completeness and details
    """
    evaluations_col = get_evaluations_collection()
    judges_col = get_judges_collection()
    teams_col = get_teams_collection()

    if team is None:
        try:
            team = teams_col.find_one({'_id': ObjectId(team_id)})
        except Exception:
            team = None
    team = team or {}
    panel_no = team.get('panel_no')

    if panel_counts is None:
        panel_counts = panel_judge_counts()
    group_expected = panel_counts.get(panel_no, 0)

    # Get all evaluations for this team
    evaluations = list(evaluations_col.find({
        'team_id': str(team_id),
        'stage_id': stage_id,
        'status': 'submitted'
    }))

    if not evaluations:
        return {
            'error': 'No evaluations found for this team',
            'team_id': str(team_id),
            'stage_id': stage_id,
            'panel_no': panel_no,
            # None, not 0 - an unscored team must render as a dash, never as a
            # real-looking zero next to teams that were actually scored.
            'final_score': None,
            'provisional_score': 0,
            'exception_average': 0,
            'group_average': 0,
            'exception_count': 0,
            'group_count': 0,
            'group_expected': group_expected,
            'evaluations_count': 0,
            'total_evaluations': 0,
            'is_complete': False,
            'status': 'NOT_SCORED',
            'prototype_avg': 0,
            'technical_avg': 0,
            'innovation_avg': 0,
            'exception_details': [],
            'group_details': [],
            'exception_weight': EXCEPTION_WEIGHT,
            'group_weight': GROUP_WEIGHT,
            'calculated_at': datetime.utcnow()
        }

    # Split into the two weighting buckets
    exception_scores = []
    group_scores = []
    exception_details = []
    group_details = []

    for evaluation in evaluations:
        # Only look the judge up when the evaluation has no stamped bucket.
        judge = None
        if not evaluation.get('judge_bucket'):
            judge = judges_col.find_one({'user_id': evaluation['judge_id']})
            if not judge:
                # A submitted score must never disappear silently. Treat it as
                # group jury (the majority case) and make the anomaly visible.
                logger.warning(
                    'Evaluation %s has no matching judge for user_id=%s; '
                    'counting it as group jury.',
                    evaluation.get('_id'), evaluation.get('judge_id')
                )

        score_data = {
            'judge_id': evaluation['judge_id'],
            'weighted_total': evaluation['weighted_total'],
            'submitted_at': evaluation['submitted_at'],
            'panel_no': evaluation.get('panel_no'),
        }

        if _evaluation_bucket(evaluation, judge) == BUCKET_EXCEPTION:
            exception_scores.append(evaluation['weighted_total'])
            exception_details.append(score_data)
        else:
            group_scores.append(evaluation['weighted_total'])
            group_details.append(score_data)

    # Averages over the scores actually present in each bucket
    exception_avg = sum(exception_scores) / len(exception_scores) if exception_scores else 0
    group_avg = sum(group_scores) / len(group_scores) if group_scores else 0

    # Complete means: at least GROUP_QUORUM panel judges have scored the team,
    # and at least EXCEPTION_QUORUM exception jurors have. The panel average is
    # taken over the judges present; group_expected (live roster) is reported
    # alongside purely as coverage information.
    group_complete = len(group_scores) >= GROUP_QUORUM
    exception_complete = len(exception_scores) >= EXCEPTION_QUORUM
    is_complete = group_complete and exception_complete

    if is_complete:
        status = 'COMPLETE'
    elif not group_complete and not exception_complete:
        status = 'NOT_SCORED' if not evaluations else 'AWAITING_PANEL'
    elif not group_complete:
        status = 'AWAITING_PANEL'
    else:
        status = 'AWAITING_EXCEPTION'

    # Criterion-level averages for tie-breaking
    prototype_scores = []
    technical_scores = []
    innovation_scores = []

    for ev in evaluations:
        raw = ev.get('raw_scores', {})
        if 'prototype' in raw:
            try: prototype_scores.append(float(raw['prototype']))
            except (ValueError, TypeError): pass
        if 'technical_design' in raw:
            try: technical_scores.append(float(raw['technical_design']))
            except (ValueError, TypeError): pass
        if 'innovation' in raw:
            try: innovation_scores.append(float(raw['innovation']))
            except (ValueError, TypeError): pass

    prototype_avg = sum(prototype_scores) / len(prototype_scores) if prototype_scores else 0
    technical_avg = sum(technical_scores) / len(technical_scores) if technical_scores else 0
    innovation_avg = sum(innovation_scores) / len(innovation_scores) if innovation_scores else 0

    weighted = (exception_avg * EXCEPTION_WEIGHT) + (group_avg * GROUP_WEIGHT)

    # A team missing one bucket blends a zero into the total, which reads as a
    # plausible-but-bad score rather than as missing data. Publish it only when
    # complete; until then it is explicitly provisional.
    return {
        'team_id': str(team_id),
        'stage_id': stage_id,
        'panel_no': panel_no,
        'final_score': round(weighted, 2) if is_complete else None,
        'provisional_score': round(weighted, 2),
        'exception_average': round(exception_avg, 2),
        'group_average': round(group_avg, 2),
        'exception_count': len(exception_scores),
        'group_count': len(group_scores),
        'group_expected': group_expected,
        'total_evaluations': len(evaluations),
        'evaluations_count': len(evaluations),
        'is_complete': is_complete,
        'status': status,
        'prototype_avg': round(prototype_avg, 2),
        'technical_avg': round(technical_avg, 2),
        'innovation_avg': round(innovation_avg, 2),
        'exception_details': exception_details,
        'group_details': group_details,
        'exception_weight': EXCEPTION_WEIGHT,
        'group_weight': GROUP_WEIGHT,
        'calculated_at': datetime.utcnow()
    }


def calculate_all_teams_scores(stage_id='final_presentation'):
    """
    Calculate scores for all teams that have been evaluated with tie-breaking
    
    Args:
        stage_id: Evaluation stage identifier
        
    Returns:
        list: List of team results sorted by rank with official tie-breaking
    """
    teams_col = get_teams_collection()
    all_teams = list(teams_col.find())

    # Counted once for the whole render, not once per team.
    panel_counts = panel_judge_counts()

    results = []

    for team in all_teams:
        score_result = calculate_team_score(
            str(team['_id']), stage_id, panel_counts=panel_counts, team=team
        )

        # Every team is included, even with no evaluations at all. Dropping them
        # would silently remove a whole panel's ten teams from the rankings and
        # from the CSV export if that panel never started scoring.
        results.append({
            'team_id': str(team['_id']),
            'team_code': team.get('team_code', ''),
            'team_name': team.get('team_name', ''),
            'leader_name': team.get('leader_name', ''),
            'theme_name': team.get('theme_name', ''),
            'panel_no': score_result['panel_no'],
            'final_score': score_result['final_score'],
            'provisional_score': score_result['provisional_score'],
            'exception_average': score_result['exception_average'],
            'group_average': score_result['group_average'],
            'exception_count': score_result['exception_count'],
            'group_count': score_result['group_count'],
            'group_expected': score_result['group_expected'],
            'total_evaluations': score_result['total_evaluations'],
            'is_complete': score_result['is_complete'],
            'status': score_result['status'],
            'prototype_avg': score_result['prototype_avg'],
            'technical_avg': score_result['technical_avg'],
            'innovation_avg': score_result['innovation_avg']
        })
    
    # Official TechForge 3.0 Tie-Breaking Order:
    # 1. Complete status (1 for complete, 0 for incomplete)
    # 2. Final Score (descending)
    # 3. Prototype & Implementation Average (descending)
    # 4. Technical Design & Feasibility Average (descending)
    # 5. Innovation & Differentiation Average (descending)
    # Sorted on provisional_score, which is always a number - final_score is
    # None for incomplete teams and would not compare.
    results.sort(key=lambda x: (
        1 if x['is_complete'] else 0,
        x['provisional_score'],
        x['prototype_avg'],
        x['technical_avg'],
        x['innovation_avg']
    ), reverse=True)
    
    # Add rank (only for complete teams; incomplete flagged accordingly)
    rank_counter = 1
    for result in results:
        if result['is_complete']:
            result['rank'] = rank_counter
            rank_counter += 1
        else:
            result['rank'] = '-'
    
    return results


def save_team_result(team_id, stage_id='final_presentation', actor_id=None):
    """
    Calculate and save team result to database
    
    Args:
        team_id: Team's ObjectId (string)
        stage_id: Evaluation stage identifier
        actor_id: User ID performing this action
        
    Returns:
        dict: Saved result or error
    """
    results_col = get_team_results_collection()
    
    # Calculate score
    score_result = calculate_team_score(team_id, stage_id)
    
    if score_result.get('error'):
        return score_result
    
    # Check if result already exists
    existing = results_col.find_one({
        'team_id': team_id,
        'stage_id': stage_id
    })
    
    if existing:
        # Update existing result
        results_col.update_one(
            {'_id': existing['_id']},
            {'$set': score_result}
        )
        result_id = existing['_id']
    else:
        # Insert new result
        result_id = results_col.insert_one(score_result).inserted_id
    
    # Log audit
    log_audit(
        actor_id,
        'result_calculated',
        'result',
        str(result_id),
        {
            'team_id': team_id,
            'final_score': score_result['final_score'],
            'provisional_score': score_result['provisional_score'],
            'status': score_result['status']
        }
    )
    
    return {
        'success': True,
        'result_id': str(result_id),
        'final_score': score_result['final_score'],
        'provisional_score': score_result['provisional_score']
    }


def recalculate_all_results(stage_id='final_presentation', actor_id=None):
    """
    Recalculate and save results for all teams
    
    Args:
        stage_id: Evaluation stage identifier
        actor_id: User ID performing this action
        
    Returns:
        dict: Summary of recalculation
    """
    teams_col = get_teams_collection()
    all_teams = list(teams_col.find())
    
    successful = 0
    failed = 0
    errors = []
    
    for team in all_teams:
        result = save_team_result(str(team['_id']), stage_id, actor_id)
        if result.get('success'):
            successful += 1
        else:
            failed += 1
            errors.append(f"{team['team_name']}: {result.get('error')}")
    
    return {
        'total_teams': len(all_teams),
        'successful': successful,
        'failed': failed,
        'errors': errors
    }


def get_leaderboard(stage_id='final_presentation', limit=None):
    """
    Get leaderboard with ranked teams
    
    Args:
        stage_id: Evaluation stage identifier
        limit: Optional limit on number of results
        
    Returns:
        list: Ranked team results
    """
    results = calculate_all_teams_scores(stage_id)
    
    if limit:
        return results[:limit]
    
    return results


def get_team_detailed_result(team_id, stage_id='final_presentation'):
    """
    Get detailed result breakdown for a specific team
    
    Args:
        team_id: Team's ObjectId (string)
        stage_id: Evaluation stage identifier
        
    Returns:
        dict: Detailed result with all evaluations
    """
    teams_col = get_teams_collection()
    evaluations_col = get_evaluations_collection()
    judges_col = get_judges_collection()
    users_col = get_users_collection()
    
    # Get team info
    team = teams_col.find_one({'_id': ObjectId(team_id)})
    if not team:
        return {'error': 'Team not found'}
    
    # Calculate score
    score_result = calculate_team_score(team_id, stage_id)
    
    if score_result.get('error'):
        return score_result
    
    # Get all evaluations with judge details
    evaluations = list(evaluations_col.find({
        'team_id': str(team_id),
        'stage_id': stage_id,
        'status': 'submitted'
    }))
    
    detailed_evaluations = []
    for evaluation in evaluations:
        jid = str(evaluation.get('judge_id', ''))
        judge = judges_col.find_one({'user_id': jid})
        user = None
        try:
            user = users_col.find_one({'_id': ObjectId(jid)})
        except Exception:
            user = None
        if not user and judge:
            user = users_col.find_one({'email': judge.get('email', '')})
        # Never drop a submitted score from the detail view just because the judge record is odd.
        # judge_type stays the internal/external badge; judge_bucket is the new
        # scoring axis. Two separate keys, so repurposing one does not silently
        # change what an existing badge means.
        stamped_type = str(evaluation.get('judge_type') or '').lower().replace('_judge', '')
        detailed_evaluations.append({
            'judge_name': (user or {}).get('name') or (judge or {}).get('name') or f'Judge {jid[:8]}',
            'judge_type': judge_kind(judge) if judge else (stamped_type or 'internal'),
            'judge_bucket': _evaluation_bucket(evaluation, judge),
            'panel_no': evaluation.get('panel_no') if evaluation.get('panel_no') is not None else judge_panel_no(judge),
            'weighted_total': evaluation.get('weighted_total', round(float(evaluation.get('weighted_score', 0)) * 10, 2)),
            'raw_scores': evaluation.get('raw_scores', {}),
            'comments': evaluation.get('comments', {}),
            'submitted_at': evaluation.get('submitted_at')
        })
    
    return {
        'team': team,
        'score_result': score_result,
        'evaluations': detailed_evaluations,
        'leaderboard_position': None  # Will be calculated when needed
    }


def get_evaluation_coverage():
    """
    Get statistics on evaluation coverage
    
    Returns:
        dict: Coverage statistics
    """
    teams_col = get_teams_collection()
    evaluations_col = get_evaluations_collection()
    judges_col = get_judges_collection()
    
    total_teams = teams_col.count_documents({})
    total_judges = judges_col.count_documents({})
    total_evaluations = evaluations_col.count_documents({'status': 'submitted'})

    # 'submitted' filter included on purpose: without it a team whose only
    # evaluation was reopened still counted as evaluated.
    teams_with_evaluations = evaluations_col.distinct('team_id', {'status': 'submitted'})
    teams_evaluated = len(teams_with_evaluations)
    teams_pending = total_teams - teams_evaluated

    # Bucket counts straight off the stamped evaluations - no judge lookup per
    # evaluation, which previously meant hundreds of round trips per render.
    exception_evaluations = evaluations_col.count_documents({
        'status': 'submitted', 'judge_bucket': BUCKET_EXCEPTION
    })
    group_evaluations = total_evaluations - exception_evaluations

    # Per-panel coverage, so "panel 3 has not started" is visible at a glance
    # instead of having to be inferred from a single global percentage.
    panel_counts = panel_judge_counts()
    panel_coverage = []
    for panel_no, judge_count in sorted(panel_counts.items()):
        panel_team_ids = [
            str(t['_id']) for t in teams_col.find({'panel_no': panel_no}, {'_id': 1})
        ]
        expected = judge_count * len(panel_team_ids)
        submitted = evaluations_col.count_documents({
            'status': 'submitted', 'team_id': {'$in': panel_team_ids}, 'panel_no': panel_no
        }) if panel_team_ids else 0
        panel_coverage.append({
            'panel_no': panel_no,
            'judges': judge_count,
            'teams': len(panel_team_ids),
            'submitted': submitted,
            'expected': expected,
            'pct': round(submitted / expected * 100) if expected else 0,
        })

    unassigned_teams = teams_col.count_documents(
        {'panel_no': {'$nin': list(range(1, len(panel_counts) + 1))}}
    )

    completion_percentage = (teams_evaluated / total_teams * 100) if total_teams > 0 else 0
    
    return {
        'total_teams': total_teams,
        'teams_evaluated': teams_evaluated,
        'teams_pending': teams_pending,
        'total_judges': total_judges,
        'total_evaluations': total_evaluations,
        'exception_evaluations': exception_evaluations,
        'group_evaluations': group_evaluations,
        'panel_coverage': panel_coverage,
        'unassigned_teams': unassigned_teams,
        'completion_percentage': round(completion_percentage, 2)
    }
