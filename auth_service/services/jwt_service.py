# auth_service/services/jwt_service.py

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
    InvalidTokenException,
    TokenExpiredException,
    TokenBlacklistedException,
    TokenGenerationException,
    AuthenticationException,
    UserNotFoundException,
    DatabaseOperationException,
    ServiceConfigurationException,
    ValidationException
)

logger = logging.getLogger(__name__)


class JWTService:
    """
    Enhanced JWT service with:
    1. Token invalidation on email change
    2. User modification tracking in token claims
    3. Token validation against user state
    """
    
    def __init__(self):
        try:
            self.secret_key = getattr(settings, 'SECRET_KEY', None)
            if not self.secret_key:
                raise ServiceConfigurationException("SECRET_KEY setting is required")
            
            simple_jwt_settings = getattr(settings, 'SIMPLE_JWT', {})
            self.access_token_lifetime = simple_jwt_settings.get(
                'ACCESS_TOKEN_LIFETIME', 
                timedelta(minutes=60)
            )
            self.refresh_token_lifetime = simple_jwt_settings.get(
                'REFRESH_TOKEN_LIFETIME', 
                timedelta(days=7)
            )
            
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
        """
        Generate JWT tokens with custom claims
        
        ✅ NEW: Includes 'updated_at' claim for user modification tracking
        """
        try:
            if not user or not hasattr(user, 'id'):
                raise ValidationException("Invalid user object")
            
            if not user.is_active:
                raise AuthenticationException("User account is deactivated")
            
            try:
                # Generate refresh token
                refresh = RefreshToken.for_user(user)
                
                if 'jti' not in refresh:
                    refresh['jti'] = str(uuid.uuid4())
                
                # ✅ Add custom claims with user modification tracking
                refresh['user_id'] = str(user.id)
                refresh['email'] = getattr(user, 'email', '')
                refresh['is_email_verified'] = getattr(user, 'is_email_verified', False)
                
                # ✅ NEW: Track user modification timestamp
                refresh['updated_at'] = int(user.updated_at.timestamp()) if hasattr(user, 'updated_at') else int(timezone.now().timestamp())
                
                # Generate access token from refresh
                access = refresh.access_token
                
                if 'jti' not in access:
                    access['jti'] = str(uuid.uuid4())
                    
            except Exception as e:
                logger.error(f"Token generation failed for user {user.id}: {str(e)}")
                raise TokenGenerationException("Failed to generate JWT tokens")
            
            try:
                self._cache_token_info(str(refresh['jti']), str(user.id), 'refresh', refresh.get('exp'))
                self._cache_token_info(str(access['jti']), str(user.id), 'access', access.get('exp'))
            except Exception as e:
                logger.warning(f"Token caching failed: {str(e)}")
            
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
    
    def validate_token_against_user(self, token: str) -> Dict:
        """
        ✅ NEW: Validate token against current user state
        
        Checks if user was modified after token was issued
        This catches email changes, password changes, etc.
        """
        try:
            decoded = self.decode_token(token, verify_exp=True)
            
            user_id = decoded.get('user_id')
            token_updated_at = decoded.get('updated_at')
            token_email = decoded.get('email')
            
            if not user_id:
                raise InvalidTokenException("Token missing user_id claim")
            
            # Get current user state
            User = model_service.user_model
            try:
                user = User.objects.get(id=user_id)
            except User.DoesNotExist:
                raise UserNotFoundException("User not found for token validation")
            
            # ✅ Check if user was modified after token issue
            if token_updated_at and hasattr(user, 'updated_at'):
                current_updated_at = int(user.updated_at.timestamp())
                
                if current_updated_at > token_updated_at:
                    logger.warning(
                        f"Token invalidated due to user modification: "
                        f"user={user.email}, token_time={token_updated_at}, "
                        f"current_time={current_updated_at}"
                    )
                    raise InvalidTokenException(
                        "User data changed. Please login again."
                    )
            
            # ✅ Check if email changed
            if token_email and user.email != token_email:
                logger.warning(
                    f"Token invalidated due to email change: "
                    f"token_email={token_email}, current_email={user.email}"
                )
                raise InvalidTokenException(
                    "Email has been changed. Please login again."
                )
            
            # ✅ Check if account is active
            if not user.is_active:
                raise AuthenticationException("User account is deactivated")
            
            return {
                'valid': True,
                'user_id': str(user.id),
                'email': user.email,
                'is_email_verified': user.is_email_verified
            }
            
        except (InvalidTokenException, UserNotFoundException, AuthenticationException):
            raise
        except Exception as e:
            logger.error(f"Token validation failed: {str(e)}")
            raise InvalidTokenException("Token validation failed")
    
    def blacklist_user_tokens(
        self,
        user_id: str,
        reason: str = 'email_change',
        ip_address: str = None
    ) -> int:
        """
        ✅ NEW: Blacklist ALL tokens for a user
        
        Used when:
        - User changes email
        - User changes password
        - User account is compromised
        
        Returns:
            int: Number of tokens blacklisted
        """
        try:
            User = model_service.user_model
            try:
                user = User.objects.get(id=user_id)
            except User.DoesNotExist:
                raise UserNotFoundException("User not found")
            
            # Get all outstanding tokens from simplejwt
            try:
                from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken
                
                outstanding_tokens = OutstandingToken.objects.filter(user=user)
                blacklisted_count = 0
                
                with transaction.atomic():
                    for outstanding_token in outstanding_tokens:
                        # Create blacklist entry in simplejwt table
                        _, created = BlacklistedToken.objects.get_or_create(
                            token=outstanding_token
                        )
                        
                        if created:
                            # Also add to our custom blacklist
                            try:
                                self._blacklist_outstanding_token(
                                    outstanding_token,
                                    user,
                                    reason,
                                    ip_address
                                )
                                blacklisted_count += 1
                            except Exception as e:
                                logger.warning(
                                    f"Failed to add custom blacklist entry: {str(e)}"
                                )
                
                logger.info(
                    f"Blacklisted {blacklisted_count} tokens for user {user.email} "
                    f"(reason: {reason})"
                )
                
                return blacklisted_count
                
            except ImportError:
                # Fallback if simplejwt blacklist not installed
                logger.warning("simplejwt blacklist not available, using custom only")
                return 0
                
        except UserNotFoundException:
            raise
        except Exception as e:
            logger.error(f"Failed to blacklist user tokens: {str(e)}")
            raise DatabaseOperationException("Token blacklisting failed")
    
    def _blacklist_outstanding_token(
        self,
        outstanding_token,
        user,
        reason: str,
        ip_address: str
    ):
        """Add outstanding token to custom blacklist"""
        try:
            TokenBlacklist = model_service.token_blacklist_model
            
            # Determine token type from token string
            token_type = 'refresh'  # Outstanding tokens are typically refresh tokens
            
            # Parse expiry
            expires_at = outstanding_token.expires_at
            if not timezone.is_aware(expires_at):
                expires_at = timezone.make_aware(expires_at)
            
            # Create blacklist entry
            TokenBlacklist.objects.get_or_create(
                jti=outstanding_token.jti,
                defaults={
                    'user': user,
                    'token_type': token_type,
                    'reason': reason,
                    'expires_at': expires_at,
                    'created_from_ip': ip_address
                }
            )
            
            # Cache blacklist status
            cache_key = f"blacklist:{outstanding_token.jti}"
            timeout = int((expires_at - timezone.now()).total_seconds())
            if timeout > 0:
                cache.set(cache_key, True, timeout=timeout)
                
        except Exception as e:
            logger.error(f"Failed to blacklist outstanding token: {str(e)}")
            raise
    
    def blacklist_token(
        self, 
        token: str, 
        token_type: str, 
        user_id: str, 
        reason: str = 'logout',
        ip_address: str = None
    ) -> bool:
        """Blacklist single token"""
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
                raise ValidationException("Token does not contain required JTI claim")
            
            if exp:
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
                            'expires_at': expires_at,
                            'created_from_ip': ip_address
                        }
                    )
                    
            except Exception as e:
                logger.error(f"Database error during token blacklisting: {str(e)}")
                raise DatabaseOperationException("Failed to create blacklist record")
            
            if created:
                try:
                    cache_key = f"blacklist:{jti}"
                    now = timezone.now()
                    
                    if expires_at > now:
                        timeout = int((expires_at - now).total_seconds())
                        timeout = max(1, timeout)
                        cache.set(cache_key, True, timeout=timeout)
                    
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
        """Check token blacklist status"""
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
    
    def refresh_token(self, refresh_token: str) -> Dict[str, str]:
        """Refresh JWT token with user state validation"""
        try:
            if not refresh_token or not refresh_token.strip():
                raise InvalidTokenException("Refresh token is required")
            
            # ✅ NEW: Validate token against user state
            self.validate_token_against_user(refresh_token)
            
            if self.is_token_blacklisted(refresh_token):
                raise TokenBlacklistedException("Refresh token has been revoked")
            
            try:
                refresh = RefreshToken(refresh_token)
                new_access = refresh.access_token
                
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
        """Safely decode JWT token"""
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
        """Cache token information"""
        try:
            if not jti or not user_id:
                return
            
            cache_key = f"token_info:{jti}"
            token_info = {
                'user_id': str(user_id),
                'token_type': token_type,
                'exp': exp or int((timezone.now() + self.access_token_lifetime).timestamp())
            }
            
            if exp:
                timeout = max(1, exp - int(timezone.now().timestamp()))
            else:
                timeout = int(self.access_token_lifetime.total_seconds())
            
            cache.set(cache_key, token_info, timeout=timeout)
            
        except Exception as e:
            logger.warning(f"Failed to cache token info: {str(e)}")


# Global instance
jwt_service = JWTService()
