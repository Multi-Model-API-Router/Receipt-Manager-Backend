import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
from unittest.mock import patch
from datetime import timedelta
from django.utils import timezone
from auth_service.models import EmailVerification

User = get_user_model()

@pytest.fixture
def api_client():
    return APIClient()

@pytest.fixture
def verified_user(db):
    user = User.objects.create_user(
        email='verified@example.com',
        first_name='John',
        last_name='Doe',
    )
    user.is_email_verified = True
    user.monthly_upload_count = 5
    user.save()
    return user

@pytest.fixture
def unverified_user(db):
    return User.objects.create_user(
        email='unverified@example.com',
        first_name='Jane',
        last_name='Smith',
    )

@pytest.mark.django_db
class TestUserProfileAPI:
    url = '/auth/v1/profile/'

    def test_get_profile_authenticated(self, api_client, verified_user):
        api_client.force_authenticate(user=verified_user)
        response = api_client.get(self.url)
        assert response.status_code == status.HTTP_200_OK
        assert 'message' in response.data
        assert 'data' in response.data

    def test_get_profile_unauthenticated(self, api_client):
        response = api_client.get(self.url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_update_profile_first_name(self, api_client, verified_user):
        api_client.force_authenticate(user=verified_user)
        data = {'first_name': 'Updated'}
        response = api_client.put(self.url, data, format='json')
        assert response.status_code == status.HTTP_200_OK
        verified_user.refresh_from_db()
        assert verified_user.first_name == 'Updated'

    def test_update_profile_email_blocked(self, api_client, verified_user):
        api_client.force_authenticate(user=verified_user)
        data = {'email': 'newemail@example.com'}
        response = api_client.put(self.url, data, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
class TestUpdateEmailAPI:
    url = '/auth/v1/email/update/'

    @patch('auth_service.services.auth_service.AuthService.request_email_change')
    def test_update_email_success(self, mock_request_email_change, api_client, verified_user):
        mock_request_email_change.return_value = {
            'current_email': verified_user.email,
            'pending_email': 'newemail@example.com',
            'verification_expires_at': timezone.now() + timedelta(hours=24),
            'requires_relogin': False,
        }
        api_client.force_authenticate(user=verified_user)
        data = {'new_email': 'newemail@example.com'}
        response = api_client.post(self.url, data, format='json')
        assert response.status_code == status.HTTP_200_OK
        assert 'message' in response.data

    def test_update_email_unauthenticated(self, api_client):
        data = {'new_email': 'newemail@example.com'}
        response = api_client.post(self.url, data, format='json')
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_update_email_already_exists(self, api_client, verified_user, unverified_user):
        api_client.force_authenticate(user=verified_user)
        data = {'new_email': unverified_user.email}
        response = api_client.post(self.url, data, format='json')
        assert response.status_code == status.HTTP_409_CONFLICT

    def test_update_email_same_as_current(self, api_client, verified_user):
        api_client.force_authenticate(user=verified_user)
        data = {'new_email': verified_user.email}
        response = api_client.post(self.url, data, format='json')
        assert response.status_code in [status.HTTP_400_BAD_REQUEST, 422]


@pytest.mark.django_db
class TestEmailVerificationAPI:
    url = '/auth/v1/email/verify/'

    @patch('auth_service.services.auth_service.AuthService.verify_email')
    def test_verify_email_success(self, mock_verify_email, api_client):
        mock_verify_email.return_value = {
            'email': 'verified@example.com',
            'tokens': {
                'access': 'new_access_token',
                'refresh': 'new_refresh_token',
            },
        }
        data = {'token': 'valid_verification_token'}
        response = api_client.post(self.url, data, format='json')
        assert response.status_code == status.HTTP_200_OK

    def test_verify_email_invalid_token(self, api_client):
        data = {'token': 'invalid_token'}
        response = api_client.post(self.url, data, format='json')
        assert response.status_code in (status.HTTP_400_BAD_REQUEST, status.HTTP_401_UNAUTHORIZED)

    def test_verify_email_missing_token(self, api_client):
        response = api_client.post(self.url, {}, format='json')
        assert response.status_code in (status.HTTP_400_BAD_REQUEST, status.HTTP_401_UNAUTHORIZED)


@pytest.mark.django_db
class TestUserStatsAPI:
    url = '/auth/v1/stats/'

    def test_get_stats_authenticated(self, api_client, verified_user):
        api_client.force_authenticate(user=verified_user)
        response = api_client.get(self.url)
        assert response.status_code == status.HTTP_200_OK
        assert 'message' in response.data
        assert 'data' in response.data

    def test_get_stats_unauthenticated(self, api_client):
        response = api_client.get(self.url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
class TestAPIPermissions:
    def test_protected_endpoints_require_auth(self, api_client):
        protected_urls = [
            ('/auth/v1/profile/', 'get'),
            ('/auth/v1/profile/', 'put'),
            ('/auth/v1/email/update/', 'post'),
            ('/auth/v1/stats/', 'get'),
            ('/auth/v1/logout/', 'post'),
        ]
        for url, method in protected_urls:
            if method == 'get':
                response = api_client.get(url)
            else:
                response = api_client.post(url, {}, format='json')
            assert response.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_404_NOT_FOUND)
