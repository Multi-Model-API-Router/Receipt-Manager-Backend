# ai_service/utils/image_preprocessing.py

import cv2
import numpy as np
from PIL import Image
import io
import logging

from ..utils.exceptions import (
    ImagePreprocessingException,
    ImageCorruptedException,
    InvalidImageFormatException,
)

logger = logging.getLogger(__name__)


class ImagePreprocessor:
    """
    Advanced image preprocessing for optimal OCR accuracy
    Optimized to work with unclear, low-quality, and rotated receipt images
    """
    
    def __init__(self):
        self.target_min_dimension = 1200  # Minimum size for good OCR
        self.max_upscale_factor = 3.0     # Don't upscale too much
        self.deskew_threshold = 0.5       # Degrees - only deskew if > this
        self.supported_formats = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif'}
    
    def preprocess_for_ocr(self, image_data: bytes) -> tuple[bytes, list]:
        """
        Complete preprocessing pipeline for receipt images
        
        Handles:
        - Low resolution images (upscaling)
        - Rotated/skewed images (deskewing)
        - Poor lighting (adaptive thresholding)
        - Noise (denoising)
        - Low contrast (CLAHE)
        
        Args:
            image_data: Raw image bytes
            
        Returns:
            Tuple of (preprocessed_image_bytes, applied_steps)
            
        Raises:
            ImageCorruptedException: If image cannot be decoded
            ImagePreprocessingException: If preprocessing fails
        """
        if not image_data or len(image_data) == 0:
            raise InvalidImageFormatException(
                detail="Empty image data provided"
            )
        
        applied_steps = []
        
        try:
            # Step 0: Decode image
            img = self._decode_image(image_data)
            if img is None:
                raise ImageCorruptedException(
                    detail="Failed to decode image data"
                )
            
            original_shape = img.shape
            logger.debug(f"Original image shape: {original_shape}")
            
            # Step 1: Upscale if low resolution
            img, upscale_step = self._upscale_if_needed(img)
            if upscale_step:
                applied_steps.append(upscale_step)
            
            # Step 2: Convert to grayscale
            if len(img.shape) == 3:
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                applied_steps.append('converted_to_grayscale')
            else:
                gray = img
            
            # Step 3: Denoise first (before other operations)
            denoised = self._denoise_image(gray)
            applied_steps.append('denoised')
            
            # Step 4: Deskew if needed
            deskewed, angle = self._deskew_image(denoised)
            if abs(angle) > self.deskew_threshold:
                applied_steps.append(f'deskewed_{angle:.1f}deg')
                gray = deskewed
            else:
                gray = denoised
            
            # Step 5: Enhance contrast (critical for unclear images)
            enhanced = self._enhance_contrast(gray)
            applied_steps.append('contrast_enhanced')
            
            # Step 6: Apply adaptive thresholding (handles varying lighting)
            thresh = self._apply_adaptive_threshold(enhanced)
            applied_steps.append('adaptive_thresholding')
            
            # Step 7: Morphological operations to clean up
            cleaned = self._morphological_cleanup(thresh)
            applied_steps.append('morphological_cleanup')
            
            # Step 8: Final sharpening
            sharpened = self._sharpen_image(cleaned)
            applied_steps.append('sharpened')
            
            # Convert back to bytes
            preprocessed_bytes = self._encode_image(img)
            
            logger.info(f"Image preprocessing completed. Applied: {applied_steps}")
            
            return preprocessed_bytes, applied_steps
            
        except (ImageCorruptedException, InvalidImageFormatException):
            # Re-raise known exceptions
            raise
            
        except Exception as e:
            logger.error(f"Image preprocessing failed: {str(e)}", exc_info=True)
            # Return original image as fallback
            logger.warning("Returning original image due to preprocessing failure")
            return image_data, ['preprocessing_failed_using_original']
    
    def _decode_image(self, image_data: bytes) -> np.ndarray:
        """Safely decode image from bytes"""
        try:
            # Try OpenCV decode
            nparr = np.frombuffer(image_data, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if img is not None:
                return img
            
            # Fallback: Try PIL
            logger.debug("OpenCV decode failed, trying PIL")
            pil_img = Image.open(io.BytesIO(image_data))
            img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
            
            return img
            
        except Exception as e:
            logger.error(f"Image decode failed: {str(e)}")
            raise ImageCorruptedException(
                detail="Unable to decode image",
                context={'error': str(e)}
            )
    
    def _encode_image(self, img: np.ndarray) -> bytes:
        """Encode image to bytes"""
        try:
            is_success, buffer = cv2.imencode('.png', img)
            if not is_success:
                raise ImagePreprocessingException(
                    detail="Failed to encode processed image"
                )
            return buffer.tobytes()
            
        except Exception as e:
            logger.error(f"Image encode failed: {str(e)}")
            raise ImagePreprocessingException(
                detail="Failed to encode image",
                context={'error': str(e)}
            )
    
    def _upscale_if_needed(self, img: np.ndarray) -> tuple[np.ndarray, str]:
        """
        Upscale image if resolution is too low
        Critical for low-quality receipt photos
        """
        try:
            height, width = img.shape[:2]
            min_dimension = min(width, height)
            
            # Need upscaling if smaller than target
            if min_dimension < self.target_min_dimension:
                scale_factor = self.target_min_dimension / min_dimension
                scale_factor = min(scale_factor, self.max_upscale_factor)
                
                new_width = int(width * scale_factor)
                new_height = int(height * scale_factor)
                
                # Use INTER_CUBIC for upscaling (better quality)
                upscaled = cv2.resize(
                    img, 
                    (new_width, new_height), 
                    interpolation=cv2.INTER_CUBIC
                )
                
                logger.debug(f"Upscaled from {width}x{height} to {new_width}x{new_height}")
                return upscaled, f'upscaled_to_{new_width}x{new_height}'
            
            return img, None
            
        except Exception as e:
            logger.warning(f"Upscaling failed: {str(e)}")
            return img, None
    
    def _deskew_image(self, image: np.ndarray) -> tuple[np.ndarray, float]:
        """
        Detect and correct image skew/rotation
        Critical for receipt photos taken at an angle
        """
        try:
            # Use binary image for better edge detection
            _, binary = cv2.threshold(
                image, 0, 255, 
                cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
            )
            
            # Find all non-zero points
            coords = np.column_stack(np.where(binary > 0))
            
            if len(coords) < 100:
                return image, 0.0
            
            # Get minimum area rectangle
            angle = cv2.minAreaRect(coords)[-1]
            
            # Normalize angle
            if angle < -45:
                angle = -(90 + angle)
            else:
                angle = -angle
            
            # Only deskew if angle is significant
            if abs(angle) > self.deskew_threshold:
                (h, w) = image.shape[:2]
                center = (w // 2, h // 2)
                M = cv2.getRotationMatrix2D(center, angle, 1.0)
                
                # Calculate new dimensions to avoid cropping
                cos = np.abs(M[0, 0])
                sin = np.abs(M[0, 1])
                new_w = int((h * sin) + (w * cos))
                new_h = int((h * cos) + (w * sin))
                
                # Adjust translation
                M[0, 2] += (new_w / 2) - center[0]
                M[1, 2] += (new_h / 2) - center[1]
                
                rotated = cv2.warpAffine(
                    image, M, (new_w, new_h),
                    flags=cv2.INTER_CUBIC,
                    borderMode=cv2.BORDER_REPLICATE
                )
                
                logger.debug(f"Deskewed by {angle:.1f} degrees")
                return rotated, angle
            
            return image, 0.0
            
        except Exception as e:
            logger.warning(f"Deskewing failed: {str(e)}")
            return image, 0.0
    
    def _denoise_image(self, image: np.ndarray) -> np.ndarray:
        """
        Remove noise from image
        Critical for photos taken in poor conditions
        """
        try:
            # Non-local means denoising (best for photos)
            denoised = cv2.fastNlMeansDenoising(
                image, 
                None, 
                h=10,           # Filter strength
                templateWindowSize=7, 
                searchWindowSize=21
            )
            return denoised
            
        except Exception as e:
            logger.warning(f"Denoising failed: {str(e)}")
            # Fallback to simpler method
            try:
                return cv2.medianBlur(image, 3)
            except:
                return image
    
    def _enhance_contrast(self, image: np.ndarray) -> np.ndarray:
        """
        Enhance image contrast using CLAHE
        Critical for unclear, faded receipts
        """
        try:
            # CLAHE (Contrast Limited Adaptive Histogram Equalization)
            clahe = cv2.createCLAHE(
                clipLimit=2.0,      # Higher = more contrast
                tileGridSize=(8, 8)
            )
            enhanced = clahe.apply(image)
            return enhanced
            
        except Exception as e:
            logger.warning(f"Contrast enhancement failed: {str(e)}")
            return image
    
    def _apply_adaptive_threshold(self, image: np.ndarray) -> np.ndarray:
        """
        Apply adaptive thresholding for binarization
        Handles varying lighting conditions across the image
        """
        try:
            # Adaptive threshold works best for receipts with uneven lighting
            thresh = cv2.adaptiveThreshold(
                image,
                255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY,
                blockSize=11,  # Size of neighborhood
                C=2            # Constant subtracted from mean
            )
            return thresh
            
        except Exception as e:
            logger.warning(f"Adaptive thresholding failed: {str(e)}")
            # Fallback to Otsu's method
            try:
                _, thresh = cv2.threshold(
                    image, 0, 255, 
                    cv2.THRESH_BINARY + cv2.THRESH_OTSU
                )
                return thresh
            except:
                return image
    
    def _morphological_cleanup(self, image: np.ndarray) -> np.ndarray:
        """
        Clean up binary image using morphological operations
        Removes small noise and connects broken text
        """
        try:
            # Remove small noise
            kernel_noise = np.ones((2, 2), np.uint8)
            cleaned = cv2.morphologyEx(
                image,
                cv2.MORPH_OPEN,
                kernel_noise,
                iterations=1
            )
            
            # Connect broken text slightly
            kernel_connect = np.ones((2, 1), np.uint8)
            cleaned = cv2.morphologyEx(
                cleaned,
                cv2.MORPH_CLOSE,
                kernel_connect,
                iterations=1
            )
            
            return cleaned
            
        except Exception as e:
            logger.warning(f"Morphological cleanup failed: {str(e)}")
            return image
    
    def _sharpen_image(self, image: np.ndarray) -> np.ndarray:
        """
        Sharpen image to improve text clarity
        Final step to make text crisp
        """
        try:
            # Gentle sharpening kernel
            kernel = np.array([
                [0, -1, 0],
                [-1, 5, -1],
                [0, -1, 0]
            ])
            
            sharpened = cv2.filter2D(image, -1, kernel)
            return sharpened
            
        except Exception as e:
            logger.warning(f"Sharpening failed: {str(e)}")
            return image


# Global instance
image_preprocessor = ImagePreprocessor()
