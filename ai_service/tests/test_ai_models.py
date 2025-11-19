"""
Unit tests for ai_service model methods and properties
Tests ProcessingJob, OCRResult, CategoryPrediction, ExtractedData models
Uses Django's database for model validation
"""
import pytest
import uuid
from decimal import Decimal
from datetime import date, timedelta
from django.utils import timezone
from django.contrib.auth import get_user_model
from ai_service.models.processing import (
    ProcessingJob,
    OCRResult,
    CategoryPrediction,
    ExtractedData
)

User = get_user_model()


@pytest.fixture
def sample_processing_job(db):
    """Create sample processing job"""
    return ProcessingJob.objects.create(
        receipt_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        status='queued'
    )


# =====================================================
# ProcessingJob Model Tests
# =====================================================

@pytest.mark.django_db
class TestProcessingJobModel:
    """Test ProcessingJob model"""
    
    def test_processing_job_creation(self, sample_processing_job):
        """Test processing job creation"""
        assert sample_processing_job.status == 'queued'
        assert sample_processing_job.current_stage == 'ocr'
        assert sample_processing_job.progress_percentage == 0
        assert sample_processing_job.retry_count == 0
    
    def test_processing_job_id_is_uuid(self, sample_processing_job):
        """Test processing job ID is UUID"""
        assert isinstance(sample_processing_job.id, uuid.UUID)
    
    def test_processing_job_str_representation(self, sample_processing_job):
        """Test processing job string representation"""
        expected = f"ProcessingJob {sample_processing_job.id} - queued"
        assert str(sample_processing_job) == expected
    
    def test_processing_job_meta_table_name(self):
        """Test correct database table name"""
        assert ProcessingJob._meta.db_table == 'ai_processing_jobs'
    
    def test_processing_job_meta_ordering(self):
        """Test default ordering"""
        assert ProcessingJob._meta.ordering == ['-created_at']
    
    def test_max_retries_default(self, sample_processing_job):
        """Test max_retries defaults to 3"""
        assert sample_processing_job.max_retries == 3
    
    def test_error_details_default_dict(self, sample_processing_job):
        """Test error_details defaults to empty dict"""
        assert sample_processing_job.error_details == {}


# =====================================================
# OCRResult Model Tests
# =====================================================

@pytest.mark.django_db
class TestOCRResultModel:
    """Test OCRResult model methods"""
    
    def test_ocr_result_creation(self, sample_processing_job):
        """Test OCR result creation"""
        ocr = OCRResult.objects.create(
            processing_job=sample_processing_job,
            extracted_text="Sample receipt text",
            confidence_score=0.95,
            ocr_engine='google_vision',
            processing_time_seconds=2.5
        )
        
        assert ocr.extracted_text == "Sample receipt text"
        assert ocr.confidence_score == 0.95
        assert ocr.language_detected == 'en'
    
    def test_ocr_result_id_is_uuid(self, sample_processing_job):
        """Test OCR result ID is UUID"""
        ocr = OCRResult.objects.create(
            processing_job=sample_processing_job,
            extracted_text="Text",
            confidence_score=0.8,
            processing_time_seconds=1.0
        )
        
        assert isinstance(ocr.id, uuid.UUID)
    
    def test_ocr_result_str_representation(self, sample_processing_job):
        """Test OCR result string representation"""
        ocr = OCRResult.objects.create(
            processing_job=sample_processing_job,
            extracted_text="Text",
            confidence_score=0.85,
            processing_time_seconds=1.5
        )
        
        expected = f"OCRResult for job {sample_processing_job.id} - 0.85"
        assert str(ocr) == expected
    
    def test_is_high_confidence_true(self, sample_processing_job):
        """Test is_high_confidence returns True"""
        ocr = OCRResult.objects.create(
            processing_job=sample_processing_job,
            extracted_text="Text",
            confidence_score=0.8,
            processing_time_seconds=1.0
        )
        
        assert ocr.is_high_confidence is True
    
    def test_is_high_confidence_false(self, sample_processing_job):
        """Test is_high_confidence returns False"""
        ocr = OCRResult.objects.create(
            processing_job=sample_processing_job,
            extracted_text="Text",
            confidence_score=0.6,
            processing_time_seconds=1.0
        )
        
        assert ocr.is_high_confidence is False
    
    def test_text_preview_short_text(self, sample_processing_job):
        """Test text_preview with short text"""
        ocr = OCRResult.objects.create(
            processing_job=sample_processing_job,
            extracted_text="Short text",
            confidence_score=0.9,
            processing_time_seconds=1.0
        )
        
        assert ocr.text_preview == "Short text"
    
    def test_text_preview_long_text(self, sample_processing_job):
        """Test text_preview with long text"""
        long_text = "A" * 150
        ocr = OCRResult.objects.create(
            processing_job=sample_processing_job,
            extracted_text=long_text,
            confidence_score=0.9,
            processing_time_seconds=1.0
        )
        
        assert len(ocr.text_preview) == 103  # 100 chars + "..."
        assert ocr.text_preview.endswith("...")
    
    def test_ocr_result_meta_table_name(self):
        """Test correct database table name"""
        assert OCRResult._meta.db_table == 'ai_ocr_results'


# =====================================================
# CategoryPrediction Model Tests
# =====================================================

@pytest.mark.django_db
class TestCategoryPredictionModel:
    """Test CategoryPrediction model methods"""
    
    def test_category_prediction_creation(self, sample_processing_job):
        """Test category prediction creation"""
        pred = CategoryPrediction.objects.create(
            processing_job=sample_processing_job,
            predicted_category_id=uuid.uuid4(),
            confidence_score=0.9,
            reasoning="Detected food-related keywords",
            processing_time_seconds=1.2
        )
        
        assert pred.confidence_score == 0.9
        assert pred.model_version == 'gemini-2.5-flash'
    
    def test_category_prediction_id_is_uuid(self, sample_processing_job):
        """Test category prediction ID is UUID"""
        pred = CategoryPrediction.objects.create(
            processing_job=sample_processing_job,
            predicted_category_id=uuid.uuid4(),
            confidence_score=0.8,
            reasoning="Test",
            processing_time_seconds=1.0
        )
        
        assert isinstance(pred.id, uuid.UUID)
    
    def test_is_high_confidence_true(self, sample_processing_job):
        """Test is_high_confidence returns True"""
        pred = CategoryPrediction.objects.create(
            processing_job=sample_processing_job,
            predicted_category_id=uuid.uuid4(),
            confidence_score=0.7,
            reasoning="Test",
            processing_time_seconds=1.0
        )
        
        assert pred.is_high_confidence is True
    
    def test_is_high_confidence_false(self, sample_processing_job):
        """Test is_high_confidence returns False"""
        pred = CategoryPrediction.objects.create(
            processing_job=sample_processing_job,
            predicted_category_id=uuid.uuid4(),
            confidence_score=0.5,
            reasoning="Test",
            processing_time_seconds=1.0
        )
        
        assert pred.is_high_confidence is False
    
    def test_get_top_alternatives(self, sample_processing_job):
        """Test get_top_alternatives method"""
        alternatives = [
            {'category_id': str(uuid.uuid4()), 'confidence': 0.3},
            {'category_id': str(uuid.uuid4()), 'confidence': 0.5},
            {'category_id': str(uuid.uuid4()), 'confidence': 0.2},
            {'category_id': str(uuid.uuid4()), 'confidence': 0.4},
        ]
        
        pred = CategoryPrediction.objects.create(
            processing_job=sample_processing_job,
            predicted_category_id=uuid.uuid4(),
            confidence_score=0.8,
            reasoning="Test",
            alternative_predictions=alternatives,
            processing_time_seconds=1.0
        )
        
        top = pred.get_top_alternatives(limit=2)
        assert len(top) == 2
        assert top[0]['confidence'] == 0.5
        assert top[1]['confidence'] == 0.4
    
    def test_category_prediction_meta_table_name(self):
        """Test correct database table name"""
        assert CategoryPrediction._meta.db_table == 'ai_category_predictions'


# =====================================================
# ExtractedData Model Tests
# =====================================================

@pytest.mark.django_db
class TestExtractedDataModel:
    """Test ExtractedData model methods"""
    
    def test_extracted_data_creation(self, sample_processing_job):
        """Test extracted data creation"""
        data = ExtractedData.objects.create(
            processing_job=sample_processing_job,
            vendor_name='Test Vendor',
            receipt_date=date.today(),
            total_amount=Decimal('99.99'),
            currency='USD',
            confidence_scores={'total_amount': 0.9, 'vendor_name': 0.8},
            processing_time_seconds=2.0
        )
        
        assert data.vendor_name == 'Test Vendor'
        assert data.total_amount == Decimal('99.99')
    
    def test_extracted_data_id_is_uuid(self, sample_processing_job):
        """Test extracted data ID is UUID"""
        data = ExtractedData.objects.create(
            processing_job=sample_processing_job,
            processing_time_seconds=1.0
        )
        
        assert isinstance(data.id, uuid.UUID)
    
    def test_has_high_confidence_amount_true(self, sample_processing_job):
        """Test has_high_confidence_amount returns True"""
        data = ExtractedData.objects.create(
            processing_job=sample_processing_job,
            total_amount=Decimal('50.00'),
            confidence_scores={'total_amount': 0.9},
            processing_time_seconds=1.0
        )
        
        assert data.has_high_confidence_amount is True
    
    def test_has_high_confidence_amount_false(self, sample_processing_job):
        """Test has_high_confidence_amount returns False"""
        data = ExtractedData.objects.create(
            processing_job=sample_processing_job,
            total_amount=Decimal('50.00'),
            confidence_scores={'total_amount': 0.6},
            processing_time_seconds=1.0
        )
        
        assert data.has_high_confidence_amount is False
    
    def test_has_high_confidence_vendor_true(self, sample_processing_job):
        """Test has_high_confidence_vendor returns True"""
        data = ExtractedData.objects.create(
            processing_job=sample_processing_job,
            vendor_name='Test',
            confidence_scores={'vendor_name': 0.8},
            processing_time_seconds=1.0
        )
        
        assert data.has_high_confidence_vendor is True
    
    def test_has_high_confidence_vendor_false(self, sample_processing_job):
        """Test has_high_confidence_vendor returns False"""
        data = ExtractedData.objects.create(
            processing_job=sample_processing_job,
            vendor_name='Test',
            confidence_scores={'vendor_name': 0.5},
            processing_time_seconds=1.0
        )
        
        assert data.has_high_confidence_vendor is False
    
    def test_get_summary(self, sample_processing_job):
        """Test get_summary method"""
        data = ExtractedData.objects.create(
            processing_job=sample_processing_job,
            vendor_name='Amazon',
            receipt_date=date.today(),
            total_amount=Decimal('149.99'),
            currency='USD',
            line_items=[{'item': 'Product 1'}, {'item': 'Product 2'}],
            confidence_scores={'total_amount': 0.9},
            processing_time_seconds=1.5
        )
        
        summary = data.get_summary()
        assert summary['vendor'] == 'Amazon'
        assert summary['amount'] == 149.99
        assert summary['items_count'] == 2
    
    def test_extracted_data_meta_table_name(self):
        """Test correct database table name"""
        assert ExtractedData._meta.db_table == 'ai_extracted_data'
