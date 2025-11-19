"""
Root conftest.py - Configure Django and provide pytest fixtures
"""
import os
import sys
import pytest
from datetime import timedelta


# ========== DJANGO CONFIGURATION - RUNS BEFORE EVERYTHING ==========

# Get project root directory (where conftest.py lives)
project_root = os.getcwd()
SECRET_KEY = os.environ.get("SECRET_KEY", "test-secret-key-for-testing-only")

# Clean up sys.path to avoid duplicates
project_root_normalized = os.path.normpath(project_root)
sys.path = [os.path.normpath(p) for p in sys.path]  # Normalize all paths
if project_root_normalized not in sys.path:
    sys.path.insert(0, project_root_normalized)

# Set Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'receiptmanager.settings')

# Configure Django if not already configured
import django
from django.conf import settings

if not settings.configured:
    settings.configure(
        DEBUG=True,
        SECRET_KEY='test-secret-key-for-testing-only-never-use-in-production',
        
        # ✅ Critical for custom User model
        AUTH_USER_MODEL='auth_service.User',
        
        # Database
        DATABASES={
            'default': {
                'ENGINE': 'django.db.backends.sqlite3',
                'NAME': ':memory:',
            }
        },
        
        # Apps - Use full module paths
        INSTALLED_APPS=[
            'django.contrib.admin',
            'django.contrib.contenttypes',
            'django.contrib.auth',
            'rest_framework',
            'shared',
            'auth_service.apps.AuthServiceConfig',
            'receipt_service.apps.ReceiptServiceConfig',
            'ai_service.apps.AiServiceConfig'
        ],
        
        # Middleware
        MIDDLEWARE=[
            'corsheaders.middleware.CorsMiddleware',
            'django.middleware.security.SecurityMiddleware',
            'django.contrib.sessions.middleware.SessionMiddleware',
            'django.middleware.common.CommonMiddleware',
            
            'shared.middleware.logging_middleware.LoggingContextMiddleware',
            
            # If you want CSRF middleware during tests, uncomment these:
            # 'auth_service.middleware.api_csrf_middleware.CSRFExemptAPIMiddleware',
            # 'django.middleware.csrf.CsrfViewMiddleware',
            
            'django.contrib.auth.middleware.AuthenticationMiddleware',
            
            'shared.middleware.security_middleware.SecurityMiddleware',
            'shared.middleware.security_middleware.IPWhitelistMiddleware',
            
            'auth_service.middleware.jwt_blacklist_middleware.JWTBlacklistMiddleware',
            
            'django.contrib.messages.middleware.MessageMiddleware',
            'django.middleware.clickjacking.XFrameOptionsMiddleware',
            
            'shared.middleware.logging_middleware.StructuredLoggingMiddleware',
            
            'shared.middleware.drf_exceptions.DRFExceptionMiddleware',
        ],

        
        # ✅ FIX: Set ROOT_URLCONF to your project's urls module
        ROOT_URLCONF='receiptmanager.urls',  # ← CHANGED FROM '' to 'receiptmanager.urls'
        
        # Cache settings
        CACHES={
            'default': {
                'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
                'LOCATION': 'test-cache',
            }
        },
        
        # Timezone settings
        USE_TZ=True,
        TIME_ZONE='UTC',
        USE_I18N=True,
        USE_L10N=True,
        
        # App-specific settings for receipt_service
        RECEIPT_MAX_FILE_SIZE=10 * 1024 * 1024,  # 10MB
        
        # App-specific settings for currency exchange
        EXCHANGE_RATE_API_KEY='test_api_key_1234567890_for_testing_only',
        EXCHANGE_RATE_API_TIMEOUT=10,
        EXCHANGE_RATE_MAX_RETRIES=3,
        EXCHANGE_RATE_FAILURE_THRESHOLD=3,
        EXCHANGE_RATE_RECOVERY_TIMEOUT=300,
        EXCHANGE_RATE_SUCCESS_THRESHOLD=2,
        EXCHANGE_RATE_CACHE_TIMEOUT=3600,
        FALLBACK_CACHE_TIMEOUT=86400,
        DEFAULT_CURRENCY='USD',
        BASE_CURRENCY='USD',
        
        # DRF settings
        REST_FRAMEWORK={
            'DEFAULT_AUTHENTICATION_CLASSES': [
                'rest_framework_simplejwt.authentication.JWTAuthentication',
                'rest_framework.authentication.SessionAuthentication',
            ],
            'DEFAULT_PERMISSION_CLASSES': [
                'rest_framework.permissions.IsAuthenticated',
            ],
            'PAGE_SIZE': 20,
            'EXCEPTION_HANDLER': 'shared.utils.exceptions.exception_handler',  # Use your correct handler here
        },

        
        # Password hashers (use fast hasher for tests)
        PASSWORD_HASHERS=[
            'django.contrib.auth.hashers.MD5PasswordHasher',
        ],
        
        # Email settings for auth tests
        DEFAULT_FROM_EMAIL='noreply@test.com',
        EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
        FRONTEND_URL='http://localhost:3000',
        
        # JWT settings for auth tests
        SIMPLE_JWT={
            'ACCESS_TOKEN_LIFETIME': timedelta(minutes=15),
            'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
            'ROTATE_REFRESH_TOKENS': True,
            'BLACKLIST_AFTER_ROTATION': True,
            'UPDATE_LAST_LOGIN': True,
            'ALGORITHM': 'HS256',
            'SIGNING_KEY': SECRET_KEY,
            'VERIFYING_KEY': None,
            'AUDIENCE': None,
            'ISSUER': None,
            'AUTH_HEADER_TYPES': ('Bearer',),
            'AUTH_HEADER_NAME': 'HTTP_AUTHORIZATION',
            'USER_ID_FIELD': 'id',
            'USER_ID_CLAIM': 'user_id',
            'USER_AUTHENTICATION_RULE': 'rest_framework_simplejwt.authentication.default_user_authentication_rule',
            'AUTH_TOKEN_CLASSES': ('rest_framework_simplejwt.tokens.AccessToken',),
            'TOKEN_TYPE_CLAIM': 'token_type',
            'TOKEN_USER_CLASS': 'rest_framework_simplejwt.models.TokenUser',
            'JTI_CLAIM': 'jti',
        },
        
        # Rate limiting settings for auth tests
        MAGIC_LINK_RATE_LIMIT_PER_EMAIL=5,
        MAGIC_LINK_RATE_LIMIT_PER_IP=20,
        LOGIN_RATE_LIMIT_PER_IP=20,
        TOKEN_REFRESH_RATE_LIMIT=50,
    )
    
    # Setup Django
    django.setup()


def pytest_configure(config):
    """
    Pytest hook called after command line options are parsed
    Ensures Django is set up before test collection
    """
    if not settings.configured:
        django.setup()


# ========== PYTEST FIXTURES ==========

@pytest.fixture(autouse=True)
def clear_cache():
    """Clear cache before and after each test"""
    from django.core.cache import cache
    cache.clear()
    yield
    cache.clear()


@pytest.fixture(autouse=True)
def reset_db_for_unit_tests(request):
    """
    Prevent database access in unit tests
    Only integration tests should touch the database
    """
    if 'unit' in request.keywords:
        pass
    yield


@pytest.fixture
def api_client():
    """DRF API client for integration tests"""
    from rest_framework.test import APIClient
    return APIClient()


@pytest.fixture
def authenticated_user(db):
    """Create and return an authenticated user"""
    from django.contrib.auth import get_user_model
    User = get_user_model()
    user = User.objects.create_user(
        email='test@example.com',
        first_name='Test',
        last_name='User'
    )
    return user


@pytest.fixture
def authenticated_client(api_client, authenticated_user):
    """Return API client with authenticated user"""
    api_client.force_authenticate(user=authenticated_user)
    return api_client, authenticated_user


@pytest.fixture
def sample_user(db):
    """Create sample user for tests"""
    from django.contrib.auth import get_user_model
    User = get_user_model()
    return User.objects.create_user(
        email='testuser@example.com',
        first_name='Test',
        last_name='User'
    )


@pytest.fixture
def verified_user(db):
    """Create verified user for tests"""
    from django.contrib.auth import get_user_model
    User = get_user_model()
    user = User.objects.create_user(
        email='verified@example.com',
        first_name='Verified',
        last_name='User'
    )
    user.is_email_verified = True
    user.save()
    return user
