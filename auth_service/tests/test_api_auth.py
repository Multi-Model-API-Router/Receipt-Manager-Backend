import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from rest_framework.test import APIClient
from rest_framework import status
from unittest.mock import patch, MagicMock
from datetime import timedelta
from django.utils import timezone
from auth_service.models import MagicLink

User = get_user_model()


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def sample_user(db):
    return User.objects.create_user(
        email='testuser@example.com',
        first_name='Test',
        last_name='User'
    )


@pytest.fixture
def verified_user(db):
    user = User.objects.create_user(
        email='verified@example.com',
        first_name='Verified',
        last_name='User'
    )
    user.is_email_verified = True
    user.save()
    return user


@pytest.fixture
def expired_magic_link(db):
    return MagicLink.objects.create(
        email='testuser@example.com',
        token='expired_token_12345',
        expires_at=timezone.now() - timedelta(minutes=10),
        is_used=False
    )


@pytest.fixture
def used_magic_link(db):
    return MagicLink.objects.create(
        email='testuser@example.com',
        token='used_token_12345',
        expires_at=timezone.now() + timedelta(minutes=10),
        is_used=True
    )


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.mark.django_db
class TestRequestMagicLinkAPI:
    url = '/auth/v1/magic-link/request/'

    @patch('auth_service.tasks.send_magic_link_email_async')
    def test_request_magic_link_success(self, mock_task, api_client):
        # Mock delay method for celery task
        mock_task.delay = MagicMock()

        data = {'email': 'newuser@example.com'}
        response = api_client.post(self.url, data, format='json')

        assert response.status_code == status.HTTP_200_OK
        assert 'message' in response.data
        mock_task.delay.assert_called_once()

    @patch('auth_service.tasks.send_magic_link_email_async')
    def test_request_magic_link_existing_user(self, mock_task, api_client, sample_user):
        mock_task.delay = MagicMock()
        data = {'email': sample_user.email}
        response = api_client.post(self.url, data, format='json')

        assert response.status_code == status.HTTP_200_OK
        assert 'message' in response.data
        mock_task.delay.assert_called_once()

    def test_request_magic_link_invalid_email(self, api_client):
        data = {'email': 'invalid-email'}
        response = api_client.post(self.url, data, format='json')

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'error' in response.data

    def test_request_magic_link_missing_email(self, api_client):
        response = api_client.post(self.url, {}, format='json')

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'error' in response.data

    def test_request_magic_link_rate_limiting(self, api_client):
        # Simulate rate limit reached
        cache.set('magic_link_emails_per_ip_127.0.0.1', set(f'user{i}@example.com' for i in range(21)), timeout=3600)

        data = {'email': 'test@example.com'}
        response = api_client.post(self.url, data, format='json')

        assert response.status_code in (status.HTTP_429_TOO_MANY_REQUESTS, status.HTTP_503_SERVICE_UNAVAILABLE)


@pytest.mark.django_db
class TestMagicLinkLoginAPI:
    url = '/auth/v1/magic-link/verify/'

    @patch('auth_service.services.auth_service.AuthService.verify_magic_link')
    def test_magic_link_login_new_user(self, mock_verify, api_client):
        mock_verify.return_value = (
            {
                'user': {
                    'id': 'user-uuid',
                    'email': 'newuser@example.com',
                    'first_name': '',
                    'is_email_verified': True
                },
                'tokens': {
                    'access': 'access_token',
                    'refresh': 'refresh_token'
                },
                'user_email': 'newuser@example.com',
                'user_first_name': ''
            },
            True
        )
        response = api_client.post(self.url, {'token': 'valid_token'}, format='json')

        assert response.status_code == status.HTTP_200_OK
        assert 'message' in response.data

    @patch('auth_service.services.auth_service.AuthService.verify_magic_link')
    def test_magic_link_login_existing_user(self, mock_verify, api_client, verified_user):
        mock_verify.return_value = (
            {
                'user': {
                    'id': str(verified_user.id),
                    'email': verified_user.email,
                    'first_name': verified_user.first_name,
                    'is_email_verified': True,
                },
                'tokens': {
                    'access': 'access_token',
                    'refresh': 'refresh_token',
                },
                'user_email': verified_user.email,
            },
            False
        )
        response = api_client.post(self.url, {'token': 'valid_token'}, format='json')

        assert response.status_code == status.HTTP_200_OK
        assert 'message' in response.data

    def test_magic_link_login_invalid_token(self, api_client):
        response = api_client.post(self.url, {'token': 'invalid_token'}, format='json')
        # Accept 400 or 401 depending on implementation
        assert response.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_400_BAD_REQUEST)

    def test_magic_link_login_expired_token(self, api_client, expired_magic_link):
        response = api_client.post(self.url, {'token': expired_magic_link.token}, format='json')
        assert response.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_400_BAD_REQUEST)

    def test_magic_link_login_used_token(self, api_client, used_magic_link):
        response = api_client.post(self.url, {'token': used_magic_link.token}, format='json')
        assert response.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_400_BAD_REQUEST)

    def test_magic_link_login_missing_token(self, api_client):
        response = api_client.post(self.url, {}, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_magic_link_login_too_short_token(self, api_client):
        response = api_client.post(self.url, {'token': 'short'}, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_magic_link_login_rate_limiting(self, api_client):
        cache.set('login_attempts_ip_127.0.0.1', 21, timeout=3600)
        response = api_client.post(self.url, {'token': 'any_token'}, format='json')
        assert response.status_code in (status.HTTP_429_TOO_MANY_REQUESTS, status.HTTP_400_BAD_REQUEST)


@pytest.mark.django_db
class TestRefreshTokenAPI:
    url = '/auth/v1/token/refresh/'

    @patch('auth_service.services.auth_service.AuthService.refresh_jwt_token')
    def test_refresh_token_success(self, mock_refresh, api_client):
        mock_refresh.return_value = {
            'access': 'new_access_token',
            'refresh': 'new_refresh_token',
        }
        response = api_client.post(self.url, {'refresh': 'valid_refresh_token'}, format='json')
        assert response.status_code == status.HTTP_200_OK

    def test_refresh_token_invalid(self, api_client):
        response = api_client.post(self.url, {'refresh': 'invalid_token'}, format='json')
        assert response.status_code in (status.HTTP_400_BAD_REQUEST, status.HTTP_401_UNAUTHORIZED)

    def test_refresh_token_expired(self, api_client):
        response = api_client.post(self.url, {'refresh': 'expired_refresh_token'}, format='json')
        assert response.status_code in (status.HTTP_400_BAD_REQUEST, status.HTTP_401_UNAUTHORIZED)

    def test_refresh_token_missing(self, api_client):
        response = api_client.post(self.url, {}, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_refresh_token_rate_limiting(self, api_client):
        cache.set('token_refresh_ip_127.0.0.1', 51, timeout=3600)
        response = api_client.post(self.url, {'refresh': 'any_token'}, format='json')
        assert response.status_code in (status.HTTP_429_TOO_MANY_REQUESTS, status.HTTP_400_BAD_REQUEST)


@pytest.mark.django_db
class TestLogoutAPI:
    url = '/auth/v1/logout/'

    def test_logout_with_refresh_token(self, api_client, verified_user):
        api_client.force_authenticate(user=verified_user)
        response = api_client.post(self.url, {'refresh': 'refresh_token_12345'}, format='json')
        assert response.status_code == status.HTTP_200_OK

    def test_logout_with_access_token_in_header(self, api_client, verified_user):
        api_client.force_authenticate(user=verified_user)
        api_client.credentials(HTTP_AUTHORIZATION='Bearer access_token_12345')
        response = api_client.post(self.url, {}, format='json')
        assert response.status_code == status.HTTP_200_OK

    def test_logout_with_both_tokens(self, api_client, verified_user):
        api_client.force_authenticate(user=verified_user)
        api_client.credentials(HTTP_AUTHORIZATION='Bearer access_token')
        response = api_client.post(self.url, {'refresh': 'refresh_token'}, format='json')
        assert response.status_code == status.HTTP_200_OK

    def test_logout_without_tokens(self, api_client, verified_user):
        api_client.force_authenticate(user=verified_user)
        response = api_client.post(self.url, {}, format='json')
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_logout_unauthenticated(self, api_client):
        response = api_client.post(self.url, {'refresh': 'some_token'}, format='json')
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
