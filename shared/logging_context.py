import contextvars
import uuid
import time
from typing import Dict, Any


# Global context variables with safe defaults
correlation_id_var = contextvars.ContextVar("correlation_id", default="-")
user_id_var = contextvars.ContextVar("user_id", default="anonymous")
ip_address_var = contextvars.ContextVar("ip_address", default="unknown")
request_start_time_var = contextvars.ContextVar("request_start_time", default=0)


class LoggingContext:
    """Centralized logging context manager with error handling"""
    
    @staticmethod
    def set_correlation_id(correlation_id: str = None) -> str:
        """Set correlation ID for request tracing"""
        try:
            if correlation_id is None:
                correlation_id = str(uuid.uuid4())[:8]
            correlation_id_var.set(correlation_id)
            return correlation_id
        except Exception:
            return "-"
    
    @staticmethod
    def get_correlation_id() -> str:
        """Get current correlation ID"""
        try:
            return correlation_id_var.get()
        except Exception:
            return "-"
    
    @staticmethod
    def set_user_context(user_id: str, ip_address: str):
        """Set user context for logging"""
        try:
            user_id_var.set(user_id or "anonymous")
            ip_address_var.set(ip_address or "unknown")
        except Exception:
            pass
    
    @staticmethod
    def set_request_start_time():
        """Set request start time for performance tracking"""
        try:
            request_start_time_var.set(time.time())
        except Exception:
            pass
    
    @staticmethod
    def get_request_duration() -> float:
        """Get request duration in milliseconds"""
        try:
            start_time = request_start_time_var.get()
            if start_time and start_time > 0:
                return (time.time() - start_time) * 1000
        except Exception:
            pass
        return 0
    
    @staticmethod
    def clear_context():
        """Clear all context variables"""
        try:
            correlation_id_var.set("-")
            user_id_var.set("anonymous")
            ip_address_var.set("unknown")
            request_start_time_var.set(0)
        except Exception:
            pass
    
    @staticmethod
    def get_full_context() -> Dict[str, Any]:
        """Get all current context"""
        try:
            return {
                'correlation_id': correlation_id_var.get(),
                'user_id': user_id_var.get(),
                'ip_address': ip_address_var.get(),
                'request_duration': LoggingContext.get_request_duration()
            }
        except Exception:
            return {
                'correlation_id': '-',
                'user_id': 'anonymous',
                'ip_address': 'unknown',
                'request_duration': 0
            }


# Safe utility functions for structured logging
def log_security_event(logger, level: str, message: str, **context):
    """Log security-related events with structured context"""
    try:
        extra_context = {
            'user_id': user_id_var.get(),
            'ip_address': ip_address_var.get(),
            'correlation_id': correlation_id_var.get(),
            **context
        }
    except Exception:
        extra_context = {
            'user_id': 'anonymous',
            'ip_address': 'unknown',
            'correlation_id': '-',
            **context
        }
    
    getattr(logger, level.lower())(message, extra=extra_context)


def log_audit_event(logger, action: str, resource: str, outcome: str, **context):
    """Log audit trail events"""
    try:
        extra_context = {
            'action': action,
            'resource': resource,
            'outcome': outcome,
            'user_id': user_id_var.get(),
            'ip_address': ip_address_var.get(),
            'correlation_id': correlation_id_var.get(),
            **context
        }
    except Exception:
        extra_context = {
            'action': action,
            'resource': resource,
            'outcome': outcome,
            'user_id': 'anonymous',
            'ip_address': 'unknown',
            'correlation_id': '-',
            **context
        }
    
    logger.info(f"Audit: {action} on {resource} - {outcome}", extra=extra_context)


def log_performance_event(logger, operation: str, duration: float, **context):
    """Log performance metrics"""
    try:
        extra_context = {
            'operation': operation,
            'duration': duration,
            'correlation_id': correlation_id_var.get(),
            **context
        }
    except Exception:
        extra_context = {
            'operation': operation,
            'duration': duration,
            'correlation_id': '-',
            **context
        }
    
    logger.info(f"Performance: {operation} took {duration:.2f}ms", extra=extra_context)
