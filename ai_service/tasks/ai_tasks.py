# ai_service/tasks/ai_tasks.py

from celery import shared_task
from typing import Dict
from django.utils import timezone
import logging

from ..services.processing_pipeline import ProcessingPipelineService
from ..utils.exceptions import (
    ProcessingPipelineException,
    ImageCorruptedException,
    InvalidImageFormatException,
)

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=25)
def process_receipt_ai_task(self, receipt_id: str, user_id: str, storage_path: str) -> Dict[str, any]:
    """
    Async task for AI receipt processing
    
    Args:
        receipt_id: Receipt identifier
        user_id: User identifier  
        storage_path: Path in storage to read file
        
    Returns:
        Dict with processing results
    """
    try:
        logger.info(f"[Task {self.request.id}] Starting AI processing for receipt {receipt_id}")
        
        # Update receipt status to processing
        _update_receipt_status_only(receipt_id, 'processing')
        
        # Load image data from storage
        image_data = _load_image_from_storage(storage_path)
        
        # Process through pipeline (stores all results in AI models)
        pipeline = ProcessingPipelineService()
        result = pipeline.process_receipt(receipt_id, user_id, image_data)
        
        # Update receipt status to processed (that's all!)
        _update_receipt_status_only(receipt_id, 'processed')
        
        logger.info(
            f"[Task {self.request.id}] AI processing completed for receipt {receipt_id} "
            f"in {result.get('processing_time_seconds', 0):.2f}s"
        )
        
        return {
            'status': 'success',
            'receipt_id': receipt_id,
            'processing_time_seconds': result.get('processing_time_seconds', 0),
        }
        
    except (ImageCorruptedException, InvalidImageFormatException) as e:
        # Don't retry for invalid images
        logger.error(f"Invalid image for receipt {receipt_id}: {str(e)}")
        _update_receipt_status_only(receipt_id, 'failed')
        raise
        
    except ProcessingPipelineException as e:
        # Pipeline exception - may be retryable
        logger.error(f"Pipeline error for receipt {receipt_id}: {str(e)}")
        
        try:
            # Exponential backoff
            countdown = 60 * (2 ** self.request.retries)
            self.retry(countdown=countdown, exc=e)
        except self.MaxRetriesExceededError:
            logger.error(f"Max retries exceeded for receipt {receipt_id}")
            _update_receipt_status_only(receipt_id, 'failed')
            raise ProcessingPipelineException(
                detail="AI processing failed after maximum retries",
                context={
                    'receipt_id': receipt_id,
                    'retries': self.request.retries,
                    'error': str(e)
                }
            )
            
    except Exception as e:
        # Unexpected error - retry with backoff
        logger.error(
            f"Unexpected error processing receipt {receipt_id}: {str(e)}", 
            exc_info=True
        )
        
        try:
            countdown = 60 * (2 ** self.request.retries)
            self.retry(countdown=countdown, exc=e)
        except self.MaxRetriesExceededError:
            logger.error(f"Max retries exceeded for receipt {receipt_id}")
            _update_receipt_status_only(receipt_id, 'failed')
            raise


@shared_task(bind=True, max_retries=2)
def batch_process_receipts_task(self, receipt_batch: list) -> Dict[str, any]:
    """
    Batch process multiple receipts
    Useful for processing uploaded files in bulk
    """
    results = []
    
    for receipt_data in receipt_batch:
        try:
            result = process_receipt_ai_task.apply_async(
                args=[
                    receipt_data['receipt_id'],
                    receipt_data['user_id'],
                    receipt_data['storage_path']
                ],
                countdown=5  # Small delay to avoid overwhelming queue
            )
            
            results.append({
                'receipt_id': receipt_data['receipt_id'],
                'task_id': result.id,
                'status': 'queued'
            })
            
        except Exception as e:
            logger.error(
                f"Failed to queue receipt {receipt_data['receipt_id']}: {str(e)}",
                exc_info=True
            )
            results.append({
                'receipt_id': receipt_data['receipt_id'],
                'status': 'failed',
                'error': str(e)
            })
    
    return {
        'batch_size': len(receipt_batch),
        'queued': len([r for r in results if r['status'] == 'queued']),
        'failed': len([r for r in results if r['status'] == 'failed']),
        'results': results
    }


@shared_task
def cleanup_expired_processing_jobs() -> Dict[str, any]:
    """
    Clean up old processing jobs and their related data
    Scheduled task - runs daily
    """
    try:
        from ..services.ai_model_service import model_service
        from datetime import timedelta
        
        # Keep for 30 days (configurable)
        cutoff_date = timezone.now() - timedelta(days=30)
        
        # Find old completed/failed jobs
        expired_jobs = model_service.processing_job_model.objects.filter(
            created_at__lt=cutoff_date,
            status__in=['completed', 'failed', 'cancelled']
        )
        
        deleted_count = 0
        error_count = 0
        
        for job in expired_jobs:
            try:
                # Django will cascade delete related OCRResult, ExtractedData, CategoryPrediction
                # if models have CASCADE on_delete
                job.delete()
                deleted_count += 1
                
            except Exception as e:
                logger.error(f"Failed to delete job {job.id}: {str(e)}")
                error_count += 1
        
        logger.info(
            f"Cleanup completed: {deleted_count} jobs deleted, {error_count} errors"
        )
        
        return {
            'deleted_jobs': deleted_count,
            'errors': error_count,
            'cutoff_date': cutoff_date.isoformat()
        }
        
    except Exception as e:
        logger.error(f"Cleanup task failed: {str(e)}", exc_info=True)
        return {'error': str(e)}


@shared_task
def health_check_ai_services() -> Dict[str, any]:
    """
    Periodic health check for AI services
    Scheduled task - runs every 5 minutes
    """
    try:
        health_status = {
            'timestamp': timezone.now().isoformat(),
            'services': {}
        }
        
        # Check OCR service (Tesseract)
        try:
            from ..services.ocr_service import ocr_service
            import pytesseract
            
            version = pytesseract.get_tesseract_version()
            health_status['services']['ocr'] = {
                'status': 'healthy',
                'version': str(version),
                'config': ocr_service.tesseract_config
            }
        except Exception as e:
            logger.error(f"OCR health check failed: {str(e)}")
            health_status['services']['ocr'] = {
                'status': 'unhealthy',
                'error': str(e)
            }
        
        # Check Gemini service
        try:
            from ..services.gemini_extraction_service import gemini_extractor
            
            if gemini_extractor._gemini_client:
                health_status['services']['gemini'] = {
                    'status': 'healthy',
                    'model': gemini_extractor.model_name,
                    'timeout': gemini_extractor.timeout
                }
            else:
                health_status['services']['gemini'] = {
                    'status': 'unhealthy',
                    'error': gemini_extractor._initialization_error or 'Client not initialized'
                }
        except Exception as e:
            logger.error(f"Gemini health check failed: {str(e)}")
            health_status['services']['gemini'] = {
                'status': 'unhealthy',
                'error': str(e)
            }
        
        # Check database connectivity
        try:
            from ..services.ai_model_service import model_service
            
            count = model_service.processing_job_model.objects.count()
            health_status['services']['database'] = {
                'status': 'healthy',
                'processing_jobs_count': count
            }
        except Exception as e:
            logger.error(f"Database health check failed: {str(e)}")
            health_status['services']['database'] = {
                'status': 'unhealthy',
                'error': str(e)
            }
        
        # Overall status
        all_healthy = all(
            service.get('status') == 'healthy' 
            for service in health_status['services'].values()
        )
        health_status['overall_status'] = 'healthy' if all_healthy else 'degraded'
        
        if not all_healthy:
            logger.warning(f"AI services health check: {health_status['overall_status']}")
        
        return health_status
        
    except Exception as e:
        logger.error(f"Health check task failed: {str(e)}", exc_info=True)
        return {
            'overall_status': 'unhealthy',
            'error': str(e),
            'timestamp': timezone.now().isoformat()
        }


# Helper functions

def _load_image_from_storage(storage_path: str) -> bytes:
    """
    Load image from storage backend
    
    Args:
        storage_path: Path to file in storage
        
    Returns:
        Image bytes
        
    Raises:
        ValueError: If file not found or cannot be read
    """
    try:
        from receipt_service.utils.storage_backends import receipt_storage
        
        logger.debug(f"Loading image from storage: {storage_path}")
        
        # Check if file exists
        if not receipt_storage.storage.exists(storage_path):
            raise FileNotFoundError(f"File not found in storage: {storage_path}")
        
        # Read file
        with receipt_storage.storage.open(storage_path, 'rb') as f:
            content = f.read()
        
        if not content or len(content) == 0:
            raise ValueError(f"Empty file in storage: {storage_path}")
        
        logger.debug(f"Loaded {len(content)} bytes from storage")
        return content
        
    except FileNotFoundError as e:
        logger.error(f"File not found in storage: {storage_path}")
        raise ValueError(f"File not found: {storage_path}") from e
        
    except Exception as e:
        logger.error(f"Failed to load image: {str(e)}", exc_info=True)
        raise ValueError(f"Failed to load image from storage: {str(e)}") from e


def _update_receipt_status_only(receipt_id: str, status: str) -> None:
    """
    Update ONLY the receipt status
    Don't pass result dict - AI data is already in ProcessingJob models!
    
    Args:
        receipt_id: Receipt UUID
        status: New status (processing, processed, failed)
    """
    try:
        from receipt_service.services.receipt_import_service import service_import
        
        receipt_service = service_import.receipt_service
        receipt_service.update_processing_status(receipt_id, status, None)
        
        logger.info(f"Receipt {receipt_id} status updated to {status}")
        
    except Exception as e:
        logger.error(
            f"Failed to update receipt status for {receipt_id}: {str(e)}",
            exc_info=True
        )
        # Don't raise - processing already completed/failed
