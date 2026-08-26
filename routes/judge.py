"""
TechForge 3.0 — Jury Routes
Handles Jury Login, Jury Dashboard and team evaluation.

Group jury see and score only the teams assigned to their panel. Exception jury
see and score every team, and may keep submitting while judging is locked. Both
rules are enforced through services.jury_scope - see can_evaluate().
"""

from flask import Blueprint, render_template, session, request, redirect, url_for, flash, jsonify
from bson.objectid import ObjectId

from routes.auth import require_auth
from models.database import (
    get_users_collection,
    get_judges_collection,
    get_teams_collection
)
from services.scoring import (
    get_judge_evaluations,
    check_evaluation_exists,
    OFFICIAL_CRITERIA
)
from services.checkpoint_manager import get_judging_status, is_judging_allowed
from services.jury_scope import (
    can_evaluate,
    is_exception_jury,
    judge_panel_no,
    load_judge_for_session,
    scope_label,
    teams_for_judge,
)
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
    Summary metrics plus the teams this judge may score: their panel's teams for
    group jury, every team for exception jury.
    """
    user_id = session.get('user_id')
    users_col = get_users_collection()

    # 1. Fetch user & judge record
    user = None
    try:
        user = users_col.find_one({'_id': ObjectId(user_id)})
    except Exception:
        pass

    judge = load_judge_for_session(user_id, session.get('email'))
    if not judge:
        flash('Jury profile not found. Please log in again.', 'error')
        return redirect(url_for('judge.login'))

    # Determine judge type (display only - it no longer decides access or weight)
    raw_type = judge.get('judge_type', 'INTERNAL_JUDGE')
    if 'external' in str(raw_type).lower():
        judge_type = 'EXTERNAL_JUDGE'
        judge_type_display = 'External Jury'
    else:
        judge_type = 'INTERNAL_JUDGE'
        judge_type_display = 'Internal Jury'

    # 2. Only the teams this judge is entitled to: their panel, or all of them
    #    for exception jury.
    all_teams = teams_for_judge(judge)

    # 3. Evaluations submitted by this judge
    evaluations = get_judge_evaluations(user_id)
    eval_map = {str(e.get('team_id')): e for e in evaluations}

    completed_evals = 0
    total_score_sum = 0
    scored_eval_count = 0

    for team in all_teams:
        t_id = str(team['_id'])
        # Read from eval_map, which was just built from this judge's own
        # evaluations, instead of one check_evaluation_exists() round trip per
        # team. A reopened evaluation does not count as done, matching the rule
        # in services.scoring.
        ev_doc = eval_map.get(t_id)
        is_evaluated = bool(ev_doc) and ev_doc.get('status') != 'reopened'
        team['evaluated'] = is_evaluated
        if is_evaluated:
            completed_evals += 1
            if 'weighted_score' in ev_doc:
                total_score_sum += float(ev_doc['weighted_score'])
                scored_eval_count += 1
            elif 'total_score' in ev_doc:
                total_score_sum += float(ev_doc['total_score'])
                scored_eval_count += 1

    # Counted over the visible teams only, so the ring and the pending count
    # agree even if a scored team was later moved to another panel.
    pending_evals = max(0, len(all_teams) - completed_evals)
    avg_score = round(total_score_sum / scored_eval_count, 1) if scored_eval_count > 0 else 0.0

    # Two separate flags on purpose. judging_status drives the banner and stays
    # global, so an exception juror still learns the event is locked; can_submit
    # drives the buttons, so their form stays reachable.
    judging_status = get_judging_status()
    can_submit = is_judging_allowed(judge)

    return render_template(
        'judge/dashboard.html',
        user=user or {'name': judge.get('name', 'Jury Member')},
        judge=judge,
        judge_type=judge_type,
        judge_type_display=judge_type_display,
        panel_no=judge_panel_no(judge),
        is_exception=is_exception_jury(judge),
        scope_display=scope_label(judge),
        teams=all_teams,
        evaluations=evaluations,
        evaluations_count=completed_evals,
        pending_count=pending_evals,
        avg_score=avg_score,
        judging_status=judging_status,
        can_submit=can_submit
    )


@judge_bp.route('/evaluate/<team_id>')
@require_auth(roles=['judge', 'internal_judge', 'external_judge'])
def evaluate_team(team_id):
    """
    Evaluation form for one team. Rejects teams outside the judge's panel, and
    rejects everyone except exception jury while judging is locked.
    """
    user_id = session.get('user_id')
    users_col = get_users_collection()
    teams_col = get_teams_collection()

    # Get user and judge info
    user = None
    try:
        user = users_col.find_one({'_id': ObjectId(user_id)})
    except Exception:
        pass

    judge = load_judge_for_session(user_id, session.get('email'))
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

    # Entitlement before the lock check, so a group judge probing another
    # panel's team learns nothing about the lock state and gets the real reason.
    if not can_evaluate(judge, team):
        return render_template('errors/error.html',
                               code=403,
                               title='Not Your Panel',
                               message="This team is assigned to a different jury panel. "
                                       "You can only score the teams listed on your dashboard."), 403

    # Refuse the form outright when locked, rather than letting a judge fill in
    # all six criteria and discover the lock only on submit.
    if not is_judging_allowed(judge):
        return render_template('errors/error.html',
                               code=403,
                               title='Judging Is Locked',
                               message="Scoring is closed right now. Please contact the "
                                       "organisers if you still have teams to evaluate."), 403

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
    """Shortcut: open the evaluation form for a team."""
    return redirect(url_for('judge.evaluate_team', team_id=team_id))
