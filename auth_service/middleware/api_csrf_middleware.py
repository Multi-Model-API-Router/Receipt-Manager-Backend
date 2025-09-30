# apps/auth_service/middleware/api_csrf_middleware.py
from django.utils.deprecation import MiddlewareMixin
import logging

logger = logging.getLogger(__name__)

class CSRFExemptAPIMiddleware(MiddlewareMixin):
    """
    Exempt API endpoints from CSRF protection
    """
    
    def process_request(self, request):
        # Check if this is an API request
        if request.path.startswith('/api/'):
            setattr(request, '_dont_enforce_csrf_checks', True)
            logger.debug(f"CSRF exempted for API path: {request.path}")
        return None
