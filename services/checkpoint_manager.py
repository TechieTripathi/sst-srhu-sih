"""
Judging Lock Service
Global lock/unlock of evaluation submissions (stored in event_settings).
"""

from datetime import datetime

from models.database import get_event_settings_collection
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


def is_judging_allowed(judge=None):
    """
    Check whether judging is currently allowed.

    Called with no argument this answers the global question - "is the switch
    off" - which is what the dashboard banner and the admin screens want.

    Called with a judge document it answers "may this person submit right now",
    which additionally lets exception jury through while judging is locked.

    Args:
        judge: Optional judges document. Exception jury bypass the lock.

    Returns:
        bool: True if judging is allowed, False if locked
    """
    status = get_judging_status()
    if not status['is_locked']:
        return True

    # Imported lazily so jury_scope stays a leaf module and cannot end up in an
    # import cycle with this one.
    from services.jury_scope import is_exception_jury
    return is_exception_jury(judge)

