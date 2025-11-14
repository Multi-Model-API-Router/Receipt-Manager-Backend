import hashlib
import mimetypes
import magic
from PIL import Image
from django.conf import settings
from typing import Dict, Any, Optional
from .exceptions import (
    InvalidFileFormatException,
    FileSizeExceededException,
    DuplicateReceiptException
)
import logging
logger = logging.getLogger(__name__)


class ReceiptFileValidator:
    """Comprehensive file validation for receipt uploads"""
    
    # Configuration constants
    MAX_FILE_SIZE = int(getattr(settings, 'RECEIPT_MAX_FILE_SIZE', 10 * 1024 * 1024))  # 10MB
    ALLOWED_EXTENSIONS = ['pdf', 'jpg', 'jpeg', 'png']
    ALLOWED_MIME_TYPES = [
        'application/pdf',
        'image/jpeg',
        'image/png',
    ]
    
    # Image validation constants
    MIN_IMAGE_WIDTH = 100
    MIN_IMAGE_HEIGHT = 100
    MAX_IMAGE_WIDTH = 10000
    MAX_IMAGE_HEIGHT = 10000
    
    def __init__(self):
        self.errors = []
    
    def validate_file(self, uploaded_file) -> Dict[str, Any]:
        """
        Comprehensive file validation
        Returns file metadata if valid, raises exception if invalid
        """
        self.errors = []
        
        try:
            # Basic validations
            self._validate_file_size(uploaded_file)
            self._validate_file_extension(uploaded_file.name)
            mime_type = self._validate_mime_type(uploaded_file)
            
            # Content validation
            self._validate_file_content(uploaded_file, mime_type)
            
            # Generate file hash for duplicate detection
            file_hash = self._generate_file_hash(uploaded_file)
            
            # Reset file pointer after reading
            uploaded_file.seek(0)
            
            return {
                'filename': uploaded_file.name,
                'size': uploaded_file.size,
                'mime_type': mime_type,
                'file_hash': file_hash,
                'extension': self._get_file_extension(uploaded_file.name)
            }
            
        except Exception as e:
            if isinstance(e, (InvalidFileFormatException, FileSizeExceededException)):
                raise
            else:
                raise InvalidFileFormatException(
                    detail=f"File validation failed: {str(e)}"
                )
    
    def _validate_file_size(self, uploaded_file):
        """Validate file size"""
        if uploaded_file.size > self.MAX_FILE_SIZE:
            size_mb = self.MAX_FILE_SIZE / (1024 * 1024)
            raise FileSizeExceededException(
                detail=f"File too large. Maximum size allowed is {size_mb:.1f}MB",
                context={
                    'max_size_bytes': self.MAX_FILE_SIZE,
                    'max_size_mb': size_mb,
                    'actual_size_bytes': uploaded_file.size
                }
            )
    
    def _validate_file_extension(self, filename: str):
        """Validate file extension"""
        extension = self._get_file_extension(filename)
        if extension not in self.ALLOWED_EXTENSIONS:
            raise InvalidFileFormatException(
                detail=f"Invalid file extension '.{extension}'. Allowed: {', '.join(self.ALLOWED_EXTENSIONS)}",
                context={
                    'allowed_extensions': self.ALLOWED_EXTENSIONS,
                    'provided_extension': extension
                }
            )
    
    def _validate_mime_type(self, uploaded_file) -> str:
        """Validate MIME type using python-magic for accurate detection"""
        try:
            # Read first chunk for MIME type detection
            chunk = uploaded_file.read(1024)
            uploaded_file.seek(0)
            
            # Detect MIME type using magic
            mime_type = magic.from_buffer(chunk, mime=True)
            
            if mime_type not in self.ALLOWED_MIME_TYPES:
                raise InvalidFileFormatException(
                    detail=f"Invalid file type detected: {mime_type}",
                    context={
                        'allowed_mime_types': self.ALLOWED_MIME_TYPES,
                        'detected_mime_type': mime_type
                    }
                )
            
            return mime_type
            
        except Exception as e:
            # Fallback to filename-based detection
            mime_type, _ = mimetypes.guess_type(uploaded_file.name)
            if mime_type not in self.ALLOWED_MIME_TYPES:
                raise InvalidFileFormatException(
                    detail="Unable to verify file type or invalid file format"
                )
            return mime_type
    
    def _validate_file_content(self, uploaded_file, mime_type: str):
        """Validate file content based on type"""
        if mime_type.startswith('image/'):
            self._validate_image_content(uploaded_file)
        elif mime_type == 'application/pdf':
            self._validate_pdf_content(uploaded_file)
    
    def _validate_image_content(self, uploaded_file):
        """Validate image file content and properties"""
        try:
            with Image.open(uploaded_file) as img:
                # Verify image can be opened
                img.verify()
                
                # Re-open for property checks (verify() closes the image)
                uploaded_file.seek(0)
                with Image.open(uploaded_file) as img:
                    width, height = img.size
                    
                    # Check image dimensions
                    if width < self.MIN_IMAGE_WIDTH or height < self.MIN_IMAGE_HEIGHT:
                        raise InvalidFileFormatException(
                            detail=f"Image too small. Minimum size: {self.MIN_IMAGE_WIDTH}x{self.MIN_IMAGE_HEIGHT}px",
                            context={
                                'min_width': self.MIN_IMAGE_WIDTH,
                                'min_height': self.MIN_IMAGE_HEIGHT,
                                'actual_width': width,
                                'actual_height': height
                            }
                        )
                    
                    if width > self.MAX_IMAGE_WIDTH or height > self.MAX_IMAGE_HEIGHT:
                        raise InvalidFileFormatException(
                            detail=f"Image too large. Maximum size: {self.MAX_IMAGE_WIDTH}x{self.MAX_IMAGE_HEIGHT}px",
                            context={
                                'max_width': self.MAX_IMAGE_WIDTH,
                                'max_height': self.MAX_IMAGE_HEIGHT,
                                'actual_width': width,
                                'actual_height': height
                            }
                        )
                        
        except Exception as e:
            if isinstance(e, InvalidFileFormatException):
                raise
            raise InvalidFileFormatException(
                detail="Invalid or corrupted image file"
            )
    
    def _validate_pdf_content(self, uploaded_file):
        """Basic PDF validation"""
        try:
            # Read first few bytes to check PDF signature
            uploaded_file.seek(0)
            header = uploaded_file.read(4)
            uploaded_file.seek(0)
            
            if header != b'%PDF':
                raise InvalidFileFormatException(
                    detail="Invalid PDF file format"
                )
                
        except Exception as e:
            if isinstance(e, InvalidFileFormatException):
                raise
            raise InvalidFileFormatException(
                detail="Invalid or corrupted PDF file"
            )
    
    def _generate_file_hash(self, uploaded_file) -> str:
        """Generate SHA-256 hash for duplicate detection"""
        uploaded_file.seek(0)
        file_hash = hashlib.sha256()
        
        # Read file in chunks to handle large files efficiently
        for chunk in iter(lambda: uploaded_file.read(4096), b""):
            file_hash.update(chunk)
        
        uploaded_file.seek(0)
        return file_hash.hexdigest()
    
    def _get_file_extension(self, filename: str) -> str:
        """Extract file extension"""
        return filename.lower().split('.')[-1] if '.' in filename else ''

    def check_duplicate_receipt(self, user, file_hash: str) -> Optional[str]:
        """
        Check for duplicates using ProcessingJob status as source of truth
        """
        from ..services.receipt_model_service import model_service
        from ai_service.services.ai_model_service import model_service as ai_model_service
        from django.utils import timezone
        from datetime import timedelta
        
        existing_receipts = model_service.receipt_model.objects.filter(
            user=user,
            file_hash=file_hash
        ).order_by('-created_at')
        
        if not existing_receipts.exists():
            return None
        
        latest_receipt = existing_receipts.first()
        
        # Get latest processing job (source of truth!)
        processing_job = ai_model_service.processing_job_model.objects.filter(
            receipt_id=latest_receipt.id
        ).order_by('-created_at').first()
        
        if not processing_job:
            # No job yet - shouldn't happen, but allow upload
            logger.warning(f"Receipt {latest_receipt.id} has no processing job")
            return None
        
        # Check job status
        if processing_job.status == 'failed':
            logger.info(f"Found failed receipt {latest_receipt.id}, allowing retry")
            return str(latest_receipt.id)
        
        # Check if stuck (older than 5 minutes but still "processing")
        if processing_job.status in ['queued', 'processing']:
            age = timezone.now() - processing_job.created_at
            
            if age > timedelta(minutes=5):
                logger.warning(
                    f"Job {processing_job.id} stuck at {processing_job.status} "
                    f"for {age.total_seconds():.0f}s, allowing retry"
                )
                return str(latest_receipt.id)
            
            # Still actively processing
            raise DuplicateReceiptException(
                detail="This receipt is currently being processed",
                context={
                    'existing_receipt_id': str(latest_receipt.id),
                    'status': processing_job.status,
                    'message': 'Please wait...',
                    'actions': {
                        'check_status': f'/api/v1/receipts/upload-status/{latest_receipt.id}/'
                    }
                }
            )
        
        # Successfully completed
        if processing_job.status == 'completed':
            if latest_receipt.status == 'confirmed':
                raise DuplicateReceiptException(
                    detail="This receipt has been confirmed"
                )
            
            raise DuplicateReceiptException(
                detail="This receipt has been processed",
                context={
                    'existing_receipt_id': str(latest_receipt.id),
                    'actions': {
                        'view': f'/api/v1/receipts/{latest_receipt.id}/'
                    }
                }
            )
        
        return None
