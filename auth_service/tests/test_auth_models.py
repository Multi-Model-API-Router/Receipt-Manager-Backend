"""
Unit tests for auth_service/models.py
Tests model methods, properties, and business logic
Uses Django's database for model validation
"""
import pytest
import uuid
from datetime import timedelta
from django.utils import timezone
from django.contrib.auth import get_user_model
from auth_service.models import (
    User,
    MagicLink,
    EmailVerification,
    LoginAttempt,
    TokenBlacklist
)

User = get_user_model()


@pytest.fixture
def sample_user(db):
    """Create sample user"""
    return User.objects.create_user(
        email='user@example.com',
        first_name='Test',
        last_name='User'
    )


@pytest.fixture
def sample_magic_link(db):
    """Create sample magic link"""
    return MagicLink.objects.create(
        email='test@example.com',
        token='test_token_12345',
        expires_at=timezone.now() + timedelta(minutes=15),
        created_from_ip='127.0.0.1'
    )


@pytest.fixture
def sample_email_verification(db, sample_user):
    """Create sample email verification"""
    return EmailVerification.objects.create(
        user=sample_user,
        email=sample_user.email,
        token='verification_token_12345',
        expires_at=timezone.now() + timedelta(hours=24)
    )


@pytest.fixture
def sample_token_blacklist(db, sample_user):
    """Create sample blacklisted token"""
    return TokenBlacklist.objects.create(
        jti='test-jti-12345',
        user=sample_user,
        token_type='access',
        reason='logout',
        expires_at=timezone.now() + timedelta(minutes=15)
    )


# =====================================================
# User Model Tests
# =====================================================

@pytest.mark.django_db
class TestUserModel:
    """Test User model methods and properties"""
    
    def test_user_creation_with_email_only(self):
        """Test creating user with email only"""
        user = User.objects.create_user(email='new@example.com')
        
        assert user.email == 'new@example.com'
        assert user.is_active is True
        assert user.is_email_verified is False
        assert user.is_staff is False
        assert user.monthly_upload_count == 0
    
    def test_user_creation_with_all_fields(self):
        """Test creating user with all fields"""
        user = User.objects.create_user(
            email='full@example.com',
            first_name='John',
            last_name='Doe'
        )
        
        assert user.email == 'full@example.com'
        assert user.first_name == 'John'
        assert user.last_name == 'Doe'
    
    def test_user_str_representation(self, sample_user):
        """Test user string representation"""
        assert str(sample_user) == 'user@example.com'
    
    def test_user_email_unique_constraint(self, sample_user, db):
        """Test email unique constraint"""
        from django.db import IntegrityError
        
        with pytest.raises(IntegrityError):
            User.objects.create_user(email='user@example.com')
    
    def test_user_id_is_uuid(self, sample_user):
        """Test user ID is UUID"""
        assert isinstance(sample_user.id, uuid.UUID)
    
    def test_created_at_auto_set(self, sample_user):
        """Test created_at is automatically set"""
        assert sample_user.created_at is not None
        assert sample_user.created_at <= timezone.now()
    
    def test_updated_at_auto_updates(self, sample_user):
        """Test updated_at updates automatically"""
        old_updated = sample_user.updated_at
        
        sample_user.first_name = 'Updated'
        sample_user.save()
        
        assert sample_user.updated_at > old_updated
    
    def test_user_meta_table_name(self):
        """Test correct database table name"""
        assert User._meta.db_table == 'auth_users'
    
    def test_user_meta_verbose_names(self):
        """Test verbose names"""
        assert User._meta.verbose_name == 'user'
        assert User._meta.verbose_name_plural == 'users'
    
    def test_user_email_indexed(self):
        """Test email field is indexed"""
        email_field = User._meta.get_field('email')
        assert email_field.db_index is True
    
    def test_monthly_upload_count_default(self, sample_user):
        """Test monthly_upload_count defaults to 0"""
        assert sample_user.monthly_upload_count == 0
    
    def test_upload_reset_date_auto_set(self, sample_user):
        """Test upload_reset_date is automatically set"""
        assert sample_user.upload_reset_date is not None


# =====================================================
# MagicLink Model Tests
# =====================================================

@pytest.mark.django_db
class TestMagicLinkModel:
    """Test MagicLink model methods"""
    
    def test_magic_link_creation(self, sample_magic_link):
        """Test magic link creation"""
        assert sample_magic_link.email == 'test@example.com'
        assert sample_magic_link.token == 'test_token_12345'
        assert sample_magic_link.is_used is False
        assert sample_magic_link.used_at is None
    
    def test_is_expired_not_expired(self, sample_magic_link):
        """Test is_expired returns False for valid link"""
        assert sample_magic_link.is_expired() is False
    
    def test_is_expired_expired(self, db):
        """Test is_expired returns True for expired link"""
        expired_link = MagicLink.objects.create(
            email='test@example.com',
            token='expired_token',
            expires_at=timezone.now() - timedelta(minutes=1)
        )
        
        assert expired_link.is_expired() is True
    
    def test_mark_as_used_without_ip(self, sample_magic_link):
        """Test marking link as used without IP"""
        sample_magic_link.mark_as_used()
        
        assert sample_magic_link.is_used is True
        assert sample_magic_link.used_at is not None
        assert sample_magic_link.used_from_ip is None
    
    def test_mark_as_used_with_ip(self, sample_magic_link):
        """Test marking link as used with IP"""
        sample_magic_link.mark_as_used(ip_address='192.168.1.1')
        
        assert sample_magic_link.is_used is True
        assert sample_magic_link.used_at is not None
        assert sample_magic_link.used_from_ip == '192.168.1.1'
    
    def test_magic_link_id_is_uuid(self, sample_magic_link):
        """Test magic link ID is UUID"""
        assert isinstance(sample_magic_link.id, uuid.UUID)
    
    def test_magic_link_token_unique(self, sample_magic_link, db):
        """Test token unique constraint"""
        from django.db import IntegrityError
        
        with pytest.raises(IntegrityError):
            MagicLink.objects.create(
                email='other@example.com',
                token='test_token_12345',  # Same token
                expires_at=timezone.now() + timedelta(minutes=15)
            )
    
    def test_magic_link_meta_table_name(self):
        """Test correct database table name"""
        assert MagicLink._meta.db_table == 'auth_magic_links'
    
    def test_created_at_auto_set(self, sample_magic_link):
        """Test created_at is automatically set"""
        assert sample_magic_link.created_at is not None
        assert sample_magic_link.created_at <= timezone.now()


# =====================================================
# EmailVerification Model Tests
# =====================================================

@pytest.mark.django_db
class TestEmailVerificationModel:
    """Test EmailVerification model methods"""
    
    def test_email_verification_creation(self, sample_email_verification):
        """Test email verification creation"""
        assert sample_email_verification.is_verified is False
        assert sample_email_verification.verified_at is None
    
    def test_is_expired_not_expired(self, sample_email_verification):
        """Test is_expired returns False for valid token"""
        assert sample_email_verification.is_expired() is False
    
    def test_is_expired_expired(self, sample_user, db):
        """Test is_expired returns True for expired token"""
        expired_verification = EmailVerification.objects.create(
            user=sample_user,
            email=sample_user.email,
            token='expired_token',
            expires_at=timezone.now() - timedelta(hours=1)
        )
        
        assert expired_verification.is_expired() is True
    
    def test_mark_as_verified(self, sample_email_verification, sample_user):
        """Test marking email as verified"""
        # Ensure user starts unverified
        sample_user.is_email_verified = False
        sample_user.save()
        
        sample_email_verification.mark_as_verified()
        
        # Refresh from database
        sample_email_verification.refresh_from_db()
        sample_user.refresh_from_db()
        
        assert sample_email_verification.is_verified is True
        assert sample_email_verification.verified_at is not None
        assert sample_user.is_email_verified is True
    
    def test_email_verification_id_is_uuid(self, sample_email_verification):
        """Test email verification ID is UUID"""
        assert isinstance(sample_email_verification.id, uuid.UUID)
    
    def test_email_verification_token_unique(self, sample_user, sample_email_verification, db):
        """Test token unique constraint"""
        from django.db import IntegrityError
        
        with pytest.raises(IntegrityError):
            EmailVerification.objects.create(
                user=sample_user,
                email=sample_user.email,
                token='verification_token_12345',  # Same token
                expires_at=timezone.now() + timedelta(hours=24)
            )
    
    def test_email_verification_meta_table_name(self):
        """Test correct database table name"""
        assert EmailVerification._meta.db_table == 'auth_email_verifications'
    
    def test_email_verification_related_name(self, sample_user, sample_email_verification):
        """Test related_name works"""
        verifications = sample_user.email_verifications.all()
        assert sample_email_verification in verifications


# =====================================================
# LoginAttempt Model Tests
# =====================================================

@pytest.mark.django_db
class TestLoginAttemptModel:
    """Test LoginAttempt model"""
    
    def test_login_attempt_creation_success(self, db):
        """Test creating successful login attempt"""
        attempt = LoginAttempt.objects.create(
            email='test@example.com',
            ip_address='127.0.0.1',
            user_agent='Mozilla/5.0',
            success=True
        )
        
        assert attempt.email == 'test@example.com'
        assert attempt.success is True
        assert attempt.failure_reason == ''
    
    def test_login_attempt_creation_failure(self, db):
        """Test creating failed login attempt"""
        attempt = LoginAttempt.objects.create(
            email='test@example.com',
            ip_address='127.0.0.1',
            user_agent='Mozilla/5.0',
            success=False,
            failure_reason='invalid_credentials'
        )
        
        assert attempt.success is False
        assert attempt.failure_reason == 'invalid_credentials'
    
    def test_login_attempt_id_is_uuid(self, db):
        """Test login attempt ID is UUID"""
        attempt = LoginAttempt.objects.create(
            email='test@example.com',
            ip_address='127.0.0.1',
            success=True
        )
        
        assert isinstance(attempt.id, uuid.UUID)
    
    def test_login_attempt_meta_table_name(self):
        """Test correct database table name"""
        assert LoginAttempt._meta.db_table == 'auth_login_attempts'
    
    def test_created_at_auto_set(self, db):
        """Test created_at is automatically set"""
        attempt = LoginAttempt.objects.create(
            email='test@example.com',
            ip_address='127.0.0.1',
            success=True
        )
        
        assert attempt.created_at is not None
        assert attempt.created_at <= timezone.now()


# =====================================================
# TokenBlacklist Model Tests
# =====================================================

@pytest.mark.django_db
class TestTokenBlacklistModel:
    """Test TokenBlacklist model methods"""
    
    def test_token_blacklist_creation(self, sample_token_blacklist):
        """Test token blacklist creation"""
        assert sample_token_blacklist.jti == 'test-jti-12345'
        assert sample_token_blacklist.token_type == 'access'
        assert sample_token_blacklist.reason == 'logout'
    
    def test_is_expired_not_expired(self, sample_token_blacklist):
        """Test is_expired returns False for valid token"""
        assert sample_token_blacklist.is_expired() is False
    
    def test_is_expired_expired(self, sample_user, db):
        """Test is_expired returns True for expired token"""
        expired_token = TokenBlacklist.objects.create(
            jti='expired-jti',
            user=sample_user,
            token_type='refresh',
            expires_at=timezone.now() - timedelta(hours=1)
        )
        
        assert expired_token.is_expired() is True
    
    def test_token_blacklist_str_representation(self, sample_token_blacklist):
        """Test string representation"""
        expected = f"Blacklisted access for user@example.com"
        assert str(sample_token_blacklist) == expected
    
    def test_token_blacklist_id_is_uuid(self, sample_token_blacklist):
        """Test token blacklist ID is UUID"""
        assert isinstance(sample_token_blacklist.id, uuid.UUID)
    
    def test_token_blacklist_jti_unique(self, sample_user, sample_token_blacklist, db):
        """Test JTI unique constraint"""
        from django.db import IntegrityError
        
        with pytest.raises(IntegrityError):
            TokenBlacklist.objects.create(
                jti='test-jti-12345',  # Same JTI
                user=sample_user,
                token_type='refresh',
                expires_at=timezone.now() + timedelta(minutes=15)
            )
    
    def test_token_blacklist_meta_table_name(self):
        """Test correct database table name"""
        assert TokenBlacklist._meta.db_table == 'auth_token_blacklist'
    
    def test_token_blacklist_meta_ordering(self):
        """Test ordering"""
        assert TokenBlacklist._meta.ordering == ['-blacklisted_at']
    
    def test_token_blacklist_related_name(self, sample_user, sample_token_blacklist):
        """Test related_name works"""
        blacklisted = sample_user.blacklisted_tokens.all()
        assert sample_token_blacklist in blacklisted
    
    def test_blacklisted_at_auto_set(self, sample_token_blacklist):
        """Test blacklisted_at is automatically set"""
        assert sample_token_blacklist.blacklisted_at is not None
        assert sample_token_blacklist.blacklisted_at <= timezone.now()
    
    def test_token_type_choices(self, sample_user, db):
        """Test token type choices"""
        access_token = TokenBlacklist.objects.create(
            jti='access-jti',
            user=sample_user,
            token_type='access',
            expires_at=timezone.now() + timedelta(minutes=15)
        )
        
        refresh_token = TokenBlacklist.objects.create(
            jti='refresh-jti',
            user=sample_user,
            token_type='refresh',
            expires_at=timezone.now() + timedelta(days=7)
        )
        
        assert access_token.token_type == 'access'
        assert refresh_token.token_type == 'refresh'
    
    def test_reason_choices(self, sample_user, db):
        """Test reason choices"""
        reasons = ['logout', 'revoked', 'suspicious', 'password_change']
        
        for reason in reasons:
            token = TokenBlacklist.objects.create(
                jti=f'jti-{reason}',
                user=sample_user,
                token_type='access',
                reason=reason,
                expires_at=timezone.now() + timedelta(minutes=15)
            )
            assert token.reason == reason
