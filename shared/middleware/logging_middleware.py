import time
import uuid
from django.utils.deprecation import MiddlewareMixin
from shared.logging_context import LoggingContext, log_performance_event, log_security_event
import logging


logger = logging.getLogger('middleware')
performance_logger = logging.getLogger('performance')
security_logger = logging.getLogger('middleware.security')


class LoggingContextMiddleware(MiddlewareMixin):
    """
    Middleware to set up logging context for each request
    """
    
    def process_request(self, request):
        """Set up logging context at start of request"""
        # Generate or extract correlation ID
        correlation_id = (
            request.META.get('HTTP_X_CORRELATION_ID') or
            request.META.get('HTTP_X_REQUEST_ID') or
            str(uuid.uuid4())[:8]
        )
        
        # Set correlation ID
        LoggingContext.set_correlation_id(correlation_id)
        
        # Set user context
        user_id = 'anonymous'
        if hasattr(request, 'user') and request.user.is_authenticated:
            user_id = str(request.user.id)
        
        ip_address = self._get_client_ip(request)
        LoggingContext.set_user_context(user_id, ip_address)
        
        # Set request start time
        LoggingContext.set_request_start_time()
        
        # Store in request for other middleware/views
        request.correlation_id = correlation_id
        request.client_ip = ip_address
        
        # Log request start
        logger.info(
            f"Request started: {request.method} {request.path}",
            extra={
                'method': request.method,
                'path': request.path,
                'user_agent': request.META.get('HTTP_USER_AGENT', ''),
                'referer': request.META.get('HTTP_REFERER', ''),
            }
        )
        
        return None
    
    def process_response(self, request, response):
        """Log response and performance metrics"""
        duration = LoggingContext.get_request_duration()
        
        # Log response
        logger.info(
            f"Request completed: {request.method} {request.path} - {response.status_code}",
            extra={
                'method': request.method,
                'path': request.path,
                'status_code': response.status_code,
                'duration': duration,
            }
        )
        
        # Log performance if request took too long
        if duration > 1000:  # > 1 second
            log_performance_event(
                performance_logger,
                f"{request.method} {request.path}",
                duration,
                status_code=response.status_code
            )
        
        # Log security events for suspicious responses
        if response.status_code in [401, 403, 429]:
            log_security_event(
                security_logger,
                'warning',
                f"Security response: {response.status_code} for {request.path}",
                status_code=response.status_code,
                method=request.method,
                path=request.path
            )
        
        # Add correlation ID to response headers
        response['X-Correlation-ID'] = LoggingContext.get_correlation_id()
        
        return response
    
    def process_exception(self, request, exception):
        """Log exceptions with full context"""
        duration = LoggingContext.get_request_duration()
        
        logger.error(
            f"Request exception: {request.method} {request.path} - {exception.__class__.__name__}: {str(exception)}",
            extra={
                'method': request.method,
                'path': request.path,
                'exception_type': exception.__class__.__name__,
                'duration': duration,
            },
            exc_info=True
        )
        
        return None
    
    def _get_client_ip(self, request) -> str:
        """Extract client IP from request"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR', '0.0.0.0')
        return ip


class StructuredLoggingMiddleware(MiddlewareMixin):
    """
    Middleware for structured logging with metrics collection
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        self.slow_request_threshold = 2000  # 2 seconds in milliseconds
    
    def __call__(self, request):
        # Pre-processing
        start_time = time.time()
        
        # Process request
        response = self.get_response(request)
        
        # Post-processing
        duration = (time.time() - start_time) * 1000  # Convert to milliseconds
        
        # Structured logging
        self._log_request_metrics(request, response, duration)
        
        return response
    
    def _log_request_metrics(self, request, response, duration):
        """Log structured request metrics"""
        metrics = {
            'event_type': 'http_request',
            'method': request.method,
            'path': request.path,
            'status_code': response.status_code,
            'duration_ms': round(duration, 2),
            'user_id': getattr(request.user, 'id', None) if hasattr(request, 'user') and request.user.is_authenticated else None,
            'ip_address': request.META.get('REMOTE_ADDR', ''),
            'user_agent': request.META.get('HTTP_USER_AGENT', ''),
            'content_length': len(response.content) if hasattr(response, 'content') else 0,
        }
        
        # Determine log level based on response
        if response.status_code >= 500:
            log_level = 'error'
        elif response.status_code >= 400:
            log_level = 'warning'
        elif duration > self.slow_request_threshold:
            log_level = 'warning'
        else:
            log_level = 'info'
        
        # Log with structured data
        getattr(logger, log_level)(
            f"HTTP {request.method} {request.path} - {response.status_code} ({duration:.1f}ms)",
            extra=metrics
        )
