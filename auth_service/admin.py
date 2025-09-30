# apps/auth_service/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, MagicLink, EmailVerification, TokenBlacklist, LoginAttempt

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ['email', 'first_name', 'last_name', 'is_email_verified', 'monthly_upload_count', 'created_at']
    list_filter = ['is_email_verified', 'is_active', 'is_staff', 'created_at']
    search_fields = ['email', 'first_name', 'last_name']
    ordering = ['-created_at']
    
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Extended Info', {
            'fields': ('is_email_verified', 'monthly_upload_count', 'upload_reset_date', 
                      'last_login_ip', 'failed_login_attempts', 'account_locked_until')
        }),
    )

@admin.register(MagicLink)
class MagicLinkAdmin(admin.ModelAdmin):
    list_display = ['email', 'is_used', 'created_at', 'expires_at', 'used_at']
    list_filter = ['is_used', 'created_at', 'expires_at']
    search_fields = ['email']
    readonly_fields = ['token', 'created_at', 'used_at']
    ordering = ['-created_at']

@admin.register(EmailVerification)
class EmailVerificationAdmin(admin.ModelAdmin):
    list_display = ['user', 'email', 'is_verified', 'created_at', 'verified_at']
    list_filter = ['is_verified', 'created_at']
    search_fields = ['user__email', 'email']
    readonly_fields = ['token', 'created_at', 'verified_at']

@admin.register(TokenBlacklist)
class TokenBlacklistAdmin(admin.ModelAdmin):
    list_display = ['user', 'token_type', 'reason', 'blacklisted_at', 'expires_at']
    list_filter = ['token_type', 'reason', 'blacklisted_at']
    search_fields = ['user__email', 'jti']
    readonly_fields = ['jti', 'blacklisted_at']
    ordering = ['-blacklisted_at']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user')

@admin.register(LoginAttempt)
class LoginAttemptAdmin(admin.ModelAdmin):
    list_display = ['email', 'success', 'ip_address', 'created_at', 'failure_reason']
    list_filter = ['success', 'created_at']
    search_fields = ['email', 'ip_address']
    readonly_fields = ['created_at']
    ordering = ['-created_at']
