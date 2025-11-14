from django.apps import apps
from typing import TYPE_CHECKING
import logging


logger = logging.getLogger(__name__)


if TYPE_CHECKING:
    from ..models.processing import ProcessingJob, OCRResult, CategoryPrediction, ExtractedData


class ModelImportService:
    """Lazy loading service for AI service models"""
    
    def __init__(self):
        self._processing_job_model = None
        self._ocr_result_model = None
        self._category_prediction_model = None
        self._extracted_data_model = None
    
    @property
    def processing_job_model(self):
        """Lazy load ProcessingJob model"""
        if self._processing_job_model is None:
            try:
                self._processing_job_model = apps.get_model('ai_service', 'ProcessingJob')
                logger.debug("Loaded ProcessingJob model")
            except Exception as e:
                logger.error(f"Failed to load ProcessingJob model: {str(e)}")
                raise ImportError("Could not import ProcessingJob model") from e
        return self._processing_job_model
    
    @property
    def ocr_result_model(self):
        """Lazy load OCRResult model"""
        if self._ocr_result_model is None:
            try:
                self._ocr_result_model = apps.get_model('ai_service', 'OCRResult')
                logger.debug("Loaded OCRResult model")
            except Exception as e:
                logger.error(f"Failed to load OCRResult model: {str(e)}")
                raise ImportError("Could not import OCRResult model") from e
        return self._ocr_result_model
    
    @property
    def category_prediction_model(self):
        """Lazy load CategoryPrediction model"""
        if self._category_prediction_model is None:
            try:
                self._category_prediction_model = apps.get_model('ai_service', 'CategoryPrediction')
                logger.debug("Loaded CategoryPrediction model")
            except Exception as e:
                logger.error(f"Failed to load CategoryPrediction model: {str(e)}")
                raise ImportError("Could not import CategoryPrediction model") from e
        return self._category_prediction_model
    
    @property
    def extracted_data_model(self):
        """Lazy load ExtractedData model"""
        if self._extracted_data_model is None:
            try:
                self._extracted_data_model = apps.get_model('ai_service', 'ExtractedData')
                logger.debug("Loaded ExtractedData model")
            except Exception as e:
                logger.error(f"Failed to load ExtractedData model: {str(e)}")
                raise ImportError("Could not import ExtractedData model") from e
        return self._extracted_data_model


# Global instance
model_service = ModelImportService()
