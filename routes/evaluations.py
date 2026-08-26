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
from services.jury_scope import can_evaluate, load_judge_for_session

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
    """Submit evaluation for a team.

    Mirrors the checks in judge.evaluate_team - a POST here is reachable
    directly, so it cannot rely on the form page having gated anything.
    """
    judge_id = session.get('user_id')
    team_id = request.form.get('team_id')
    stage_id = request.form.get('stage_id', 'final_presentation')

    judge = load_judge_for_session(judge_id, session.get('email'))
    if not judge:
        flash('Jury profile not found. Please sign in again.', 'error')
        return redirect(url_for('judge.login'))

    if not team_id:
        flash('Team ID is required', 'error')
        return redirect(url_for('judge.dashboard'))

    # team_id was previously passed straight through to the evaluation document,
    # so a POST with a bogus id inserted a score pointing at nothing - which then
    # inflated the "teams evaluated" coverage figure.
    try:
        team = get_teams_collection().find_one({'_id': ObjectId(team_id)})
    except Exception:
        team = None

    if not team:
        return render_template('errors/error.html',
                               code=404,
                               title='Team Not Found',
                               message="The requested team does not exist."), 404

    # Entitlement first, then the lock - same order as evaluate_team.
    #
    # Rendered as a 403 rather than the flash-and-redirect used elsewhere in this
    # handler: a redirect to the dashboard is indistinguishable from the judging
    # lock rejection below, and two different failures that look identical are
    # impossible to support during a live event.
    if not can_evaluate(judge, team):
        return render_template('errors/error.html',
                               code=403,
                               title='Not Your Panel',
                               message="This team is assigned to a different jury panel."), 403

    if not is_judging_allowed(judge):
        flash('Judging is currently locked. Please contact the administrator.', 'error')
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
        actor_id=judge_id,
        judge=judge
    )
    
    if result.get('error'):
        flash(result['error'], 'error')
        return redirect(request.referrer or url_for('judge.dashboard'))
    
    flash(f'Evaluation submitted successfully! Total Score: {result["weighted_total"]}/100', 'success')
    return redirect(url_for('judge.dashboard'))
