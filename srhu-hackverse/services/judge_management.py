"""
Judge Management Service
Handles judge creation, assignments, and panel management
"""

from datetime import datetime
from werkzeug.security import generate_password_hash
from bson.objectid import ObjectId

from models.database import (
    get_users_collection,
    get_judges_collection,
    get_jury_panels_collection,
    get_judge_assignments_collection,
    get_teams_collection
)
from services.audit import log_audit


def create_judge(name, email, phone, judge_type, panel_id=None, actor_id=None):
    """
    Create a new judge account
    
    Args:
        name: Judge's full name
        email: Email address (will be login username)
        phone: Phone number
        judge_type: 'internal' or 'external'
        panel_id: Optional jury panel assignment
        actor_id: User ID performing this action
        
    Returns:
        dict: Created judge record or None if error
    """
    users_col = get_users_collection()
    judges_col = get_judges_collection()
    
    # Check if email already exists
    if users_col.find_one({'email': email.lower()}):
        return {'error': 'Email already exists'}
    
    # Normalize and validate judge type
    clean_type = str(judge_type).lower().replace('_judge', '')
    if clean_type not in ['internal', 'external']:
        return {'error': 'Invalid judge type. Must be "internal" or "external"'}
    
    db_judge_type = 'INTERNAL_JUDGE' if clean_type == 'internal' else 'EXTERNAL_JUDGE'

    # Create user account
    user_data = {
        'name': name,
        'email': email.lower(),
        'phone': phone,
        'password_hash': generate_password_hash('judge123'),  # Default placeholder for jury accounts
        'role': 'judge',
        'status': 'active',
        'created_at': datetime.utcnow()
    }
    
    user_id = users_col.insert_one(user_data).inserted_id
    
    # Create judge record
    judge_data = {
        'user_id': str(user_id),
        'name': name,
        'email': email.lower(),
        'judge_type': db_judge_type,
        'panel_id': panel_id,
        'status': 'active',
        'created_at': datetime.utcnow()
    }
    
    judge_id = judges_col.insert_one(judge_data).inserted_id
    
    # Log audit
    log_audit(
        actor_id,
        'judge_created',
        'judge',
        str(judge_id),
        {
            'name': name,
            'email': email,
            'judge_type': judge_type,
            'panel_id': panel_id
        }
    )
    
    return {
        'success': True,
        'judge_id': str(judge_id),
        'user_id': str(user_id),
        'default_password': 'judge123'
    }


def create_jury_panel(panel_name, panel_id, coordinator_name=None, description=None, actor_id=None):
    """
    Create a new jury panel
    
    Args:
        panel_name: Name of the panel
        panel_id: Unique identifier (e.g., 'panel_1', 'panel_2')
        coordinator_name: Name of the panel coordinator
        description: Panel description
        actor_id: User ID performing this action
        
    Returns:
        dict: Created panel record
    """
    panels_col = get_jury_panels_collection()
    
    # Check if panel_id already exists
    if panels_col.find_one({'panel_id': panel_id}):
        return {'error': 'Panel ID already exists'}
    
    panel_data = {
        'panel_name': panel_name,
        'panel_id': panel_id,
        'coordinator_name': coordinator_name,
        'description': description,
        'status': 'active',
        'created_at': datetime.utcnow()
    }
    
    panel_record_id = panels_col.insert_one(panel_data).inserted_id
    
    # Log audit
    log_audit(
        actor_id,
        'panel_created',
        'panel',
        str(panel_record_id),
        {'panel_id': panel_id, 'panel_name': panel_name}
    )
    
    return {
        'success': True,
        'panel_record_id': str(panel_record_id),
        'panel_id': panel_id
    }


def assign_judge_to_team(judge_id, team_id, panel_id=None, actor_id=None):
    """
    Assign a judge to evaluate a specific team
    
    Args:
        judge_id: Judge's MongoDB ObjectId (string)
        team_id: Team's MongoDB ObjectId (string)
        panel_id: Optional panel identifier
        actor_id: User ID performing this action
        
    Returns:
        dict: Assignment result
    """
    judges_col = get_judges_collection()
    teams_col = get_teams_collection()
    assignments_col = get_judge_assignments_collection()
    
    # Verify judge exists
    judge = judges_col.find_one({'_id': ObjectId(judge_id)})
    if not judge:
        return {'error': 'Judge not found'}
    
    # Verify team exists
    team = teams_col.find_one({'_id': ObjectId(team_id)})
    if not team:
        return {'error': 'Team not found'}
    
    # Check if assignment already exists
    existing = assignments_col.find_one({
        'judge_id': judge_id,
        'team_id': team_id
    })
    
    if existing:
        return {'error': 'This judge is already assigned to this team'}
    
    # Create assignment
    assignment_data = {
        'judge_id': judge_id,
        'team_id': team_id,
        'panel_id': panel_id or judge.get('panel_id'),
        'judge_type': judge['judge_type'],
        'status': 'active',
        'assigned_at': datetime.utcnow()
    }
    
    assignment_id = assignments_col.insert_one(assignment_data).inserted_id
    
    # Log audit
    log_audit(
        actor_id,
        'judge_assigned',
        'assignment',
        str(assignment_id),
        {
            'judge_id': judge_id,
            'team_id': team_id,
            'judge_type': judge['judge_type']
        }
    )
    
    return {
        'success': True,
        'assignment_id': str(assignment_id)
    }


def bulk_assign_judges_to_teams(judge_ids, team_ids, actor_id=None):
    """
    Bulk assign multiple judges to multiple teams
    
    Args:
        judge_ids: List of judge IDs
        team_ids: List of team IDs
        actor_id: User ID performing this action
        
    Returns:
        dict: Summary of assignments
    """
    successful = 0
    failed = 0
    errors = []
    
    for judge_id in judge_ids:
        for team_id in team_ids:
            result = assign_judge_to_team(judge_id, team_id, actor_id=actor_id)
            if result.get('success'):
                successful += 1
            else:
                failed += 1
                errors.append(result.get('error'))
    
    return {
        'successful': successful,
        'failed': failed,
        'errors': errors
    }


def get_judge_assignments(judge_id):
    """
    Get all teams assigned to a specific judge
    
    Args:
        judge_id: Judge's MongoDB ObjectId (string)
        
    Returns:
        list: List of team records with assignment info
    """
    assignments_col = get_judge_assignments_collection()
    teams_col = get_teams_collection()
    
    assignments = list(assignments_col.find({'judge_id': judge_id}))
    
    teams_with_assignments = []
    for assignment in assignments:
        team = teams_col.find_one({'_id': ObjectId(assignment['team_id'])})
        if team:
            team['assignment_id'] = str(assignment['_id'])
            team['assigned_at'] = assignment.get('assigned_at')
            teams_with_assignments.append(team)
    
    return teams_with_assignments


def remove_judge_assignment(assignment_id, actor_id=None):
    """
    Remove a judge-team assignment
    
    Args:
        assignment_id: Assignment's MongoDB ObjectId (string)
        actor_id: User ID performing this action
        
    Returns:
        dict: Deletion result
    """
    assignments_col = get_judge_assignments_collection()
    
    result = assignments_col.delete_one({'_id': ObjectId(assignment_id)})
    
    if result.deleted_count > 0:
        log_audit(actor_id, 'assignment_removed', 'assignment', assignment_id)
        return {'success': True}
    else:
        return {'error': 'Assignment not found'}
