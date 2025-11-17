"""
Unit tests for ai_service/services/ai_model_service.py
Tests lazy loading of AI service models
"""
import pytest
from unittest.mock import Mock, patch, MagicMock

from ai_service.services.ai_model_service import ModelImportService, model_service


@pytest.mark.unit
class TestModelImportServiceInitialization:
    """Test ModelImportService initialization"""
    
    def test_initialization(self):
        """Test service initializes with None values"""
        service = ModelImportService()
        
        assert service._processing_job_model is None
        assert service._ocr_result_model is None
        assert service._category_prediction_model is None
        assert service._extracted_data_model is None


@pytest.mark.unit
class TestProcessingJobModel:
    """Test ProcessingJob model loading"""
    
    @patch('ai_service.services.ai_model_service.apps')
    def test_load_processing_job_model_success(self, mock_apps):
        """Test successful ProcessingJob model loading"""
        mock_model = Mock()
        mock_apps.get_model.return_value = mock_model
        
        service = ModelImportService()
        model = service.processing_job_model
        
        assert model == mock_model
        mock_apps.get_model.assert_called_once_with('ai_service', 'ProcessingJob')
    
    @patch('ai_service.services.ai_model_service.apps')
    def test_load_processing_job_model_caching(self, mock_apps):
        """Test model is cached after first load"""
        mock_model = Mock()
        mock_apps.get_model.return_value = mock_model
        
        service = ModelImportService()
        
        # First access
        model1 = service.processing_job_model
        # Second access
        model2 = service.processing_job_model
        
        assert model1 == model2
        # Should only call get_model once due to caching
        assert mock_apps.get_model.call_count == 1
    
    @patch('ai_service.services.ai_model_service.apps')
    def test_load_processing_job_model_failure(self, mock_apps):
        """Test model loading handles errors"""
        mock_apps.get_model.side_effect = Exception('Model not found')
        
        service = ModelImportService()
        
        with pytest.raises(ImportError) as exc_info:
            _ = service.processing_job_model
        
        assert 'Could not import ProcessingJob model' in str(exc_info.value)


@pytest.mark.unit
class TestOCRResultModel:
    """Test OCRResult model loading"""
    
    @patch('ai_service.services.ai_model_service.apps')
    def test_load_ocr_result_model_success(self, mock_apps):
        """Test successful OCRResult model loading"""
        mock_model = Mock()
        mock_apps.get_model.return_value = mock_model
        
        service = ModelImportService()
        model = service.ocr_result_model
        
        assert model == mock_model
        mock_apps.get_model.assert_called_once_with('ai_service', 'OCRResult')
    
    @patch('ai_service.services.ai_model_service.apps')
    def test_load_ocr_result_model_caching(self, mock_apps):
        """Test OCRResult model is cached"""
        mock_model = Mock()
        mock_apps.get_model.return_value = mock_model
        
        service = ModelImportService()
        
        model1 = service.ocr_result_model
        model2 = service.ocr_result_model
        
        assert model1 == model2
        assert mock_apps.get_model.call_count == 1
    
    @patch('ai_service.services.ai_model_service.apps')
    def test_load_ocr_result_model_failure(self, mock_apps):
        """Test OCRResult model loading handles errors"""
        mock_apps.get_model.side_effect = Exception('Model not found')
        
        service = ModelImportService()
        
        with pytest.raises(ImportError) as exc_info:
            _ = service.ocr_result_model
        
        assert 'Could not import OCRResult model' in str(exc_info.value)


@pytest.mark.unit
class TestCategoryPredictionModel:
    """Test CategoryPrediction model loading"""
    
    @patch('ai_service.services.ai_model_service.apps')
    def test_load_category_prediction_model_success(self, mock_apps):
        """Test successful CategoryPrediction model loading"""
        mock_model = Mock()
        mock_apps.get_model.return_value = mock_model
        
        service = ModelImportService()
        model = service.category_prediction_model
        
        assert model == mock_model
        mock_apps.get_model.assert_called_once_with('ai_service', 'CategoryPrediction')
    
    @patch('ai_service.services.ai_model_service.apps')
    def test_load_category_prediction_model_caching(self, mock_apps):
        """Test CategoryPrediction model is cached"""
        mock_model = Mock()
        mock_apps.get_model.return_value = mock_model
        
        service = ModelImportService()
        
        model1 = service.category_prediction_model
        model2 = service.category_prediction_model
        
        assert model1 == model2
        assert mock_apps.get_model.call_count == 1
    
    @patch('ai_service.services.ai_model_service.apps')
    def test_load_category_prediction_model_failure(self, mock_apps):
        """Test CategoryPrediction model loading handles errors"""
        mock_apps.get_model.side_effect = Exception('Model not found')
        
        service = ModelImportService()
        
        with pytest.raises(ImportError) as exc_info:
            _ = service.category_prediction_model
        
        assert 'Could not import CategoryPrediction model' in str(exc_info.value)


@pytest.mark.unit
class TestExtractedDataModel:
    """Test ExtractedData model loading"""
    
    @patch('ai_service.services.ai_model_service.apps')
    def test_load_extracted_data_model_success(self, mock_apps):
        """Test successful ExtractedData model loading"""
        mock_model = Mock()
        mock_apps.get_model.return_value = mock_model
        
        service = ModelImportService()
        model = service.extracted_data_model
        
        assert model == mock_model
        mock_apps.get_model.assert_called_once_with('ai_service', 'ExtractedData')
    
    @patch('ai_service.services.ai_model_service.apps')
    def test_load_extracted_data_model_caching(self, mock_apps):
        """Test ExtractedData model is cached"""
        mock_model = Mock()
        mock_apps.get_model.return_value = mock_model
        
        service = ModelImportService()
        
        model1 = service.extracted_data_model
        model2 = service.extracted_data_model
        
        assert model1 == model2
        assert mock_apps.get_model.call_count == 1
    
    @patch('ai_service.services.ai_model_service.apps')
    def test_load_extracted_data_model_failure(self, mock_apps):
        """Test ExtractedData model loading handles errors"""
        mock_apps.get_model.side_effect = Exception('Model not found')
        
        service = ModelImportService()
        
        with pytest.raises(ImportError) as exc_info:
            _ = service.extracted_data_model
        
        assert 'Could not import ExtractedData model' in str(exc_info.value)


@pytest.mark.unit
class TestMultipleModelLoading:
    """Test loading multiple models"""
    
    @patch('ai_service.services.ai_model_service.apps')
    def test_load_all_models_success(self, mock_apps):
        """Test loading all models successfully"""
        mock_apps.get_model.return_value = Mock()
        
        service = ModelImportService()
        
        # Load all models
        processing_job = service.processing_job_model
        ocr_result = service.ocr_result_model
        category_prediction = service.category_prediction_model
        extracted_data = service.extracted_data_model
        
        assert processing_job is not None
        assert ocr_result is not None
        assert category_prediction is not None
        assert extracted_data is not None
        
        # Should have called get_model 4 times
        assert mock_apps.get_model.call_count == 4
    
    @patch('ai_service.services.ai_model_service.apps')
    def test_independent_model_caching(self, mock_apps):
        """Test each model is cached independently"""
        mock_apps.get_model.return_value = Mock()
        
        service = ModelImportService()
        
        # Access models multiple times
        _ = service.processing_job_model
        _ = service.processing_job_model
        _ = service.ocr_result_model
        _ = service.ocr_result_model
        
        # Should only call get_model twice (once per unique model)
        assert mock_apps.get_model.call_count == 2


@pytest.mark.unit
class TestGlobalInstance:
    """Test global model_service instance"""
    
    def test_global_instance_exists(self):
        """Test global model_service instance is available"""
        assert model_service is not None
        assert isinstance(model_service, ModelImportService)
    
    def test_global_instance_is_singleton(self):
        """Test global instance behaves like singleton"""
        from ai_service.services.ai_model_service import model_service as service1
        from ai_service.services.ai_model_service import model_service as service2
        
        assert service1 is service2
