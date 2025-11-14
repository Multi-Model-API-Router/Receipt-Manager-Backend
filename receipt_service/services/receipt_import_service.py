from importlib import import_module
from typing import Any


class ServiceImportService:
    """Service for lazy importing services and utilities to avoid circular imports"""
    
    def __init__(self):
        self._quota_service = None
        self._file_service = None
        self._category_service = None
        self._receipt_service = None
        self._ledger_service = None
        self._cache_service = None
    
    @property
    def quota_service(self):
        """Lazy import quota service"""
        if self._quota_service is None:
            module = import_module('receipt_service.services.quota_service')
            self._quota_service = module.QuotaService()
        return self._quota_service
    
    @property
    def file_service(self):
        """Lazy import file service"""
        if self._file_service is None:
            module = import_module('receipt_service.services.file_service')
            self._file_service = module.FileService()
        return self._file_service
    
    @property
    def category_service(self):
        """Lazy import category service"""
        if self._category_service is None:
            module = import_module('receipt_service.services.category_service')
            self._category_service = module.CategoryService()
        return self._category_service
    
    @property
    def receipt_service(self):
        """Lazy import receipt service"""
        if self._receipt_service is None:
            module = import_module('receipt_service.services.receipt_service')
            self._receipt_service = module.ReceiptService()
        return self._receipt_service
    
    @property
    def ledger_service(self):
        """Lazy import ledger service"""
        if self._ledger_service is None:
            module = import_module('receipt_service.services.ledger_service')
            self._ledger_service = module.LedgerService()
        return self._ledger_service
    
    @property
    def cache_service(self):
        """Lazy import cache service"""
        if self._cache_service is None:
            module = import_module('django.core.cache')
            self._cache_service = module.cache
        return self._cache_service
    
    def get_service(self, module_path: str, class_name: str) -> Any:
        """Dynamic service import"""
        try:
            module = import_module(module_path)
            return getattr(module, class_name)()
        except (ImportError, AttributeError) as e:
            raise ImportError(f"Failed to import {class_name} from {module_path}: {str(e)}")


# Global instance
service_import = ServiceImportService()
