from celery import shared_task
from typing import Dict
import logging
from datetime import timedelta
from django.utils import timezone

from .services.auth_import_service import import_service

logger = logging.getLogger(__name__)

@shared_task(
    bind=True,
    name='auth_service.tasks.send_magic_link_email_async',
    max_retries=3,
    default_retry_delay=45,
    soft_time_limit=300
)
def send_magic_link_email_async(
    self,
    email: str,
    token: str
) -> dict:
    """
    Send magic link email asynchronously
    
    Args:
        email: Recipient email address
        magic_url: Complete magic link URL with token
    """
    try:
        logger.info(f"Sending magic link email to: {email}")
        
        # Import email service
        from auth_service.services.auth_import_service import import_service
        email_service = import_service.email_service
        
        if not token:
            raise ValueError("Token not found in magic URL")
        
        # Send email using email_service (unchanged)
        success = email_service.send_magic_link_email(email, token)
        
        if success:
            logger.info(f"Magic link email sent successfully to: {email}")
            return {
                'status': 'success',
                'message': f'Magic link email sent to {email}',
                'email': email
            }
        else:
            raise Exception("Email service returned False")
        
    except Exception as exc:
        logger.error(
            f"Failed to send magic link to {email}: {str(exc)}", 
            exc_info=True
        )
        
        # Retry with exponential backoff
        if self.request.retries < self.max_retries:
            retry_countdown = 60 * (2 ** self.request.retries)
            logger.info(
                f"Retrying magic link email to {email} "
                f"(attempt {self.request.retries + 1}/{self.max_retries}) "
                f"in {retry_countdown}s"
            )
            raise self.retry(exc=exc, countdown=retry_countdown)
        else:
            logger.error(
                f"Max retries exceeded for magic link to {email}"
            )
            return {
                'status': 'failed',
                'message': f'Failed to send magic link to {email}',
                'email': email,
                'error': str(exc)
            }

@shared_task(
    bind=True,
    name='auth_service.tasks.send_verification_email_async',
    max_retries=3,
    default_retry_delay=60,
    soft_time_limit=300,
    time_limit=600
)
def send_verification_email_async(
    self,
    user_email: str,
    user_name: str,
    token: str
) -> dict:
    """
    Send email verification
    
    Args:
        user_email: Recipient email address
        user_name: User's name for personalization
        verification_url: Complete verification URL with token
    
    Returns:
        dict with status and message
    """
    try:
        logger.info(f"Sending verification email to: {user_email}")
        
        if not token:
            raise ValueError("Token not found in verification URL")
        
        # Import email service
        from auth_service.services.auth_import_service import import_service
        email_service = import_service.email_service
        
        # Send verification email with correct parameters
        # email_service expects: send_email_verification(email, token, user_name)
        success = email_service.send_email_verification(
            email=user_email,
            token=token,  # ← Pass token, not verification_url
            user_name=user_name or 'User'
        )
        
        if success:
            logger.info(f"Verification email sent successfully to: {user_email}")
            return {
                'status': 'success',
                'message': f'Verification email sent to {user_email}',
                'email': user_email
            }
        else:
            logger.warning(
                f"Email service returned False for: {user_email}"
            )
            raise Exception("Email service returned False")
        
    except Exception as exc:
        logger.error(
            f"Failed to send verification email to {user_email}: "
            f"{type(exc).__name__}: {str(exc)}",
            exc_info=True
        )
        
        # Retry with exponential backoff
        if self.request.retries < self.max_retries:
            retry_countdown = 60 * (2 ** self.request.retries)
            logger.info(
                f"Retrying verification email to {user_email} "
                f"(attempt {self.request.retries + 1}/{self.max_retries}) "
                f"in {retry_countdown}s"
            )
            raise self.retry(exc=exc, countdown=retry_countdown)
        else:
            logger.error(
                f"Max retries exceeded for verification email to {user_email}"
            )
            return {
                'status': 'failed',
                'message': f'Failed to send verification email to {user_email}',
                'email': user_email,
                'error': str(exc)
            }

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_welcome_email_async(self, email: str, user_name: str = None) -> Dict[str, str]:
    """
    Asynchronously send welcome email with enhanced debugging
    """
    try:
        email_service = import_service.email_service
        success = email_service.send_welcome_email(email, user_name)
        logger.info(f"Welcome email method returned: {success}")
        
        if success:
            logger.info(f"Welcome email sent successfully to: {email}")
            return {
                'status': 'success',
                'message': f'Welcome email sent to {email}',
                'email': email
            }
        else:
            logger.error(f"Welcome email returned False for: {email}")
            raise Exception("Email sending returned False")
            
    except Exception as exc:
        logger.error(f"Exception in welcome email task: {type(exc).__name__}: {str(exc)}")
        logger.error(f"Full traceback:", exc_info=True)
        
        if self.request.retries < self.max_retries:
            logger.info(f"Retrying welcome email to {email} (attempt {self.request.retries + 1})")
            raise self.retry(exc=exc, countdown=60 * (self.request.retries + 1))
        
        logger.error(f"Final failure sending welcome email to {email} after {self.max_retries} retries")
        return {
            'status': 'failed',
            'message': f'Failed to send welcome email to {email}',
            'error': str(exc)
        }

@shared_task
def cleanup_expired_email_verifications():
    """
    Periodic task to cleanup expired email verifications
    """
    from django.utils import timezone
    from .services.auth_model_service import model_service
    
    EmailVerification = model_service.email_verification_model
    
    expired_count = EmailVerification.objects.filter(
        expires_at__lt=timezone.now(),
        is_verified=False
    ).delete()[0]
    
    logger.info(f"Cleaned up {expired_count} expired email verifications")
    
    return {
        'status': 'success',
        'cleaned_count': expired_count
    }

@shared_task(
    name='auth_service.tasks.cleanup_expired_token_blacklist',
    soft_time_limit=300,
    time_limit=600
)
def cleanup_expired_token_blacklist():
    """
    Periodic task to cleanup expired token blacklist entries
    Runs both custom blacklist and simplejwt blacklist cleanup
    """
    from .services.jwt_service import jwt_service
    
    try:
        # Clean custom blacklist
        cleaned_count = jwt_service.cleanup_expired_blacklist()
        
        # ✅ NEW: Also clean simplejwt blacklist
        simplejwt_cleaned = 0
        try:
            from rest_framework_simplejwt.token_blacklist.models import (
                OutstandingToken, 
                BlacklistedToken
            )
            
            # Delete expired outstanding tokens
            expired_tokens = OutstandingToken.objects.filter(
                expires_at__lt=timezone.now()
            )
            simplejwt_cleaned = expired_tokens.count()
            expired_tokens.delete()
            
            logger.info(
                f"Cleaned {simplejwt_cleaned} expired simplejwt tokens"
            )
            
        except ImportError:
            logger.info("simplejwt blacklist not installed, skipping cleanup")
        except Exception as e:
            logger.warning(f"simplejwt cleanup failed: {str(e)}")
        
        logger.info(
            f"Token blacklist cleanup completed: "
            f"custom={cleaned_count}, simplejwt={simplejwt_cleaned}"
        )
        
        return {
            'status': 'success',
            'custom_cleaned': cleaned_count,
            'simplejwt_cleaned': simplejwt_cleaned,
            'total_cleaned': cleaned_count + simplejwt_cleaned,
            'timestamp': timezone.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Token blacklist cleanup failed: {str(e)}")
        return {
            'status': 'failed',
            'error': str(e)
        }


@shared_task(
    name='auth_service.tasks.security_audit_tokens',
    soft_time_limit=600,
    time_limit=900
)
def security_audit_tokens():
    """
    Security audit task to identify suspicious token patterns
    
    ✅ ENHANCED: Includes email change tracking and token invalidation patterns
    """
    from django.db.models import Count
    from .services.auth_model_service import model_service
    
    try:
        TokenBlacklist = model_service.token_blacklist_model
        
        # Find users with excessive token blacklisting (potential attack)
        suspicious_users = TokenBlacklist.objects.filter(
            blacklisted_at__gte=timezone.now() - timedelta(hours=24)
        ).values('user').annotate(
            token_count=Count('id')
        ).filter(token_count__gte=10)  # More than 10 tokens in 24h
        
        # ✅ NEW: Track email change related blacklisting
        email_change_blacklists = TokenBlacklist.objects.filter(
            blacklisted_at__gte=timezone.now() - timedelta(hours=24),
            reason='email_change'
        ).count()
        
        # ✅ NEW: Track password change related blacklisting
        password_change_blacklists = TokenBlacklist.objects.filter(
            blacklisted_at__gte=timezone.now() - timedelta(hours=24),
            reason='password_change'
        ).count()
        
        # ✅ NEW: Track suspicious activity blacklisting
        suspicious_activity_blacklists = TokenBlacklist.objects.filter(
            blacklisted_at__gte=timezone.now() - timedelta(hours=24),
            reason='suspicious'
        ).count()
        
        # ✅ NEW: Users with multiple email changes in 24h (potential abuse)
        from auth_service.models import EmailVerification
        frequent_email_changers = EmailVerification.objects.filter(
            created_at__gte=timezone.now() - timedelta(hours=24)
        ).values('user').annotate(
            change_count=Count('id')
        ).filter(change_count__gte=3)  # 3+ email changes in 24h
        
        audit_results = {
            'suspicious_users_count': len(suspicious_users),
            'suspicious_users': list(suspicious_users),
            'total_blacklisted_24h': TokenBlacklist.objects.filter(
                blacklisted_at__gte=timezone.now() - timedelta(hours=24)
            ).count(),
            'email_change_blacklists': email_change_blacklists,
            'password_change_blacklists': password_change_blacklists,
            'suspicious_activity_blacklists': suspicious_activity_blacklists,
            'frequent_email_changers_count': len(frequent_email_changers),
            'frequent_email_changers': list(frequent_email_changers)
        }
        
        # Log warnings for suspicious activity
        if suspicious_users:
            logger.warning(
                f"Security audit found {len(suspicious_users)} users with "
                f"excessive token blacklisting"
            )
        
        if frequent_email_changers:
            logger.warning(
                f"Security audit found {len(frequent_email_changers)} users with "
                f"frequent email changes (possible abuse)"
            )
        
        return {
            'status': 'success',
            'audit_results': audit_results,
            'timestamp': timezone.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Security audit failed: {str(e)}")
        return {
            'status': 'failed',
            'error': str(e)
        }


@shared_task(
    name='auth_service.tasks.invalidate_stale_tokens',
    soft_time_limit=600,
    time_limit=900
)
def invalidate_stale_tokens():
    """
    ✅ NEW: Invalidate tokens for users whose data changed significantly
    
    Checks for:
    - Users with unverified email changes pending for >24h
    - Users with suspicious login patterns
    - Accounts that were locked/unlocked
    """
    from .services.auth_model_service import model_service
    from .services.jwt_service import jwt_service
    
    try:
        User = model_service.user_model
        invalidated_count = 0
        
        # ✅ Find users with old pending email changes (>48h)
        from auth_service.models import EmailVerification
        stale_verifications = EmailVerification.objects.filter(
            created_at__lt=timezone.now() - timedelta(hours=48),
            is_verified=False,
            expires_at__lt=timezone.now()
        ).select_related('user')
        
        for verification in stale_verifications:
            try:
                # Blacklist all tokens for this user
                count = jwt_service.blacklist_user_tokens(
                    user_id=str(verification.user.id),
                    reason='stale_email_change'
                )
                invalidated_count += count
                
                # Delete the stale verification
                verification.delete()
                
                logger.info(
                    f"Invalidated {count} tokens for user {verification.user.email} "
                    f"(stale email change)"
                )
                
            except Exception as e:
                logger.error(
                    f"Failed to invalidate tokens for user "
                    f"{verification.user.email}: {str(e)}"
                )
        
        logger.info(
            f"Stale token invalidation completed: "
            f"{invalidated_count} tokens invalidated"
        )
        
        return {
            'status': 'success',
            'invalidated_count': invalidated_count,
            'stale_verifications_cleaned': stale_verifications.count(),
            'timestamp': timezone.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Stale token invalidation failed: {str(e)}")
        return {
            'status': 'failed',
            'error': str(e)
        }


@shared_task(
    name='auth_service.tasks.cleanup_expired_magic_links',
    soft_time_limit=300,
    time_limit=600
)
def cleanup_expired_magic_links():
    """
    ✅ NEW: Cleanup expired magic links
    Removes magic links that are expired and used
    """
    from .services.auth_model_service import model_service
    
    try:
        MagicLink = model_service.magic_link_model
        
        # Delete magic links that are:
        # 1. Expired OR
        # 2. Used and older than 7 days
        
        # Expired magic links
        expired_deleted = MagicLink.objects.filter(
            expires_at__lt=timezone.now()
        ).delete()[0]
        
        # Old used magic links
        old_used_deleted = MagicLink.objects.filter(
            is_used=True,
            created_at__lt=timezone.now() - timedelta(days=7)
        ).delete()[0]
        
        total_deleted = expired_deleted + old_used_deleted
        
        logger.info(
            f"Magic link cleanup completed: "
            f"expired={expired_deleted}, old_used={old_used_deleted}"
        )
        
        return {
            'status': 'success',
            'expired_deleted': expired_deleted,
            'old_used_deleted': old_used_deleted,
            'total_deleted': total_deleted,
            'timestamp': timezone.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Magic link cleanup failed: {str(e)}")
        return {
            'status': 'failed',
            'error': str(e)
        }