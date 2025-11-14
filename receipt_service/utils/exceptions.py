from shared.utils.exceptions import (
    BaseServiceException,
    ValidationException,
    ResourceNotFoundException,
    ResourceConflictException,
    BusinessLogicException,
    DatabaseOperationException,
    ExternalServiceException
)
from rest_framework import status


# ========================
# Receipt Service Base Exceptions
# ========================

class ReceiptServiceException(BaseServiceException):
    """Base exception for receipt service operations"""
    default_code = 'receipt_service_error'
    default_detail = 'Receipt service operation failed'


# ========================
# File Upload & Storage Exceptions
# ========================

class FileUploadException(ValidationException):
    """Base class for file upload related exceptions"""
    default_code = 'file_upload_error'
    default_detail = 'File upload failed'


class InvalidFileFormatException(FileUploadException):
    """Invalid file format uploaded"""
    default_code = 'invalid_file_format'
    default_detail = 'Invalid file format. Only PDF, JPG, JPEG, and PNG files are supported'


class FileSizeExceededException(FileUploadException):
    """File size exceeds maximum allowed"""
    default_code = 'file_size_exceeded'
    default_detail = 'File size exceeds maximum allowed limit'


class FileCorruptedException(FileUploadException):
    """File is corrupted or unreadable"""
    default_code = 'file_corrupted'
    default_detail = 'File appears to be corrupted or unreadable'


class DuplicateReceiptException(BusinessLogicException):
    """Duplicate receipt file detected"""
    default_code = 'duplicate_receipt'
    default_detail = 'This receipt has already been uploaded'


class FileStorageException(ExternalServiceException):
    """File storage operation failed"""
    default_code = 'file_storage_error'
    default_detail = 'Failed to store file'


class FileRetrievalException(ExternalServiceException):
    """File retrieval operation failed"""
    default_code = 'file_retrieval_error'
    default_detail = 'Failed to retrieve file'


class FileDeletionException(ExternalServiceException):
    """File deletion operation failed"""
    default_code = 'file_deletion_error'
    default_detail = 'Failed to delete file'


# ========================
# Receipt Resource Exceptions
# ========================

class ReceiptNotFoundException(ResourceNotFoundException):
    """Receipt not found"""
    default_code = 'receipt_not_found'
    default_detail = 'Receipt not found'


class ReceiptAccessDeniedException(BaseServiceException):
    """User doesn't have access to receipt"""
    default_code = 'receipt_access_denied'
    default_detail = 'You do not have permission to access this receipt'
    status_code = status.HTTP_403_FORBIDDEN


# ========================
# Receipt State Exceptions
# ========================

class ReceiptNotProcessedException(BusinessLogicException):
    """Receipt not yet processed"""
    default_code = 'receipt_not_processed'
    default_detail = 'Receipt has not been processed yet and cannot be confirmed'


class ReceiptAlreadyConfirmedException(ResourceConflictException):
    """Receipt already confirmed"""
    default_code = 'receipt_already_confirmed'
    default_detail = 'Receipt has already been confirmed'


class ReceiptProcessingInProgressException(ResourceConflictException):
    """Receipt is currently being processed"""
    default_code = 'receipt_processing_in_progress'
    default_detail = 'Receipt is currently being processed. Please wait for completion'


class ReceiptProcessingFailedException(BaseServiceException):
    """Receipt processing failed"""
    default_code = 'receipt_processing_failed'
    default_detail = 'Receipt processing failed'
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR


class ReceiptConfirmationException(ValidationException):
    """Invalid receipt confirmation data"""
    default_code = 'receipt_confirmation_invalid'
    default_detail = 'Invalid receipt confirmation data provided'


# ========================
# Category Exceptions
# ========================

class CategoryNotFoundException(ResourceNotFoundException):
    """Category not found"""
    default_code = 'category_not_found'
    default_detail = 'Category not found'


class CategoryInactiveException(BusinessLogicException):
    """Category is inactive"""
    default_code = 'category_inactive'
    default_detail = 'Selected category is no longer active'


# ========================
# Ledger Exceptions
# ========================

class LedgerEntryNotFoundException(ResourceNotFoundException):
    """Ledger entry not found"""
    default_code = 'ledger_entry_not_found'
    default_detail = 'Ledger entry not found'


class LedgerEntryAccessDeniedException(BaseServiceException):
    """User doesn't have access to ledger entry"""
    default_code = 'ledger_entry_access_denied'
    default_detail = 'You do not have permission to access this ledger entry'
    status_code = status.HTTP_403_FORBIDDEN


class LedgerEntryConflictException(ResourceConflictException):
    """Ledger entry already exists"""
    default_code = 'ledger_entry_exists'
    default_detail = 'Ledger entry already exists for this receipt'


class LedgerEntryCreationException(DatabaseOperationException):
    """Failed to create ledger entry"""
    default_code = 'ledger_entry_creation_failed'
    default_detail = 'Failed to create ledger entry'


class LedgerEntryUpdateException(DatabaseOperationException):
    """Failed to update ledger entry"""
    default_code = 'ledger_entry_update_failed'
    default_detail = 'Failed to update ledger entry'


class LedgerEntryDeletionException(DatabaseOperationException):
    """Failed to delete ledger entry"""
    default_code = 'ledger_entry_deletion_failed'
    default_detail = 'Failed to delete ledger entry'


# ========================
# Quota & Limits Exceptions
# ========================

class QuotaServiceException(BaseServiceException):
    """Base quota service exception"""
    default_code = 'quota_service_error'
    default_detail = 'Quota service operation failed'


class MonthlyUploadLimitExceededException(BusinessLogicException):
    """Monthly upload limit exceeded"""
    default_code = 'monthly_upload_limit_exceeded'
    default_detail = 'Monthly upload limit has been exceeded'
    status_code = status.HTTP_429_TOO_MANY_REQUESTS


class QuotaCalculationException(BaseServiceException):
    """Error calculating quota"""
    default_code = 'quota_calculation_error'
    default_detail = 'Failed to calculate quota usage'
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR


# ========================
# Processing Pipeline Exceptions
# ========================

class OCRExtractionException(ExternalServiceException):
    """OCR text extraction failed"""
    default_code = 'ocr_extraction_failed'
    default_detail = 'Failed to extract text from receipt image'


class DataParsingException(BaseServiceException):
    """Data parsing failed"""
    default_code = 'data_parsing_failed'
    default_detail = 'Failed to parse receipt data'
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR


class AICategorizationException(ExternalServiceException):
    """AI categorization failed"""
    default_code = 'ai_categorization_failed'
    default_detail = 'Failed to categorize receipt using AI'


class ProcessingTimeoutException(BaseServiceException):
    """Processing timeout"""
    default_code = 'processing_timeout'
    default_detail = 'Receipt processing timed out'
    status_code = status.HTTP_504_GATEWAY_TIMEOUT


# ========================
# Cache Exceptions
# ========================

class CacheException(BaseServiceException):
    """Cache operation failed"""
    default_code = 'cache_error'
    default_detail = 'Cache operation failed'
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
