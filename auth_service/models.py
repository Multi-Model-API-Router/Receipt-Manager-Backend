import uuid
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
from datetime import timedelta

class User(AbstractUser):
    """Extended User model for receipt management"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True, db_index=True)
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    is_email_verified = models.BooleanField(default=False)
    monthly_upload_count = models.PositiveIntegerField(default=0)
    upload_reset_date = models.DateField(auto_now_add=True)
    last_login_ip = models.GenericIPAddressField(null=True, blank=True)
    failed_login_attempts = models.PositiveIntegerField(default=0)
    account_locked_until = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []
    
    class Meta:
        db_table = 'auth_users'
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['created_at']),
            models.Index(fields=['is_email_verified']),
        ]
    
    def is_account_locked(self) -> bool:
        """Check if account is currently locked"""
        if self.account_locked_until:
            return timezone.now() < self.account_locked_until
        return False
    
    def lock_account(self, minutes: int = 30):
        """Lock account for specified minutes"""
        self.account_locked_until = timezone.now() + timedelta(minutes=minutes)
        self.save(update_fields=['account_locked_until'])

class MagicLink(models.Model):
    """Magic link tokens for passwordless authentication"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(db_index=True)
    token = models.CharField(max_length=255, unique=True, db_index=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    is_used = models.BooleanField(default=False)
    created_from_ip = models.GenericIPAddressField(null=True, blank=True)
    used_from_ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'auth_magic_links'
        indexes = [
            models.Index(fields=['token', 'expires_at']),
            models.Index(fields=['email', 'created_at']),
        ]
    
    def is_expired(self) -> bool:
        """Check if magic link is expired"""
        return timezone.now() > self.expires_at
    
    def mark_as_used(self, ip_address: str = None):
        """Mark magic link as used"""
        self.is_used = True
        self.used_at = timezone.now()
        if ip_address:
            self.used_from_ip = ip_address
        self.save(update_fields=['is_used', 'used_at', 'used_from_ip'])

class EmailVerification(models.Model):
    """Email verification tokens"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='email_verifications')
    email = models.EmailField()
    token = models.CharField(max_length=255, unique=True, db_index=True)
    expires_at = models.DateTimeField()
    verified_at = models.DateTimeField(null=True, blank=True)
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'auth_email_verifications'
        indexes = [
            models.Index(fields=['token', 'expires_at']),
            models.Index(fields=['user', 'created_at']),
        ]
    
    def is_expired(self) -> bool:
        """Check if verification token is expired"""
        return timezone.now() > self.expires_at
    
    def mark_as_verified(self):
        """Mark email as verified"""
        self.is_verified = True
        self.verified_at = timezone.now()
        self.user.is_email_verified = True
        self.user.save(update_fields=['is_email_verified'])
        self.save(update_fields=['is_verified', 'verified_at'])

class LoginAttempt(models.Model):
    """Track login attempts for security"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(db_index=True)
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField(blank=True)
    success = models.BooleanField()
    failure_reason = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'auth_login_attempts'
        indexes = [
            models.Index(fields=['email', 'created_at']),
            models.Index(fields=['ip_address', 'created_at']),
        ]


class TokenBlacklist(models.Model):
    """JWT token blacklist for secure logout"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    jti = models.CharField(max_length=255, unique=True, db_index=True)  # JWT ID claim
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='blacklisted_tokens')
    token_type = models.CharField(max_length=20, choices=[
        ('access', 'Access Token'),
        ('refresh', 'Refresh Token')
    ])
    reason = models.CharField(max_length=50, choices=[
        ('logout', 'User Logout'),
        ('revoked', 'Admin Revoked'),
        ('suspicious', 'Suspicious Activity'),
        ('password_change', 'Password Changed')
    ], default='logout')
    expires_at = models.DateTimeField()  # Original token expiry
    blacklisted_at = models.DateTimeField(auto_now_add=True)
    created_from_ip = models.GenericIPAddressField(null=True, blank=True)
    
    class Meta:
        db_table = 'auth_token_blacklist'
        indexes = [
            models.Index(fields=['jti']),
            models.Index(fields=['user', 'blacklisted_at']),
            models.Index(fields=['expires_at']),
            models.Index(fields=['token_type', 'jti']),
        ]
        ordering = ['-blacklisted_at']
    
    def is_expired(self) -> bool:
        """Check if the original token would have expired anyway"""
        return timezone.now() > self.expires_at
    
    def __str__(self):
        return f"Blacklisted {self.token_type} for {self.user.email}"
