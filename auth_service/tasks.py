from celery import shared_task
from typing import Dict
import logging
from datetime import timedelta
from django.utils import timezone

from .services.auth_import_service import import_service

logger = logging.getLogger(__name__)

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_magic_link_email_async(self, email: str, token: str) -> Dict[str, str]:
    """
    Asynchronously send magic link email
    """
    try:
        email_service = import_service.email_service
        
        success = email_service.send_magic_link_email(email, token)
        
        if success:
            logger.info(f"Magic link email sent successfully to: {email}")
            return {
                'status': 'success',
                'message': f'Magic link email sent to {email}',
                'email': email
            }
        else:
            raise Exception("Email sending returned False")
            
    except Exception as exc:
        logger.error(f"Failed to send magic link email to {email}: {str(exc)}")
        
        # Retry logic
        if self.request.retries < self.max_retries:
            logger.info(f"Retrying magic link email to {email} (attempt {self.request.retries + 1})")
            raise self.retry(exc=exc, countdown=60 * (self.request.retries + 1))
        
        # Final failure
        logger.error(f"Final failure sending magic link email to {email} after {self.max_retries} retries")
        return {
            'status': 'failed',
            'message': f'Failed to send magic link email to {email}',
            'error': str(exc)
        }

# @shared_task(bind=True, max_retries=3, default_retry_delay=60)
# def send_email_verification_async(self, email: str, token: str, user_name: str = None) -> Dict[str, str]:
#     """
#     Asynchronously send email verification
#     """
#     try:
#         email_service = import_service.email_service
        
#         success = email_service.send_email_verification(email, token, user_name)
        
#         if success:
#             logger.info(f"Email verification sent successfully to: {email}")
#             return {
#                 'status': 'success',
#                 'message': f'Verification email sent to {email}',
#                 'email': email
#             }
#         else:
#             raise Exception("Email sending returned False")
            
#     except Exception as exc:
#         logger.error(f"Failed to send verification email to {email}: {str(exc)}")
        
#         if self.request.retries < self.max_retries:
#             logger.info(f"Retrying verification email to {email} (attempt {self.request.retries + 1})")
#             raise self.retry(exc=exc, countdown=60 * (self.request.retries + 1))
        
#         logger.error(f"Final failure sending verification email to {email} after {self.max_retries} retries")
#         return {
#             'status': 'failed',
#             'message': f'Failed to send verification email to {email}',
#             'error': str(exc)
#         }

# @shared_task(bind=True, max_retries=3, default_retry_delay=60)
# def send_welcome_email_async(self, email: str, user_name: str = None) -> Dict[str, str]:
#     """
#     Asynchronously send welcome email
#     """
#     try:
#         email_service = import_service.email_service
        
#         success = email_service.send_welcome_email(email, user_name)
        
#         if success:
#             logger.info(f"Welcome email sent successfully to: {email}")
#             return {
#                 'status': 'success',
#                 'message': f'Welcome email sent to {email}',
#                 'email': email
#             }
#         else:
#             raise Exception("Email sending returned False")
            
#     except Exception as exc:
#         logger.error(f"Failed to send welcome email to {email}: {str(exc)}")
        
#         if self.request.retries < self.max_retries:
#             logger.info(f"Retrying welcome email to {email} (attempt {self.request.retries + 1})")
#             raise self.retry(exc=exc, countdown=60 * (self.request.retries + 1))
        
#         logger.error(f"Final failure sending welcome email to {email} after {self.max_retries} retries")
#         return {
#             'status': 'failed',
#             'message': f'Failed to send welcome email to {email}',
#             'error': str(exc)
#         }
# apps/auth_service/tasks.py
@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_email_verification_async(self, email: str, token: str, user_name: str = None) -> Dict[str, str]:
    """
    Asynchronously send email verification with enhanced debugging
    """
    try:
        logger.info(f"Starting email verification task for: {email}")
        logger.info(f"Token: {token[:20]}... User: {user_name}")
        
        email_service = import_service.email_service
        logger.info(f"Email service loaded: {type(email_service)}")
        
        success = email_service.send_email_verification(email, token, user_name)
        logger.info(f"Email verification method returned: {success}")
        
        if success:
            logger.info(f"Email verification sent successfully to: {email}")
            return {
                'status': 'success',
                'message': f'Verification email sent to {email}',
                'email': email
            }
        else:
            logger.error(f"Email verification returned False for: {email}")
            raise Exception("Email sending returned False")
            
    except Exception as exc:
        logger.error(f"Exception in email verification task: {type(exc).__name__}: {str(exc)}")
        logger.error(f"Full traceback:", exc_info=True)
        
        if self.request.retries < self.max_retries:
            logger.info(f"Retrying verification email to {email} (attempt {self.request.retries + 1})")
            raise self.retry(exc=exc, countdown=60 * (self.request.retries + 1))
        
        logger.error(f"Final failure sending verification email to {email} after {self.max_retries} retries")
        return {
            'status': 'failed',
            'message': f'Failed to send verification email to {email}',
            'error': str(exc)
        }

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_welcome_email_async(self, email: str, user_name: str = None) -> Dict[str, str]:
    """
    Asynchronously send welcome email with enhanced debugging
    """
    try:
        logger.info(f"Starting welcome email task for: {email}")
        logger.info(f"User name: {user_name}")
        
        email_service = import_service.email_service
        logger.info(f"Email service loaded: {type(email_service)}")
        
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
def cleanup_expired_magic_links():
    """
    Periodic task to cleanup expired magic links
    """
    from django.utils import timezone
    from .services.auth_model_service import model_service
    
    MagicLink = model_service.magic_link_model
    
    expired_count = MagicLink.objects.filter(
        expires_at__lt=timezone.now()
    ).delete()[0]
    
    logger.info(f"Cleaned up {expired_count} expired magic links")
    
    return {
        'status': 'success',
        'cleaned_count': expired_count
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

# Add to existing tasks.py

@shared_task
def cleanup_expired_token_blacklist():
    """
    Periodic task to cleanup expired token blacklist entries
    """
    from .services.jwt_service import jwt_service
    
    try:
        cleaned_count = jwt_service.cleanup_expired_blacklist()
        
        logger.info(f"Token blacklist cleanup completed: {cleaned_count} entries removed")
        
        return {
            'status': 'success',
            'cleaned_count': cleaned_count,
            'timestamp': timezone.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Token blacklist cleanup failed: {str(e)}")
        return {
            'status': 'failed',
            'error': str(e)
        }

@shared_task
def security_audit_tokens():
    """
    Security audit task to identify suspicious token patterns
    """
    from django.db.models import Count
    from .services.auth_model_service import model_service
    
    try:
        TokenBlacklist = model_service.user_model._meta.get_model('auth_service', 'TokenBlacklist')
        
        # Find users with excessive token blacklisting
        suspicious_users = TokenBlacklist.objects.filter(
            blacklisted_at__gte=timezone.now() - timedelta(hours=24)
        ).values('user').annotate(
            token_count=Count('id')
        ).filter(token_count__gte=10)  # More than 10 tokens in 24h
        
        audit_results = {
            'suspicious_users_count': len(suspicious_users),
            'suspicious_users': list(suspicious_users),
            'total_blacklisted_24h': TokenBlacklist.objects.filter(
                blacklisted_at__gte=timezone.now() - timedelta(hours=24)
            ).count()
        }
        
        if suspicious_users:
            logger.warning(f"Security audit found {len(suspicious_users)} suspicious users")
        
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
