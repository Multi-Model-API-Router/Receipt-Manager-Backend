"""
Unit tests for ai_service/services/cache_service.py
Tests AI processing result caching
"""
import pytest
import uuid
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta

from ai_service.services.cache_service import AICacheService, ai_cache_service


@pytest.fixture
def cache_service():
    """Create cache service instance"""
    with patch('ai_service.services.cache_service.settings') as mock_settings:
        mock_settings.AI_SERVICE = {'CACHE_TTL': 3600}
        return AICacheService()


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear cache before and after each test"""
    from django.core.cache import cache
    cache.clear()
    yield
    cache.clear()


@pytest.mark.unit
class TestCacheServiceInitialization:
    """Test cache service initialization"""
    
    def test_initialization_with_defaults(self, cache_service):
        """Test service initializes with default TTLs"""
        assert cache_service.default_ttl == 3600
        assert cache_service.cache_ttls['ocr_result'] == 86400
        assert cache_service.cache_ttls['categorization'] == 3600
        assert cache_service.cache_ttls['user_preferences'] == 1800
        assert cache_service.cache_ttls['category_list'] == 7200
        assert cache_service.cache_ttls['processing_status'] == 300
    
    def test_initialization_without_config(self):
        """Test initialization with missing config"""
        with patch('ai_service.services.cache_service.settings') as mock_settings:
            mock_settings.AI_SERVICE = {}
            service = AICacheService()
            
            assert service.default_ttl == 3600  # Default fallback


@pytest.mark.unit
class TestOCRResultCaching:
    """Test OCR result caching"""
    
    @patch('ai_service.services.cache_service.cache')
    def test_get_ocr_result_hit(self, mock_cache, cache_service):
        """Test getting cached OCR result"""
        receipt_id = str(uuid.uuid4())
        image_hash = 'abc123def456'
        expected_result = {'text': 'Sample receipt text', 'confidence': 0.95}
        
        mock_cache.get.return_value = expected_result
        
        result = cache_service.get_ocr_result(receipt_id, image_hash)
        
        assert result == expected_result
        mock_cache.get.assert_called_once_with(f"ocr:{receipt_id}:{image_hash}")
    
    @patch('ai_service.services.cache_service.cache')
    def test_get_ocr_result_miss(self, mock_cache, cache_service):
        """Test OCR cache miss"""
        receipt_id = str(uuid.uuid4())
        image_hash = 'abc123'
        
        mock_cache.get.return_value = None
        
        result = cache_service.get_ocr_result(receipt_id, image_hash)
        
        assert result is None
    
    @patch('ai_service.services.cache_service.cache')
    def test_set_ocr_result(self, mock_cache, cache_service):
        """Test caching OCR result"""
        receipt_id = str(uuid.uuid4())
        image_hash = 'abc123'
        result = {'text': 'Receipt text', 'confidence': 0.9}
        
        cache_service.set_ocr_result(receipt_id, image_hash, result)
        
        mock_cache.set.assert_called_once_with(
            f"ocr:{receipt_id}:{image_hash}",
            result,
            86400  # OCR TTL
        )
    
    @patch('ai_service.services.cache_service.cache')
    def test_get_ocr_result_error_handling(self, mock_cache, cache_service):
        """Test OCR cache get handles errors gracefully"""
        mock_cache.get.side_effect = Exception('Cache error')
        
        result = cache_service.get_ocr_result('receipt_id', 'hash')
        
        assert result is None  # Should return None on error
    
    @patch('ai_service.services.cache_service.cache')
    def test_set_ocr_result_error_handling(self, mock_cache, cache_service):
        """Test OCR cache set handles errors gracefully"""
        mock_cache.set.side_effect = Exception('Cache error')
        
        # Should not raise exception
        cache_service.set_ocr_result('receipt_id', 'hash', {'text': 'test'})


@pytest.mark.unit
class TestCategorizationCaching:
    """Test categorization result caching"""
    
    @patch('ai_service.services.cache_service.cache')
    def test_get_categorization_without_user(self, mock_cache, cache_service):
        """Test getting categorization without user ID"""
        text_hash = 'abc123'
        expected_result = {'category': 'Food & Dining', 'confidence': 0.85}
        
        mock_cache.get.return_value = expected_result
        
        result = cache_service.get_categorization_result(text_hash)
        
        assert result == expected_result
        mock_cache.get.assert_called_once_with(f"categorization:{text_hash}")
    
    @patch('ai_service.services.cache_service.cache')
    def test_get_categorization_with_user(self, mock_cache, cache_service):
        """Test getting categorization with user ID"""
        text_hash = 'abc123'
        user_id = str(uuid.uuid4())
        expected_result = {'category': 'Shopping', 'confidence': 0.9}
        
        mock_cache.get.return_value = expected_result
        
        result = cache_service.get_categorization_result(text_hash, user_id)
        
        assert result == expected_result
        mock_cache.get.assert_called_once_with(f"categorization:{text_hash}:{user_id}")
    
    @patch('ai_service.services.cache_service.cache')
    def test_set_categorization_without_user(self, mock_cache, cache_service):
        """Test caching categorization without user ID"""
        text_hash = 'abc123'
        result = {'category': 'Food & Dining'}
        
        cache_service.set_categorization_result(text_hash, result)
        
        mock_cache.set.assert_called_once_with(
            f"categorization:{text_hash}",
            result,
            3600  # Categorization TTL
        )
    
    @patch('ai_service.services.cache_service.cache')
    def test_set_categorization_with_user(self, mock_cache, cache_service):
        """Test caching categorization with user ID"""
        text_hash = 'abc123'
        user_id = str(uuid.uuid4())
        result = {'category': 'Shopping'}
        
        cache_service.set_categorization_result(text_hash, result, user_id)
        
        mock_cache.set.assert_called_once_with(
            f"categorization:{text_hash}:{user_id}",
            result,
            3600
        )


@pytest.mark.unit
class TestUserPreferencesCaching:
    """Test user preferences caching"""
    
    @patch('ai_service.services.cache_service.cache')
    def test_get_user_preferences_hit(self, mock_cache, cache_service):
        """Test getting cached user preferences"""
        user_id = str(uuid.uuid4())
        expected_prefs = [
            {'category': 'Food & Dining', 'usage_count': 10},
            {'category': 'Transportation', 'usage_count': 5}
        ]
        
        mock_cache.get.return_value = expected_prefs
        
        result = cache_service.get_user_category_preferences(user_id)
        
        assert result == expected_prefs
        mock_cache.get.assert_called_once_with(f"user_prefs:{user_id}")
    
    @patch('ai_service.services.cache_service.cache')
    def test_set_user_preferences(self, mock_cache, cache_service):
        """Test caching user preferences"""
        user_id = str(uuid.uuid4())
        preferences = [{'category': 'Food & Dining'}]
        
        cache_service.set_user_category_preferences(user_id, preferences)
        
        mock_cache.set.assert_called_once_with(
            f"user_prefs:{user_id}",
            preferences,
            1800  # User preferences TTL
        )


@pytest.mark.unit
class TestCategoriesCaching:
    """Test categories list caching"""
    
    @patch('ai_service.services.cache_service.cache')
    def test_get_categories_hit(self, mock_cache, cache_service):
        """Test getting cached categories"""
        expected_categories = [
            {'id': str(uuid.uuid4()), 'name': 'Food & Dining'},
            {'id': str(uuid.uuid4()), 'name': 'Transportation'}
        ]
        
        mock_cache.get.return_value = expected_categories
        
        result = cache_service.get_available_categories()
        
        assert result == expected_categories
        mock_cache.get.assert_called_once_with("categories:all")
    
    @patch('ai_service.services.cache_service.cache')
    def test_set_categories(self, mock_cache, cache_service):
        """Test caching categories"""
        categories = [{'id': str(uuid.uuid4()), 'name': 'Food & Dining'}]
        
        cache_service.set_available_categories(categories)
        
        mock_cache.set.assert_called_once_with(
            "categories:all",
            categories,
            7200  # Category list TTL
        )


@pytest.mark.unit
class TestProcessingStatusCaching:
    """Test processing status caching"""
    
    @patch('ai_service.services.cache_service.cache')
    def test_get_processing_status(self, mock_cache, cache_service):
        """Test getting cached processing status"""
        user_id = str(uuid.uuid4())
        receipt_id = str(uuid.uuid4())
        expected_status = {'stage': 'ocr', 'progress': 50}
        
        mock_cache.get.return_value = expected_status
        
        result = cache_service.get_processing_status(user_id, receipt_id)
        
        assert result == expected_status
        mock_cache.get.assert_called_once_with(f"processing_status:{user_id}:{receipt_id}")
    
    @patch('ai_service.services.cache_service.cache')
    def test_set_processing_status(self, mock_cache, cache_service):
        """Test caching processing status"""
        user_id = str(uuid.uuid4())
        receipt_id = str(uuid.uuid4())
        status = {'stage': 'categorization', 'progress': 75}
        
        cache_service.set_processing_status(user_id, receipt_id, status)
        
        mock_cache.set.assert_called_once_with(
            f"processing_status:{user_id}:{receipt_id}",
            status,
            300  # Processing status TTL
        )


@pytest.mark.unit
class TestCacheInvalidation:
    """Test cache invalidation"""
    
    @patch('ai_service.services.cache_service.cache')
    def test_invalidate_user_cache(self, mock_cache, cache_service):
        """Test invalidating all user cache"""
        user_id = str(uuid.uuid4())
        
        cache_service.invalidate_user_cache(user_id)
        
        # Should attempt to delete multiple patterns
        assert mock_cache.delete_pattern.call_count == 3
    
    @patch('ai_service.services.cache_service.cache')
    def test_invalidate_user_cache_error_handling(self, mock_cache, cache_service):
        """Test cache invalidation handles errors gracefully"""
        mock_cache.delete_pattern.side_effect = Exception('Delete error')
        
        # Should not raise exception
        cache_service.invalidate_user_cache(str(uuid.uuid4()))


@pytest.mark.unit
class TestHashGeneration:
    """Test hash generation methods"""
    
    def test_create_content_hash(self, cache_service):
        """Test content hash generation"""
        content = "Sample receipt text"
        
        hash1 = cache_service.create_content_hash(content)
        hash2 = cache_service.create_content_hash(content)
        
        assert hash1 == hash2  # Same content = same hash
        assert len(hash1) == 32  # MD5 hex length
    
    def test_create_content_hash_different_content(self, cache_service):
        """Test different content produces different hashes"""
        hash1 = cache_service.create_content_hash("content1")
        hash2 = cache_service.create_content_hash("content2")
        
        assert hash1 != hash2
    
    def test_create_image_hash(self, cache_service):
        """Test image hash generation"""
        image_data = b"fake image bytes"
        
        hash1 = cache_service.create_image_hash(image_data)
        hash2 = cache_service.create_image_hash(image_data)
        
        assert hash1 == hash2
        assert len(hash1) == 16  # SHA256 truncated
    
    def test_create_image_hash_different_data(self, cache_service):
        """Test different image data produces different hashes"""
        hash1 = cache_service.create_image_hash(b"data1")
        hash2 = cache_service.create_image_hash(b"data2")
        
        assert hash1 != hash2


@pytest.mark.unit
class TestCacheWarming:
    """Test cache warming functionality"""
    
    def test_warm_cache_for_user_success(self, cache_service):
        """Test successful cache warming"""
        user_id = str(uuid.uuid4())
        
        # Mock the ServiceImportService
        mock_service_import = Mock()
        
        mock_user = Mock()
        mock_user_model = Mock()
        mock_user_model.objects.get.return_value = mock_user
        
        mock_category_service = Mock()
        mock_category_service.get_user_category_preferences.return_value = [{'category': 'Food'}]
        mock_category_service.get_all_categories.return_value = [{'id': str(uuid.uuid4())}]
        
        mock_service_import.user_model = mock_user_model
        mock_service_import.category_service = mock_category_service
        
        # Mock the import from ai_import_service module
        with patch('ai_service.services.ai_import_service.service_import', mock_service_import):
            with patch.object(cache_service, 'set_user_category_preferences'):
                with patch.object(cache_service, 'set_available_categories'):
                    cache_service.warm_cache_for_user(user_id)
    
    def test_warm_cache_handles_errors(self, cache_service):
        """Test cache warming handles errors gracefully"""
        user_id = str(uuid.uuid4())
        
        # Mock import to raise error
        mock_service_import = Mock()
        mock_service_import.user_model.objects.get.side_effect = Exception('User not found')
        
        with patch('ai_service.services.ai_import_service.service_import', mock_service_import):
            # Should not raise exception
            cache_service.warm_cache_for_user(user_id)
    
    def test_warm_cache_category_service_error(self, cache_service):
        """Test cache warming handles category service errors"""
        user_id = str(uuid.uuid4())
        
        mock_service_import = Mock()
        mock_user_model = Mock()
        mock_user_model.objects.get.return_value = Mock()
        
        mock_category_service = Mock()
        mock_category_service.get_user_category_preferences.side_effect = Exception('Category error')
        
        mock_service_import.user_model = mock_user_model
        mock_service_import.category_service = mock_category_service
        
        with patch('ai_service.services.ai_import_service.service_import', mock_service_import):
            # Should not raise exception
            cache_service.warm_cache_for_user(user_id)

@pytest.mark.unit
class TestGlobalInstance:
    """Test global ai_cache_service instance"""
    
    def test_global_instance_exists(self):
        """Test global instance is available"""
        assert ai_cache_service is not None
        assert isinstance(ai_cache_service, AICacheService)
