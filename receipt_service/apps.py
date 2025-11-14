from django.apps import AppConfig


class ReceiptServiceConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'receipt_service'
    verbose_name = 'Receipt Management Service'
    
    def ready(self):
        """Initialize app when Django starts"""
        # Import signal handlers
        try:
            from . import signals
        except ImportError:
            pass
        
        # Initialize default categories
        self._initialize_default_categories()
    
    def _initialize_default_categories(self):
        """Initialize default expense categories"""
        try:
            from django.db import transaction
            from .models.category import Category
            
            # Check if categories already exist
            if Category.objects.exists():
                return
            
            default_categories = [
                # (name, slug, icon, color)
                ('Food & Dining', 'food-dining', '🍽️', '#28a745'),
                ('Groceries', 'groceries', '🛒', '#20c997'),
                ('Transportation', 'transportation', '🚗', '#007bff'),
                ('Gas & Fuel', 'gas-fuel', '⛽', '#6f42c1'),
                ('Healthcare', 'healthcare', '🏥', '#dc3545'),
                ('Shopping', 'shopping', '🛍️', '#fd7e14'),
                ('Utilities', 'utilities', '💡', '#ffc107'),
                ('Entertainment', 'entertainment', '🎬', '#e83e8c'),
                ('Travel', 'travel', '✈️', '#17a2b8'),
                ('Office Supplies', 'office-supplies', '📎', '#6c757d'),
                ('Insurance', 'insurance', '🛡️', '#495057'),
                ('Education', 'education', '📚', '#6f42c1'),
                ('Personal Care', 'personal-care', '💄', '#e83e8c'),
                ('Home & Garden', 'home-garden', '🏠', '#28a745'),
                ('Subscriptions', 'subscriptions', '📱', '#007bff'),
                ('Other', 'other', '📂', '#6c757d'),
            ]
            
            with transaction.atomic():
                categories = [
                    Category(name=name, slug=slug, icon=icon, color=color)
                    for name, slug, icon, color in default_categories
                ]
                Category.objects.bulk_create(categories, ignore_conflicts=True)
                
        except Exception:
            # Fail silently during app initialization
            pass
