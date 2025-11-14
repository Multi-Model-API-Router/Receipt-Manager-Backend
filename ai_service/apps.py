from django.apps import AppConfig


class AiServiceConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'ai_service'
    verbose_name = 'AI Processing Service'
    
    def ready(self):
        """Initialize app when Django starts"""
        # Import signal handlers
        try:
            from . import signals
        except ImportError:
            pass
        
        # Initialize AI service configurations
        self._initialize_ai_configurations()
    
    def _initialize_ai_configurations(self):
        """Initialize AI service configurations"""
        try:
            # Setup default OCR configurations
            from django.conf import settings
            
            # Ensure required AI settings exist
            ai_settings = getattr(settings, 'AI_SERVICE', {})
            
            # Set defaults if not configured
            defaults = {
                'OCR_ENGINE': 'google_vision',
                'CATEGORIZATION_MODEL': 'gemini-2.5-flash',
                'MAX_PROCESSING_TIME': 300,  # 5 minutes
                'MAX_RETRIES': 3,
                'CONFIDENCE_THRESHOLD_OCR': 0.7,
                'CONFIDENCE_THRESHOLD_CATEGORIZATION': 0.6,
            }
            
            for key, default_value in defaults.items():
                if key not in ai_settings:
                    ai_settings[key] = default_value
            
            # Update settings
            settings.AI_SERVICE = ai_settings
            
        except Exception:
            # Fail silently during app initialization
            pass
