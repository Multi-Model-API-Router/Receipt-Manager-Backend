import secrets
import hashlib
from datetime import timedelta
from django.utils import timezone
from django.core.cache import cache
from django.conf import settings
from django.db import transaction, DatabaseError
from typing import Dict, Tuple
import logging

from .auth_model_service import model_service
from .auth_import_service import import_service
from shared.utils.exceptions import (
    # Authentication exceptions
    InvalidMagicLinkException,
    MagicLinkExpiredException,
    MagicLinkAlreadyUsedException,
    InvalidTokenException,
    AccountLockedException,
    
    # User management exceptions
    UserNotFoundException,
    EmailAlreadyExistsException,
    InvalidEmailVerificationTokenException,
    EmailVerificationTokenExpiredException,
    
    # Database exceptions
    DatabaseOperationException,
    ModelCreationException,
    ModelUpdateException,
    CacheOperationException,
    
    # Security exceptions
    RateLimitExceededException,
    SuspiciousActivityException,
    
    # Token generation exceptions
    TokenGenerationException,
    CryptographicException,
    
    # Validation exceptions
    ValidationException,
    InvalidEmailFormatException,
    InvalidUserDataException,
    
    # Service exceptions
    ServiceConfigurationException
)

logger = logging.getLogger(__name__)

class AuthService:
    """Enhanced Authentication service with comprehensive exception handling"""
    
    def __init__(self):
        try:
            self.magic_link_expiry = getattr(settings, 'MAGIC_LINK_EXPIRY_MINUTES', 60)
            self.max_failed_attempts = getattr(settings, 'MAX_FAILED_LOGIN_ATTEMPTS', 5)
            self.account_lock_minutes = getattr(settings, 'ACCOUNT_LOCK_MINUTES', 30)
        except Exception as e:
            logger.error(f"Failed to initialize AuthService: {str(e)}")
            raise ServiceConfigurationException("Authentication service configuration error")
    
    def request_magic_link(
        self, 
        email: str, 
        request_ip: str = None,
        user_agent: str = None
    ) -> Dict[str, str]:
        """
        Generate and store magic link token with comprehensive error handling
        """
        try:
            # Validate email format
            self._validate_email_format(email)
            
            # Check rate limiting
            self._check_magic_link_rate_limit(email, request_ip)
            
            # Generate secure token
            try:
                raw_token = secrets.token_urlsafe(32)
                token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
            except Exception as e:
                logger.error(f"Token generation failed: {str(e)}")
                raise CryptographicException("Failed to generate secure token")
            
            # Create magic link record with transaction
            try:
                with transaction.atomic():
                    MagicLink = model_service.magic_link_model
                    magic_link = MagicLink.objects.create(
                        email=email,
                        token=token_hash,
                        expires_at=timezone.now() + timedelta(minutes=self.magic_link_expiry),
                        created_from_ip=request_ip,
                        user_agent=user_agent or ''
                    )
            except DatabaseError as e:
                logger.error(f"Database error creating magic link: {str(e)}")
                raise ModelCreationException("Failed to create magic link record")
            except Exception as e:
                logger.error(f"Unexpected error creating magic link: {str(e)}")
                raise DatabaseOperationException("Database operation failed")
            
            # Cache token for quick lookup
            try:
                cache_key = f"magic_link:{token_hash}"
                cache.set(cache_key, {
                    'email': email,
                    'magic_link_id': str(magic_link.id)
                }, timeout=self.magic_link_expiry * 60)
            except Exception as e:
                logger.warning(f"Cache operation failed: {str(e)}")
                # Don't fail the request if cache fails
                
            logger.info(f"Magic link requested for email: {email}")
            return {
                'token': raw_token,
                'expires_at': magic_link.expires_at.isoformat()
            }
            
        except (RateLimitExceededException, ValidationException, CryptographicException, 
                ModelCreationException, DatabaseOperationException):
            # Re-raise our custom exceptions
            raise
        except Exception as e:
            logger.error(f"Unexpected error in request_magic_link: {str(e)}")
            raise ServiceConfigurationException("Magic link generation failed")
    
    def verify_magic_link(
        self, 
        token: str, 
        request_ip: str = None
    ) -> Tuple[Dict, bool]:
        """
        Verify magic link with comprehensive validation and debugging
        """
        try:
            # Validate token format
            if not token or len(token.strip()) < 10:
                raise InvalidMagicLinkException("Invalid token format")
            
            original_token = token
            token_hash = hashlib.sha256(token.encode()).hexdigest()
            
            # Debug logging
            logger.info(f"Verifying magic link - Original token: {original_token[:20]}...")
            logger.info(f"Token hash: {token_hash[:20]}...")
            
            # Try cache first
            cache_key = f"magic_link:{token_hash}"
            try:
                cached_data = cache.get(cache_key)
                logger.info(f"Cache lookup result: {cached_data}")
            except Exception as e:
                logger.warning(f"Cache lookup failed: {str(e)}")
                cached_data = None
            
            MagicLink = model_service.magic_link_model
            User = model_service.user_model
            
            # Debug: Check what magic links exist
            recent_links = MagicLink.objects.filter(
                created_at__gte=timezone.now() - timedelta(hours=2)
            ).values('id', 'email', 'token', 'is_used', 'created_at', 'expires_at')
            
            logger.info(f"Recent magic links in database: {list(recent_links)}")
            
            # Wrap database operations in transaction
            with transaction.atomic():
                try:
                    if cached_data:
                        # Use select_for_update within transaction
                        logger.info(f"Using cached magic link ID: {cached_data['magic_link_id']}")
                        magic_link = MagicLink.objects.select_for_update().get(
                            id=cached_data['magic_link_id']
                        )
                    else:
                        # Use select_for_update within transaction
                        logger.info(f"Looking up magic link by token hash: {token_hash}")
                        magic_link = MagicLink.objects.select_for_update().get(
                            token=token_hash,
                            is_used=False
                        )
                except MagicLink.DoesNotExist:
                    # Additional debugging
                    logger.error(f"Magic link not found for token hash: {token_hash}")
                    
                    # Check if token exists but is used
                    used_link = MagicLink.objects.filter(token=token_hash, is_used=True).first()
                    if used_link:
                        logger.error(f"Magic link was already used: {used_link.id}")
                        raise MagicLinkAlreadyUsedException("Magic link already used")
                    
                    # Check if token exists but expired
                    expired_link = MagicLink.objects.filter(token=token_hash).first()
                    if expired_link:
                        logger.error(f"Magic link found but expired: {expired_link.expires_at}")
                        if expired_link.is_expired():
                            raise MagicLinkExpiredException("Magic link has expired")
                    
                    raise InvalidMagicLinkException("Invalid magic link token")
                
                # Mark as used
                magic_link.mark_as_used(request_ip)
                
                # Clear cache
                try:
                    cache.delete(cache_key)
                except Exception as e:
                    logger.warning(f"Cache clear failed: {str(e)}")
                
                # Get or create user
                user, is_new_user = User.objects.get_or_create(
                    email=magic_link.email,
                    defaults={
                        'username': magic_link.email,
                        'is_email_verified': True,
                        'last_login_ip': request_ip
                    }
                )
                
                if not is_new_user:
                    # Check if account is locked
                    if user.is_account_locked():
                        raise AccountLockedException("Account is temporarily locked")
                    
                    user.last_login_ip = request_ip
                    user.failed_login_attempts = 0
                    user.account_locked_until = None
                    user.save(update_fields=['last_login_ip', 'failed_login_attempts', 'account_locked_until'])
            
            # Generate JWT tokens (outside transaction)
            try:
                jwt_service = import_service.jwt_service
                token_data = jwt_service.generate_tokens(user)
            except Exception as e:
                logger.error(f"Token generation failed: {str(e)}")
                raise TokenGenerationException("Failed to generate authentication tokens")
            
            # Log successful login
            self._log_login_attempt(
                email=magic_link.email,
                ip_address=request_ip,
                success=True
            )
            
            logger.info(f"Successful magic link authentication for: {user.email}")
            
            return {
                'user': {
                    'id': str(user.id),
                    'email': user.email,
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                    'is_email_verified': user.is_email_verified,
                    'monthly_upload_count': user.monthly_upload_count,
                    'created_at': user.created_at.isoformat()
                },
                'tokens': {
                    'access': token_data['access'],
                    'refresh': token_data['refresh'],
                    'expires_at': token_data['expires_at'],
                    'refresh_expires_at': token_data['refresh_expires_at']
                }
            }, is_new_user
            
        except (InvalidMagicLinkException, MagicLinkExpiredException, MagicLinkAlreadyUsedException,
                AccountLockedException, TokenGenerationException):
            # Re-raise our custom exceptions
            raise
        except DatabaseError as e:
            logger.error(f"Database error in verify_magic_link: {str(e)}")
            raise DatabaseOperationException("Database operation failed")
        except Exception as e:
            logger.error(f"Unexpected error in verify_magic_link: {str(e)}")
            raise ServiceConfigurationException("Magic link verification failed")
    
    def generate_email_verification_token(self, user_id: str) -> str:
        """Generate email verification token with error handling and proper transactions"""
        try:
            User = model_service.user_model
            EmailVerification = model_service.email_verification_model
            
            try:
                user = User.objects.get(id=user_id)
            except User.DoesNotExist:
                raise UserNotFoundException("User not found")
            except (ValueError, TypeError):
                raise InvalidUserDataException("Invalid user ID format")
            except DatabaseError as e:
                logger.error(f"Database error retrieving user: {str(e)}")
                raise DatabaseOperationException("User lookup failed")
            
            with transaction.atomic():
                try:
                    # Invalidate existing tokens
                    EmailVerification.objects.filter(
                        user=user,
                        is_verified=False
                    ).update(is_verified=True)
                    
                    # Generate new token
                    raw_token = secrets.token_urlsafe(32)
                    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
                    
                    EmailVerification.objects.create(
                        user=user,
                        email=user.email,
                        token=token_hash,
                        expires_at=timezone.now() + timedelta(hours=24)
                    )
                    
                except DatabaseError as e:
                    logger.error(f"Database error creating verification token: {str(e)}")
                    raise ModelCreationException("Failed to create email verification token")
                except Exception as e:
                    logger.error(f"Token generation error: {str(e)}")
                    raise CryptographicException("Failed to generate verification token")
            
            return raw_token
            
        except (UserNotFoundException, InvalidUserDataException, DatabaseOperationException,
                ModelCreationException, CryptographicException):
            raise
        except Exception as e:
            logger.error(f"Unexpected error in generate_email_verification_token: {str(e)}")
            raise ServiceConfigurationException("Email verification token generation failed")

    
    def verify_email(self, token: str) -> Dict:
        """Verify email with comprehensive validation and proper transactions"""
        try:
            if not token or len(token.strip()) < 10:
                raise InvalidEmailVerificationTokenException("Invalid verification token format")
            
            token_hash = hashlib.sha256(token.encode()).hexdigest()
            EmailVerification = model_service.email_verification_model
            
            with transaction.atomic():
                try:
                    verification = EmailVerification.objects.select_for_update().get(
                        token=token_hash,
                        is_verified=False
                    )
                    
                    if verification.is_expired():
                        raise EmailVerificationTokenExpiredException("Verification token has expired")
                    
                    verification.mark_as_verified()
                    
                except EmailVerification.DoesNotExist:
                    raise InvalidEmailVerificationTokenException("Invalid verification token")
            
            logger.info(f"Email verified for user: {verification.user.email}")
            
            return {
                'user_id': str(verification.user.id),
                'email': verification.user.email,
                'verified_at': verification.verified_at.isoformat()
            }
            
        except (InvalidEmailVerificationTokenException, EmailVerificationTokenExpiredException):
            raise
        except DatabaseError as e:
            logger.error(f"Database error during email verification: {str(e)}")
            raise DatabaseOperationException("Email verification failed")
        except Exception as e:
            logger.error(f"Unexpected error in verify_email: {str(e)}")
            raise ServiceConfigurationException("Email verification failed")
    
    def update_user_email(self, user_id: str, new_email: str) -> Dict:
        """Update user email with validation and proper transactions"""
        try:
            # Validate email format
            self._validate_email_format(new_email)
            
            User = model_service.user_model
            
            try:
                user = User.objects.get(id=user_id)
            except User.DoesNotExist:
                raise UserNotFoundException("User not found")
            except (ValueError, TypeError):
                raise InvalidUserDataException("Invalid user ID format")
            
            # Check if email already exists
            if User.objects.filter(email=new_email).exclude(id=user_id).exists():
                raise EmailAlreadyExistsException("Email address already in use")
            
            with transaction.atomic():
                try:
                    old_email = user.email
                    user.email = new_email
                    user.is_email_verified = False
                    user.save(update_fields=['email', 'is_email_verified'])
                    
                except DatabaseError as e:
                    logger.error(f"Database error updating user email: {str(e)}")
                    raise ModelUpdateException("Failed to update user email")
            
            logger.info(f"Email updated from {old_email} to {new_email} for user {user_id}")
            
            return {
                'user_id': str(user.id),
                'old_email': old_email,
                'new_email': new_email,
                'verification_required': True
            }
            
        except (ValidationException, UserNotFoundException, InvalidUserDataException,
                EmailAlreadyExistsException, ModelUpdateException):
            raise
        except Exception as e:
            logger.error(f"Unexpected error in update_user_email: {str(e)}")
            raise ServiceConfigurationException("Email update failed")
    
    def refresh_jwt_token(self, refresh_token: str) -> Dict:
        """Refresh JWT token with error handling"""
        try:
            if not refresh_token or not refresh_token.strip():
                raise InvalidTokenException("Refresh token is required")
            
            jwt_service = import_service.jwt_service
            return jwt_service.refresh_token(refresh_token)
            
        except InvalidTokenException:
            raise
        except Exception as e:
            logger.error(f"Token refresh error: {str(e)}")
            raise TokenGenerationException("Token refresh failed")
    
    def _validate_email_format(self, email: str):
        """Validate email format"""
        if not email or not email.strip():
            raise InvalidEmailFormatException("Email address is required")
        
        import re
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, email.strip()):
            raise InvalidEmailFormatException("Invalid email address format")
    
    def _check_magic_link_rate_limit(self, email: str, ip_address: str):
        """Enhanced rate limiting with better error handling"""
        try:
            # Email-based rate limiting (5 requests per hour)
            email_key = f"magic_link_rate_email:{email}"
            email_count = cache.get(email_key, 0)
            
            if email_count >= 5:
                raise RateLimitExceededException(
                    "Too many magic link requests for this email. Try again later.",
                    retry_after=3600
                )
            
            # IP-based rate limiting (20 requests per hour)
            if ip_address:
                ip_key = f"magic_link_rate_ip:{ip_address}"
                ip_count = cache.get(ip_key, 0)
                
                if ip_count >= 20:
                    # Log suspicious activity
                    logger.warning(f"Suspicious activity detected from IP: {ip_address}")
                    raise SuspiciousActivityException(
                        "Too many requests from this IP address. Try again later.",
                        context={'ip_address': ip_address, 'retry_after': 3600}
                    )
                
                # Increment counters
                try:
                    cache.set(ip_key, ip_count + 1, timeout=3600)
                except Exception as e:
                    logger.warning(f"Cache increment failed for IP rate limit: {str(e)}")
            
            try:
                cache.set(email_key, email_count + 1, timeout=3600)
            except Exception as e:
                logger.warning(f"Cache increment failed for email rate limit: {str(e)}")
                
        except (RateLimitExceededException, SuspiciousActivityException):
            raise
        except Exception as e:
            logger.error(f"Rate limit check failed: {str(e)}")
            raise CacheOperationException("Rate limit validation failed")
    
    def _log_login_attempt(self, email: str, ip_address: str, success: bool, failure_reason: str = None):
        """Log login attempt with error handling"""
        try:
            LoginAttempt = model_service.login_attempt_model
            
            LoginAttempt.objects.create(
                email=email,
                ip_address=ip_address or '0.0.0.0',
                success=success,
                failure_reason=failure_reason or ''
            )
        except Exception as e:
            # Don't fail the main operation if logging fails
            logger.error(f"Failed to log login attempt: {str(e)}")
