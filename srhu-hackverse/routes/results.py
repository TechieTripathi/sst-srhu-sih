from flask import Blueprint, render_template, session, request, redirect, url_for, flash, jsonify
from routes.auth import require_auth
from bson.objectid import ObjectId

from models.database import get_teams_collection
from services.results_calculator import (
    calculate_team_score,
    calculate_all_teams_scores,
    get_leaderboard,
    get_team_detailed_result,
    recalculate_all_results,
    get_evaluation_coverage
)

results_bp = Blueprint('results', __name__)


@results_bp.route('/leaderboard')
@require_auth(roles=['admin', 'internal_judge', 'external_judge'])
def leaderboard():
    """View leaderboard with team rankings"""
    stage_id = request.args.get('stage_id', 'final_presentation')
    
    # Get leaderboard
    rankings = get_leaderboard(stage_id)
    
    # Get coverage statistics
    coverage = get_evaluation_coverage()
    
    return render_template('results/leaderboard.html',
                         rankings=rankings,
                         coverage=coverage,
                         stage_id=stage_id)


@results_bp.route('/team/<team_id>')
@require_auth(roles=['admin'])
def team_result(team_id):
    """View detailed result for a specific team"""
    stage_id = request.args.get('stage_id', 'final_presentation')
    
    result = get_team_detailed_result(team_id, stage_id)
    
    if result.get('error'):
        flash(result['error'], 'error')
        return redirect(url_for('results.leaderboard'))
    
    # Get team's position in leaderboard
    leaderboard_data = get_leaderboard(stage_id)
    for idx, team_rank in enumerate(leaderboard_data, 1):
        if team_rank['team_id'] == team_id:
            result['leaderboard_position'] = idx
            break
    
    return render_template('results/team_detail.html',
                         result=result,
                         stage_id=stage_id)


@results_bp.route('/recalculate', methods=['POST'])
@require_auth(roles=['admin'])
def recalculate():
    """Recalculate all results (Admin only)"""
    stage_id = request.form.get('stage_id', 'final_presentation')
    actor_id = session.get('user_id')
    
    result = recalculate_all_results(stage_id, actor_id)
    
    flash(f'Results recalculated: {result["successful"]} successful, {result["failed"]} failed', 'success')
    
    if result['errors']:
        for error in result['errors'][:5]:  # Show first 5 errors
            flash(error, 'warning')
    
    return redirect(url_for('results.leaderboard'))


@results_bp.route('/api/team/<team_id>/score')
@require_auth(roles=['admin', 'internal_judge', 'external_judge'])
def api_team_score(team_id):
    """API endpoint to get team score"""
    stage_id = request.args.get('stage_id', 'final_presentation')
    
    score_result = calculate_team_score(team_id, stage_id)
    
    if score_result.get('error'):
        return jsonify({'error': score_result['error']}), 404
    
    return jsonify(score_result), 200
