"""
Checkpoint Manager Service
Manages evaluation checkpoints and judging lock/unlock functionality
"""

from datetime import datetime
from bson.objectid import ObjectId

from models.database import (
    get_event_settings_collection,
    get_evaluation_stages_collection
)
from services.audit import log_audit


def get_judging_status():
    """
    Get current judging status (locked/unlocked)
    
    Returns:
        dict: Contains is_locked status and current settings
    """
    settings_col = get_event_settings_collection()
    
    settings = settings_col.find_one()
    
    if not settings:
        # Default: judging is open
        return {
            'is_locked': False,
            'locked_at': None,
            'locked_by': None,
            'lock_reason': None
        }
    
    return {
        'is_locked': settings.get('judging_locked', False),
        'locked_at': settings.get('judging_locked_at'),
        'locked_by': settings.get('judging_locked_by'),
        'lock_reason': settings.get('judging_lock_reason')
    }


def lock_judging(reason=None, actor_id=None):
    """
    Lock judging system (prevent new evaluations)
    
    Args:
        reason: Optional reason for locking
        actor_id: User ID performing this action
        
    Returns:
        dict: Result of lock operation
    """
    settings_col = get_event_settings_collection()
    
    settings = settings_col.find_one()
    
    if settings:
        settings_col.update_one(
            {'_id': settings['_id']},
            {
                '$set': {
                    'judging_locked': True,
                    'judging_locked_at': datetime.utcnow(),
                    'judging_locked_by': actor_id,
                    'judging_lock_reason': reason
                }
            }
        )
    else:
        settings_col.insert_one({
            'judging_locked': True,
            'judging_locked_at': datetime.utcnow(),
            'judging_locked_by': actor_id,
            'judging_lock_reason': reason
        })
    
    # Log audit
    log_audit(
        actor_id,
        'judging_locked',
        'system',
        'judging_control',
        {'reason': reason}
    )
    
    return {'success': True, 'message': 'Judging has been locked'}


def unlock_judging(actor_id=None):
    """
    Unlock judging system (allow evaluations)
    
    Args:
        actor_id: User ID performing this action
        
    Returns:
        dict: Result of unlock operation
    """
    settings_col = get_event_settings_collection()
    
    settings = settings_col.find_one()
    
    if settings:
        settings_col.update_one(
            {'_id': settings['_id']},
            {
                '$set': {
                    'judging_locked': False,
                    'judging_unlocked_at': datetime.utcnow(),
                    'judging_unlocked_by': actor_id
                },
                '$unset': {
                    'judging_locked_at': '',
                    'judging_locked_by': '',
                    'judging_lock_reason': ''
                }
            }
        )
    else:
        settings_col.insert_one({
            'judging_locked': False,
            'judging_unlocked_at': datetime.utcnow(),
            'judging_unlocked_by': actor_id
        })
    
    # Log audit
    log_audit(
        actor_id,
        'judging_unlocked',
        'system',
        'judging_control'
    )
    
    return {'success': True, 'message': 'Judging has been unlocked'}


def is_judging_allowed():
    """
    Check if judging is currently allowed
    
    Returns:
        bool: True if judging is allowed, False if locked
    """
    status = get_judging_status()
    return not status['is_locked']


def get_all_stages():
    """
    Get all evaluation stages
    
    Returns:
        list: List of evaluation stages
    """
    stages_col = get_evaluation_stages_collection()
    return list(stages_col.find().sort('order', 1))


def get_active_stage():
    """
    Get currently active evaluation stage
    
    Returns:
        dict: Active stage or None
    """
    stages_col = get_evaluation_stages_collection()
    return stages_col.find_one({'is_active': True})


def set_active_stage(stage_id, actor_id=None):
    """
    Set a specific stage as active (deactivate others)
    
    Args:
        stage_id: Stage identifier to activate
        actor_id: User ID performing this action
        
    Returns:
        dict: Result of operation
    """
    stages_col = get_evaluation_stages_collection()
    
    # Check if stage exists
    stage = stages_col.find_one({'stage_id': stage_id})
    if not stage:
        return {'error': 'Stage not found'}
    
    # Deactivate all stages
    stages_col.update_many({}, {'$set': {'is_active': False}})
    
    # Activate the specified stage
    stages_col.update_one(
        {'stage_id': stage_id},
        {
            '$set': {
                'is_active': True,
                'activated_at': datetime.utcnow(),
                'activated_by': actor_id
            }
        }
    )
    
    # Log audit
    log_audit(
        actor_id,
        'stage_activated',
        'stage',
        stage_id,
        {'stage_name': stage.get('stage_name')}
    )
    
    return {
        'success': True,
        'stage_id': stage_id,
        'stage_name': stage.get('stage_name')
    }


def create_checkpoint(stage_id, checkpoint_name, description=None, actor_id=None):
    """
    Create a new evaluation checkpoint/stage
    
    Args:
        stage_id: Unique stage identifier
        checkpoint_name: Name of the checkpoint
        description: Optional description
        actor_id: User ID performing this action
        
    Returns:
        dict: Created checkpoint
    """
    stages_col = get_evaluation_stages_collection()
    
    # Check if stage_id already exists
    if stages_col.find_one({'stage_id': stage_id}):
        return {'error': 'Stage ID already exists'}
    
    # Get current max order
    max_stage = stages_col.find_one(sort=[('order', -1)])
    next_order = (max_stage['order'] + 1) if max_stage else 1
    
    checkpoint_data = {
        'stage_id': stage_id,
        'stage_name': checkpoint_name,
        'description': description,
        'order': next_order,
        'is_active': False,
        'created_at': datetime.utcnow(),
        'created_by': actor_id
    }
    
    checkpoint_id = stages_col.insert_one(checkpoint_data).inserted_id
    
    # Log audit
    log_audit(
        actor_id,
        'checkpoint_created',
        'stage',
        str(checkpoint_id),
        {'stage_id': stage_id, 'stage_name': checkpoint_name}
    )
    
    return {
        'success': True,
        'checkpoint_id': str(checkpoint_id),
        'stage_id': stage_id
    }


def get_checkpoint_stats(stage_id):
    """
    Get statistics for a specific checkpoint
    
    Args:
        stage_id: Stage identifier
        
    Returns:
        dict: Statistics for the checkpoint
    """
    from models.database import get_evaluations_collection, get_teams_collection
    
    evaluations_col = get_evaluations_collection()
    teams_col = get_teams_collection()
    
    total_teams = teams_col.count_documents({})
    total_evaluations = evaluations_col.count_documents({
        'stage_id': stage_id,
        'status': 'submitted'
    })
    
    # Count unique teams evaluated
    teams_evaluated = len(evaluations_col.distinct('team_id', {
        'stage_id': stage_id,
        'status': 'submitted'
    }))
    
    completion_rate = (teams_evaluated / total_teams * 100) if total_teams > 0 else 0
    
    return {
        'stage_id': stage_id,
        'total_teams': total_teams,
        'teams_evaluated': teams_evaluated,
        'teams_pending': total_teams - teams_evaluated,
        'total_evaluations': total_evaluations,
        'completion_rate': round(completion_rate, 2)
    }
