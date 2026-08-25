"""
Scoring Service
Handles evaluation scoring calculations with official TechForge 3.0 criteria
"""

from datetime import datetime
from bson.objectid import ObjectId

from models.database import (
    get_evaluations_collection,
    get_evaluation_criteria_collection
)
from services.audit import log_audit


# Official TechForge 3.0 Evaluation Criteria Weights
OFFICIAL_CRITERIA = {
    'problem_understanding': {
        'name': 'Problem Understanding & Relevance',
        'weight': 0.15,
        'description': 'Clarity of problem statement, relevance to theme, and understanding of target audience'
    },
    'innovation': {
        'name': 'Innovation & Differentiation',
        'weight': 0.15,
        'description': 'Uniqueness of idea, creative approach, and competitive differentiation'
    },
    'technical_design': {
        'name': 'Technical Design & Feasibility',
        'weight': 0.20,
        'description': 'Architecture quality, technology choices, and implementation feasibility'
    },
    'prototype': {
        'name': 'Prototype & Implementation',
        'weight': 0.25,
        'description': 'Working prototype, code quality, and feature completeness'
    },
    'impact': {
        'name': 'Impact, Scalability & Sustainability',
        'weight': 0.15,
        'description': 'Potential impact, scalability considerations, and long-term sustainability'
    },
    'presentation': {
        'name': 'Presentation & Team Response',
        'weight': 0.10,
        'description': 'Clarity of presentation, communication skills, and response to questions'
    }
}


def validate_scores(scores_dict):
    """
    Validate that all scores are within 0-10 range
    
    Args:
        scores_dict: Dictionary with criterion_id as key and score as value
        
    Returns:
        tuple: (is_valid, error_message)
    """
    if not scores_dict:
        return False, "No scores provided"
    
    for criterion_id, score in scores_dict.items():
        try:
            score_value = float(score)
            if score_value < 0 or score_value > 10:
                return False, f"Score for {criterion_id} must be between 0 and 10"
        except (ValueError, TypeError):
            return False, f"Invalid score value for {criterion_id}"
    
    return True, None


def calculate_weighted_score(raw_scores, criteria_weights=None):
    """
    Calculate weighted total score from raw scores
    
    Args:
        raw_scores: Dictionary with criterion_id as key and raw score (0-10) as value
        criteria_weights: Optional dictionary of weights (uses official if not provided)
        
    Returns:
        dict: Contains weighted_score (0-100) and breakdown by criterion
    """
    if criteria_weights is None:
        criteria_weights = {k: v['weight'] for k, v in OFFICIAL_CRITERIA.items()}
    
    weighted_total = 0.0
    breakdown = {}
    
    for criterion_id, raw_score in raw_scores.items():
        weight = criteria_weights.get(criterion_id, 0)
        weighted_value = float(raw_score) * weight * 10  # Multiply by 10 to get 0-100 scale
        weighted_total += weighted_value
        
        breakdown[criterion_id] = {
            'raw_score': float(raw_score),
            'weight': weight,
            'weighted_score': round(weighted_value, 2)
        }
    
    return {
        'weighted_total': round(weighted_total, 2),
        'breakdown': breakdown
    }


def create_evaluation(judge_id, team_id, stage_id, raw_scores, comments=None, actor_id=None):
    """
    Create a new evaluation with calculated weighted score
    
    Args:
        judge_id: Judge's user ID
        team_id: Team's ObjectId
        stage_id: Evaluation stage identifier
        raw_scores: Dictionary of criterion_id: score (0-10)
        comments: Optional dictionary of criterion_id: comment
        actor_id: User ID performing this action
        
    Returns:
        dict: Created evaluation or error
    """
    evaluations_col = get_evaluations_collection()
    
    # Validate scores
    is_valid, error = validate_scores(raw_scores)
    if not is_valid:
        return {'error': error}
    
    # Check for duplicate evaluation
    existing = evaluations_col.find_one({
        'judge_id': judge_id,
        'team_id': str(team_id),
        'stage_id': stage_id
    })
    
    if existing and existing.get('status') != 'reopened':
        return {'error': 'You have already evaluated this team at this stage'}

    # Calculate weighted score
    scoring_result = calculate_weighted_score(raw_scores)

    if existing:
        # Reopened by an admin: replace the scores in place (the unique index on
        # judge/team/stage forbids a second document) and keep the old ones in history.
        now = datetime.utcnow()
        evaluations_col.update_one({'_id': existing['_id']}, {
            '$set': {
                'raw_scores': raw_scores,
                'comments': comments or {},
                'weighted_total': scoring_result['weighted_total'],
                'score_breakdown': scoring_result['breakdown'],
                'status': 'submitted',
                'submitted_at': now,
                'resubmitted_at': now,
            },
            '$unset': {'reopened_at': '', 'reopened_by': ''}
        })
        log_audit(actor_id or judge_id, 'evaluation_resubmitted', 'evaluation', str(existing['_id']),
                  {'judge_id': judge_id, 'team_id': str(team_id), 'stage_id': stage_id,
                   'weighted_total': scoring_result['weighted_total'], 'previous_total': existing.get('weighted_total')})
        return {'success': True, 'evaluation_id': str(existing['_id']), 'weighted_total': scoring_result['weighted_total']}
    
    # Prepare evaluation document
    evaluation_data = {
        'judge_id': judge_id,
        'team_id': str(team_id),
        'stage_id': stage_id,
        'raw_scores': raw_scores,
        'comments': comments or {},
        'weighted_total': scoring_result['weighted_total'],
        'score_breakdown': scoring_result['breakdown'],
        'status': 'submitted',
        'submitted_at': datetime.utcnow(),
        'created_at': datetime.utcnow()
    }
    
    evaluation_id = evaluations_col.insert_one(evaluation_data).inserted_id
    
    # Log audit
    log_audit(
        actor_id or judge_id,
        'evaluation_submitted',
        'evaluation',
        str(evaluation_id),
        {
            'judge_id': judge_id,
            'team_id': str(team_id),
            'stage_id': stage_id,
            'weighted_total': scoring_result['weighted_total']
        }
    )
    
    return {
        'success': True,
        'evaluation_id': str(evaluation_id),
        'weighted_total': scoring_result['weighted_total']
    }


def get_evaluation(evaluation_id):
    """
    Get a specific evaluation by ID
    
    Args:
        evaluation_id: Evaluation's ObjectId (string)
        
    Returns:
        dict: Evaluation document or None
    """
    evaluations_col = get_evaluations_collection()
    return evaluations_col.find_one({'_id': ObjectId(evaluation_id)})


def get_judge_evaluations(judge_id, team_id=None, stage_id=None):
    """
    Get evaluations by a specific judge
    
    Args:
        judge_id: Judge's user ID
        team_id: Optional team filter
        stage_id: Optional stage filter
        
    Returns:
        list: List of evaluation documents
    """
    evaluations_col = get_evaluations_collection()
    
    query = {'judge_id': judge_id}
    if team_id:
        query['team_id'] = str(team_id)
    if stage_id:
        query['stage_id'] = stage_id
    
    return list(evaluations_col.find(query).sort('submitted_at', -1))


def get_team_evaluations(team_id, stage_id=None):
    """
    Get all evaluations for a specific team
    
    Args:
        team_id: Team's ObjectId (string)
        stage_id: Optional stage filter
        
    Returns:
        list: List of evaluation documents
    """
    evaluations_col = get_evaluations_collection()
    
    query = {'team_id': str(team_id)}
    if stage_id:
        query['stage_id'] = stage_id
    
    return list(evaluations_col.find(query).sort('submitted_at', -1))


def check_evaluation_exists(judge_id, team_id, stage_id):
    """
    Check if an evaluation already exists
    
    Args:
        judge_id: Judge's user ID
        team_id: Team's ObjectId (string)
        stage_id: Stage identifier
        
    Returns:
        bool: True if evaluation exists
    """
    evaluations_col = get_evaluations_collection()
    
    existing = evaluations_col.find_one({
        'judge_id': judge_id,
        'team_id': str(team_id),
        'stage_id': stage_id
    })
    # A reopened evaluation must be scored again, so it does not count as existing.
    return existing is not None and existing.get('status') != 'reopened'


def preview_score(raw_scores):
    """
    Preview weighted score without saving (for frontend preview)
    
    Args:
        raw_scores: Dictionary of criterion_id: score (0-10)
        
    Returns:
        dict: Scoring preview with weighted total and breakdown
    """
    is_valid, error = validate_scores(raw_scores)
    if not is_valid:
        return {'error': error}
    
    return calculate_weighted_score(raw_scores)


def get_criteria_config():
    """
    Get official evaluation criteria configuration
    
    Returns:
        dict: Criteria configuration with weights
    """
    return OFFICIAL_CRITERIA
