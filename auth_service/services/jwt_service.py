import jwt
import uuid
from datetime import datetime, timedelta
from django.conf import settings
from django.utils import timezone
from django.core.cache import cache
from django.db import transaction, DatabaseError
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from typing import Dict, Optional
import logging

from .auth_model_service import model_service
from shared.utils.exceptions import (
    # Token exceptions
    InvalidTokenException,
    TokenExpiredException,
    TokenBlacklistedException,
    TokenGenerationException,
    
    # Authentication exceptions
    AuthenticationException,
    UserNotFoundException,
    
    # Database exceptions
    DatabaseOperationException,
    ModelCreationException,
    CacheOperationException,
    
    # Service exceptions
    ServiceConfigurationException,
    ServiceUnavailableException,
    
    # Security exceptions
    SecurityViolationException,
    
    # Validation exceptions
    ValidationException
)

logger = logging.getLogger(__name__)

class JWTService:
    """Enhanced JWT service with comprehensive error handling"""
    
    def __init__(self):
        try:
            self.secret_key = getattr(settings, 'SECRET_KEY', None)
            if not self.secret_key:
                raise ServiceConfigurationException("SECRET_KEY setting is required")
            
            # Get JWT settings with defaults
            simple_jwt_settings = getattr(settings, 'SIMPLE_JWT', {})
            self.access_token_lifetime = simple_jwt_settings.get(
                'ACCESS_TOKEN_LIFETIME', 
                timedelta(minutes=15)
            )
            self.refresh_token_lifetime = simple_jwt_settings.get(
                'REFRESH_TOKEN_LIFETIME', 
                timedelta(days=7)
            )
            
            # Validate token lifetimes
            if not isinstance(self.access_token_lifetime, timedelta):
                raise ServiceConfigurationException("ACCESS_TOKEN_LIFETIME must be a timedelta")
            
            if not isinstance(self.refresh_token_lifetime, timedelta):
                raise ServiceConfigurationException("REFRESH_TOKEN_LIFETIME must be a timedelta")
                
        except ServiceConfigurationException:
            raise
        except Exception as e:
            logger.error(f"Failed to initialize JWTService: {str(e)}")
            raise ServiceConfigurationException("JWT service initialization failed")
        
    def generate_tokens(self, user) -> Dict[str, str]:
        """Generate JWT tokens with comprehensive error handling"""
        try:
            # Validate user object
            if not user or not hasattr(user, 'id'):
                raise ValidationException("Invalid user object")
            
            if not user.is_active:
                raise AuthenticationException("User account is deactivated")
            
            try:
                # Generate refresh token
                refresh = RefreshToken.for_user(user)
                
                # Add custom JTI if not present
                if 'jti' not in refresh:
                    refresh['jti'] = str(uuid.uuid4())
                
                # Add custom claims with validation
                refresh['user_id'] = str(user.id)
                refresh['email'] = getattr(user, 'email', '')
                refresh['is_email_verified'] = getattr(user, 'is_email_verified', False)
                
                # Generate access token from refresh
                access = refresh.access_token
                
                # Add JTI to access token
                if 'jti' not in access:
                    access['jti'] = str(uuid.uuid4())
                    
            except Exception as e:
                logger.error(f"Token generation failed for user {user.id}: {str(e)}")
                raise TokenGenerationException("Failed to generate JWT tokens")
            
            try:
                # Cache token info for fast blacklist checking
                self._cache_token_info(str(refresh['jti']), str(user.id), 'refresh', refresh.get('exp'))
                self._cache_token_info(str(access['jti']), str(user.id), 'access', access.get('exp'))
            except Exception as e:
                logger.warning(f"Token caching failed: {str(e)}")
                # Don't fail token generation if caching fails
            
            logger.info(f"Generated JWT tokens for user: {user.email}")
            
            return {
                'access': str(access),
                'refresh': str(refresh),
                'expires_at': datetime.fromtimestamp(access.get('exp')).isoformat(),
                'refresh_expires_at': datetime.fromtimestamp(refresh.get('exp')).isoformat()
            }
            
        except (ValidationException, AuthenticationException, TokenGenerationException):
            raise
        except Exception as e:
            logger.error(f"Unexpected error in generate_tokens: {str(e)}")
            raise TokenGenerationException("Token generation failed")
    
    def blacklist_token(
        self, 
        token: str, 
        token_type: str, 
        user_id: str, 
        reason: str = 'logout',
        ip_address: str = None
    ) -> bool:
        """Blacklist token with proper timezone handling"""
        try:
            if not token or not token.strip():
                raise ValidationException("Token is required for blacklisting")
            
            if token_type not in ['access', 'refresh']:
                raise ValidationException("Token type must be 'access' or 'refresh'")
            
            try:
                decoded = jwt.decode(
                    token, 
                    self.secret_key, 
                    algorithms=['HS256'],
                    options={"verify_exp": False}
                )
            except jwt.InvalidTokenError as e:
                logger.error(f"Invalid token for blacklisting: {str(e)}")
                raise InvalidTokenException("Cannot blacklist invalid token")
            
            jti = decoded.get('jti')
            exp = decoded.get('exp')
            
            if not jti:
                logger.warning("Token without JTI cannot be blacklisted")
                raise ValidationException("Token does not contain required JTI claim")
            
            # Calculate expiry with proper timezone handling
            if exp:
                # Convert Unix timestamp to timezone-aware datetime
                expires_at = timezone.make_aware(
                    datetime.fromtimestamp(exp), 
                    timezone.get_current_timezone()
                )
            else:
                expires_at = timezone.now() + self.refresh_token_lifetime
            
            try:
                with transaction.atomic():
                    User = model_service.user_model
                    try:
                        user = User.objects.get(id=user_id)
                    except User.DoesNotExist:
                        raise UserNotFoundException("User not found for token blacklisting")
                    
                    TokenBlacklist = model_service.token_blacklist_model
                    blacklist_entry, created = TokenBlacklist.objects.get_or_create(
                        jti=jti,
                        defaults={
                            'user': user,
                            'token_type': token_type,
                            'reason': reason,
                            'expires_at': expires_at,  # Now timezone-aware
                            'created_from_ip': ip_address
                        }
                    )
                    
            except Exception as e:
                logger.error(f"Database error during token blacklisting: {str(e)}")
                raise DatabaseOperationException("Failed to create blacklist record")
            
            if created:
                try:
                    # Cache blacklist status with proper timezone calculation
                    cache_key = f"blacklist:{jti}"
                    now = timezone.now()
                    
                    # Both datetimes are now timezone-aware
                    if expires_at > now:
                        timeout = int((expires_at - now).total_seconds())
                        timeout = max(1, timeout)  # Ensure positive timeout
                        cache.set(cache_key, True, timeout=timeout)
                    
                    # Remove from token info cache
                    token_cache_key = f"token_info:{jti}"
                    cache.delete(token_cache_key)
                    
                except Exception as e:
                    logger.warning(f"Cache operation failed during blacklisting: {str(e)}")
                
                logger.info(f"Token blacklisted: {jti[:10]}... for user: {user.email}")
                return True
            else:
                logger.info(f"Token already blacklisted: {jti[:10]}...")
                return True
                
        except (ValidationException, InvalidTokenException, UserNotFoundException, 
                DatabaseOperationException):
            raise
        except Exception as e:
            logger.error(f"Unexpected error in blacklist_token: {str(e)}")
            raise DatabaseOperationException("Token blacklisting failed")
    
    def is_token_blacklisted(self, token: str) -> bool:
        """Check token blacklist status with proper timezone handling"""
        try:
            if not token or not token.strip():
                return True
            
            try:
                decoded = jwt.decode(
                    token,
                    self.secret_key,
                    algorithms=['HS256'],
                    options={"verify_exp": False}
                )
            except jwt.InvalidTokenError:
                return True
            
            jti = decoded.get('jti')
            if not jti:
                return False
            
            try:
                cache_key = f"blacklist:{jti}"
                cached_result = cache.get(cache_key)
                
                if cached_result is not None:
                    return cached_result
            except Exception as e:
                logger.warning(f"Cache lookup failed in blacklist check: {str(e)}")
            
            try:
                TokenBlacklist = model_service.token_blacklist_model
                is_blacklisted = TokenBlacklist.objects.filter(jti=jti).exists()
                
                # Cache result with proper timezone handling
                try:
                    exp = decoded.get('exp')
                    if exp:
                        expires_at = timezone.make_aware(
                            datetime.fromtimestamp(exp),
                            timezone.get_current_timezone()
                        )
                        now = timezone.now()
                        
                        if expires_at > now:
                            timeout = int((expires_at - now).total_seconds())
                            timeout = max(1, timeout)
                            cache.set(cache_key, is_blacklisted, timeout=timeout)
                except Exception as e:
                    logger.warning(f"Failed to cache blacklist result: {str(e)}")
                
                return is_blacklisted
                
            except Exception as e:
                logger.error(f"Database error checking blacklist: {str(e)}")
                return True
                
        except Exception as e:
            logger.error(f"Unexpected error in is_token_blacklisted: {str(e)}")
            return True
    
    def blacklist_user_tokens(
        self, 
        user_id: str, 
        reason: str = 'security',
        ip_address: str = None
    ) -> int:
        """Blacklist all user tokens with error handling"""
        try:
            if not user_id or not user_id.strip():
                raise ValidationException("User ID is required")
            
            TokenBlacklist = model_service.token_blacklist_model
            User = model_service.user_model
            
            try:
                user = User.objects.get(id=user_id)
            except User.DoesNotExist:
                raise UserNotFoundException("User not found for token blacklisting")
            except DatabaseError as e:
                logger.error(f"Database error retrieving user: {str(e)}")
                raise DatabaseOperationException("Failed to retrieve user")
            
            blacklisted_count = 0
            
            try:
                # Get all cached token info for this user
                try:
                    cache_keys = cache.keys(f"token_info:*") or []
                except Exception as e:
                    logger.warning(f"Failed to get cache keys: {str(e)}")
                    cache_keys = []
                
                for cache_key in cache_keys:
                    try:
                        token_info = cache.get(cache_key)
                        if token_info and token_info.get('user_id') == str(user_id):
                            jti = cache_key.split(':')[1]
                            
                            with transaction.atomic():
                                # Create blacklist entry
                                _, created = TokenBlacklist.objects.get_or_create(
                                    jti=jti,
                                    defaults={
                                        'user': user,
                                        'token_type': token_info.get('token_type', 'unknown'),
                                        'reason': reason,
                                        'expires_at': datetime.fromtimestamp(
                                            token_info.get('exp', timezone.now().timestamp())
                                        ),
                                        'created_from_ip': ip_address
                                    }
                                )
                                
                                if created:
                                    # Update cache
                                    blacklist_cache_key = f"blacklist:{jti}"
                                    cache.set(blacklist_cache_key, True, timeout=3600)
                                    blacklisted_count += 1
                                    
                    except Exception as e:
                        logger.warning(f"Failed to blacklist token {cache_key}: {str(e)}")
                        continue
                        
            except DatabaseError as e:
                logger.error(f"Database error during bulk blacklisting: {str(e)}")
                raise ModelCreationException("Failed to blacklist user tokens")
            
            logger.info(f"Blacklisted {blacklisted_count} tokens for user: {user.email}")
            return blacklisted_count
            
        except (ValidationException, UserNotFoundException, DatabaseOperationException, 
                ModelCreationException):
            raise
        except Exception as e:
            logger.error(f"Unexpected error in blacklist_user_tokens: {str(e)}")
            raise DatabaseOperationException("Bulk token blacklisting failed")
    
    def refresh_token(self, refresh_token: str) -> Dict[str, str]:
        """Refresh JWT token with comprehensive error handling"""
        try:
            if not refresh_token or not refresh_token.strip():
                raise InvalidTokenException("Refresh token is required")
            
            # Check if refresh token is blacklisted
            if self.is_token_blacklisted(refresh_token):
                raise TokenBlacklistedException("Refresh token has been revoked")
            
            try:
                # Create RefreshToken object and validate
                refresh = RefreshToken(refresh_token)
                
                # Generate new access token
                new_access = refresh.access_token
                
                # Add JTI if not present
                if 'jti' not in new_access:
                    new_access['jti'] = str(uuid.uuid4())
                
            except TokenError as e:
                error_msg = str(e).lower()
                if 'expired' in error_msg:
                    raise TokenExpiredException("Refresh token has expired")
                else:
                    raise InvalidTokenException(f"Invalid refresh token: {str(e)}")
            except Exception as e:
                logger.error(f"Token refresh processing failed: {str(e)}")
                raise TokenGenerationException("Failed to process token refresh")
            
            try:
                # Cache new access token info
                user_id = refresh.get('user_id')
                if user_id:
                    self._cache_token_info(
                        str(new_access['jti']), 
                        str(user_id), 
                        'access', 
                        new_access.get('exp')
                    )
            except Exception as e:
                logger.warning(f"Failed to cache refreshed token info: {str(e)}")
            
            return {
                'access': str(new_access),
                'refresh': str(refresh),
                'expires_at': datetime.fromtimestamp(new_access.get('exp')).isoformat()
            }
            
        except (InvalidTokenException, TokenExpiredException, TokenBlacklistedException, 
                TokenGenerationException):
            raise
        except Exception as e:
            logger.error(f"Unexpected error in refresh_token: {str(e)}")
            raise TokenGenerationException("Token refresh failed")
    
    def decode_token(self, token: str, verify_exp: bool = True) -> Dict:
        """Safely decode JWT token with proper timezone handling"""
        try:
            if not token or not token.strip():
                raise InvalidTokenException("Token is required")
            
            decoded = jwt.decode(
                token,
                self.secret_key,
                algorithms=['HS256'],
                options={"verify_exp": verify_exp}
            )
            
            return decoded
            
        except jwt.ExpiredSignatureError:
            raise InvalidTokenException("Token has expired")
        except jwt.InvalidTokenError as e:
            raise InvalidTokenException(f"Invalid token: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error in decode_token: {str(e)}")
            raise InvalidTokenException("Token decoding failed")
    
    def cleanup_expired_blacklist(self) -> int:
        """Clean up expired blacklist entries"""
        try:
            TokenBlacklist = model_service.token_blacklist_model
            
            # Use timezone-aware datetime for comparison
            now = timezone.now()
            deleted_result = TokenBlacklist.objects.filter(
                expires_at__lt=now
            ).delete()
            
            deleted_count = deleted_result[0] if deleted_result else 0
            
            logger.info(f"Cleaned up {deleted_count} expired blacklist entries")
            return deleted_count
            
        except Exception as e:
            logger.error(f"Database error during blacklist cleanup: {str(e)}")
            raise DatabaseOperationException("Blacklist cleanup failed")
    
    def _cache_token_info(self, jti: str, user_id: str, token_type: str, exp: int):
        """Cache token information with error handling"""
        try:
            if not jti or not user_id:
                return  # Skip caching for invalid data
            
            cache_key = f"token_info:{jti}"
            token_info = {
                'user_id': str(user_id),
                'token_type': token_type,
                'exp': exp or int((timezone.now() + self.access_token_lifetime).timestamp())
            }
            
            # Calculate cache timeout
            if exp:
                timeout = max(1, exp - int(timezone.now().timestamp()))
            else:
                timeout = int(self.access_token_lifetime.total_seconds())
            
            cache.set(cache_key, token_info, timeout=timeout)
            
        except Exception as e:
            logger.warning(f"Failed to cache token info: {str(e)}")
            # Don't raise exception for caching failures

# Global instance
jwt_service = JWTService()
