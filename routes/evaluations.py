from flask import Blueprint, render_template, session, request, redirect, url_for, flash, jsonify
from routes.auth import require_auth
from bson.objectid import ObjectId

from models.database import (
    get_teams_collection,
    get_judges_collection,
    get_users_collection
)
from services.scoring import (
    create_evaluation,
    get_judge_evaluations,
    check_evaluation_exists,
    preview_score,
    get_criteria_config,
    OFFICIAL_CRITERIA
)
from services.checkpoint_manager import is_judging_allowed

evaluations_bp = Blueprint('evaluations', __name__)


@evaluations_bp.route('/preview', methods=['POST'])
@require_auth(roles=['internal_judge', 'external_judge', 'admin'])
def preview_evaluation_score():
    """API endpoint to preview weighted score"""
    try:
        data = request.get_json()
        raw_scores = data.get('scores', {})
        
        result = preview_score(raw_scores)
        
        if result.get('error'):
            return jsonify({'error': result['error']}), 400
        
        return jsonify(result), 200
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@evaluations_bp.route('/submit', methods=['POST'])
@require_auth(roles=['internal_judge', 'external_judge'])
def submit_evaluation():
    """Submit evaluation for a team"""
    
    # Check if judging is locked
    if not is_judging_allowed():
        flash('Judging is currently locked. Please contact the administrator.', 'error')
        return redirect(url_for('judge.dashboard'))
    judge_id = session.get('user_id')
    team_id = request.form.get('team_id')
    stage_id = request.form.get('stage_id', 'final_presentation')
    
    if not team_id:
        flash('Team ID is required', 'error')
        return redirect(url_for('judge.dashboard'))
    
    # Collect raw scores from form
    raw_scores = {}
    comments = {}
    
    for criterion_id in OFFICIAL_CRITERIA.keys():
        score = request.form.get(f'score_{criterion_id}')
        comment = request.form.get(f'comment_{criterion_id}', '').strip()
        
        if score:
            try:
                raw_scores[criterion_id] = float(score)
            except ValueError:
                flash(f'Invalid score for {criterion_id}', 'error')
                return redirect(request.referrer or url_for('judge.dashboard'))
        
        if comment:
            comments[criterion_id] = comment
    
    # Validate all criteria have scores
    if len(raw_scores) != len(OFFICIAL_CRITERIA):
        flash('Please provide scores for all criteria', 'error')
        return redirect(request.referrer or url_for('judge.dashboard'))
    
    # Create evaluation
    result = create_evaluation(
        judge_id=judge_id,
        team_id=team_id,
        stage_id=stage_id,
        raw_scores=raw_scores,
        comments=comments,
        actor_id=judge_id
    )
    
    if result.get('error'):
        flash(result['error'], 'error')
        return redirect(request.referrer or url_for('judge.dashboard'))
    
    flash(f'Evaluation submitted successfully! Total Score: {result["weighted_total"]}/100', 'success')
    return redirect(url_for('judge.dashboard'))
