from flask import Blueprint, render_template, session, request, redirect, url_for, flash, jsonify
from routes.auth import require_auth, staff_login
from bson.objectid import ObjectId
from datetime import datetime

from models.database import (
    get_teams_collection,
    get_users_collection,
    get_judges_collection,
    get_evaluations_collection,
    get_event_settings_collection,
    get_audit_logs_collection
)
from services.audit import log_audit
from services.judge_management import create_judge, send_judge_credentials, regenerate_external_password, reset_judge_password
from services.results_calculator import get_evaluation_coverage
from services.jury_panels import (
    auto_assign_teams,
    clear_assignments,
    exception_judges,
    judge_submitted_count,
    list_panels,
    panel_detail as panel_detail_data,
    roster_overview,
    set_judge_panel,
    set_team_panel,
    unassigned_teams,
)
from services.jury_scope import (
    FILTER_EXCEPTION, FILTER_GROUP, PANEL_NUMBERS, SCOPE_ALL, SCOPE_ASSIGNED,
    is_exception_jury, judge_panel_no, scope_label,
)
from utils.urls import public_url

admin_bp = Blueprint('admin', __name__)


@admin_bp.route('', methods=['GET', 'POST'], strict_slashes=False)
def login():
    """Admin (operations team) sign-in."""
    return staff_login('admin')


@admin_bp.route('/login')
def login_alias():
    """Old URL — the sign-in page lives at the blueprint root."""
    return redirect(url_for('admin.login'), code=301)


@admin_bp.route('/dashboard')
@require_auth(roles=['admin'])
def dashboard():
    """Admin dashboard with statistics"""
    teams = get_teams_collection()
    judges = get_judges_collection()
    evaluations = get_evaluations_collection()
    settings = get_event_settings_collection()

    coverage = get_evaluation_coverage()
    stats = {
        'total_teams': teams.count_documents({}),
        'registered_teams': teams.count_documents({'status': 'registered'}),
        'internal_judges': judges.count_documents({'judge_type': {'$in': ['internal', 'INTERNAL_JUDGE']}}),
        'external_judges': judges.count_documents({'judge_type': {'$in': ['external', 'EXTERNAL_JUDGE']}}),
        # Filters built from the shared constants rather than hand-typed $in
        # clauses, which is how the internal/external ones ended up duplicated
        # across two route modules.
        'exception_judges': judges.count_documents(FILTER_EXCEPTION),
        'group_judges': judges.count_documents(FILTER_GROUP),
        'teams_unassigned': coverage['unassigned_teams'],
        'panel_coverage': coverage['panel_coverage'],
        'evaluations_completed': evaluations.count_documents({'status': 'submitted'}),
        'teams_evaluated': coverage['teams_evaluated'],
        'teams_pending': coverage['teams_pending'],
        'completion_percentage': int(coverage['completion_percentage']),
    }
    
    # Get event settings
    event_settings = settings.find_one({})
    stats['judging_locked'] = event_settings.get('judging_locked', False) if event_settings else False
    stats['results_published'] = event_settings.get('results_published', False) if event_settings else False
    stats['registration_open'] = event_settings.get('registration_open', True) if event_settings else True
    
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
    
    evaluations = get_evaluations_collection()
    team_evaluations = list(evaluations.find({'team_id': team_id}))

    return render_template('admin/team_detail.html', team=team, evaluations=team_evaluations)


@admin_bp.route('/teams/<team_id>/remark', methods=['POST'])
@require_auth(roles=['admin'])
def team_remark(team_id):
    """Save (or clear) an admin remark on a team — internal note, never shown to judges or students."""
    teams = get_teams_collection()
    try:
        team = teams.find_one({'_id': ObjectId(team_id)})
    except Exception:
        team = None
    if not team:
        flash('Team not found', 'error')
        return redirect(url_for('admin.teams_list'))
    remark = request.form.get('remark', '').strip()[:1000]
    now = datetime.utcnow()
    if remark:
        teams.update_one({'_id': team['_id']}, {'$set': {'remark': remark, 'remark_by': session.get('name') or session.get('user_id'),
                                                          'remark_by_id': session.get('user_id'), 'remark_at': now}})
        log_audit(session.get('user_id'), 'team_remark_saved', 'team', team_id, {'team_name': team.get('team_name'), 'length': len(remark)})
        flash('Remark saved', 'success')
    else:
        teams.update_one({'_id': team['_id']}, {'$unset': {'remark': '', 'remark_by': '', 'remark_by_id': '', 'remark_at': ''}})
        log_audit(session.get('user_id'), 'team_remark_cleared', 'team', team_id, {'team_name': team.get('team_name')})
        flash('Remark cleared', 'success')
    return redirect(url_for('admin.team_detail', team_id=team_id))


@admin_bp.route('/judges')
@require_auth(roles=['admin'])
def judges_list():
    """List all judges"""
    judges_col = get_judges_collection()
    users_col = get_users_collection()

    all_judges = list(judges_col.find().sort('created_at', -1))
    for judge in all_judges:
        try:
            user = users_col.find_one({'_id': ObjectId(judge.get('user_id'))})
        except Exception:
            user = None
        if user:
            judge['name'] = user['name']
            judge['email'] = user['email']
            judge['credentials_sent'] = user.get('credentials_sent', judge.get('credentials_sent'))
            judge['credentials_sent_at'] = user.get('credentials_sent_at', judge.get('credentials_sent_at'))
            judge['credentials_sent_to'] = user.get('credentials_sent_to', judge.get('credentials_sent_to'))
        judge['kind'] = 'external' if 'external' in str(judge.get('judge_type', '')).lower() else 'internal'
        if judge['kind'] != 'external':
            judge.pop('temp_password', None)   # never expose anything for internal judges
        # Scope is a separate axis from kind. A judge with no jury_scope at all is
        # reported as 'unset' rather than guessed into a bucket - guessing would
        # silently change the weight their scores carry.
        raw_scope = judge.get('jury_scope')
        if raw_scope == SCOPE_ALL:
            judge['scope'] = 'exception'
        elif raw_scope == SCOPE_ASSIGNED:
            judge['scope'] = 'group'
        else:
            judge['scope'] = 'unset'
        judge['panel_no'] = judge_panel_no(judge) if judge['scope'] == 'group' else None

    tab = request.args.get('type', 'all')
    if tab not in ('all', 'internal', 'external'):
        tab = 'all'
    # Orthogonal to the type tabs, which the dashboard quick-links and the bulk
    # credential sender both key off - those keep their existing vocabulary.
    scope_tab = request.args.get('scope', 'all')
    if scope_tab not in ('all', 'exception', 'group', 'unset'):
        scope_tab = 'all'

    judges = all_judges if tab == 'all' else [j for j in all_judges if j['kind'] == tab]
    if scope_tab != 'all':
        judges = [j for j in judges if j['scope'] == scope_tab]

    counts = {
        'all': len(all_judges),
        'internal': sum(1 for j in all_judges if j['kind'] == 'internal'),
        'external': sum(1 for j in all_judges if j['kind'] == 'external'),
        'exception': sum(1 for j in all_judges if j['scope'] == 'exception'),
        'group': sum(1 for j in all_judges if j['scope'] == 'group'),
        'unset': sum(1 for j in all_judges if j['scope'] == 'unset'),
        'not_sent': sum(1 for j in judges if not j.get('credentials_sent') and (tab != 'all' or j['kind'] != 'external')),
        'not_sent_all': sum(1 for j in judges if not j.get('credentials_sent')),
    }

    settings = get_event_settings_collection().find_one({}) or {}
    credential_notices = session.pop('credential_notices', None)
    return render_template('admin/judges.html', judges=judges, tab=tab, counts=counts,
                           scope_tab=scope_tab,
                           bulk_enabled=bool(settings.get('bulk_credentials_enabled', True)),
                           credential_notices=credential_notices)


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



def _send_failure_reason(sent, recipient):
    err = sent.get('error') or ''
    if err == 'SMTP_NOT_CONFIGURED':
        return 'Email is not configured on this server (set the SMTP_* environment variables), so nothing was sent.'
    if err == 'SMTP_AUTH_FAILED':
        return 'The mail server rejected the SMTP username/password (for Gmail use an App Password), so nothing was sent.'
    if err == 'RECIPIENT_REFUSED':
        return f'The mail server refused the address {recipient}, so nothing was sent.'
    return f'The email to {recipient} could not be delivered ({err}).'


def _remember_credentials(name, email, password, recipient, reason):
    """Stash one-time credentials so the Judges page can show them in a persistent,
    copyable panel (a toast would vanish before anyone could copy the password)."""
    notices = session.get('credential_notices') or []
    notices.append({'name': name, 'email': email, 'password': password, 'recipient': recipient, 'reason': reason})
    session['credential_notices'] = notices


@admin_bp.route('/judges/create', methods=['GET', 'POST'])
@require_auth(roles=['admin'])
def create_judge_form():
    """Create a new judge and deliver their login credentials."""
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        phone = request.form.get('phone', '').strip()
        judge_type = request.form.get('judge_type')
        deliver = request.form.get('deliver', 'judge_email')
        alt_email = request.form.get('alt_email', '').strip().lower()
        jury_scope = request.form.get('jury_scope', SCOPE_ASSIGNED)
        panel_no = request.form.get('panel_no')
        # The form disables the email options when this is ticked, but the server
        # must not trust the browser for it.
        no_mailbox = request.form.get('no_mailbox') == 'on'
        if no_mailbox:
            deliver = 'none'

        if not all([name, email, judge_type]):
            flash('Name, email, and judge type are required', 'error')
            return render_template('admin/create_judge.html')
        if jury_scope not in (SCOPE_ALL, SCOPE_ASSIGNED):
            flash('Please choose a jury role.', 'error')
            return render_template('admin/create_judge.html')
        if deliver == 'other_email' and not alt_email:
            flash('Please enter the email address that should receive the credentials', 'error')
            return render_template('admin/create_judge.html')

        result = create_judge(name=name, email=email, phone=phone, judge_type=judge_type,
                              actor_id=session.get('user_id'),
                              jury_scope=jury_scope, panel_no=panel_no,
                              credentials_deliverable=not no_mailbox)
        if result.get('error'):
            flash(result['error'], 'error')
            return render_template('admin/create_judge.html')

        if deliver == 'none':
            _remember_credentials(name, email, result['temp_password'], None,
                                  'Password not emailed — share it with the judge securely.')
            flash(f'Judge {name} created', 'success')
            return redirect(url_for('admin.judges_list'))

        recipient = alt_email if deliver == 'other_email' else email
        sent = send_judge_credentials(result['judge_id'], recipient_email=recipient,
                                      actor_id=session.get('user_id'),
                                      login_url=public_url('judge.login'))
        if sent.get('success'):
            flash(f'Judge {name} created and login credentials emailed to {sent["recipient"]}', 'success')
        else:
            _remember_credentials(name, email, sent.get('password'), recipient, _send_failure_reason(sent, recipient))
            flash(f'Judge {name} created', 'success')
        return redirect(url_for('admin.judges_list'))

    return render_template('admin/create_judge.html')


@admin_bp.route('/judges/<judge_id>/send-credentials', methods=['POST'])
@require_auth(roles=['admin'])
def send_credentials(judge_id):
    """Generate a new password for a judge and email it (to the judge or another address)."""
    recipient = request.form.get('recipient', '').strip().lower() or None
    sent = send_judge_credentials(judge_id, recipient_email=recipient,
                                  actor_id=session.get('user_id'),
                                  login_url=public_url('judge.login'))
    judge = get_judges_collection().find_one({'_id': ObjectId(judge_id)}) or {}
    wants_json = request.headers.get('X-Requested-With') == 'fetch' or 'application/json' in request.headers.get('Accept', '')

    if wants_json:
        # Answer the in-page email modal directly; it renders sent / not-sent itself.
        payload = {'success': bool(sent.get('success')), 'name': judge.get('name', 'Judge'),
                   'email': judge.get('email', ''), 'recipient': sent.get('recipient'),
                   'sent_at': datetime.utcnow().strftime('%d %b %H:%M')}
        if not sent.get('success'):
            payload['reason'] = _send_failure_reason(sent, sent.get('recipient')) if sent.get('password') else sent.get('error', 'Could not send credentials')
            if sent.get('password'):
                payload['password'] = sent['password']
        return jsonify(payload), (200 if sent.get('success') or sent.get('password') else 400)

    if sent.get('success'):
        flash(f'New login credentials emailed to {sent["recipient"]}', 'success')
    elif sent.get('password'):
        _remember_credentials(judge.get('name', 'Judge'), judge.get('email', ''), sent['password'],
                              sent.get('recipient'), _send_failure_reason(sent, sent.get('recipient')))
    else:
        flash(sent.get('error', 'Could not send credentials'), 'error')
    return redirect(url_for('admin.judges_list'))


@admin_bp.route('/judges/<judge_id>/regenerate-password', methods=['POST'])
@require_auth(roles=['admin'])
def regenerate_password(judge_id):
    """New password, NOT emailed.
    External judges: stored, so the sign-in details can be copied from the table at any time.
    Internal judges: shown once in the copyable panel and never stored."""
    judge = None
    try:
        judge = get_judges_collection().find_one({'_id': ObjectId(judge_id)})
    except Exception:
        pass
    external = 'external' in str((judge or {}).get('judge_type', '')).lower()
    res = (regenerate_external_password if external else reset_judge_password)(judge_id, actor_id=session.get('user_id'))
    if not res.get('success'):
        flash(res.get('error', 'Could not generate a new password'), 'error')
        return redirect(url_for('admin.judges_list'))
    _remember_credentials(res['name'], res['email'], res['password'], None,
                          'Kept in the Judges table — copy it whenever you need it.' if external
                          else 'Not emailed — copy it now; it is not stored.')
    flash(f'New password generated for {res["name"]}', 'success')
    return redirect(url_for('admin.judges_list', type='external' if external else 'internal'))


BULK_BATCH_SIZE_MAX = 10
BULK_BATCH_SIZE_DEFAULT = 5


def _bulk_targets(tab, include_sent, include_external=False):
    """Active judges in the tab; skips already-emailed ones unless include_sent.
    External judges are skipped unless include_external (or the External tab is selected).
    Judges with no reachable mailbox are always skipped."""
    judges_col = get_judges_collection()
    users_col = get_users_collection()
    targets = []
    for judge in judges_col.find():
        kind = 'external' if 'external' in str(judge.get('judge_type', '')).lower() else 'internal'
        if tab in ('internal', 'external') and kind != tab:
            continue
        if tab == 'all' and kind == 'external' and not include_external:
            continue
        # Outside guests have placeholder addresses. Queuing one would generate a
        # brand-new password first - invalidating the one already handed over in
        # person - and only then fail to deliver it.
        if not judge.get('credentials_deliverable', True):
            continue
        if str(judge.get('status', 'active')).lower() != 'active':
            continue
        user = None
        try:
            user = users_col.find_one({'_id': ObjectId(judge.get('user_id'))})
        except Exception:
            pass
        if (user or judge).get('credentials_sent', False) and not include_sent:
            continue
        targets.append(judge)
    return targets


@admin_bp.route('/judges/send-credentials-batch', methods=['POST'])
@require_auth(roles=['admin'])
def send_credentials_batch():
    """
    Batched bulk send (JSON). One call = one batch, so long runs never hit the
    serverless timeout and the browser controls the pause between batches
    (SMTP providers throttle bursts).

    Body: {"action": "start", "type": "all|internal|external", "include_sent": bool, "batch_size": 5}
          {"action": "next"}      -> sends the next batch from the session queue
          {"action": "cancel"}    -> drops the queue
    Reply: {"queued": n, "sent": s, "failed": f, "done": bool, "batch": [{"name","email","ok"}]}
    """
    settings = get_event_settings_collection().find_one({}) or {}
    if not settings.get('bulk_credentials_enabled', True):
        return jsonify({'error': 'Bulk credential emails are disabled by the Super Admin (System Settings).'}), 403

    data = request.get_json(silent=True) or {}
    action = data.get('action', 'next')

    if action == 'cancel':
        session.pop('bulk_queue', None)
        return jsonify({'done': True, 'cancelled': True})

    if action == 'start':
        tab = data.get('type', 'all')
        include_sent = bool(data.get('include_sent'))
        include_external = bool(data.get('include_external'))
        try:
            batch_size = max(1, min(int(data.get('batch_size', BULK_BATCH_SIZE_DEFAULT)), BULK_BATCH_SIZE_MAX))
        except (TypeError, ValueError):
            batch_size = BULK_BATCH_SIZE_DEFAULT
        targets = _bulk_targets(tab, include_sent, include_external)
        if not targets:
            return jsonify({'error': 'No judges to email — everyone in this list already has credentials. '
                                     'Tick "include already-emailed" to resend.', 'queued': 0, 'done': True}), 200
        session['bulk_queue'] = {'ids': [str(j['_id']) for j in targets], 'tab': tab, 'batch_size': batch_size,
                                 'sent': 0, 'failed': 0, 'total': len(targets), 'include_sent': include_sent, 'include_external': include_external}
        log_audit(session.get('user_id'), 'judge_credentials_bulk_started', 'judge', tab,
                  {'targets': len(targets), 'batch_size': batch_size, 'include_sent': include_sent, 'include_external': include_external})

    q = session.get('bulk_queue')
    if not q:
        return jsonify({'error': 'No bulk send in progress. Start again.', 'done': True}), 400

    judges_col = get_judges_collection()
    login_url = public_url('judge.login')
    batch_ids, q['ids'] = q['ids'][:q['batch_size']], q['ids'][q['batch_size']:]
    batch = []
    for jid in batch_ids:
        judge = judges_col.find_one({'_id': ObjectId(jid)}) or {}
        res = send_judge_credentials(jid, actor_id=session.get('user_id'), login_url=login_url)
        ok = bool(res.get('success'))
        q['sent' if ok else 'failed'] += 1
        if not ok and res.get('password'):
            _remember_credentials(judge.get('name', 'Judge'), judge.get('email', ''), res['password'],
                                  res.get('recipient'), _send_failure_reason(res, res.get('recipient')))
        batch.append({'name': judge.get('name', ''), 'email': judge.get('email', ''), 'ok': ok,
                      'error': None if ok else res.get('error')})

    done = not q['ids']
    if done:
        log_audit(session.get('user_id'), 'judge_credentials_bulk_sent', 'judge', q['tab'],
                  {'targets': q['total'], 'sent': q['sent'], 'failed': q['failed'], 'include_sent': q['include_sent'], 'batched': True})
        session.pop('bulk_queue', None)
    else:
        session['bulk_queue'] = q
    return jsonify({'queued': len(q['ids']), 'sent': q['sent'], 'failed': q['failed'], 'total': q['total'],
                    'batch': batch, 'done': done})


@admin_bp.route('/judges/send-credentials-all', methods=['POST'])
@require_auth(roles=['admin'])
def send_credentials_all():
    """Email (new) login credentials to every judge in the selected tab.
    Gated by the Super Admin switch 'bulk_credentials_enabled'."""
    settings = get_event_settings_collection().find_one({}) or {}
    if not settings.get('bulk_credentials_enabled', True):
        flash('Bulk credential emails are disabled by the Super Admin (System Settings).', 'error')
        return redirect(url_for('admin.judges_list'))

    tab = request.form.get('type', 'all')
    include_sent = request.form.get('include_sent') == 'on'
    include_external = request.form.get('include_external') == 'on'
    targets = _bulk_targets(tab, include_sent, include_external)

    if not targets:
        flash('No judges to email — everyone in this list has already received credentials. '
              'Tick "include already-emailed" to resend.', 'warning')
        return redirect(url_for('admin.judges_list', type=tab))

    login_url = public_url('judge.login')
    sent_ok, failed = 0, 0
    for judge in targets:
        res = send_judge_credentials(str(judge['_id']), actor_id=session.get('user_id'), login_url=login_url)
        if res.get('success'):
            sent_ok += 1
        else:
            failed += 1
            if res.get('password'):
                _remember_credentials(judge.get('name', 'Judge'), judge.get('email', ''), res['password'],
                                      res.get('recipient'), _send_failure_reason(res, res.get('recipient')))

    log_audit(session.get('user_id'), 'judge_credentials_bulk_sent', 'judge', tab,
              {'targets': len(targets), 'sent': sent_ok, 'failed': failed, 'include_sent': include_sent})
    if failed:
        flash(f'Emailed {sent_ok} judge(s); {failed} could not be emailed — their passwords are shown below.', 'warning')
    else:
        flash(f'Login credentials emailed to {sent_ok} judge(s).', 'success')
    return redirect(url_for('admin.judges_list', type=tab))



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


def _back_to_settings():
    """Return to the admin page the toggle was clicked on (Rankings or Settings), never off-site."""
    ref = request.referrer or ''
    if ref.startswith(request.host_url.rstrip('/') + '/admin/') or ref.startswith('/admin/'):
        return redirect(ref)
    return redirect(url_for('admin.settings'))


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
    return _back_to_settings()


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
    return _back_to_settings()


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
    from routes.teams import invalidate_registration_cache
    invalidate_registration_cache()
    flash(f'Registration has been {"opened" if new_open else "closed"}', 'success')
    return _back_to_settings()


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
    # Panel is included because this file is the artefact organisers actually
    # work from, and 'which panel scored this team' is the first thing they ask.
    writer.writerow(['Rank', 'Team Code', 'Team Name', 'Leader Name', 'Panel',
                     'Exception Jury Average (0-100)', 'Panel Jury Average (0-100)',
                     'Final Score (0-100)', 'Provisional Score (0-100)',
                     'Exception Evaluations', 'Panel Evaluations', 'Panel Jury Expected',
                     'Status', 'Stage'])
    for team in rankings:
        writer.writerow([
            team.get('rank', ''), team.get('team_code', ''), team.get('team_name', ''),
            team.get('leader_name', ''), team.get('panel_no') or 'UNASSIGNED',
            team.get('exception_average', ''), team.get('group_average', ''),
            # Empty rather than 0 for an incomplete team, so a blank cell cannot
            # be mistaken for a genuine score of zero.
            team.get('final_score') if team.get('is_complete') else '',
            team.get('provisional_score', ''),
            team.get('exception_count', 0), team.get('group_count', 0),
            team.get('group_expected', 0), team.get('status', ''), stage_id,
        ])
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
            ev['judge_type'] = 'internal' if 'internal' in str(judge.get('judge_type', '')).lower() else 'external'
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


# --------------------------------------------------------------------------- #
# Jury panels
# --------------------------------------------------------------------------- #

@admin_bp.route('/panels')
@require_auth(roles=['admin'])
def panels_list():
    """Five panels, their rosters, their teams and their scoring progress."""
    return render_template(
        'admin/panels.html',
        panels=list_panels(),
        counts=roster_overview(),
        exception=exception_judges(),
        unassigned=unassigned_teams(),
    )


@admin_bp.route('/panels/<int:panel_no>')
@require_auth(roles=['admin'])
def panel_detail(panel_no):
    """One panel: its judges, its teams and who has scored what."""
    panel = panel_detail_data(panel_no)
    if not panel:
        return render_template('errors/error.html', code=404, title='Panel Not Found',
                               message='There are only five jury panels.'), 404
    return render_template('admin/panel_detail.html', panel=panel,
                           panel_numbers=PANEL_NUMBERS)


@admin_bp.route('/panels/members', methods=['GET', 'POST'])
@require_auth(roles=['admin'])
def panel_members():
    """Edit which panel each judge sits on, or move them to the exception jury."""
    judges_col = get_judges_collection()

    if request.method == 'POST':
        moved = 0
        for judge in list(judges_col.find({}, {'_id': 1})):
            jid = str(judge['_id'])
            raw = request.form.get(f'panel_no_{jid}')
            if raw is None:
                continue
            try:
                if set_judge_panel(jid, None if raw == 'exception' else raw,
                                   actor_id=session.get('user_id')):
                    moved += 1
            except ValueError:
                flash(f'Ignored an invalid panel value for judge {jid}.', 'warning')
        flash(f'{moved} judge(s) updated.' if moved else 'No changes to save.',
              'success' if moved else 'info')
        return redirect(url_for('admin.panel_members'))

    rows = []
    for judge in judges_col.find().sort([('jury_scope', 1), ('panel_no', 1), ('name', 1)]):
        rows.append({
            'judge': judge,
            'panel_no': judge_panel_no(judge),
            'is_exception': is_exception_jury(judge),
            'scope_display': scope_label(judge),
            # Surfaced so an admin can see, before moving someone, that they
            # already have scores on the board.
            'submitted': judge_submitted_count(judge),
        })
    return render_template('admin/panel_members.html', rows=rows,
                           panels=list_panels(), panel_numbers=PANEL_NUMBERS)


@admin_bp.route('/panels/assign', methods=['GET', 'POST'])
@require_auth(roles=['admin'])
def panel_assign():
    """Assign teams to panels, all in one screen."""
    teams_col = get_teams_collection()

    if request.method == 'POST':
        moved = 0
        for team in list(teams_col.find({}, {'_id': 1})):
            tid = str(team['_id'])
            raw = request.form.get(f'panel_no_{tid}')
            if raw is None:
                continue
            try:
                if set_team_panel(tid, raw or None, actor_id=session.get('user_id')):
                    moved += 1
            except ValueError:
                flash(f'Ignored an invalid panel value for team {tid}.', 'warning')
        flash(f'{moved} team(s) updated.' if moved else 'No changes to save.',
              'success' if moved else 'info')
        return redirect(url_for('admin.panel_assign'))

    # Unassigned first - they are the ones needing attention.
    teams = sorted(
        teams_col.find(),
        key=lambda t: (1 if t.get('panel_no') else 0,
                       t.get('panel_no') or 0,
                       str(t.get('team_name', '')).lower()),
    )
    return render_template('admin/panel_assign.html', teams=teams,
                           panel_numbers=PANEL_NUMBERS, counts=roster_overview())


@admin_bp.route('/panels/auto-assign', methods=['POST'])
@require_auth(roles=['admin'])
def panel_auto_assign():
    """Distribute teams across the five panels."""
    mode = request.form.get('mode', 'blocks')
    overwrite = request.form.get('overwrite') == 'on'
    if mode not in ('blocks', 'round_robin'):
        mode = 'blocks'
    result = auto_assign_teams(mode=mode, overwrite=overwrite,
                               actor_id=session.get('user_id'))
    spread = ', '.join(f'P{k}: {v}' for k, v in sorted(result['per_panel'].items()))
    flash(f"Assigned {result['assigned']} team(s), left {result['skipped']} as they were. {spread}",
          'success')
    return redirect(url_for('admin.panels_list'))


@admin_bp.route('/panels/clear-assignments', methods=['POST'])
@require_auth(roles=['admin'])
def panel_clear_assignments():
    """Remove every team's panel."""
    result = clear_assignments(actor_id=session.get('user_id'))
    flash(f"Cleared the panel on {result['cleared']} team(s). No team can be scored "
          f"by group jury until they are reassigned.", 'warning')
    return redirect(url_for('admin.panels_list'))


@admin_bp.route('/teams/<team_id>/panel', methods=['POST'])
@require_auth(roles=['admin'])
def team_set_panel(team_id):
    """Set or clear one team's panel."""
    try:
        changed = set_team_panel(team_id, request.form.get('panel_no') or None,
                                actor_id=session.get('user_id'))
    except ValueError:
        flash('That is not a valid panel.', 'error')
        return redirect(request.referrer or url_for('admin.panels_list'))
    flash('Panel updated.' if changed else 'No change.', 'success' if changed else 'info')
    return redirect(request.referrer or url_for('admin.panels_list'))


@admin_bp.route('/judges/<judge_id>/panel', methods=['POST'])
@require_auth(roles=['admin'])
def judge_set_panel(judge_id):
    """Move one judge between panels, or to the exception jury."""
    raw = request.form.get('panel_no')
    try:
        changed = set_judge_panel(judge_id, None if raw == 'exception' else (raw or None),
                                 actor_id=session.get('user_id'))
    except ValueError:
        flash('That is not a valid panel.', 'error')
        return redirect(request.referrer or url_for('admin.panel_members'))
    flash('Jury role updated.' if changed else 'No change.', 'success' if changed else 'info')
    return redirect(request.referrer or url_for('admin.panel_members'))
