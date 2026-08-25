from flask import Blueprint, render_template, session, request, redirect, url_for, flash, jsonify
from routes.auth import require_auth
from bson.objectid import ObjectId
from datetime import datetime

from models.database import (
    get_teams_collection,
    get_users_collection,
    get_judges_collection,
    get_judge_assignments_collection,
    get_evaluations_collection,
    get_jury_panels_collection,
    get_event_settings_collection,
    get_audit_logs_collection
)
from services.audit import log_audit
from services.judge_management import (
    create_judge,
    create_jury_panel,
    assign_judge_to_team,
    remove_judge_assignment
)

admin_bp = Blueprint('admin', __name__)


@admin_bp.route('/dashboard')
@require_auth(roles=['admin'])
def dashboard():
    """Admin dashboard with statistics"""
    teams = get_teams_collection()
    judges = get_judges_collection()
    assignments = get_judge_assignments_collection()
    evaluations = get_evaluations_collection()
    settings = get_event_settings_collection()
    
    # Get statistics
    stats = {
        'total_teams': teams.count_documents({}),
        'registered_teams': teams.count_documents({'status': 'registered'}),
        'internal_judges': judges.count_documents({'judge_type': 'internal'}),
        'external_judges': judges.count_documents({'judge_type': 'external'}),
        'total_assignments': assignments.count_documents({}),
        'evaluations_completed': evaluations.count_documents({'status': 'submitted'}),
        'evaluations_pending': assignments.count_documents({}) - evaluations.count_documents({'status': 'submitted'}),
    }
    
    # Calculate completion percentage
    if stats['total_assignments'] > 0:
        stats['completion_percentage'] = int((stats['evaluations_completed'] / stats['total_assignments']) * 100)
    else:
        stats['completion_percentage'] = 0
    
    # Get event settings
    event_settings = settings.find_one({})
    stats['judging_locked'] = event_settings.get('judging_locked', False) if event_settings else False
    stats['results_published'] = event_settings.get('results_published', False) if event_settings else False
    
    # Get recent teams
    recent_teams = list(teams.find().sort('created_at', -1).limit(5))
    
    return render_template('admin/dashboard.html', stats=stats, recent_teams=recent_teams)


@admin_bp.route('/teams')
@require_auth(roles=['admin'])
def teams_list():
    """List all teams"""
    teams = get_teams_collection()
    all_teams = list(teams.find().sort('created_at', -1))
    
    return render_template('admin/teams.html', teams=all_teams)


@admin_bp.route('/teams/<team_id>')
@require_auth(roles=['admin'])
def team_detail(team_id):
    """View team details"""
    teams = get_teams_collection()
    team = teams.find_one({'_id': ObjectId(team_id)})
    
    if not team:
        flash('Team not found', 'error')
        return redirect(url_for('admin.teams_list'))
    
    # Get team evaluations
    evaluations = get_evaluations_collection()
    team_evaluations = list(evaluations.find({'team_id': team_id}))
    
    # Get judge assignments
    assignments = get_judge_assignments_collection()
    judges_col = get_judges_collection()
    users_col = get_users_collection()
    
    team_assignments = list(assignments.find({'team_id': team_id}))
    for assignment in team_assignments:
        judge = judges_col.find_one({'_id': ObjectId(assignment['judge_id'])})
        if judge:
            user = users_col.find_one({'_id': ObjectId(judge['user_id'])})
            assignment['judge_name'] = user['name'] if user else 'Unknown'
            assignment['judge_type'] = judge['judge_type']
    
    return render_template('admin/team_detail.html', 
                         team=team, 
                         evaluations=team_evaluations,
                         assignments=team_assignments)


@admin_bp.route('/judges')
@require_auth(roles=['admin'])
def judges_list():
    """List all judges"""
    judges_col = get_judges_collection()
    users_col = get_users_collection()
    assignments_col = get_judge_assignments_collection()
    
    all_judges = list(judges_col.find().sort('created_at', -1))
    
    # Enrich with user data and assignment count
    for judge in all_judges:
        user = users_col.find_one({'_id': ObjectId(judge['user_id'])})
        if user:
            judge['name'] = user['name']
            judge['email'] = user['email']
        
        judge['assignment_count'] = assignments_col.count_documents({'judge_id': str(judge['_id'])})
    
    return render_template('admin/judges.html', judges=all_judges)


@admin_bp.route('/panels')
@require_auth(roles=['admin'])
def panels_list():
    """List all jury panels"""
    panels_col = get_jury_panels_collection()
    all_panels = list(panels_col.find().sort('created_at', -1))
    
    return render_template('admin/panels.html', panels=all_panels)


@admin_bp.route('/settings')
@require_auth(roles=['admin'])
def settings():
    """Event settings"""
    settings_col = get_event_settings_collection()
    event_settings = settings_col.find_one({})
    
    if not event_settings:
        event_settings = {
            'judging_locked': False,
            'results_published': False,
            'registration_open': True
        }
    
    return render_template('admin/settings.html', settings=event_settings)



@admin_bp.route('/judges/create', methods=['GET', 'POST'])
@require_auth(roles=['admin'])
def create_judge_form():
    """Create new judge"""
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        phone = request.form.get('phone', '').strip()
        judge_type = request.form.get('judge_type')
        panel_id = request.form.get('panel_id', '').strip() or None
        
        if not all([name, email, judge_type]):
            flash('Name, email, and judge type are required', 'error')
            return render_template('admin/create_judge.html')
        
        result = create_judge(
            name=name,
            email=email,
            phone=phone,
            judge_type=judge_type,
            panel_id=panel_id,
            actor_id=session.get('user_id')
        )
        
        if result.get('error'):
            flash(result['error'], 'error')
            return render_template('admin/create_judge.html')
        
        flash(f'Judge created successfully! Default password: {result["default_password"]}', 'success')
        return redirect(url_for('admin.judges_list'))
    
    # GET request - show form
    panels_col = get_jury_panels_collection()
    panels = list(panels_col.find())
    return render_template('admin/create_judge.html', panels=panels)


@admin_bp.route('/panels/create', methods=['GET', 'POST'])
@require_auth(roles=['admin'])
def create_panel_form():
    """Create new jury panel"""
    if request.method == 'POST':
        panel_name = request.form.get('panel_name', '').strip()
        panel_id = request.form.get('panel_id', '').strip()
        coordinator_name = request.form.get('coordinator_name', '').strip()
        description = request.form.get('description', '').strip()
        
        if not all([panel_name, panel_id]):
            flash('Panel name and ID are required', 'error')
            return render_template('admin/create_panel.html')
        
        result = create_jury_panel(
            panel_name=panel_name,
            panel_id=panel_id,
            coordinator_name=coordinator_name or None,
            description=description or None,
            actor_id=session.get('user_id')
        )
        
        if result.get('error'):
            flash(result['error'], 'error')
            return render_template('admin/create_panel.html')
        
        flash('Jury panel created successfully!', 'success')
        return redirect(url_for('admin.panels_list'))
    
    return render_template('admin/create_panel.html')


@admin_bp.route('/assignments')
@require_auth(roles=['admin'])
def assignments_management():
    """Manage judge-team assignments"""
    teams_col = get_teams_collection()
    judges_col = get_judges_collection()
    users_col = get_users_collection()
    assignments_col = get_judge_assignments_collection()
    
    # Get all teams
    all_teams = list(teams_col.find().sort('team_name', 1))
    
    # Get all judges with user info
    all_judges = list(judges_col.find())
    for judge in all_judges:
        user = users_col.find_one({'_id': ObjectId(judge['user_id'])})
        if user:
            judge['name'] = user['name']
            judge['email'] = user['email']
    
    # Get all assignments
    all_assignments = list(assignments_col.find())
    
    return render_template('admin/assignments.html',
                         teams=all_teams,
                         judges=all_judges,
                         assignments=all_assignments)


@admin_bp.route('/assignments/create', methods=['POST'])
@require_auth(roles=['admin'])
def create_assignment():
    """Create judge-team assignment"""
    judge_id = request.form.get('judge_id')
    team_id = request.form.get('team_id')
    
    if not all([judge_id, team_id]):
        flash('Judge and team selection are required', 'error')
        return redirect(url_for('admin.assignments_management'))
    
    result = assign_judge_to_team(
        judge_id=judge_id,
        team_id=team_id,
        actor_id=session.get('user_id')
    )
    
    if result.get('error'):
        flash(result['error'], 'error')
    else:
        flash('Judge assigned successfully!', 'success')
    
    return redirect(url_for('admin.assignments_management'))


@admin_bp.route('/assignments/<assignment_id>/delete', methods=['POST'])
@require_auth(roles=['admin'])
def delete_assignment(assignment_id):
    """Remove a judge-team assignment"""
    result = remove_judge_assignment(assignment_id, actor_id=session.get('user_id'))
    
    if result.get('error'):
        flash(result['error'], 'error')
    else:
        flash('Assignment removed successfully', 'success')
    
    return redirect(url_for('admin.assignments_management'))



@admin_bp.route('/audit-logs')
@require_auth(roles=['admin'])
def audit_logs():
    """View audit logs"""
    audit_logs_col = get_audit_logs_collection()
    users_col = get_users_collection()
    
    # Pagination
    page = int(request.args.get('page', 1))
    per_page = 50
    skip = (page - 1) * per_page
    
    # Filters
    action_filter = request.args.get('action', '')
    entity_filter = request.args.get('entity_type', '')
    
    # Build query
    query = {}
    if action_filter:
        query['action'] = action_filter
    if entity_filter:
        query['entity_type'] = entity_filter
    
    # Get logs
    total_logs = audit_logs_col.count_documents(query)
    logs = list(audit_logs_col.find(query).sort('created_at', -1).skip(skip).limit(per_page))
    
    # Add actor names
    for log in logs:
        if log.get('actor_id'):
            user = users_col.find_one({'_id': ObjectId(log['actor_id'])})
            log['actor_name'] = user['name'] if user else 'Unknown'
        else:
            log['actor_name'] = 'System'
    
    # Get unique actions and entity types for filters
    all_actions = audit_logs_col.distinct('action')
    all_entity_types = audit_logs_col.distinct('entity_type')
    
    total_pages = (total_logs + per_page - 1) // per_page
    
    return render_template('admin/audit_logs.html',
                         logs=logs,
                         total_logs=total_logs,
                         page=page,
                         total_pages=total_pages,
                         per_page=per_page,
                         all_actions=all_actions,
                         all_entity_types=all_entity_types,
                         action_filter=action_filter,
                         entity_filter=entity_filter)



@admin_bp.route('/checkpoints')
@require_auth(roles=['admin'])
def checkpoints_management():
    """Manage evaluation checkpoints and judging lock"""
    from services.checkpoint_manager import (
        get_judging_status,
        get_all_stages,
        get_active_stage,
        get_checkpoint_stats
    )
    
    # Get judging status
    judging_status = get_judging_status()
    
    # Get all stages
    stages = get_all_stages()
    
    # Add stats to each stage
    for stage in stages:
        stage['stats'] = get_checkpoint_stats(stage['stage_id'])
    
    # Get active stage
    active_stage = get_active_stage()
    
    return render_template('admin/checkpoints.html',
                         judging_status=judging_status,
                         stages=stages,
                         active_stage=active_stage)


@admin_bp.route('/checkpoints/lock', methods=['POST'])
@require_auth(roles=['admin'])
def lock_judging_system():
    """Lock judging system"""
    from services.checkpoint_manager import lock_judging
    
    reason = request.form.get('reason', '').strip()
    actor_id = session.get('user_id')
    
    result = lock_judging(reason=reason, actor_id=actor_id)
    
    if result.get('success'):
        flash('Judging system has been locked', 'success')
    else:
        flash(result.get('error', 'Failed to lock judging'), 'error')
    
    return redirect(url_for('admin.checkpoints_management'))


@admin_bp.route('/checkpoints/unlock', methods=['POST'])
@require_auth(roles=['admin'])
def unlock_judging_system():
    """Unlock judging system"""
    from services.checkpoint_manager import unlock_judging
    
    actor_id = session.get('user_id')
    
    result = unlock_judging(actor_id=actor_id)
    
    if result.get('success'):
        flash('Judging system has been unlocked', 'success')
    else:
        flash(result.get('error', 'Failed to unlock judging'), 'error')
    
    return redirect(url_for('admin.checkpoints_management'))


@admin_bp.route('/checkpoints/activate/<stage_id>', methods=['POST'])
@require_auth(roles=['admin'])
def activate_stage(stage_id):
    """Set a stage as active"""
    from services.checkpoint_manager import set_active_stage
    
    actor_id = session.get('user_id')
    
    result = set_active_stage(stage_id, actor_id=actor_id)
    
    if result.get('success'):
        flash(f'Stage "{result["stage_name"]}" is now active', 'success')
    else:
        flash(result.get('error', 'Failed to activate stage'), 'error')
    
    return redirect(url_for('admin.checkpoints_management'))


@admin_bp.route('/settings/toggle-judging', methods=['POST'])
@require_auth(roles=['admin'])
def toggle_judging():
    """Toggle judging lock/unlock from settings page"""
    settings_col = get_event_settings_collection()
    event_settings = settings_col.find_one({})
    if not event_settings:
        settings_col.insert_one({'judging_locked': False, 'results_published': False, 'registration_open': True})
        event_settings = settings_col.find_one({})
    current_locked = event_settings.get('judging_locked', False)
    new_locked = not current_locked
    settings_col.update_one({}, {'$set': {'judging_locked': new_locked, 'judging_locked_at': datetime.utcnow()}})
    log_audit(session.get('user_id'), 'judging_locked' if new_locked else 'judging_unlocked', 'event_settings', str(event_settings['_id']), {'locked': new_locked})
    flash(f'Judging has been {"locked" if new_locked else "unlocked"}', 'success')
    return redirect(url_for('admin.settings'))


@admin_bp.route('/settings/toggle-results', methods=['POST'])
@require_auth(roles=['admin'])
def toggle_results():
    """Toggle results publication"""
    settings_col = get_event_settings_collection()
    event_settings = settings_col.find_one({})
    if not event_settings:
        settings_col.insert_one({'judging_locked': False, 'results_published': False, 'registration_open': True})
        event_settings = settings_col.find_one({})
    current_published = event_settings.get('results_published', False)
    new_published = not current_published
    settings_col.update_one({}, {'$set': {'results_published': new_published, 'results_published_at': datetime.utcnow()}})
    log_audit(session.get('user_id'), 'results_published' if new_published else 'results_unpublished', 'event_settings', str(event_settings['_id']), {'published': new_published})
    flash(f'Results have been {"published" if new_published else "unpublished"}', 'success')
    return redirect(url_for('admin.settings'))


@admin_bp.route('/settings/toggle-registration', methods=['POST'])
@require_auth(roles=['admin'])
def toggle_registration():
    """Toggle registration open/closed"""
    settings_col = get_event_settings_collection()
    event_settings = settings_col.find_one({})
    if not event_settings:
        settings_col.insert_one({'judging_locked': False, 'results_published': False, 'registration_open': True})
        event_settings = settings_col.find_one({})
    current_open = event_settings.get('registration_open', True)
    new_open = not current_open
    settings_col.update_one({}, {'$set': {'registration_open': new_open}})
    flash(f'Registration has been {"opened" if new_open else "closed"}', 'success')
    return redirect(url_for('admin.settings'))


@admin_bp.route('/evaluations/<evaluation_id>/reopen', methods=['POST'])
@require_auth(roles=['admin'])
def reopen_evaluation(evaluation_id):
    """Reopen a submitted evaluation"""
    evaluations_col = get_evaluations_collection()
    try:
        evaluation = evaluations_col.find_one({'_id': ObjectId(evaluation_id)})
    except Exception:
        flash('Invalid evaluation ID', 'error')
        return redirect(url_for('admin.teams_list'))
    if not evaluation:
        flash('Evaluation not found', 'error')
        return redirect(url_for('admin.teams_list'))
    if evaluation.get('status') != 'submitted':
        flash('Only submitted evaluations can be reopened', 'error')
        return redirect(url_for('admin.team_detail', team_id=evaluation.get('team_id', '')))
    evaluations_col.update_one(
        {'_id': ObjectId(evaluation_id)},
        {
            '$set': {'status': 'reopened', 'reopened_at': datetime.utcnow(), 'reopened_by': session.get('user_id')},
            '$push': {'submission_history': {'weighted_total': evaluation.get('weighted_total'), 'raw_scores': evaluation.get('raw_scores', {}), 'submitted_at': evaluation.get('submitted_at'), 'archived_at': datetime.utcnow()}}
        }
    )
    log_audit(session.get('user_id'), 'evaluation_reopened', 'evaluation', evaluation_id, {'team_id': evaluation.get('team_id'), 'judge_id': evaluation.get('judge_id'), 'previous_score': evaluation.get('weighted_total')})
    flash('Evaluation has been reopened for re-submission', 'success')
    return redirect(url_for('admin.team_detail', team_id=evaluation.get('team_id', '')))


@admin_bp.route('/export/results')
@require_auth(roles=['admin'])
def export_results():
    """Export results as CSV"""
    import csv
    import io
    from flask import Response
    from services.results_calculator import get_leaderboard
    stage_id = request.args.get('stage_id', 'final_presentation')
    rankings = get_leaderboard(stage_id)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Rank', 'Team Code', 'Team Name', 'Leader Name', 'Internal Average (0-100)', 'External Average (0-100)', 'Final Score (0-100)', 'Internal Evaluations', 'External Evaluations', 'Stage'])
    for team in rankings:
        writer.writerow([team.get('rank',''), team.get('team_code',''), team.get('team_name',''), team.get('leader_name',''), team.get('internal_average','INCOMPLETE'), team.get('external_average','INCOMPLETE'), team.get('final_score',''), team.get('internal_count',0), team.get('external_count',0), stage_id])
    log_audit(session.get('user_id'), 'results_exported', 'results', stage_id, {'format': 'csv', 'count': len(rankings)})
    output.seek(0)
    return Response(output.getvalue(), mimetype='text/csv', headers={'Content-Disposition': f'attachment;filename=techforge3_results_{stage_id}.csv'})


@admin_bp.route('/export/teams')
@require_auth(roles=['admin'])
def export_teams():
    """Export team registrations as CSV"""
    import csv
    import io
    from flask import Response
    teams_col = get_teams_collection()
    all_teams = list(teams_col.find().sort('created_at', 1))
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Team Code', 'Team Name', 'Leader Name', 'Leader Email', 'Leader Mobile', 'Status', 'Registered At'])
    for team in all_teams:
        created_at = team.get('created_at')
        writer.writerow([team.get('team_code',''), team.get('team_name',''), team.get('leader_name',''), team.get('leader_email',''), team.get('leader_mobile',''), team.get('status',''), created_at.strftime('%Y-%m-%d %H:%M') if created_at else ''])
    output.seek(0)
    return Response(output.getvalue(), mimetype='text/csv', headers={'Content-Disposition': 'attachment;filename=techforge3_teams.csv'})


@admin_bp.route('/evaluations-list')
@require_auth(roles=['admin'])
def evaluations_list():
    """List all submitted evaluations"""
    evaluations_col = get_evaluations_collection()
    judges_col = get_judges_collection()
    users_col = get_users_collection()
    teams_col = get_teams_collection()
    page = int(request.args.get('page', 1))
    per_page = 25
    skip = (page - 1) * per_page
    status_filter = request.args.get('status', '')
    query = {}
    if status_filter:
        query['status'] = status_filter
    total = evaluations_col.count_documents(query)
    evaluations = list(evaluations_col.find(query).sort('submitted_at', -1).skip(skip).limit(per_page))
    for ev in evaluations:
        judge = judges_col.find_one({'user_id': ev.get('judge_id', '')})
        if judge:
            try:
                user = users_col.find_one({'_id': ObjectId(ev['judge_id'])})
                ev['judge_name'] = user['name'] if user else 'Unknown'
            except Exception:
                ev['judge_name'] = 'Unknown'
            ev['judge_type'] = judge['judge_type']
        else:
            ev['judge_name'] = 'Unknown'
            ev['judge_type'] = 'unknown'
        try:
            team = teams_col.find_one({'_id': ObjectId(ev.get('team_id', ''))}) if ev.get('team_id') else None
            ev['team_name'] = team['team_name'] if team else 'Unknown'
        except Exception:
            ev['team_name'] = 'Unknown'
    total_pages = (total + per_page - 1) // per_page
    return render_template('admin/evaluations_list.html', evaluations=evaluations, total=total, page=page, total_pages=total_pages, status_filter=status_filter)


@admin_bp.route('/results-overview')
@require_auth(roles=['admin'])
def results_overview():
    """Admin results overview with rankings"""
    from services.results_calculator import get_leaderboard, get_evaluation_coverage
    stage_id = request.args.get('stage_id', 'final_presentation')
    settings_col = get_event_settings_collection()
    event_settings = settings_col.find_one({}) or {}
    rankings = get_leaderboard(stage_id)
    coverage = get_evaluation_coverage()
    return render_template('admin/results_overview.html', rankings=rankings, coverage=coverage, stage_id=stage_id, event_settings=event_settings)
