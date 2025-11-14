from shared.utils.exceptions import (
    BaseServiceException,
    ExternalServiceException
)
from rest_framework import status


# ========================
# AI Service Base Exception
# ========================

class AIServiceException(BaseServiceException):
    """Base exception for AI service operations"""
    default_code = 'ai_service_error'
    default_detail = 'AI service operation failed'


# ========================
# OCR Processing Exceptions
# ========================

class OCRException(AIServiceException):
    """Base OCR processing exception"""
    default_code = 'ocr_error'
    default_detail = 'OCR processing failed'
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR


class OCRServiceUnavailableException(ExternalServiceException):
    """OCR service unavailable"""
    default_code = 'ocr_service_unavailable'
    default_detail = 'OCR service is temporarily unavailable'


class ImagePreprocessingException(OCRException):
    """Image preprocessing failed"""
    default_code = 'image_preprocessing_failed'
    default_detail = 'Failed to preprocess image for OCR'


class OCRExtractionException(OCRException):
    """OCR text extraction failed"""
    default_code = 'ocr_extraction_failed'
    default_detail = 'Failed to extract text from image'


class OCRLowConfidenceException(OCRException):
    """OCR confidence too low"""
    default_code = 'ocr_low_confidence'
    default_detail = 'OCR text extraction confidence is too low'


# ========================
# AI Categorization Exceptions
# ========================

class AICategorizationException(AIServiceException):
    """Base AI categorization exception"""
    default_code = 'ai_categorization_error'
    default_detail = 'AI categorization failed'
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR


class GeminiServiceException(ExternalServiceException):
    """Google Gemini service exception"""
    default_code = 'gemini_service_error'
    default_detail = 'Google Gemini service unavailable'


class CategoryPredictionException(AICategorizationException):
    """Category prediction failed"""
    default_code = 'category_prediction_failed'
    default_detail = 'Failed to predict category for receipt'


class LowConfidencePredictionException(AICategorizationException):
    """Category prediction confidence too low"""
    default_code = 'low_confidence_prediction'
    default_detail = 'AI category prediction confidence is too low'


# ========================
# Data Processing Exceptions
# ========================

class DataExtractionException(AIServiceException):
    """Data extraction from text failed"""
    default_code = 'data_extraction_failed'
    default_detail = 'Failed to extract structured data from text'
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR


class DateParsingException(DataExtractionException):
    """Date parsing failed"""
    default_code = 'date_parsing_failed'
    default_detail = 'Failed to parse date from receipt text'


class AmountParsingException(DataExtractionException):
    """Amount parsing failed"""
    default_code = 'amount_parsing_failed'
    default_detail = 'Failed to parse amount from receipt text'


class VendorExtractionException(DataExtractionException):
    """Vendor extraction failed"""
    default_code = 'vendor_extraction_failed'
    default_detail = 'Failed to extract vendor information'


# ========================
# Processing Pipeline Exceptions
# ========================

class ProcessingPipelineException(AIServiceException):
    """Processing pipeline exception"""
    default_code = 'processing_pipeline_error'
    default_detail = 'Processing pipeline failed'
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR


class ProcessingTimeoutException(ProcessingPipelineException):
    """Processing timeout"""
    default_code = 'processing_timeout'
    default_detail = 'Receipt processing timed out'
    status_code = status.HTTP_504_GATEWAY_TIMEOUT


class ProcessingJobNotFoundException(ProcessingPipelineException):
    """Processing job not found"""
    default_code = 'processing_job_not_found'
    default_detail = 'Processing job not found'
    status_code = status.HTTP_404_NOT_FOUND


class InvalidImageFormatException(AIServiceException):
    """Invalid image format"""
    default_code = 'invalid_image_format'
    default_detail = 'Image format not supported for processing'
    status_code = status.HTTP_400_BAD_REQUEST


class ImageCorruptedException(AIServiceException):
    """Corrupted image file"""
    default_code = 'image_corrupted'
    default_detail = 'Image file appears to be corrupted'
    status_code = status.HTTP_400_BAD_REQUEST


# ========================
# Model Management Exceptions
# ========================

class ModelException(AIServiceException):
    """Base model exception"""
    default_code = 'model_error'
    default_detail = 'AI model operation failed'
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR


class ModelLoadingException(ModelException):
    """Model loading failed"""
    default_code = 'model_loading_failed'
    default_detail = 'Failed to load AI model'


class ModelPredictionException(ModelException):
    """Model prediction failed"""
    default_code = 'model_prediction_failed' 
    default_detail = 'AI model prediction failed'
