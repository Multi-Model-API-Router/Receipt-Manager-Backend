# auth_service/api/v1/urls.py
from django.urls import path
from .views import (
    RequestMagicLinkView,
    MagicLinkLoginView,
    UserProfileView,
    UpdateEmailView,
    EmailVerificationView,
    ResendVerificationView,
    RefreshTokenView,
    LogoutView,
    LogoutAllDevicesView,
    ForceLogoutUserView,  # New
    CheckTokenStatusView,  # New
    UserStatsView
)

urlpatterns = [
    # Authentication endpoints
    path('magic-link/request/', RequestMagicLinkView.as_view(), name='request_magic_link'),
    path('magic-link/login/', MagicLinkLoginView.as_view(), name='magic_link_login'),
    path('token/refresh/', RefreshTokenView.as_view(), name='token_refresh'),
    path('token/status/', CheckTokenStatusView.as_view(), name='token_status'),
    
    # Logout endpoints
    path('logout/', LogoutView.as_view(), name='logout'),
    path('logout/all-devices/', LogoutAllDevicesView.as_view(), name='logout_all_devices'),
    path('admin/force-logout/', ForceLogoutUserView.as_view(), name='admin_force_logout'),
    
    # Email verification endpoints
    path('email/verify/', EmailVerificationView.as_view(), name='verify_email'),
    path('email/resend-verification/', ResendVerificationView.as_view(), name='resend_verification'),
    path('email/update/', UpdateEmailView.as_view(), name='update_email'),
    
    # User profile endpoints
    path('profile/', UserProfileView.as_view(), name='user_profile'),
    path('stats/', UserStatsView.as_view(), name='user_stats'),
]
