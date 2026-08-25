"""
Results Calculator Service
Calculates final scores with Internal 40% + External 60% weighting
"""

from datetime import datetime
from bson.objectid import ObjectId

from models.database import (
    get_teams_collection,
    get_evaluations_collection,
    get_judges_collection,
    get_team_results_collection
)
from services.audit import log_audit


# Official TechForge 3.0 Scoring Weights
INTERNAL_WEIGHT = 0.40
EXTERNAL_WEIGHT = 0.60


def _is_internal(judge):
    """judge_type is stored as 'INTERNAL_JUDGE'/'EXTERNAL_JUDGE' (legacy docs: 'internal'/'external')."""
    return 'internal' in str((judge or {}).get('judge_type', '')).lower()


def judge_kind(judge):
    return 'internal' if _is_internal(judge) else 'external'


def calculate_team_score(team_id, stage_id='final_presentation'):
    """
    Calculate final score for a team with Internal 40% + External 60% weighting
    
    Args:
        team_id: Team's ObjectId (string)
        stage_id: Evaluation stage identifier
        
    Returns:
        dict: Contains final_score, internal_avg, external_avg, and details
    """
    evaluations_col = get_evaluations_collection()
    judges_col = get_judges_collection()
    
    # Get all evaluations for this team
    evaluations = list(evaluations_col.find({
        'team_id': str(team_id),
        'stage_id': stage_id,
        'status': 'submitted'
    }))
    
    if not evaluations:
        return {
            'error': 'No evaluations found for this team',
            'final_score': 0,
            'evaluations_count': 0
        }
    
    # Separate internal and external evaluations
    internal_scores = []
    external_scores = []
    internal_details = []
    external_details = []
    
    for evaluation in evaluations:
        judge = judges_col.find_one({'user_id': evaluation['judge_id']})
        if not judge:
            continue
        
        score_data = {
            'judge_id': evaluation['judge_id'],
            'weighted_total': evaluation['weighted_total'],
            'submitted_at': evaluation['submitted_at']
        }
        
        if _is_internal(judge):
            internal_scores.append(evaluation['weighted_total'])
            internal_details.append(score_data)
        else:
            external_scores.append(evaluation['weighted_total'])
            external_details.append(score_data)
    
    # Calculate averages
    internal_avg = sum(internal_scores) / len(internal_scores) if internal_scores else 0
    external_avg = sum(external_scores) / len(external_scores) if external_scores else 0
    
    # Check completeness
    is_complete = (len(internal_scores) > 0 and len(external_scores) > 0)
    status = 'COMPLETE' if is_complete else 'INCOMPLETE'
    
    # Calculate criterion-level averages for tie-breaking
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
    
    # Calculate final weighted score
    final_score = (internal_avg * INTERNAL_WEIGHT) + (external_avg * EXTERNAL_WEIGHT)
    
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
        'status': status,
        'prototype_avg': round(prototype_avg, 2),
        'technical_avg': round(technical_avg, 2),
        'innovation_avg': round(innovation_avg, 2),
        'internal_details': internal_details,
        'external_details': external_details,
        'internal_weight': INTERNAL_WEIGHT,
        'external_weight': EXTERNAL_WEIGHT,
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
    
    results = []
    
    for team in all_teams:
        score_result = calculate_team_score(str(team['_id']), stage_id)
        
        # Only include teams with evaluations
        if not score_result.get('error'):
            results.append({
                'team_id': str(team['_id']),
                'team_code': team.get('team_code', ''),
                'team_name': team.get('team_name', ''),
                'leader_name': team.get('leader_name', ''),
                'theme_name': team.get('theme_name', ''),
                'final_score': score_result['final_score'],
                'internal_average': score_result['internal_average'],
                'external_average': score_result['external_average'],
                'internal_count': score_result['internal_count'],
                'external_count': score_result['external_count'],
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
    results.sort(key=lambda x: (
        1 if x['is_complete'] else 0,
        x['final_score'],
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
            'final_score': score_result['final_score']
        }
    )
    
    return {
        'success': True,
        'result_id': str(result_id),
        'final_score': score_result['final_score']
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
        judge = judges_col.find_one({'user_id': evaluation['judge_id']})
        user = users_col.find_one({'_id': ObjectId(evaluation['judge_id'])})
        
        if judge and user:
            detailed_evaluations.append({
                'judge_name': user['name'],
                'judge_type': judge_kind(judge),
                'weighted_total': evaluation['weighted_total'],
                'raw_scores': evaluation.get('raw_scores', {}),
                'comments': evaluation.get('comments', {}),
                'submitted_at': evaluation['submitted_at']
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
    
    # Count teams by evaluation status
    teams_with_evaluations = evaluations_col.distinct('team_id')
    teams_evaluated = len(teams_with_evaluations)
    teams_pending = total_teams - teams_evaluated
    
    # Count by judge type
    internal_count = evaluations_col.count_documents({
        'status': 'submitted'
    })
    
    internal_judges = 0
    external_judges = 0
    for eval_doc in evaluations_col.find({'status': 'submitted'}):
        judge = judges_col.find_one({'user_id': eval_doc['judge_id']})
        if judge:
            if _is_internal(judge):
                internal_judges += 1
            else:
                external_judges += 1
    
    completion_percentage = (teams_evaluated / total_teams * 100) if total_teams > 0 else 0
    
    return {
        'total_teams': total_teams,
        'teams_evaluated': teams_evaluated,
        'teams_pending': teams_pending,
        'total_judges': total_judges,
        'total_evaluations': total_evaluations,
        'internal_evaluations': internal_judges,
        'external_evaluations': external_judges,
        'completion_percentage': round(completion_percentage, 2)
    }
