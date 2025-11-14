# shared/logging.py

import logging
import json
from datetime import datetime
from shared.logging_context import correlation_id_var, user_id_var, ip_address_var


class SafeFormatter(logging.Formatter):
    """
    Safe formatter that provides default values for missing fields
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
    
    def format(self, record):
        # Ensure all required fields have default values
        default_fields = {
            'correlation_id': correlation_id_var.get(),
            'user_id': 'anonymous',
            'ip_address': 'unknown',
            'method': 'unknown',
            'path': 'unknown',
            'duration': 0,
            'action': 'unknown',
            'resource': 'unknown',
            'receipt_id': '-',          # ← Added
            'task_name': '-',           # ← Added
            'user': 'anonymous',        # ← Added (alias for user_id)
            'ip': 'unknown',            # ← Added (alias for ip_address)
            'corr_id': '-',             # ← Added (alias for correlation_id)
        }
        
        for field, default_value in default_fields.items():
            if not hasattr(record, field):
                setattr(record, field, default_value)
        
        # Sync aliases
        if hasattr(record, 'user_id') and not hasattr(record, 'user'):
            record.user = record.user_id
        if hasattr(record, 'ip_address') and not hasattr(record, 'ip'):
            record.ip = record.ip_address
        if hasattr(record, 'correlation_id') and not hasattr(record, 'corr_id'):
            record.corr_id = record.correlation_id
        
        return super().format(record)


class CorrelationIdFilter(logging.Filter):
    """Inject correlation_id into log records from contextvars"""
    
    def filter(self, record):
        if not hasattr(record, 'correlation_id'):
            record.correlation_id = correlation_id_var.get()
        if not hasattr(record, 'corr_id'):
            record.corr_id = record.correlation_id or '-'
        return True


class UserContextFilter(logging.Filter):
    """Inject user context into log records with safe defaults"""
    
    def filter(self, record):
        # Set correlation_id
        if not hasattr(record, 'correlation_id'):
            try:
                record.correlation_id = correlation_id_var.get()
            except:
                record.correlation_id = '-'
        
        if not hasattr(record, 'corr_id'):
            record.corr_id = record.correlation_id or '-'
        
        # Set user_id
        if not hasattr(record, 'user_id'):
            try:
                record.user_id = user_id_var.get()
            except:
                record.user_id = 'anonymous'
        
        if not hasattr(record, 'user'):
            record.user = record.user_id
        
        # Set ip_address
        if not hasattr(record, 'ip_address'):
            try:
                record.ip_address = ip_address_var.get()
            except:
                record.ip_address = 'unknown'
        
        if not hasattr(record, 'ip'):
            record.ip = record.ip_address
        
        # Set request context
        if not hasattr(record, 'method'):
            record.method = 'unknown'
        
        if not hasattr(record, 'path'):
            record.path = 'unknown'
        
        # Set additional fields
        if not hasattr(record, 'receipt_id'):
            record.receipt_id = '-'
        
        if not hasattr(record, 'task_name'):
            record.task_name = '-'
        
        return True


class PerformanceFilter(logging.Filter):
    """Filter for performance-related logs with safe defaults"""
    
    def filter(self, record):
        if not hasattr(record, 'duration'):
            record.duration = 0
        return True


class SecurityFilter(logging.Filter):
    """Filter for security-related logs"""
    
    def filter(self, record):
        # Only pass security-related log records
        security_keywords = [
            'security', 'auth', 'login', 'logout', 'permission', 'access',
            'rate_limit', 'blocked', 'suspicious', 'failed', 'breach',
            'blacklist', 'whitelist', 'csrf', 'xss', 'injection'
        ]
        
        message = str(record.getMessage()).lower()
        return any(keyword in message for keyword in security_keywords)


class AuditFilter(logging.Filter):
    """Filter for audit trail logs with safe defaults"""
    
    def filter(self, record):
        # Add audit context with defaults
        if not hasattr(record, 'action'):
            record.action = 'unknown'
        if not hasattr(record, 'resource'):
            record.resource = 'unknown'
        if not hasattr(record, 'outcome'):
            record.outcome = 'unknown'
        if not hasattr(record, 'user_id'):
            record.user_id = 'anonymous'
        if not hasattr(record, 'receipt_id'):
            record.receipt_id = '-'
        
        return True


class SafeJSONFormatter(logging.Formatter):
    """
    Safe JSON formatter that handles missing fields gracefully
    """
    def format(self, record):
        # Ensure all fields have default values
        log_entry = {
            'timestamp': datetime.fromtimestamp(record.created).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'correlation_id': getattr(record, 'correlation_id', '-'),
            'corr_id': getattr(record, 'corr_id', '-'),
            'user_id': getattr(record, 'user_id', 'anonymous'),
            'user': getattr(record, 'user', 'anonymous'),
            'ip_address': getattr(record, 'ip_address', 'unknown'),
            'ip': getattr(record, 'ip', 'unknown'),
            'method': getattr(record, 'method', 'unknown'),
            'path': getattr(record, 'path', 'unknown'),
            'receipt_id': getattr(record, 'receipt_id', '-'),
            'task_name': getattr(record, 'task_name', '-'),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
        }
        
        # Add exception info if present
        if record.exc_info:
            log_entry['exception'] = self.formatException(record.exc_info)
        
        # Add any extra fields that were passed
        for key, value in record.__dict__.items():
            if key not in log_entry and not key.startswith('_'):
                try:
                    # Ensure the value is JSON serializable
                    json.dumps(value)
                    log_entry[key] = value
                except (TypeError, ValueError):
                    log_entry[key] = str(value)
        
        return json.dumps(log_entry)


class CeleryTaskFilter(logging.Filter):
    """
    Filter specifically for Celery tasks
    Adds task-specific context
    """
    def filter(self, record):
        # Add Celery-specific fields
        if not hasattr(record, 'task_name'):
            record.task_name = getattr(record, 'name', '-')
        
        if not hasattr(record, 'task_id'):
            record.task_id = '-'
        
        if not hasattr(record, 'receipt_id'):
            record.receipt_id = '-'
        
        if not hasattr(record, 'user_id'):
            record.user_id = 'anonymous'
        
        # Ensure other required fields exist
        if not hasattr(record, 'correlation_id'):
            record.correlation_id = '-'
        
        if not hasattr(record, 'corr_id'):
            record.corr_id = record.correlation_id
        
        if not hasattr(record, 'user'):
            record.user = record.user_id
        
        if not hasattr(record, 'ip'):
            record.ip = 'unknown'
        
        if not hasattr(record, 'method'):
            record.method = 'unknown'
        
        if not hasattr(record, 'path'):
            record.path = 'unknown'
        
        return True
