"""
TechForge 3.0 — Jury Routes
Handles Jury Login, Jury Dashboard (Internal/External), and Assignment-Guarded Evaluation.
"""

from flask import Blueprint, render_template, session, request, redirect, url_for, flash, jsonify
from bson.objectid import ObjectId

from routes.auth import require_auth
from models.database import (
    get_users_collection,
    get_judges_collection,
    get_teams_collection,
    get_judge_assignments_collection
)
from services.judge_management import get_judge_assignments
from services.scoring import (
    get_judge_evaluations,
    check_evaluation_exists,
    OFFICIAL_CRITERIA
)
from services.checkpoint_manager import get_judging_status
from services.otp_service import authenticate_jury_credentials

judge_bp = Blueprint('judge', __name__)


@judge_bp.route('/login', methods=['GET', 'POST'])
def login():
    """
    Jury Login Portal (Email + Password)
    No OTP required for normal login.
    """
    if 'user_id' in session:
        role = str(session.get('role', '')).lower()
        if role in ['judge', 'internal_judge', 'external_judge']:
            return redirect(url_for('judge.dashboard'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        if not email or not password:
            flash('Please provide both email and password.', 'error')
            return render_template('judge/login.html')

        result = authenticate_jury_credentials(email, password, request.remote_addr)
        if result.get('success'):
            session.permanent = True
            session['user_id'] = result['user_id']
            session['email'] = result['email']
            session['name'] = result['name']
            session['role'] = 'judge'
            session['judge_type'] = result.get('judge_type', 'INTERNAL_JUDGE')
            if result.get('panel_id'):
                session['panel_id'] = result['panel_id']
            flash('Welcome back! You have successfully logged in.', 'success')
            return redirect(url_for('judge.dashboard'))
        else:
            flash(result.get('message', 'Invalid email or password.'), 'error')
            return render_template('judge/login.html')

    return render_template('judge/login.html')


@judge_bp.route('/dashboard')
@require_auth(roles=['judge', 'internal_judge', 'external_judge'])
def dashboard():
    """
    Jury Dashboard
    Displays Internal / External Jury portal with panel information,
    summary metrics, and strictly authorized assigned teams.
    """
    user_id = session.get('user_id')
    users_col = get_users_collection()
    judges_col = get_judges_collection()
    
    # 1. Fetch user & judge record
    user = None
    try:
        user = users_col.find_one({'_id': ObjectId(user_id)})
    except Exception:
        pass
    
    judge = judges_col.find_one({'user_id': user_id})
    if not judge and user:
        judge = judges_col.find_one({'email': user.get('email', '').lower()})
    
    if not judge:
        # Fallback query if user_id was stored as string or object ID
        judge = judges_col.find_one({'email': session.get('email', '').lower()})

    if not judge:
        flash('Jury profile not found. Please log in again.', 'error')
        return redirect(url_for('judge.login'))
    
    # Determine judge type and panel
    raw_type = judge.get('judge_type', 'INTERNAL_JUDGE')
    if 'external' in str(raw_type).lower():
        judge_type = 'EXTERNAL_JUDGE'
        judge_type_display = 'External Jury'
    else:
        judge_type = 'INTERNAL_JUDGE'
        judge_type_display = 'Internal Jury'
    
    panel_id = judge.get('panel_id') or session.get('panel_id') or 'PANEL_1'
    judge_db_id = str(judge['_id'])
    
    # 2. Query ONLY assigned teams from MongoDB
    assigned_teams = get_judge_assignments(judge_db_id)
    
    # 3. Query evaluations submitted by this judge
    evaluations = get_judge_evaluations(user_id)
    eval_map = {str(e.get('team_id')): e for e in evaluations}
    
    # Add evaluation status to teams
    completed_evals = 0
    total_score_sum = 0
    scored_eval_count = 0
    
    for team in assigned_teams:
        t_id = str(team['_id'])
        is_evaluated = check_evaluation_exists(user_id, t_id, 'final_presentation')
        team['evaluated'] = is_evaluated
        if is_evaluated:
            completed_evals += 1
            ev_doc = eval_map.get(t_id)
            if ev_doc and 'weighted_score' in ev_doc:
                total_score_sum += float(ev_doc['weighted_score'])
                scored_eval_count += 1
            elif ev_doc and 'total_score' in ev_doc:
                total_score_sum += float(ev_doc['total_score'])
                scored_eval_count += 1

    pending_evals = max(0, len(assigned_teams) - completed_evals)
    avg_score = round(total_score_sum / scored_eval_count, 1) if scored_eval_count > 0 else 0.0
    
    # Get judging lock status
    judging_status = get_judging_status()
    
    return render_template(
        'judge/dashboard.html',
        user=user or {'name': judge.get('name', 'Jury Member')},
        judge=judge,
        judge_type=judge_type,
        judge_type_display=judge_type_display,
        panel_id=panel_id,
        teams=assigned_teams,
        evaluations=evaluations,
        evaluations_count=completed_evals,
        pending_count=pending_evals,
        avg_score=avg_score,
        judging_status=judging_status
    )


@judge_bp.route('/evaluate/<team_id>')
@require_auth(roles=['judge', 'internal_judge', 'external_judge'])
def evaluate_team(team_id):
    """
    Evaluation form for a specific team.
    Strictly verifies that the logged-in judge is assigned to this team.
    Returns 403 Forbidden if unassigned.
    """
    user_id = session.get('user_id')
    users_col = get_users_collection()
    judges_col = get_judges_collection()
    teams_col = get_teams_collection()
    assignments_col = get_judge_assignments_collection()
    
    # Get user and judge info
    user = None
    try:
        user = users_col.find_one({'_id': ObjectId(user_id)})
    except Exception:
        pass
    
    judge = judges_col.find_one({'user_id': user_id})
    if not judge and user:
        judge = judges_col.find_one({'email': user.get('email', '').lower()})
    
    if not judge:
        flash('Jury profile not found', 'error')
        return redirect(url_for('judge.login'))

    # Get team info
    try:
        team = teams_col.find_one({'_id': ObjectId(team_id)})
    except Exception:
        team = None

    if not team:
        return render_template('errors/error.html',
                               code=404,
                               title='Team Not Found',
                               message="The requested team does not exist."), 404
    
    # CRITICAL AUTHORIZATION CHECK: Verify judge is assigned to this team in MongoDB
    assignment = assignments_col.find_one({
        'judge_id': str(judge['_id']),
        'team_id': team_id
    })
    
    if not assignment:
        # Return 403 Forbidden without leaking team info
        return render_template('errors/error.html',
                               code=403,
                               title='Access Forbidden',
                               message="You are not authorized to evaluate this team. Only assigned jury members have access."), 403
    
    # Check if already evaluated
    already_evaluated = check_evaluation_exists(user_id, team_id, 'final_presentation')
    if already_evaluated:
        flash('You have already submitted an evaluation for this team.', 'warning')
    
    # Criteria
    criteria = OFFICIAL_CRITERIA
    
    return render_template('judge/evaluate.html',
                         user=user or {'name': judge.get('name', 'Jury Member')},
                         judge=judge,
                         team=team,
                         criteria=criteria,
                         already_evaluated=already_evaluated)


@judge_bp.route('/teams/<team_id>')
@require_auth(roles=['judge', 'internal_judge', 'external_judge'])
def view_team(team_id):
    """
    Direct team route protection.
    Checks judge assignment and redirects to evaluation or returns 403 Forbidden.
    """
    user_id = session.get('user_id')
    judges_col = get_judges_collection()
    assignments_col = get_judge_assignments_collection()

    judge = judges_col.find_one({'user_id': user_id})
    if not judge:
        judge = judges_col.find_one({'email': session.get('email', '').lower()})

    if not judge:
        return redirect(url_for('judge.login'))

    assignment = assignments_col.find_one({
        'judge_id': str(judge['_id']),
        'team_id': team_id
    })

    if not assignment:
        return render_template('errors/error.html',
                               code=403,
                               title='Access Forbidden',
                               message="You are not authorized to access this team."), 403

    return redirect(url_for('judge.evaluate_team', team_id=team_id))
