from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin
from rest_framework_simplejwt.authentication import JWTAuthentication
import logging

from ..services.jwt_service import jwt_service

logger = logging.getLogger(__name__)

class JWTBlacklistMiddleware(MiddlewareMixin):
    """
    Middleware to check JWT blacklist before processing requests
    Implements fail-fast pattern for blacklisted tokens
    """
    
    def __init__(self, get_response):
        super().__init__(get_response)
        self.jwt_auth = JWTAuthentication()
        self.protected_paths = ['/api/v1/']  # Paths that require JWT validation
    
    def process_request(self, request):
        """
        Check JWT blacklist before processing request
        """
        # Skip non-protected paths
        if not any(request.path.startswith(path) for path in self.protected_paths):
            return None
        
        # Skip if no authorization header
        auth_header = request.META.get('HTTP_AUTHORIZATION')
        if not auth_header or not auth_header.startswith('Bearer '):
            return None
        
        try:
            # Extract token
            token = auth_header.split(' ')[1]
            
            # Fast blacklist check
            if jwt_service.is_token_blacklisted(token):
                logger.warning(f"Blocked request with blacklisted token from IP: {self._get_client_ip(request)}")
                
                return JsonResponse({
                    'error': {
                        'code': 'token_blacklisted',
                        'message': 'Token has been revoked',
                        'status_code': 401
                    }
                }, status=401)
        
        except Exception as e:
            logger.error(f"Error in JWT blacklist middleware: {str(e)}")
            # Don't block request on middleware errors, let main auth handle it
            
        return None
    
    def _get_client_ip(self, request) -> str:
        """Extract client IP from request"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR', '0.0.0.0')
        return ip
