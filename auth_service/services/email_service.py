from django.core.mail import EmailMessage, BadHeaderError
from django.template.loader import render_to_string, TemplateDoesNotExist
from django.utils.html import strip_tags
from django.conf import settings
from smtplib import SMTPException, SMTPAuthenticationError, SMTPConnectError, SMTPRecipientsRefused
from socket import gaierror, timeout as socket_timeout
import logging
from typing import Dict, List
import os

from shared.utils.exceptions import (
    # Email specific exceptions
    EmailServiceException,
    EmailSendFailedException,
    EmailTemplateException,
    EmailConfigurationException,
    
    # General exceptions
    ValidationException,
    InvalidEmailFormatException,
    ServiceConfigurationException,
    ServiceUnavailableException,
    ServiceTimeoutException,
    ExternalServiceException
)

logger = logging.getLogger(__name__)

class EmailService:
    """Enhanced Email service with comprehensive error handling using EmailMessage"""
    
    def __init__(self):
        try:
            self.from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', None)
            self.frontend_url = getattr(settings, 'FRONTEND_URL', 'https://receipt-manager-frontend-2dyd.onrender.com')
            
            # Validate configuration
            if not self.from_email:
                raise EmailConfigurationException("DEFAULT_FROM_EMAIL setting is required")
            
            if not self.frontend_url:
                raise EmailConfigurationException("FRONTEND_URL setting is required")
                
            # Validate email settings (skip for console backend)
            if not self._is_console_backend():
                self._validate_email_configuration()
            
        except EmailConfigurationException:
            raise
        except Exception as e:
            logger.error(f"Failed to initialize EmailService: {str(e)}")
            raise ServiceConfigurationException("Email service initialization failed")
    
    def send_magic_link_email(self, email: str, token: str) -> bool:
        """Send magic link email with comprehensive error handling"""
        try:
            # Validate inputs
            self._validate_email_address(email)
            self._validate_token(token, "Magic link token")
            
            magic_url = f"{self.frontend_url}/login?token={token}"
            subject = "Your Magic Login Link - Receipt Manager"
            
            # Context for template
            context = {
                'user_name': 'User',
                'magic_url': magic_url,
                'frontend_url': self.frontend_url,
                'email': email
            }
            
            return self._send_html_email(
                subject=subject,
                template_name='emails/magic_link.html',
                context=context,
                recipient_list=[email],
                email_type="magic_link"
            )
            
        except (ValidationException, EmailTemplateException, EmailSendFailedException):
            raise
        except Exception as e:
            logger.error(f"Unexpected error in send_magic_link_email: {str(e)}")
            raise EmailServiceException("Failed to send magic link email")
    
    def send_email_verification(self, email: str, token: str, user_name: str = None) -> bool:
        """Send email verification with error handling"""
        try:
            # Validate inputs
            self._validate_email_address(email)
            self._validate_token(token, "Email verification token")
            
            if user_name and len(user_name.strip()) == 0:
                user_name = None
            
            verification_url = f"{self.frontend_url}/verify-email?token={token}"
            subject = "Verify Your Email Address - Receipt Manager"
            
            # Context for template
            context = {
                'user_name': user_name or 'User',
                'verification_url': verification_url,
                'frontend_url': self.frontend_url,
                'email': email
            }
            
            return self._send_html_email(
                subject=subject,
                template_name='emails/email_verification.html',
                context=context,
                recipient_list=[email],
                email_type="email_verification"
            )
            
        except (ValidationException, EmailTemplateException, EmailSendFailedException):
            raise
        except Exception as e:
            logger.error(f"Unexpected error in send_email_verification: {str(e)}")
            raise EmailServiceException("Failed to send email verification")
    
    def send_welcome_email(self, email: str, user_name: str = None) -> bool:
        """Send welcome email with error handling"""
        try:
            # Validate inputs
            self._validate_email_address(email)
            
            if user_name and len(user_name.strip()) == 0:
                user_name = None
            
            subject = "Welcome to Receipt Manager!"
            
            # Context for template
            context = {
                'user_name': user_name or 'User',
                'frontend_url': self.frontend_url,
                'email': email
            }
            
            return self._send_html_email(
                subject=subject,
                template_name='emails/welcome.html',
                context=context,
                recipient_list=[email],
                email_type="welcome"
            )
            
        except (ValidationException, EmailTemplateException, EmailSendFailedException):
            raise
        except Exception as e:
            logger.error(f"Unexpected error in send_welcome_email: {str(e)}")
            raise EmailServiceException("Failed to send welcome email")
    
    def _send_html_email(
        self, 
        subject: str, 
        template_name: str,
        context: Dict,
        recipient_list: List[str],
        email_type: str = "general"
    ) -> bool:
        """Send HTML email using EmailMessage (following your email_utils pattern)"""
        try:
            # Validate inputs
            if not subject or not subject.strip():
                raise ValidationException("Email subject is required")
            
            if not recipient_list or len(recipient_list) == 0:
                raise ValidationException("At least one recipient is required")
            
            # Validate all recipient emails
            for email in recipient_list:
                self._validate_email_address(email)
            
            # Check for header injection
            self._validate_email_headers(subject)
            
            # Render HTML template
            try:
                # Try to find template in multiple locations
                template_paths = [
                    template_name,
                    f'email_templates/{template_name.split("/")[-1]}',  # For your pattern
                    f'templates/{template_name}'
                ]
                
                html_message = None
                for template_path in template_paths:
                    try:
                        html_message = render_to_string(template_path, context)
                        break
                    except TemplateDoesNotExist:
                        continue
                
                if not html_message:
                    logger.error(f"Email template not found: {template_name}")
                    raise EmailTemplateException(f"Email template not found: {template_name}")
                    
            except Exception as e:
                if isinstance(e, EmailTemplateException):
                    raise
                logger.error(f"Template rendering failed: {str(e)}")
                raise EmailTemplateException(f"Failed to render email template: {str(e)}")
            
            # Create plain text version
            plain_message = strip_tags(html_message)
            
            # Send email with specific error handling
            try:
                # Create EmailMessage instance
                email_msg = EmailMessage(
                    subject=subject.strip(),
                    body=plain_message,
                    from_email=self.from_email,
                    to=recipient_list,
                )
                
                # Set HTML content
                email_msg.content_subtype = 'html'
                email_msg.body = html_message  # Use HTML as main body
                
                # Send the email
                result = email_msg.send(fail_silently=False)
                
                if result == 0:
                    logger.error(f"Email sending returned 0 for type: {email_type}")
                    raise EmailSendFailedException("Email was not sent (no recipients)")
                
                logger.info(f"Email sent successfully - Type: {email_type}, Recipients: {', '.join(recipient_list)}")
                return True
                
            except BadHeaderError as e:
                logger.error(f"Bad email header detected: {str(e)}")
                raise ValidationException("Invalid characters in email headers")
            
            except SMTPAuthenticationError as e:
                logger.error(f"SMTP authentication failed: {str(e)}")
                raise EmailConfigurationException("Email authentication failed - check credentials")
            
            except SMTPConnectError as e:
                logger.error(f"SMTP connection failed: {str(e)}")
                raise ServiceUnavailableException("Email server is unreachable")
            
            except SMTPRecipientsRefused as e:
                logger.error(f"SMTP recipients refused: {str(e)}")
                # Check if it's a validation issue or server issue
                invalid_emails = [email for email, (code, msg) in e.recipients.items() if 500 <= code < 600]
                if invalid_emails:
                    raise ValidationException(f"Invalid email addresses: {', '.join(invalid_emails)}")
                else:
                    raise EmailSendFailedException("Email delivery was refused by server")
            
            except SMTPException as e:
                error_msg = str(e).lower()
                if 'timeout' in error_msg:
                    logger.error(f"SMTP timeout: {str(e)}")
                    raise ServiceTimeoutException("Email sending timed out")
                elif 'quota' in error_msg or 'limit' in error_msg:
                    logger.error(f"SMTP quota exceeded: {str(e)}")
                    raise EmailServiceException("Email sending quota exceeded")
                else:
                    logger.error(f"SMTP error: {str(e)}")
                    raise EmailSendFailedException(f"SMTP error: {str(e)}")
            
            except (gaierror, socket_timeout) as e:
                logger.error(f"Network error sending email: {str(e)}")
                raise ServiceUnavailableException("Network error - email server unreachable")
            
            except OSError as e:
                logger.error(f"OS error sending email: {str(e)}")
                raise ExternalServiceException("System error while sending email")
                
        except (ValidationException, EmailConfigurationException, ServiceUnavailableException, 
                ServiceTimeoutException, EmailSendFailedException, ExternalServiceException):
            raise
        except Exception as e:
            logger.error(f"Unexpected error in _send_html_email: {str(e)}")
            raise EmailServiceException("Unexpected email sending error")
    
    def _is_console_backend(self) -> bool:
        """Check if using console email backend"""
        email_backend = getattr(settings, 'EMAIL_BACKEND', '')
        return 'console' in email_backend.lower()
    
    def _validate_email_address(self, email: str):
        """Validate email address format"""
        if not email or not isinstance(email, str):
            raise InvalidEmailFormatException("Email address is required")
        
        email = email.strip()
        if not email:
            raise InvalidEmailFormatException("Email address cannot be empty")
        
        # Basic email format validation
        import re
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, email):
            raise InvalidEmailFormatException("Invalid email address format")
        
        # Check for common issues
        if '..' in email or email.startswith('.') or email.endswith('.'):
            raise InvalidEmailFormatException("Invalid email address format")
        
        if len(email) > 254:  # RFC 5321 limit
            raise InvalidEmailFormatException("Email address too long")
    
    def _validate_token(self, token: str, token_name: str = "Token"):
        """Validate token format"""
        if not token or not isinstance(token, str):
            raise ValidationException(f"{token_name} is required")
        
        token = token.strip()
        if not token:
            raise ValidationException(f"{token_name} cannot be empty")
        
        if len(token) < 10:
            raise ValidationException(f"{token_name} format is invalid")
    
    def _validate_email_headers(self, subject: str):
        """Validate email headers for injection attacks"""
        dangerous_chars = ['\n', '\r', '\0']
        for char in dangerous_chars:
            if char in subject:
                raise ValidationException("Invalid characters in email subject")
    
    def _validate_email_configuration(self):
        """Validate email configuration settings"""
        try:
            # Skip validation for console backend
            if self._is_console_backend():
                return
                
            required_settings = [
                'EMAIL_HOST',
                'EMAIL_PORT',
                'EMAIL_HOST_USER',
                'EMAIL_HOST_PASSWORD'
            ]
            
            missing_settings = []
            for setting in required_settings:
                if not getattr(settings, setting, None):
                    missing_settings.append(setting)
            
            if missing_settings:
                logger.warning(f"Missing email configuration: {', '.join(missing_settings)}")
                # Don't raise exception for missing config in development
                if not settings.DEBUG:
                    raise EmailConfigurationException(
                        f"Missing email configuration: {', '.join(missing_settings)}"
                    )
            
        except EmailConfigurationException:
            raise
        except Exception as e:
            logger.error(f"Email configuration validation failed: {str(e)}")
            raise EmailConfigurationException("Email configuration validation failed")
    
    def test_email_connection(self) -> Dict[str, any]:
        """Test email server connection"""
        try:
            from django.core.mail import get_connection
            
            connection = get_connection()
            connection.open()
            connection.close()
            
            logger.info("Email connection test successful")
            return {
                'status': 'success',
                'message': 'Email server connection successful'
            }
            
        except SMTPAuthenticationError:
            raise EmailConfigurationException("Email authentication failed")
        except SMTPConnectError:
            raise ServiceUnavailableException("Cannot connect to email server")
        except Exception as e:
            logger.error(f"Email connection test failed: {str(e)}")
            raise EmailServiceException("Email connection test failed")
