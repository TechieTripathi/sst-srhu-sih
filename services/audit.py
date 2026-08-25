from datetime import datetime
from models.database import get_audit_logs_collection


def log_audit(actor_id, action, entity_type, entity_id, metadata=None):
    """
    Log an audit event
    
    Args:
        actor_id: User ID performing the action
        action: Action being performed
        entity_type: Type of entity being acted upon
        entity_id: ID of the entity
        metadata: Additional metadata dictionary
    """
    audit_logs = get_audit_logs_collection()
    
    log_entry = {
        'actor_id': actor_id,
        'action': action,
        'entity_type': entity_type,
        'entity_id': entity_id,
        'metadata': metadata or {},
        'created_at': datetime.utcnow()
    }
    
    audit_logs.insert_one(log_entry)
