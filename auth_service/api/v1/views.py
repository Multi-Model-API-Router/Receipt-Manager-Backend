from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.throttling import UserRateThrottle, AnonRateThrottle
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django.core.cache import cache
import logging
from typing import Dict, Any
from django.utils import timezone
from datetime import datetime

from ...services.auth_import_service import import_service
from ...services.auth_model_service import model_service
from shared.utils.responses import success_response
from shared.utils.exceptions import (
    # Validation exceptions
    ValidationException,
    
    # Authentication exceptions
    AuthenticationException,
    AuthorizationException,  # Now we'll use this
    InvalidTokenException,
    TokenExpiredException,
    AccountLockedException,
    
    # User management exceptions
    UserNotFoundException,
    EmailAlreadyExistsException,
    
    # Email exceptions
    EmailServiceException,
    
    # Service exceptions
    ServiceUnavailableException,
    DatabaseOperationException,
    
    # Security exceptions
    RateLimitExceededException,
    SecurityViolationException,
    
    # Business logic exceptions
    BusinessLogicException,
    QuotaExceededException,

    # Magic link specific exceptions
    InvalidMagicLinkException,
    MagicLinkExpiredException,
    MagicLinkAlreadyUsedException,
    TokenGenerationException
)
from .serializers import (
    RequestMagicLinkSerializer,
    MagicLinkLoginSerializer,
    UserProfileSerializer,
    UpdateEmailSerializer,
    EmailVerificationSerializer,
    RefreshTokenSerializer
)
from ...tasks import (
    send_email_verification_async,
    send_welcome_email_async
)

logger = logging.getLogger(__name__)

class RequestMagicLinkView(APIView):
    """Request magic link for authentication with enhanced error handling"""
    permission_classes = [AllowAny]
    throttle_classes = [AnonRateThrottle]
    
    def post(self, request) -> Dict[str, Any]:
        """Send magic link to email with comprehensive validation"""
        try:
            # Validate serializer
            serializer = RequestMagicLinkSerializer(data=request.data)
            
            if not serializer.is_valid():
                raise ValidationException(
                    detail="Invalid request data",
                    context={'errors': serializer.errors}
                )
            
            email = serializer.validated_data['email']
            
            # Get client information
            client_ip = getattr(request, 'client_ip', request.META.get('REMOTE_ADDR'))
            user_agent = request.META.get('HTTP_USER_AGENT', '')
            
            # Additional security checks
            self._validate_request_security(request, email)
            
            # Generate magic link
            auth_service = import_service.auth_service
            magic_link_data = auth_service.request_magic_link(
                email=email,
                request_ip=client_ip,
                user_agent=user_agent
            )
            
            # Send email asynchronously
            try:
                # Send email synchronously for development
                email_service = import_service.email_service
                success = email_service.send_magic_link_email(email, magic_link_data['token'])
                
                if success:
                    task_id = 'sync_email_sent'
                    logger.info(f"Magic link email sent successfully to: {email}")
                else:
                    task_id = 'sync_email_failed'
                    logger.warning(f"Magic link email failed to send to: {email}")
                    
            except Exception as e:
                logger.error(f"Email sending error: {str(e)}")
                task_id = 'sync_email_error'
            
            logger.info(f"Magic link requested for: {email}, task_id: {task_id}")
            
            return success_response(
                message="Magic link sent to your email address",
                data={
                    'email': email,
                    'expires_at': magic_link_data['expires_at'],
                }
            )
            
        except (ValidationException, RateLimitExceededException, SecurityViolationException,
                EmailServiceException, DatabaseOperationException):
            # Re-raise our custom exceptions
            raise
        except Exception as e:
            logger.error(f"Unexpected error in magic link request: {str(e)}")
            raise ServiceUnavailableException("Magic link service temporarily unavailable")
    
    def _validate_request_security(self, request, email: str):
        """Additional security validation"""
        # Check for suspicious patterns
        client_ip = getattr(request, 'client_ip', request.META.get('REMOTE_ADDR'))
        
        # Check if IP is making too many requests across different emails
        cache_key = f"magic_link_emails_per_ip:{client_ip}"
        unique_emails = cache.get(cache_key, set())
        
        if isinstance(unique_emails, set) and len(unique_emails) >= 10:  # 10 different emails from same IP
            raise SecurityViolationException(
                "Suspicious activity detected from this IP address",
                context={'ip_address': client_ip}
            )
        
        # Add current email to set
        if isinstance(unique_emails, set):
            unique_emails.add(email)
            cache.set(cache_key, unique_emails, timeout=3600)

class MagicLinkLoginView(APIView):
    """Authenticate using magic link with enhanced security"""
    permission_classes = [AllowAny]
    throttle_classes = [AnonRateThrottle]
    
    def post(self, request) -> Dict[str, Any]:
        """Verify magic link and login user with comprehensive validation"""
        try:
            # Validate serializer
            serializer = MagicLinkLoginSerializer(data=request.data)
            
            if not serializer.is_valid():
                raise ValidationException(
                    detail="Invalid request data",
                    context={'errors': serializer.errors}
                )
            
            token = serializer.validated_data['token']
            client_ip = getattr(request, 'client_ip', request.META.get('REMOTE_ADDR'))
            
            # Additional security validation
            self._validate_login_security(request, token)
            
            # Verify magic link
            auth_service = import_service.auth_service
            user_data, is_new_user = auth_service.verify_magic_link(token, client_ip)
            
            # Send welcome email for new users (async)
            if is_new_user:
                try:
                    send_welcome_email_async.delay(
                        user_data['user']['email'],
                        user_data['user']['first_name'] or 'User'
                    )
                except Exception as e:
                    logger.warning(f"Failed to queue welcome email: {str(e)}")
                    # Don't fail login if welcome email fails
            
            logger.info(f"Successful login for: {user_data['user']['email']}")
            
            response_message = "Welcome! Account created successfully." if is_new_user else "Login successful"
            
            return success_response(
                message=response_message,
                data={
                    'user': user_data['user'],
                    'tokens': user_data['tokens'],
                    'is_new_user': is_new_user
                }
            )
            
        except (
            # Don't catch these - let them propagate with their specific error messages
            ValidationException, 
            InvalidMagicLinkException,           # Let this through
            MagicLinkExpiredException,           # Let this through  
            MagicLinkAlreadyUsedException,       # Let this through
            InvalidTokenException, 
            AccountLockedException,
            SecurityViolationException, 
            DatabaseOperationException,
            TokenGenerationException,
            RateLimitExceededException
        ):
            # Re-raise these exceptions as-is so their specific messages are preserved
            raise
            
        except Exception as e:
            # Only catch truly unexpected errors
            logger.error(f"Unexpected error in magic link login: {str(e)}")
            raise ServiceUnavailableException("Login service temporarily unavailable")
    
    def _validate_login_security(self, request, token: str):
        """Additional login security validation"""
        client_ip = getattr(request, 'client_ip', request.META.get('REMOTE_ADDR'))
        
        # Check for rapid login attempts from same IP
        cache_key = f"login_attempts_ip:{client_ip}"
        attempts = cache.get(cache_key, 0)
        
        if attempts >= 20:  # 20 attempts per hour from same IP
            raise SecurityViolationException(
                "Too many login attempts from this IP address",
                context={'ip_address': client_ip, 'retry_after': 3600}
            )
        
        cache.set(cache_key, attempts + 1, timeout=3600)

class UserProfileView(APIView):
    """User profile management with authorization checks"""
    permission_classes = [IsAuthenticated]
    throttle_classes = [UserRateThrottle]
    
    def get(self, request) -> Dict[str, Any]:
        """Get user profile with security validation"""
        try:
            # Validate user access
            self._validate_user_access(request.user)
            
            serializer = UserProfileSerializer(request.user)
            
            # Add additional data
            profile_data = serializer.data
            profile_data.update({
                'upload_limit': 50,
                'remaining_uploads': max(0, 50 - request.user.monthly_upload_count),
                'account_status': 'active' if not request.user.is_account_locked() else 'locked',
                'last_login': request.user.last_login.isoformat() if request.user.last_login else None
            })
            
            return success_response(
                message="Profile retrieved successfully",
                data=profile_data
            )
            
        except (AuthorizationException, AccountLockedException):
            raise
        except Exception as e:
            logger.error(f"Error retrieving profile for user {request.user.id}: {str(e)}")
            raise ServiceUnavailableException("Profile service temporarily unavailable")
    
    def put(self, request) -> Dict[str, Any]:
        """Update user profile with validation and authorization"""
        try:
            # Validate user access and permissions
            self._validate_user_access(request.user)
            self._validate_profile_update_permissions(request.user, request.data)
            
            serializer = UserProfileSerializer(
                request.user, 
                data=request.data, 
                partial=True
            )
            
            if not serializer.is_valid():
                raise ValidationException(
                    detail="Invalid profile data",
                    context={'errors': serializer.errors}
                )
            
            # Handle email update separately with additional validation
            if 'email' in serializer.validated_data:
                new_email = serializer.validated_data.pop('email')
                
                # Check email update permissions
                if not self._can_update_email(request.user):
                    raise AuthorizationException("Email updates are restricted for this account")
                
                auth_service = import_service.auth_service
                email_update_result = auth_service.update_user_email(
                    str(request.user.id), 
                    new_email
                )
                
                # Generate and send verification email
                try:
                    verification_token = auth_service.generate_email_verification_token(
                        str(request.user.id)
                    )
                    
                    send_email_verification_async.delay(
                        new_email,
                        verification_token,
                        request.user.first_name or 'User'
                    )
                except Exception as e:
                    logger.error(f"Failed to send verification email: {str(e)}")
                    # Don't fail the update, but inform user
            
            # Update other fields
            user = serializer.save()
            
            logger.info(f"Profile updated for user: {user.email}")
            
            return success_response(
                message="Profile updated successfully",
                data=UserProfileSerializer(user).data
            )
            
        except (ValidationException, AuthorizationException, EmailAlreadyExistsException,
                DatabaseOperationException):
            raise
        except Exception as e:
            logger.error(f"Error updating profile for user {request.user.id}: {str(e)}")
            raise ServiceUnavailableException("Profile update service temporarily unavailable")
    
    def _validate_user_access(self, user):
        """Validate user has access to their profile"""
        if not user.is_active:
            raise AuthorizationException("Account has been deactivated")
        
        if user.is_account_locked():
            raise AccountLockedException("Account is temporarily locked")
    
    def _validate_profile_update_permissions(self, user, data):
        """Validate user permissions for profile updates"""
        # Check if user can update sensitive fields
        sensitive_fields = ['email', 'is_email_verified']
        
        for field in sensitive_fields:
            if field in data and field == 'is_email_verified':
                # Only allow system to set email verification status
                raise AuthorizationException(f"Cannot directly modify {field}")
    
    def _can_update_email(self, user) -> bool:
        """Check if user can update their email address"""
        # Business logic: limit email updates
        from datetime import timedelta
        
        # Check if user has updated email recently (within 24 hours)
        if hasattr(user, 'email_verifications'):
            recent_updates = user.email_verifications.filter(
                created_at__gte=timezone.now() - timedelta(hours=24)
            ).count()
            
            if recent_updates >= 3:  # Max 3 email updates per day
                return False
        
        return True

# apps/auth_service/api/v1/views.py
class UpdateEmailView(APIView):
    """Update user email address with enhanced validation"""
    permission_classes = [IsAuthenticated]
    throttle_classes = [UserRateThrottle]
    
    def post(self, request) -> Dict[str, Any]:
        """Update user email with comprehensive validation"""
        try:
            # Validate user permissions
            self._validate_email_update_permissions(request.user)
            
            serializer = UpdateEmailSerializer(data=request.data)
            
            if not serializer.is_valid():
                raise ValidationException(
                    detail="Invalid email data",
                    context={'errors': serializer.errors}
                )
            
            new_email = serializer.validated_data['new_email']
            
            # Additional business validation
            self._validate_email_change_business_rules(request.user, new_email)
            
            auth_service = import_service.auth_service
            
            # Update email
            update_result = auth_service.update_user_email(
                str(request.user.id),
                new_email
            )
            
            # Generate and send verification
            verification_token = auth_service.generate_email_verification_token(
                str(request.user.id)
            )
            
            task = send_email_verification_async.delay(
                new_email,
                verification_token,
                request.user.first_name or 'User'
            )
            
            logger.info(f"Email update initiated for user: {request.user.id}")
            
            return success_response(
                message="Email updated. Please check your new email for verification.",
                data={
                    'old_email': update_result['old_email'],
                    'new_email': update_result['new_email'],
                    'verification_required': True,
                    'task_id': task.id
                }
            )
            
        except (ValidationException, AuthorizationException, EmailAlreadyExistsException,
                BusinessLogicException, DatabaseOperationException):
            raise
        except Exception as e:
            logger.error(f"Email update failed for user {request.user.id}: {str(e)}")
            raise ServiceUnavailableException("Email update service temporarily unavailable")
    
    def _validate_email_update_permissions(self, user):
        """Validate user can update email"""
        if not user.is_active:
            raise AuthorizationException("Account must be active to update email")
        
        if user.is_account_locked():
            raise AccountLockedException("Cannot update email while account is locked")
    
    def _validate_email_change_business_rules(self, user, new_email: str):
        """Validate business rules for email changes"""
        # Check if it's the same email
        if user.email.lower() == new_email.lower():
            raise BusinessLogicException("New email must be different from current email")
        
        # Check email change frequency using model_service directly
        from datetime import timedelta
        from django.utils import timezone
        
        # Fix: Use model_service directly instead of the broken import_service chain
        EmailVerification = model_service.email_verification_model
        
        recent_changes = EmailVerification.objects.filter(
            user=user,
            created_at__gte=timezone.now() - timedelta(days=1)
        ).count()
        
        if recent_changes >= 3:
            raise QuotaExceededException("Email update limit exceeded. Try again tomorrow.")

class EmailVerificationView(APIView):
    """Verify email address with enhanced validation"""
    permission_classes = [AllowAny]
    throttle_classes = [AnonRateThrottle]
    
    def post(self, request) -> Dict[str, Any]:
        """Verify email with token and comprehensive validation"""
        try:
            serializer = EmailVerificationSerializer(data=request.data)
            
            if not serializer.is_valid():
                raise ValidationException(
                    detail="Invalid verification data",
                    context={'errors': serializer.errors}
                )
            
            token = serializer.validated_data['token']
            
            # Additional security checks
            self._validate_verification_security(request, token)
            
            auth_service = import_service.auth_service
            verification_result = auth_service.verify_email(token)
            
            logger.info(f"Email verified for user: {verification_result['user_id']}")
            
            return success_response(
                message="Email verified successfully",
                data=verification_result
            )
            
        except (ValidationException, InvalidTokenException, SecurityViolationException):
            raise
        except Exception as e:
            logger.error(f"Email verification failed: {str(e)}")
            raise AuthenticationException("Email verification failed")
    
    def _validate_verification_security(self, request, token: str):
        """Additional verification security checks"""
        client_ip = getattr(request, 'client_ip', request.META.get('REMOTE_ADDR'))
        
        # Rate limit verification attempts per IP
        cache_key = f"email_verify_attempts:{client_ip}"
        attempts = cache.get(cache_key, 0)
        
        if attempts >= 10:  # 10 attempts per hour
            raise RateLimitExceededException(
                "Too many verification attempts from this IP",
                retry_after=3600
            )
        
        cache.set(cache_key, attempts + 1, timeout=3600)

class ResendVerificationView(APIView):
    """Resend email verification with rate limiting"""
    permission_classes = [IsAuthenticated]
    throttle_classes = [UserRateThrottle]
    
    def post(self, request) -> Dict[str, Any]:
        """Resend email verification with validation"""
        try:
            # Check if already verified
            if request.user.is_email_verified:
                return success_response(
                    message="Email is already verified",
                    data={'email': request.user.email, 'verified': True}
                )
            
            # Validate user can request verification
            self._validate_resend_permissions(request.user)
            
            # Check resend rate limiting
            self._check_resend_rate_limit(request.user)
            
            auth_service = import_service.auth_service
            
            # Generate new verification token
            verification_token = auth_service.generate_email_verification_token(
                str(request.user.id)
            )
            
            # Send verification email
            task = send_email_verification_async.delay(
                request.user.email,
                verification_token,
                request.user.first_name or 'User'
            )
            
            logger.info(f"Verification email resent for user: {request.user.id}")
            
            return success_response(
                message="Verification email sent",
                data={
                    'email': request.user.email,
                    'task_id': task.id
                }
            )
            
        except (AuthorizationException, RateLimitExceededException, EmailServiceException):
            raise
        except Exception as e:
            logger.error(f"Failed to resend verification for user {request.user.id}: {str(e)}")
            raise ServiceUnavailableException("Email verification service temporarily unavailable")
    
    def _validate_resend_permissions(self, user):
        """Validate user can request verification resend"""
        if not user.is_active:
            raise AuthorizationException("Account must be active to resend verification")
        
        if user.is_account_locked():
            raise AccountLockedException("Cannot resend verification while account is locked")
    
    def _check_resend_rate_limit(self, user):
        """Check rate limiting for verification resends"""
        cache_key = f"resend_verification:{user.id}"
        resend_count = cache.get(cache_key, 0)
        
        if resend_count >= 3:  # 3 resends per hour
            raise RateLimitExceededException(
                "Too many verification resend requests. Try again later.",
                retry_after=3600
            )
        
        cache.set(cache_key, resend_count + 1, timeout=3600)

class RefreshTokenView(APIView):
    """Refresh JWT access token with enhanced validation"""
    permission_classes = [AllowAny]
    throttle_classes = [UserRateThrottle]
    
    def post(self, request) -> Dict[str, Any]:
        """Refresh access token with comprehensive validation"""
        try:
            serializer = RefreshTokenSerializer(data=request.data)
            
            if not serializer.is_valid():
                raise ValidationException(
                    detail="Invalid token data",
                    context={'errors': serializer.errors}
                )
            
            refresh_token = serializer.validated_data['refresh']
            
            # Additional security validation
            self._validate_token_refresh_security(request, refresh_token)
            
            auth_service = import_service.auth_service
            new_tokens = auth_service.refresh_jwt_token(refresh_token)
            
            return success_response(
                message="Token refreshed successfully",
                data={'tokens': new_tokens}
            )
            
        except (ValidationException, InvalidTokenException, TokenExpiredException,
                SecurityViolationException):
            raise
        except Exception as e:
            logger.error(f"Token refresh failed: {str(e)}")
            raise AuthenticationException("Token refresh failed")
    
    def _validate_token_refresh_security(self, request, refresh_token: str):
        """Additional token refresh security validation"""
        client_ip = getattr(request, 'client_ip', request.META.get('REMOTE_ADDR'))
        
        # Rate limit refresh attempts per IP
        cache_key = f"token_refresh_ip:{client_ip}"
        attempts = cache.get(cache_key, 0)
        
        if attempts >= 50:  # 50 refreshes per hour per IP
            raise SecurityViolationException(
                "Too many token refresh attempts from this IP",
                context={'ip_address': client_ip, 'retry_after': 3600}
            )
        
        cache.set(cache_key, attempts + 1, timeout=3600)

# Keep existing LogoutView, LogoutAllDevicesView, and UserStatsView with minor enhancements...

class UserStatsView(APIView):
    """User statistics and usage with authorization"""
    permission_classes = [IsAuthenticated]
    throttle_classes = [UserRateThrottle]
    
    @method_decorator(cache_page(300))
    def get(self, request) -> Dict[str, Any]:
        """Get user statistics with access validation"""
        try:
            # Validate user access
            if not request.user.is_active:
                raise AuthorizationException("Account must be active to view statistics")
            
            user = request.user
            
            # Get cached stats or calculate
            cache_key = f"user_stats:{user.id}"
            stats = cache.get(cache_key)
            
            if not stats:
                # Calculate stats with error handling
                try:
                    stats = {
                        'upload_count': user.monthly_upload_count,
                        'upload_limit': 50,
                        'remaining_uploads': max(0, 50 - user.monthly_upload_count),
                        'account_age_days': (timezone.now() - user.created_at).days,
                        'email_verified': user.is_email_verified,
                        'account_status': 'active' if not user.is_account_locked() else 'locked',
                        'last_login': user.last_login.isoformat() if user.last_login else None
                    }
                    
                    # Cache stats for 5 minutes
                    cache.set(cache_key, stats, timeout=300)
                    
                except Exception as e:
                    logger.error(f"Error calculating user stats: {str(e)}")
                    raise ServiceUnavailableException("Statistics service temporarily unavailable")
            
            return success_response(
                message="User statistics retrieved",
                data=stats
            )
            
        except (AuthorizationException, ServiceUnavailableException):
            raise
        except Exception as e:
            logger.error(f"Error retrieving stats for user {request.user.id}: {str(e)}")
            raise ServiceUnavailableException("Statistics service temporarily unavailable")

class LogoutView(APIView):
    """Enhanced logout with JWT token blacklisting and comprehensive error handling"""
    permission_classes = [IsAuthenticated]
    throttle_classes = [UserRateThrottle]
    
    def post(self, request) -> Dict[str, Any]:
        """
        Logout user and blacklist tokens with enhanced validation
        """
        try:
            # Validate user can logout
            self._validate_logout_permissions(request.user)
            
            # Get tokens from request
            refresh_token = request.data.get('refresh')
            access_token = None
            
            # Extract access token from header
            auth_header = request.META.get('HTTP_AUTHORIZATION')
            if auth_header and auth_header.startswith('Bearer '):
                access_token = auth_header.split(' ')[1]
            
            # Validate at least one token is provided
            if not refresh_token and not access_token:
                raise ValidationException("At least one token (access or refresh) must be provided for logout")
            
            jwt_service = import_service.jwt_service
            client_ip = getattr(request, 'client_ip', request.META.get('REMOTE_ADDR'))
            user_id = str(request.user.id)
            
            blacklisted_tokens = []
            blacklist_errors = []
            
            # Blacklist refresh token
            if refresh_token:
                try:
                    if jwt_service.blacklist_token(
                        token=refresh_token,
                        token_type='refresh',
                        user_id=user_id,
                        reason='logout',
                        ip_address=client_ip
                    ):
                        blacklisted_tokens.append('refresh')
                        logger.info(f"Refresh token blacklisted for user: {request.user.email}")
                    else:
                        blacklist_errors.append('refresh token blacklisting failed')
                except Exception as e:
                    logger.warning(f"Failed to blacklist refresh token: {str(e)}")
                    blacklist_errors.append(f'refresh token error: {str(e)}')
            
            # Blacklist access token
            if access_token:
                try:
                    if jwt_service.blacklist_token(
                        token=access_token,
                        token_type='access',
                        user_id=user_id,
                        reason='logout',
                        ip_address=client_ip
                    ):
                        blacklisted_tokens.append('access')
                        logger.info(f"Access token blacklisted for user: {request.user.email}")
                    else:
                        blacklist_errors.append('access token blacklisting failed')
                except Exception as e:
                    logger.warning(f"Failed to blacklist access token: {str(e)}")
                    blacklist_errors.append(f'access token error: {str(e)}')
            
            # Update user login info (don't fail logout if this fails)
            try:
                request.user.failed_login_attempts = 0
                request.user.last_login = timezone.now()
                request.user.save(update_fields=['failed_login_attempts', 'last_login'])
            except Exception as e:
                logger.warning(f"Failed to update user logout info: {str(e)}")
            
            # Log logout attempt
            self._log_logout_attempt(request.user, client_ip, success=True)
            
            logger.info(f"User logged out successfully: {request.user.email}")
            
            # Prepare response data
            response_data = {
                'user_id': user_id,
                'blacklisted_tokens': blacklisted_tokens,
                'logout_time': timezone.now().isoformat()
            }
            
            # Include warnings if some tokens failed to blacklist
            if blacklist_errors:
                response_data['warnings'] = blacklist_errors
                logger.warning(f"Logout completed with warnings for user {user_id}: {blacklist_errors}")
            
            return success_response(
                message="Logged out successfully",
                data=response_data
            )
            
        except (ValidationException, AuthorizationException, AccountLockedException):
            # Re-raise our custom exceptions
            raise
        except Exception as e:
            logger.error(f"Unexpected error during logout for user {request.user.id}: {str(e)}")
            
            # Log failed logout attempt
            client_ip = getattr(request, 'client_ip', request.META.get('REMOTE_ADDR'))
            self._log_logout_attempt(request.user, client_ip, success=False, error=str(e))
            
            # Even if there are errors, consider logout successful from user perspective
            return success_response(
                message="Logged out successfully",
                data={
                    'user_id': str(request.user.id),
                    'logout_time': timezone.now().isoformat(),
                    'note': 'Token cleanup may be pending due to system issues'
                }
            )
    
    def _validate_logout_permissions(self, user):
        """Validate user can perform logout"""
        if not user or not user.is_authenticated:
            raise AuthenticationException("User must be authenticated to logout")
        
        # Note: We don't prevent logout for locked/inactive accounts
        # as logout should always be allowed for security
    
    def _log_logout_attempt(self, user, ip_address: str, success: bool, error: str = None):
        """Log logout attempt for security monitoring - FIXED"""
        try:
            # Use model_service directly instead of the broken circular reference
            LoginAttempt = model_service.login_attempt_model
            
            LoginAttempt.objects.create(
                email=user.email,
                ip_address=ip_address or '0.0.0.0',
                success=success,
                failure_reason=f'logout_error: {error}' if error else 'logout_success'
            )
        except Exception as e:
            logger.warning(f"Failed to log logout attempt: {str(e)}")

class LogoutAllDevicesView(APIView):
    """Logout from all devices by blacklisting all user tokens"""
    permission_classes = [IsAuthenticated]
    throttle_classes = [UserRateThrottle]
    
    def post(self, request) -> Dict[str, Any]:
        """
        Logout user from all devices with comprehensive validation
        """
        try:
            # Validate user permissions
            self._validate_logout_all_permissions(request.user)
            
            # Additional security validation for this sensitive operation
            self._validate_logout_all_security(request)
            
            jwt_service = import_service.jwt_service
            client_ip = getattr(request, 'client_ip', request.META.get('REMOTE_ADDR'))
            user_id = str(request.user.id)
            
            # Blacklist all tokens for this user
            try:
                blacklisted_count = jwt_service.blacklist_user_tokens(
                    user_id=user_id,
                    reason='logout_all_devices',
                    ip_address=client_ip
                )
            except Exception as e:
                logger.error(f"Failed to blacklist all tokens for user {user_id}: {str(e)}")
                raise DatabaseOperationException("Failed to logout from all devices")
            
            # Update user security info
            try:
                request.user.failed_login_attempts = 0
                request.user.last_login = timezone.now()
                request.user.save(update_fields=['failed_login_attempts', 'last_login'])
            except Exception as e:
                logger.warning(f"Failed to update user info during logout all: {str(e)}")
            
            # Log security event
            self._log_logout_all_attempt(request.user, client_ip, blacklisted_count)
            
            logger.info(f"All devices logged out for user: {request.user.email}, tokens blacklisted: {blacklisted_count}")
            
            return success_response(
                message="Successfully logged out from all devices",
                data={
                    'user_id': user_id,
                    'blacklisted_tokens_count': blacklisted_count,
                    'logout_time': timezone.now().isoformat(),
                    'affected_devices': 'all'
                }
            )
            
        except (ValidationException, AuthorizationException, SecurityViolationException,
                DatabaseOperationException, RateLimitExceededException):
            raise
        except Exception as e:
            logger.error(f"Unexpected error in logout all devices for user {request.user.id}: {str(e)}")
            raise ServiceUnavailableException("Logout all devices service temporarily unavailable")
    
    def _validate_logout_all_permissions(self, user):
        """Validate user can perform logout from all devices"""
        if not user.is_active:
            raise AuthorizationException("Account must be active to logout from all devices")
        
        # Additional validation - ensure user is not performing this too frequently
        cache_key = f"logout_all_attempts:{user.id}"
        recent_attempts = cache.get(cache_key, 0)
        
        if recent_attempts >= 3:  # Max 3 logout-all operations per hour
            raise RateLimitExceededException(
                "Too many logout-all attempts. This is a security-sensitive operation.",
                retry_after=3600
            )
        
        cache.set(cache_key, recent_attempts + 1, timeout=3600)
    
    def _validate_logout_all_security(self, request):
        """Additional security validation for logout all devices"""
        client_ip = getattr(request, 'client_ip', request.META.get('REMOTE_ADDR'))
        
        # Check for suspicious patterns - same IP performing logout-all for multiple users
        cache_key = f"logout_all_ip:{client_ip}"
        ip_attempts = cache.get(cache_key, 0)
        
        if ip_attempts >= 5:  # Max 5 logout-all operations per hour from same IP
            raise SecurityViolationException(
                "Suspicious activity detected: too many logout-all requests from this IP",
                context={'ip_address': client_ip, 'retry_after': 3600}
            )
        
        cache.set(cache_key, ip_attempts + 1, timeout=3600)
        
        # Require recent authentication for this sensitive operation
        last_login = request.user.last_login
        if last_login and (timezone.now() - last_login).total_seconds() > 1800:  # 30 minutes
            raise AuthorizationException(
                "Recent authentication required for logout from all devices. Please login again."
            )
    
    def _log_logout_all_attempt(self, user, ip_address: str, token_count: int):
        """Log logout all devices attempt for security monitoring - FIXED"""
        try:
            logger.info(
                f"SECURITY_EVENT: Logout all devices - User: {user.email}, "
                f"IP: {ip_address}, Tokens blacklisted: {token_count}"
            )
            
            # Use model_service directly instead of the broken circular reference
            LoginAttempt = model_service.login_attempt_model
            
            LoginAttempt.objects.create(
                email=user.email,
                ip_address=ip_address or '0.0.0.0',
                success=True,
                failure_reason=f'logout_all_devices_success: {token_count} tokens'
            )
        except Exception as e:
            logger.warning(f"Failed to log logout all attempt: {str(e)}")

class ForceLogoutUserView(APIView):
    """Admin endpoint to force logout a user (for security incidents)"""
    permission_classes = [IsAuthenticated]  # Add admin permission in production
    
    def post(self, request) -> Dict[str, Any]:
        """
        Force logout a user (admin only)
        """
        try:
            # Validate admin permissions
            self._validate_admin_permissions(request.user)
            
            # Get target user ID
            target_user_id = request.data.get('user_id')
            if not target_user_id:
                raise ValidationException("User ID is required")
            
            reason = request.data.get('reason', 'admin_force_logout')
            
            # Validate reason
            valid_reasons = [
                'security_incident', 
                'admin_force_logout', 
                'account_compromise',
                'policy_violation'
            ]
            
            if reason not in valid_reasons:
                raise ValidationException(f"Invalid reason. Must be one of: {', '.join(valid_reasons)}")
            
            # Get target user - FIXED
            User = model_service.user_model
            
            try:
                target_user = User.objects.get(id=target_user_id)
            except User.DoesNotExist:
                raise UserNotFoundException("Target user not found")
            
            # Prevent self-logout via this endpoint
            if target_user.id == request.user.id:
                raise AuthorizationException("Cannot force logout yourself. Use regular logout endpoint.")
            
            # Blacklist all tokens for target user
            jwt_service = import_service.jwt_service
            client_ip = getattr(request, 'client_ip', request.META.get('REMOTE_ADDR'))
            
            blacklisted_count = jwt_service.blacklist_user_tokens(
                user_id=str(target_user.id),
                reason=reason,
                ip_address=client_ip
            )
            
            # Log security event
            logger.warning(
                f"ADMIN_ACTION: Force logout - Admin: {request.user.email}, "
                f"Target: {target_user.email}, Reason: {reason}, "
                f"Tokens blacklisted: {blacklisted_count}, IP: {client_ip}"
            )
            
            return success_response(
                message=f"User {target_user.email} has been logged out from all devices",
                data={
                    'target_user_id': str(target_user.id),
                    'target_user_email': target_user.email,
                    'blacklisted_tokens_count': blacklisted_count,
                    'reason': reason,
                    'admin_user': request.user.email,
                    'timestamp': timezone.now().isoformat()
                }
            )
            
        except (ValidationException, AuthorizationException, UserNotFoundException,
                DatabaseOperationException):
            raise
        except Exception as e:
            logger.error(f"Error in force logout: {str(e)}")
            raise ServiceUnavailableException("Force logout service temporarily unavailable")
    
    def _validate_admin_permissions(self, user):
        """Validate user has admin permissions"""
        # In production, implement proper admin role checking
        if not user.is_staff and not user.is_superuser:
            raise AuthorizationException("Admin permissions required for this operation")
        
        # Additional security check
        if not user.is_active:
            raise AuthorizationException("Admin account must be active")

# In apps/auth_service/api/v1/views.py
class CheckTokenStatusView(APIView):
    """Check if current token is valid and not blacklisted"""
    permission_classes = [IsAuthenticated]
    throttle_classes = [UserRateThrottle]
    
    def get(self, request) -> Dict[str, Any]:
        """Check current token status with proper timezone handling"""
        try:
            access_token = None
            auth_header = request.META.get('HTTP_AUTHORIZATION')
            
            if auth_header and auth_header.startswith('Bearer '):
                access_token = auth_header.split(' ')[1]
            else:
                raise ValidationException("No access token found in request")
            
            jwt_service = import_service.jwt_service
            
            # Check if token is blacklisted
            is_blacklisted = jwt_service.is_token_blacklisted(access_token)
            
            # Decode token to get expiry info with proper timezone handling
            try:
                decoded_token = jwt_service.decode_token(access_token, verify_exp=False)
                exp_timestamp = decoded_token.get('exp')
                
                if exp_timestamp:
                    expires_at = timezone.make_aware(
                        datetime.fromtimestamp(exp_timestamp),
                        timezone.get_current_timezone()
                    )
                    now = timezone.now()
                    time_until_expiry = expires_at - now
                else:
                    expires_at = None
                    time_until_expiry = None
                    
            except Exception as e:
                logger.warning(f"Could not decode token for status check: {str(e)}")
                expires_at = None
                time_until_expiry = None
            
            token_status = {
                'is_valid': not is_blacklisted and (time_until_expiry is None or time_until_expiry.total_seconds() > 0),
                'is_blacklisted': is_blacklisted,
                'expires_at': expires_at.isoformat() if expires_at else None,
                'seconds_until_expiry': int(time_until_expiry.total_seconds()) if time_until_expiry and time_until_expiry.total_seconds() > 0 else None,
                'user_id': str(request.user.id),
                'user_email': request.user.email
            }
            
            return success_response(
                message="Token status retrieved",
                data=token_status
            )
            
        except (ValidationException, InvalidTokenException):
            raise
        except Exception as e:
            logger.error(f"Error checking token status: {str(e)}")
            raise ServiceUnavailableException("Token status service temporarily unavailable")
