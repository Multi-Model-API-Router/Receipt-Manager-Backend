from django.apps import apps
from django.db import models
from typing import Type

class ModelImportService:
    """Service for lazy loading models to avoid circular imports"""
    
    def __init__(self):
        self._user_model = None
        self._magic_link_model = None
        self._email_verification_model = None
        self._token_blacklist_model = None
        self._login_attempt_model = None
    
    @property
    def user_model(self) -> Type[models.Model]:
        """Lazy load User model"""
        if self._user_model is None:
            self._user_model = apps.get_model('auth_service', 'User')
        return self._user_model
    
    @property
    def magic_link_model(self) -> Type[models.Model]:
        """Lazy load MagicLink model"""
        if self._magic_link_model is None:
            self._magic_link_model = apps.get_model('auth_service', 'MagicLink')
        return self._magic_link_model
    
    @property
    def email_verification_model(self) -> Type[models.Model]:
        """Lazy load EmailVerification model"""
        if self._email_verification_model is None:
            self._email_verification_model = apps.get_model('auth_service', 'EmailVerification')
        return self._email_verification_model
    
    @property
    def token_blacklist_model(self) -> Type[models.Model]:
        """Lazy load TokenBlacklist model"""
        if self._token_blacklist_model is None:
            self._token_blacklist_model = apps.get_model('auth_service', 'TokenBlacklist')
        return self._token_blacklist_model
    
    @property
    def login_attempt_model(self) -> Type[models.Model]:
        """Lazy load LoginAttempt model"""
        if self._login_attempt_model is None:
            self._login_attempt_model = apps.get_model('auth_service', 'LoginAttempt')
        return self._login_attempt_model

# Global instance for easy access
model_service = ModelImportService()
