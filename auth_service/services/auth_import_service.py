from importlib import import_module
from typing import Any

class ImportService:
    """Service for lazy importing modules and classes"""
    
    def __init__(self):
        self._auth_service = None
        self._email_service = None
        self._cache_service = None
        self._jwt_service = None
    
    @property
    def auth_service(self):
        """Lazy import auth service"""
        if self._auth_service is None:
            module = import_module('auth_service.services.auth_service')
            self._auth_service = module.AuthService()
        return self._auth_service
    
    @property
    def email_service(self):
        """Lazy import email service"""
        if self._email_service is None:
            module = import_module('auth_service.services.email_service')
            self._email_service = module.EmailService()
        return self._email_service
    
    @property
    def cache_service(self):
        """Lazy import cache service"""
        if self._cache_service is None:
            module = import_module('django.core.cache')
            self._cache_service = module.cache
        return self._cache_service
    
    @property
    def jwt_service(self):
        """Lazy load JWTService (your custom service, not the module)"""
        if self._jwt_service is None:
            module = import_module('auth_service.services.jwt_service')
            self._jwt_service = module.JWTService()
        return self._jwt_service
    
    def get_service(self, module_path: str, class_name: str) -> Any:
        """Dynamic service import"""
        try:
            module = import_module(module_path)
            return getattr(module, class_name)()
        except (ImportError, AttributeError) as e:
            raise ImportError(f"Failed to import {class_name} from {module_path}: {str(e)}")

# Global instance
import_service = ImportService()
