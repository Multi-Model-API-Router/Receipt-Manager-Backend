import hashlib
from typing import Any, Dict, Optional, List
from django.core.cache import cache
from django.conf import settings
import logging


logger = logging.getLogger(__name__)


class AICacheService:
    """
    Caching service for AI processing results with intelligent cache strategies
    """
    
    def __init__(self):
        ai_config = getattr(settings, 'AI_SERVICE', {})
        self.default_ttl = ai_config.get('CACHE_TTL', 3600)  # 1 hour
        self.cache_ttls = {
            'ocr_result': 86400,        # 24 hours - OCR rarely changes
            'categorization': 3600,     # 1 hour - may change with model updates
            'user_preferences': 1800,   # 30 minutes - user behavior changes
            'category_list': 7200,      # 2 hours - categories rarely change
            'processing_status': 300,   # 5 minutes - status changes frequently
            'extraction_result': 3600,  # 1 hour - extraction logic may improve
        }
    
    def get_ocr_result(self, receipt_id: str, image_hash: str) -> Optional[Dict[str, Any]]:
        """Get cached OCR result"""
        try:
            cache_key = f"ocr:{receipt_id}:{image_hash}"
            return cache.get(cache_key)
        except Exception as e:
            logger.warning(f"Failed to get OCR cache: {str(e)}")
            return None
    
    def set_ocr_result(self, receipt_id: str, image_hash: str, result: Dict[str, Any]):
        """Cache OCR result"""
        try:
            cache_key = f"ocr:{receipt_id}:{image_hash}"
            cache.set(cache_key, result, self.cache_ttls['ocr_result'])
            logger.debug(f"Cached OCR result for receipt {receipt_id}")
        except Exception as e:
            logger.warning(f"Failed to cache OCR result: {str(e)}")
    
    def get_categorization_result(self, text_hash: str, user_id: str = None) -> Optional[Dict[str, Any]]:
        """Get cached categorization result"""
        try:
            cache_key = f"categorization:{text_hash}"
            if user_id:
                cache_key += f":{user_id}"
            return cache.get(cache_key)
        except Exception as e:
            logger.warning(f"Failed to get categorization cache: {str(e)}")
            return None
    
    def set_categorization_result(self, text_hash: str, result: Dict[str, Any], user_id: str = None):
        """Cache categorization result"""
        try:
            cache_key = f"categorization:{text_hash}"
            if user_id:
                cache_key += f":{user_id}"
            cache.set(cache_key, result, self.cache_ttls['categorization'])
            logger.debug(f"Cached categorization result")
        except Exception as e:
            logger.warning(f"Failed to cache categorization result: {str(e)}")
    
    def get_user_category_preferences(self, user_id: str) -> Optional[List[Dict]]:
        """Get cached user category preferences"""
        try:
            cache_key = f"user_prefs:{user_id}"
            return cache.get(cache_key)
        except Exception as e:
            logger.warning(f"Failed to get user preferences cache: {str(e)}")
            return None
    
    def set_user_category_preferences(self, user_id: str, preferences: List[Dict]):
        """Cache user category preferences"""
        try:
            cache_key = f"user_prefs:{user_id}"
            cache.set(cache_key, preferences, self.cache_ttls['user_preferences'])
        except Exception as e:
            logger.warning(f"Failed to cache user preferences: {str(e)}")
    
    def get_available_categories(self) -> Optional[List[Dict]]:
        """Get cached category list"""
        try:
            cache_key = "categories:all"
            return cache.get(cache_key)
        except Exception as e:
            logger.warning(f"Failed to get categories cache: {str(e)}")
            return None
    
    def set_available_categories(self, categories: List[Dict]):
        """Cache category list"""
        try:
            cache_key = "categories:all"
            cache.set(cache_key, categories, self.cache_ttls['category_list'])
        except Exception as e:
            logger.warning(f"Failed to cache categories: {str(e)}")
    
    def invalidate_user_cache(self, user_id: str):
        """Invalidate all cache entries for a user"""
        try:
            cache_patterns = [
                f"user_prefs:{user_id}",
                f"categorization:*:{user_id}",
                f"processing_status:{user_id}:*"
            ]
            
            for pattern in cache_patterns:
                cache.delete_pattern(pattern)
                
        except Exception as e:
            logger.warning(f"Failed to invalidate user cache: {str(e)}")
    
    def get_processing_status(self, user_id: str, receipt_id: str) -> Optional[Dict]:
        """Get cached processing status"""
        try:
            cache_key = f"processing_status:{user_id}:{receipt_id}"
            return cache.get(cache_key)
        except Exception as e:
            logger.warning(f"Failed to get processing status cache: {str(e)}")
            return None
    
    def set_processing_status(self, user_id: str, receipt_id: str, status: Dict):
        """Cache processing status"""
        try:
            cache_key = f"processing_status:{user_id}:{receipt_id}"
            cache.set(cache_key, status, self.cache_ttls['processing_status'])
        except Exception as e:
            logger.warning(f"Failed to cache processing status: {str(e)}")
    
    def create_content_hash(self, content: str) -> str:
        """Create hash for content-based caching"""
        return hashlib.md5(content.encode()).hexdigest()
    
    def create_image_hash(self, image_data: bytes) -> str:
        """Create hash for image data"""
        return hashlib.sha256(image_data).hexdigest()[:16]
    
    def warm_cache_for_user(self, user_id: str):
        """Pre-warm cache with user-specific data"""
        try:
            # This could be called when user logs in
            from .ai_import_service import service_import
            
            # Pre-load user preferences
            try:
                category_service = service_import.category_service
                user_model = service_import.user_model
                user = user_model.objects.get(id=user_id)
                preferences = category_service.get_user_category_preferences(user, limit=10)
                self.set_user_category_preferences(user_id, preferences)
            except Exception as e:
                logger.warning(f"Failed to warm user preferences cache: {str(e)}")
            
            # Pre-load categories
            try:
                categories = service_import.category_service.get_all_categories()
                self.set_available_categories(categories)
            except Exception as e:
                logger.warning(f"Failed to warm categories cache: {str(e)}")
                
        except Exception as e:
            logger.error(f"Cache warming failed for user {user_id}: {str(e)}")


# Global cache service instance
ai_cache_service = AICacheService()
