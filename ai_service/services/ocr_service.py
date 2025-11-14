# import time
# from typing import Dict, Any, Tuple
# from django.conf import settings
# from django.core.cache import cache
# import logging
# from PIL import Image
# import io
# import pytesseract
# import numpy as np
# import cv2
# from ..utils.exceptions import (
#     ImagePreprocessingException,
#     OCRExtractionException,
#     OCRLowConfidenceException,
#     InvalidImageFormatException,
#     ImageCorruptedException,
#     ModelLoadingException,
# )
# from ..utils.image_preprocessing import ImagePreprocessor
# from ..utils.text_cleaning import TextCleaner
# from ..utils.confidence_scoring import ConfidenceScorer
# from .cache_service import ai_cache_service
# from ..utils.rate_limiter import rate_limiter


# logger = logging.getLogger(__name__)


# class OCRService:
#     """
#     OCR service using Tesseract OCR with comprehensive error handling
#     """
    
#     def __init__(self):
#         self.preprocessor = ImagePreprocessor()
#         self.text_cleaner = TextCleaner()
#         self.confidence_scorer = ConfidenceScorer()
        
#         # Configuration
#         self.min_confidence_threshold = getattr(settings, 'OCR_MIN_CONFIDENCE', 0.7)
#         self.max_processing_time = getattr(settings, 'OCR_MAX_PROCESSING_TIME', 30)
#         self.cache_ttl = getattr(settings, 'OCR_CACHE_TTL', 3600)  # 1 hour
        
#         # Tesseract configuration
#         self.tesseract_cmd = getattr(settings, 'TESSERACT_CMD', None)
#         self._initialize_tesseract()
        
#         # Custom Tesseract configuration for receipts
#         # PSM 6: Assume a single uniform block of text (good for receipts)
#         # OEM 3: Use both Legacy and LSTM engines
#         self.tesseract_config = r'--oem 3 --psm 6'
    
#     def _initialize_tesseract(self):
#         """
#         Initialize Tesseract OCR
        
#         Raises:
#             ModelLoadingException: If Tesseract initialization fails
#         """
#         try:
#             # Set Tesseract command path if provided
#             if self.tesseract_cmd:
#                 pytesseract.pytesseract.tesseract_cmd = self.tesseract_cmd
            
#             # Test Tesseract availability
#             version = pytesseract.get_tesseract_version()
#             logger.info(f"Tesseract OCR initialized successfully - Version: {version}")
            
#         except pytesseract.TesseractNotFoundError:
#             raise ModelLoadingException(
#                 detail="Tesseract OCR not found. Please install Tesseract.",
#                 context={
#                     'install_instructions': {
#                         'Ubuntu/Debian': 'sudo apt-get install tesseract-ocr',
#                         'macOS': 'brew install tesseract',
#                         'Windows': 'Download from https://github.com/UB-Mannheim/tesseract/wiki'
#                     }
#                 }
#             )
#         except Exception as e:
#             logger.error(f"Failed to initialize Tesseract: {str(e)}")
#             raise ModelLoadingException(
#                 detail="Failed to initialize OCR service",
#                 context={'error': str(e), 'service': 'tesseract'}
#             )
    
#     def extract_text_from_image(self, image_data: bytes, receipt_id: str) -> Dict[str, Any]:
#         """
#         Extract text from receipt image using OCR
        
#         Args:
#             image_data: Raw image bytes
#             receipt_id: Receipt ID for caching/logging
            
#         Returns:
#             Dictionary containing OCR results and metadata
            
#         Raises:
#             InvalidImageFormatException: Invalid or unsupported image format
#             ImageCorruptedException: Corrupted image file
#             ImagePreprocessingException: Image preprocessing failed
#             OCRExtractionException: OCR processing failed
#             OCRLowConfidenceException: OCR confidence below threshold
#         """
#         start_time = time.time()
        
#         try:
#             # Create image hash for content-based caching
#             image_hash = ai_cache_service.create_image_hash(image_data)
            
#             # Check cache first
#             cached_result = ai_cache_service.get_ocr_result(receipt_id, image_hash)
#             if cached_result:
#                 logger.info(f"OCR result retrieved from cache for receipt {receipt_id}")
#                 cached_result['from_cache'] = True
#                 return cached_result
            
#             # No rate limiting needed for local Tesseract
            
#             # Mark processing started
#             self._mark_processing_started(receipt_id)
            
#             # Validate and preprocess image
#             processed_image_data, preprocessing_steps = self._preprocess_image(image_data)
            
#             # Update processing status
#             self._update_processing_status(receipt_id, 40, 'Extracting text...')
            
#             # Extract text using Tesseract
#             raw_ocr_result = self._extract_text_with_tesseract(processed_image_data)
            
#             # Update processing status
#             self._update_processing_status(receipt_id, 70, 'Cleaning text...')
            
#             # Clean and process OCR text
#             cleaned_text = self._clean_ocr_text(raw_ocr_result['text'])
            
#             # Calculate confidence scores
#             confidence_scores = self._calculate_confidence_scores(raw_ocr_result, cleaned_text)
            
#             # Validate confidence threshold
#             if confidence_scores['overall_confidence'] < self.min_confidence_threshold:
#                 logger.warning(
#                     f"OCR confidence {confidence_scores['overall_confidence']:.2f} below threshold "
#                     f"{self.min_confidence_threshold} for receipt {receipt_id}"
#                 )
#                 raise OCRLowConfidenceException(
#                     detail=f"OCR confidence {confidence_scores['overall_confidence']:.2f} below threshold {self.min_confidence_threshold}",
#                     context={
#                         'confidence_score': confidence_scores['overall_confidence'],
#                         'threshold': self.min_confidence_threshold,
#                         'receipt_id': receipt_id,
#                         'text_preview': cleaned_text[:100] if cleaned_text else ''
#                     }
#                 )
            
#             # Build final result
#             processing_time = time.time() - start_time
#             result = {
#                 'extracted_text': cleaned_text,
#                 'confidence_score': confidence_scores['overall_confidence'],
#                 'language_detected': raw_ocr_result.get('language', 'en'),
#                 'ocr_engine': 'tesseract',
#                 'processing_time_seconds': round(processing_time, 2),
#                 'image_preprocessing_applied': preprocessing_steps,
#                 'text_regions': raw_ocr_result.get('text_regions', []),
#                 'confidence_breakdown': confidence_scores,
#                 'text_quality_score': confidence_scores.get('text_quality', 0.5),
#                 'receipt_id': receipt_id,
#                 'from_cache': False,
#                 'image_hash': image_hash,
#                 'processed_at': time.time()
#             }
            
#             # Cache the successful result
#             try:
#                 ai_cache_service.set_ocr_result(receipt_id, image_hash, result)
#                 logger.debug(f"OCR result cached for receipt {receipt_id}")
#             except Exception as cache_error:
#                 logger.warning(f"Failed to cache OCR result: {str(cache_error)}")
            
#             # Clear processing status
#             self._clear_processing_status(receipt_id)
            
#             logger.info(
#                 f"OCR processing completed for receipt {receipt_id} in {processing_time:.2f}s "
#                 f"with confidence {confidence_scores['overall_confidence']:.2f}"
#             )
            
#             return result
            
#         except (InvalidImageFormatException, ImageCorruptedException, ImagePreprocessingException,
#                 OCRExtractionException, OCRLowConfidenceException):
#             self._clear_processing_status(receipt_id)
#             raise
#         except Exception as e:
#             self._clear_processing_status(receipt_id)
#             logger.error(f"Unexpected OCR processing error for receipt {receipt_id}: {str(e)}", exc_info=True)
#             raise OCRExtractionException(
#                 detail="Unexpected error during OCR processing",
#                 context={'receipt_id': receipt_id, 'error': str(e)}
#             )
    
#     def _extract_text_with_tesseract(self, image_data: bytes) -> Dict[str, Any]:
#         """
#         Extract text using Tesseract OCR
        
#         Raises:
#             OCRExtractionException: Extraction failed
#         """
#         try:
#             # Load image
#             image = Image.open(io.BytesIO(image_data))
            
#             # Convert to OpenCV format for better preprocessing
#             img_array = np.array(image)
            
#             # Convert to grayscale if not already
#             if len(img_array.shape) == 3:
#                 gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
#             else:
#                 gray = img_array
            
#             # Apply adaptive thresholding for better text detection
#             binary = cv2.adaptiveThreshold(
#                 gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
#                 cv2.THRESH_BINARY, 11, 2
#             )
            
#             # Get detailed OCR data with confidence scores
#             ocr_data = pytesseract.image_to_data(
#                 binary,
#                 config=self.tesseract_config,
#                 output_type=pytesseract.Output.DICT
#             )
            
#             # Extract full text
#             full_text = pytesseract.image_to_string(
#                 binary,
#                 config=self.tesseract_config
#             )
            
#             if not full_text or len(full_text.strip()) < 5:
#                 logger.warning("Tesseract extracted very little or no text")
#                 return {
#                     'text': '',
#                     'confidence': 0.0,
#                     'language': 'en',
#                     'text_regions': []
#                 }
            
#             # Extract text regions with confidence
#             text_regions = []
#             n_boxes = len(ocr_data['text'])
            
#             for i in range(n_boxes):
#                 text = ocr_data['text'][i].strip()
#                 conf = int(ocr_data['conf'][i])
                
#                 # Only include regions with text and reasonable confidence
#                 if text and conf > 0:
#                     x, y, w, h = (
#                         ocr_data['left'][i],
#                         ocr_data['top'][i],
#                         ocr_data['width'][i],
#                         ocr_data['height'][i]
#                     )
                    
#                     text_regions.append({
#                         'text': text,
#                         'confidence': conf / 100.0,  # Convert to 0-1 scale
#                         'bounding_box': [
#                             {'x': x, 'y': y},
#                             {'x': x + w, 'y': y},
#                             {'x': x + w, 'y': y + h},
#                             {'x': x, 'y': y + h}
#                         ]
#                     })
            
#             # Calculate average confidence from regions
#             if text_regions:
#                 avg_confidence = sum(r['confidence'] for r in text_regions) / len(text_regions)
#             else:
#                 avg_confidence = 0.5
            
#             # Detect language (Tesseract can detect this)
#             try:
#                 lang_info = pytesseract.image_to_osd(binary, output_type=pytesseract.Output.DICT)
#                 detected_language = lang_info.get('script', 'Latin').lower()
#                 if 'latin' in detected_language:
#                     detected_language = 'en'
#             except Exception:
#                 detected_language = 'en'
            
#             return {
#                 'text': full_text,
#                 'confidence': avg_confidence,
#                 'language': detected_language,
#                 'text_regions': text_regions
#             }
            
#         except pytesseract.TesseractError as e:
#             logger.error(f"Tesseract OCR error: {str(e)}")
#             raise OCRExtractionException(
#                 detail="Tesseract OCR processing failed",
#                 context={'error': str(e), 'tesseract_error': True}
#             )
#         except Exception as e:
#             logger.error(f"OCR extraction failed: {str(e)}")
#             raise OCRExtractionException(
#                 detail="Failed to extract text from image",
#                 context={'error': str(e)}
#             )
    
#     def _mark_processing_started(self, receipt_id: str):
#         """Mark OCR processing as started - does not raise exceptions"""
#         try:
#             processing_key = f"ocr_processing_{receipt_id}"
#             cache.set(processing_key, {
#                 'status': 'processing',
#                 'progress': 10,
#                 'message': 'Starting OCR processing...',
#                 'started_at': time.time()
#             }, timeout=300)
#         except Exception as e:
#             logger.warning(f"Failed to mark processing started: {str(e)}")
    
#     def _update_processing_status(self, receipt_id: str, progress: int, message: str):
#         """Update OCR processing status - does not raise exceptions"""
#         try:
#             processing_key = f"ocr_processing_{receipt_id}"
#             existing = cache.get(processing_key) or {}
#             existing.update({
#                 'progress': progress,
#                 'message': message,
#                 'updated_at': time.time()
#             })
#             cache.set(processing_key, existing, timeout=300)
#         except Exception as e:
#             logger.warning(f"Failed to update processing status: {str(e)}")
    
#     def _clear_processing_status(self, receipt_id: str):
#         """Clear OCR processing status - does not raise exceptions"""
#         try:
#             processing_key = f"ocr_processing_{receipt_id}"
#             cache.delete(processing_key)
#         except Exception as e:
#             logger.warning(f"Failed to clear processing status: {str(e)}")
    
#     def _preprocess_image(self, image_data: bytes) -> Tuple[bytes, list]:
#         """
#         Preprocess image for optimal OCR
        
#         Raises:
#             InvalidImageFormatException: Invalid image format
#             ImageCorruptedException: Corrupted image
#             ImagePreprocessingException: Preprocessing failed
#         """
#         try:
#             return self.preprocessor.preprocess_for_ocr(image_data)
#         except (InvalidImageFormatException, ImageCorruptedException, ImagePreprocessingException):
#             raise
#         except Exception as e:
#             logger.error(f"Image preprocessing failed: {str(e)}")
#             raise ImagePreprocessingException(
#                 detail="Image preprocessing failed",
#                 context={'error': str(e)}
#             )
    
#     def _clean_ocr_text(self, raw_text: str) -> str:
#         """Clean OCR text - does not raise exceptions, returns best effort result"""
#         try:
#             return self.text_cleaner.clean_ocr_text(raw_text)
#         except Exception as e:
#             logger.warning(f"Text cleaning failed, using raw text: {str(e)}")
#             return raw_text or ""
    
#     def _calculate_confidence_scores(self, raw_ocr_result: Dict, cleaned_text: str) -> Dict[str, float]:
#         """Calculate confidence scores - does not raise exceptions"""
#         try:
#             text_quality_score = self.text_cleaner.get_text_quality_score(cleaned_text)
            
#             ocr_confidence = self.confidence_scorer.calculate_ocr_confidence(
#                 raw_ocr_result,
#                 text_quality_score,
#                 len(cleaned_text)
#             )
            
#             return {
#                 'overall_confidence': round(ocr_confidence, 3),
#                 'text_quality': round(text_quality_score, 3),
#                 'api_confidence': round(raw_ocr_result.get('confidence', 0.0), 3),
#                 'length_factor': round(min(1.0, len(cleaned_text) / 100), 3)
#             }
#         except Exception as e:
#             logger.warning(f"Confidence calculation failed: {str(e)}")
#             return {
#                 'overall_confidence': round(raw_ocr_result.get('confidence', 0.5), 3),
#                 'text_quality': 0.5,
#                 'api_confidence': round(raw_ocr_result.get('confidence', 0.0), 3),
#                 'length_factor': 0.5
#             }
    
#     def get_processing_status(self, receipt_id: str) -> Dict[str, Any]:
#         """Get OCR processing status for a receipt"""
#         try:
#             processing_key = f"ocr_processing_{receipt_id}"
#             processing_status = cache.get(processing_key)
            
#             if processing_status:
#                 return {
#                     'status': 'processing',
#                     'progress': processing_status.get('progress', 0),
#                     'message': processing_status.get('message', 'Processing...'),
#                     'estimated_completion': max(0, 60 - (time.time() - processing_status.get('started_at', time.time())))
#                 }
            
#             # Check database for completed results
#             try:
#                 from .ai_model_service import model_service
#                 ocr_result = model_service.ocr_result_model.objects.filter(
#                     processing_job__receipt_id=receipt_id
#                 ).first()
                
#                 if ocr_result:
#                     return {
#                         'status': 'completed',
#                         'progress': 100,
#                         'confidence': float(ocr_result.confidence_score),
#                         'processing_time': float(ocr_result.processing_time_seconds)
#                     }
#             except Exception:
#                 pass
            
#             return {
#                 'status': 'not_started',
#                 'progress': 0
#             }
            
#         except Exception as e:
#             logger.error(f"Error getting OCR processing status: {str(e)}")
#             return {
#                 'status': 'error',
#                 'progress': 0,
#                 'error': 'Failed to get processing status'
#             }
    
#     def health_check(self) -> Dict[str, Any]:
#         """Perform health check for OCR service"""
#         health_status = {
#             'service': 'ocr_service',
#             'status': 'healthy',
#             'checks': {},
#             'timestamp': time.time()
#         }
        
#         try:
#             # Check Tesseract availability
#             try:
#                 version = pytesseract.get_tesseract_version()
#                 health_status['checks']['tesseract'] = f'available (v{version})'
#             except Exception as e:
#                 health_status['checks']['tesseract'] = f'unavailable: {str(e)}'
#                 health_status['status'] = 'unhealthy'
            
#             # Check cache connectivity
#             try:
#                 cache.set('ocr_health_test', 'ok', 60)
#                 result = cache.get('ocr_health_test')
#                 health_status['checks']['cache'] = 'available' if result == 'ok' else 'unavailable'
#                 if result != 'ok':
#                     health_status['status'] = 'degraded'
#             except Exception as e:
#                 health_status['checks']['cache'] = f'error: {str(e)}'
#                 health_status['status'] = 'degraded'
            
#             return health_status
            
#         except Exception as e:
#             logger.error(f"OCR service health check failed: {str(e)}")
#             return {
#                 'service': 'ocr_service',
#                 'status': 'unhealthy',
#                 'error': str(e),
#                 'timestamp': time.time()
#             }

# ai_service/services/ocr_service.py

# ai_service/services/ocr_service.py

# ai_service/services/ocr_service.py

# ai_service/services/ocr_service.py

import pytesseract
from pytesseract import TesseractError, TesseractNotFoundError
import time
import logging
from typing import Dict, Any
from PIL import Image
import io

from ..utils.image_preprocessing import image_preprocessor
from ..utils.exceptions import (
    OCRException,
    OCRExtractionException,
    OCRServiceUnavailableException,
    ImagePreprocessingException,
    ImageCorruptedException,
    InvalidImageFormatException,
)

logger = logging.getLogger(__name__)


class OCRService:
    """Enhanced OCR service with preprocessing for receipts"""
    
    def __init__(self):
        # Optimal Tesseract config for receipts
        # PSM 4 = Single column of variable-sized text (perfect for receipts)
        # OEM 1 = Neural nets LSTM engine only
        self.tesseract_config = r'--oem 1 --psm 4 -c preserve_interword_spaces=1'
        self.min_confidence_threshold = 0.3
        
        # Verify Tesseract is installed
        self._verify_tesseract()
    
    def _verify_tesseract(self) -> None:
        """Verify Tesseract OCR is installed and accessible"""
        try:
            pytesseract.get_tesseract_version()
            logger.info(f"Tesseract OCR found: {pytesseract.get_tesseract_version()}")
        except TesseractNotFoundError:
            logger.error("Tesseract OCR not found! Please install Tesseract.")
            # Don't raise here - let it fail on first use with proper error
        except Exception as e:
            logger.warning(f"Could not verify Tesseract: {str(e)}")
    
    def extract_text_from_image(
        self, 
        image_data: bytes, 
        receipt_id: str
    ) -> Dict[str, Any]:
        """
        Extract text from receipt image with preprocessing
        
        Args:
            image_data: Raw image bytes
            receipt_id: Receipt identifier for logging
            
        Returns:
            Dict with extracted_text and confidence_score (NO preprocessing_steps)
            
        Raises:
            ImageCorruptedException: If image cannot be decoded
            InvalidImageFormatException: If image format is not supported
            ImagePreprocessingException: If preprocessing fails
            OCRExtractionException: If OCR extraction fails
            OCRServiceUnavailableException: If Tesseract is not installed
        """
        start_time = time.time()
        
        try:
            # Validate image data
            if not image_data or len(image_data) == 0:
                raise InvalidImageFormatException(
                    detail="Empty image data",
                    context={'receipt_id': receipt_id}
                )
            
            # Step 1: Preprocess image
            logger.info(f"Preprocessing image for receipt {receipt_id}")
            
            try:
                preprocessed_image, preprocessing_steps = image_preprocessor.preprocess_for_ocr(
                    image_data
                )
                # Log preprocessing steps but don't store them
                logger.debug(f"Preprocessing steps applied: {preprocessing_steps}")
            except (ImagePreprocessingException, ImageCorruptedException, InvalidImageFormatException):
                raise
            except Exception as prep_error:
                logger.error(f"Preprocessing failed: {str(prep_error)}", exc_info=True)
                raise ImagePreprocessingException(
                    detail="Image preprocessing failed",
                    context={'receipt_id': receipt_id, 'error': str(prep_error)}
                )
            
            # Step 2: Convert to PIL Image
            try:
                image = Image.open(io.BytesIO(preprocessed_image))
            except Exception as img_error:
                logger.error(f"Failed to open image: {str(img_error)}")
                raise ImageCorruptedException(
                    detail="Failed to decode preprocessed image",
                    context={'receipt_id': receipt_id, 'error': str(img_error)}
                )
            
            # Step 3: Perform OCR
            logger.info(f"Performing OCR for receipt {receipt_id}")
            
            try:
                extracted_text = pytesseract.image_to_string(
                    image,
                    config=self.tesseract_config
                )
            except TesseractNotFoundError:
                logger.error("Tesseract not found on system")
                raise OCRServiceUnavailableException(
                    detail="Tesseract OCR is not installed or not in PATH",
                    context={'receipt_id': receipt_id}
                )
            except TesseractError as tess_error:
                logger.error(f"Tesseract error: {str(tess_error)}")
                raise OCRExtractionException(
                    detail="OCR text extraction failed",
                    context={'receipt_id': receipt_id, 'error': str(tess_error)}
                )
            except Exception as ocr_error:
                logger.error(f"OCR failed: {str(ocr_error)}", exc_info=True)
                raise OCRExtractionException(
                    detail="Unexpected OCR error",
                    context={'receipt_id': receipt_id, 'error': str(ocr_error)}
                )
            
            # Step 4: Get confidence score
            confidence_score = self._calculate_confidence(image, extracted_text)
            
            # Step 5: Clean extracted text
            cleaned_text = self._clean_ocr_text(extracted_text)
            
            # Check if we got meaningful text
            if not cleaned_text or len(cleaned_text) < 10:
                logger.warning(
                    f"Very short OCR output for receipt {receipt_id}: {len(cleaned_text)} chars"
                )
            
            processing_time = time.time() - start_time
            
            # Return ONLY fields that exist in OCRResult model!
            result = {
                'extracted_text': cleaned_text,
                'confidence_score': round(confidence_score, 2),
                # DO NOT include: preprocessing_steps, character_count, word_count
            }
            
            logger.info(
                f"OCR completed for receipt {receipt_id} in {processing_time:.2f}s "
                f"with confidence {confidence_score:.2f} ({len(cleaned_text)} chars)"
            )
            
            return result
            
        except (ImageCorruptedException, InvalidImageFormatException, 
                ImagePreprocessingException, OCRExtractionException, 
                OCRServiceUnavailableException):
            raise
            
        except Exception as e:
            logger.error(
                f"OCR processing failed for receipt {receipt_id}: {str(e)}", 
                exc_info=True
            )
            raise OCRException(
                detail="OCR processing failed unexpectedly",
                context={'receipt_id': receipt_id, 'error': str(e)}
            )
    
    def _calculate_confidence(self, image: Image, extracted_text: str) -> float:
        """Calculate OCR confidence score"""
        try:
            # Get word-level confidence from Tesseract
            ocr_data = pytesseract.image_to_data(
                image,
                output_type=pytesseract.Output.DICT,
                config=self.tesseract_config
            )
            
            # Calculate average confidence from word-level confidence scores
            confidences = [
                int(conf) for conf in ocr_data['conf'] 
                if conf != '-1' and int(conf) > 0
            ]
            
            if confidences:
                avg_confidence = sum(confidences) / len(confidences)
                confidence = avg_confidence / 100.0
                
                logger.debug(
                    f"OCR confidence: {confidence:.2f} "
                    f"({len(confidences)} words with confidence)"
                )
                
                return confidence
            
            # Fallback: estimate based on text characteristics
            return self._estimate_confidence_from_text(extracted_text)
                
        except Exception as e:
            logger.warning(f"Failed to calculate confidence: {str(e)}")
            # Return conservative estimate
            return self._estimate_confidence_from_text(extracted_text)
    
    def _estimate_confidence_from_text(self, text: str) -> float:
        """
        Estimate confidence based on text characteristics
        Used as fallback when word-level confidence is unavailable
        """
        if not text or len(text) < 5:
            return 0.1
        
        # Calculate metrics
        alphanumeric_count = sum(c.isalnum() for c in text)
        total_chars = len(text)
        alphanumeric_ratio = alphanumeric_count / total_chars if total_chars > 0 else 0
        
        # Words vs total characters (spacing indicator)
        words = text.split()
        word_count = len(words)
        avg_word_length = alphanumeric_count / word_count if word_count > 0 else 0
        
        # Base confidence on multiple factors
        confidence = 0.3  # Base confidence
        
        # Add confidence based on alphanumeric ratio (should be high for receipts)
        confidence += alphanumeric_ratio * 0.3
        
        # Add confidence based on length (more text = more confidence)
        if total_chars > 200:
            confidence += 0.2
        elif total_chars > 100:
            confidence += 0.15
        elif total_chars > 50:
            confidence += 0.1
        
        # Add confidence based on reasonable word length
        if 3 <= avg_word_length <= 10:
            confidence += 0.1
        
        return min(confidence, 0.95)  # Cap at 0.95 for estimates
    
    def _clean_ocr_text(self, text: str) -> str:
        """
        Clean OCR text by removing excessive whitespace and artifacts
        Keep structure for better Gemini parsing
        """
        if not text:
            return ""
        
        # Split into lines
        lines = text.split('\n')
        
        # Clean each line
        cleaned_lines = []
        for line in lines:
            line = line.strip()
            
            # Skip lines with only special characters or very short
            if len(line) < 2:
                continue
            
            # Skip lines that are just symbols/noise
            if all(not c.isalnum() for c in line):
                continue
            
            cleaned_lines.append(line)
        
        # Join with single newlines
        cleaned = '\n'.join(cleaned_lines)
        
        return cleaned


# Global instance
ocr_service = OCRService()
