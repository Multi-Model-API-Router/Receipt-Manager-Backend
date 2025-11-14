from django.apps import apps
from django.db import models
from typing import TYPE_CHECKING, Type, Optional
import logging


logger = logging.getLogger(__name__)


if TYPE_CHECKING:
    from ..models.receipt import Receipt
    from ..models.category import Category, UserCategoryPreference
    from ..models.ledger import LedgerEntry
    from auth_service.models import User


class ModelImportService:
    """
    Lazy loading service for models to avoid circular imports
    Updated to match actual receipt_service models
    """
    
    def __init__(self):
        # Receipt service models
        self._receipt_model = None
        self._category_model = None
        self._user_category_preference_model = None
        self._ledger_entry_model = None
        
        # External models
        self._user_model = None
    
    @property
    def receipt_model(self) -> Type['Receipt']:
        """Lazy load Receipt model"""
        if self._receipt_model is None:
            try:
                self._receipt_model = apps.get_model('receipt_service', 'Receipt')
                logger.debug("Loaded Receipt model")
            except Exception as e:
                logger.error(f"Failed to load Receipt model: {str(e)}")
                raise ImportError("Could not import Receipt model") from e
        return self._receipt_model
    
    @property
    def category_model(self) -> Type['Category']:
        """Lazy load Category model (replaces expense_category_model)"""
        if self._category_model is None:
            try:
                self._category_model = apps.get_model('receipt_service', 'Category')
                logger.debug("Loaded Category model")
            except Exception as e:
                logger.error(f"Failed to load Category model: {str(e)}")
                raise ImportError("Could not import Category model") from e
        return self._category_model
    
    # Backward compatibility alias
    @property
    def expense_category_model(self) -> Type['Category']:
        """Backward compatibility alias for category_model"""
        return self.category_model
    
    @property
    def user_category_preference_model(self) -> Type['UserCategoryPreference']:
        """Lazy load UserCategoryPreference model"""
        if self._user_category_preference_model is None:
            try:
                self._user_category_preference_model = apps.get_model('receipt_service', 'UserCategoryPreference')
                logger.debug("Loaded UserCategoryPreference model")
            except Exception as e:
                logger.error(f"Failed to load UserCategoryPreference model: {str(e)}")
                raise ImportError("Could not import UserCategoryPreference model") from e
        return self._user_category_preference_model
    
    @property
    def ledger_entry_model(self) -> Type['LedgerEntry']:
        """Lazy load LedgerEntry model"""
        if self._ledger_entry_model is None:
            try:
                self._ledger_entry_model = apps.get_model('receipt_service', 'LedgerEntry')
                logger.debug("Loaded LedgerEntry model")
            except Exception as e:
                logger.error(f"Failed to load LedgerEntry model: {str(e)}")
                raise ImportError("Could not import LedgerEntry model") from e
        return self._ledger_entry_model
    
    @property
    def user_model(self) -> Type['User']:
        """Lazy load User model from auth_service"""
        if self._user_model is None:
            try:
                self._user_model = apps.get_model('auth_service', 'User')
                logger.debug("Loaded User model from auth_service")
            except Exception as e:
                logger.error(f"Failed to load User model: {str(e)}")
                raise ImportError("Could not import User model from auth_service") from e
        return self._user_model
    
    # Removed receipt_file_model since we're not using a separate ReceiptFile model
    # The file path is stored directly in the Receipt model
    
    def get_model(self, app_label: str, model_name: str) -> Type[models.Model]:
        """
        Generic method to get any model by app_label and model_name
        
        Args:
            app_label: Django app label (e.g., 'receipt_service')
            model_name: Model class name (e.g., 'Receipt')
            
        Returns:
            Model class
            
        Raises:
            ImportError: If model cannot be loaded
        """
        try:
            model = apps.get_model(app_label, model_name)
            logger.debug(f"Loaded {model_name} model from {app_label}")
            return model
        except Exception as e:
            logger.error(f"Failed to load {model_name} model from {app_label}: {str(e)}")
            raise ImportError(f"Could not import {model_name} model from {app_label}") from e
    
    def is_model_available(self, app_label: str, model_name: str) -> bool:
        """
        Check if a model is available without raising exceptions
        
        Args:
            app_label: Django app label
            model_name: Model class name
            
        Returns:
            True if model is available, False otherwise
        """
        try:
            apps.get_model(app_label, model_name)
            return True
        except Exception:
            return False
    
    def get_all_models(self) -> dict:
        """
        Get all available models as a dictionary
        
        Returns:
            Dictionary mapping model names to model classes
        """
        models_dict = {}
        
        try:
            models_dict['Receipt'] = self.receipt_model
            models_dict['Category'] = self.category_model
            models_dict['UserCategoryPreference'] = self.user_category_preference_model
            models_dict['LedgerEntry'] = self.ledger_entry_model
            models_dict['User'] = self.user_model
            
            logger.debug(f"Loaded {len(models_dict)} models")
            
        except Exception as e:
            logger.error(f"Error loading models: {str(e)}")
            raise
        
        return models_dict
    
    def validate_models(self) -> dict:
        """
        Validate that all required models can be loaded
        
        Returns:
            Dictionary with validation results
        """
        validation_results = {
            'success': True,
            'loaded_models': [],
            'failed_models': [],
            'errors': []
        }
        
        models_to_check = [
            ('receipt_service', 'Receipt'),
            ('receipt_service', 'Category'),
            ('receipt_service', 'UserCategoryPreference'),
            ('receipt_service', 'LedgerEntry'),
            ('auth_service', 'User'),
        ]
        
        for app_label, model_name in models_to_check:
            try:
                self.get_model(app_label, model_name)
                validation_results['loaded_models'].append(f"{app_label}.{model_name}")
            except Exception as e:
                validation_results['success'] = False
                validation_results['failed_models'].append(f"{app_label}.{model_name}")
                validation_results['errors'].append(str(e))
        
        if validation_results['success']:
            logger.info("All required models validated successfully")
        else:
            logger.error(f"Model validation failed: {validation_results['failed_models']}")
        
        return validation_results
    
    def clear_cache(self):
        """Clear all cached model references"""
        self._receipt_model = None
        self._category_model = None
        self._user_category_preference_model = None
        self._ledger_entry_model = None
        self._user_model = None
        logger.debug("Model cache cleared")
    
    def __str__(self):
        """String representation for debugging"""
        models = []
        try:
            if self._receipt_model:
                models.append("Receipt")
            if self._category_model:
                models.append("Category")
            if self._user_category_preference_model:
                models.append("UserCategoryPreference")
            if self._ledger_entry_model:
                models.append("LedgerEntry")
            if self._user_model:
                models.append("User")
        except:
            pass
        
        return f"ModelImportService(loaded: {models})"


# Global instance
model_service = ModelImportService()


# Convenience functions for backward compatibility and ease of use
def get_receipt_model():
    """Convenience function to get Receipt model"""
    return model_service.receipt_model


def get_category_model():
    """Convenience function to get Category model"""
    return model_service.category_model


def get_expense_category_model():
    """Backward compatibility function"""
    return model_service.category_model


def get_ledger_entry_model():
    """Convenience function to get LedgerEntry model"""
    return model_service.ledger_entry_model


def get_user_category_preference_model():
    """Convenience function to get UserCategoryPreference model"""
    return model_service.user_category_preference_model


def get_user_model():
    """Convenience function to get User model"""
    return model_service.user_model


def validate_all_models():
    """Convenience function to validate all models"""
    return model_service.validate_models()
