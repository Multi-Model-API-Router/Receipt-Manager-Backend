# ai_service/services/gemini_extraction_service.py

import json
import logging
from typing import Dict, Any, List
from django.conf import settings
import google.generativeai as genai

from ..utils.exceptions import (
    GeminiServiceException,
    DataExtractionException,
    ModelLoadingException,
)

logger = logging.getLogger(__name__)


class GeminiExtractionService:
    """
    Use Gemini AI to extract structured data AND categorize in ONE call
    This saves API credits and provides better context for categorization
    """
    
    def __init__(self):
        self.model_name = 'gemini-2.0-flash-exp'
        self.timeout = 30
        self._gemini_client = None
        self._initialization_error = None
        
        # Initialize Gemini
        self._initialize_client()
    
    def _initialize_client(self) -> None:
        """Initialize Gemini client"""
        try:
            api_key = getattr(settings, 'GOOGLE_GEMINI_API_KEY', None)
            if not api_key:
                self._initialization_error = "GOOGLE_GEMINI_API_KEY not configured"
                logger.error(self._initialization_error)
                return
            
            genai.configure(api_key=api_key)
            
            generation_config = {
                "temperature": 0.1,  # Low for consistent extraction
                "top_p": 0.8,
                "top_k": 20,
                "max_output_tokens": 1500,
                "response_mime_type": "application/json",
            }
            
            safety_settings = [
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_ONLY_HIGH"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_ONLY_HIGH"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_ONLY_HIGH"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_ONLY_HIGH"},
            ]
            
            self._gemini_client = genai.GenerativeModel(
                model_name=self.model_name,
                generation_config=generation_config,
                safety_settings=safety_settings
            )
            
            logger.info(f"[OK] Gemini extraction service initialized: {self.model_name}")
            
        except Exception as e:
            self._initialization_error = str(e)
            logger.error(f"Failed to initialize Gemini: {str(e)}", exc_info=True)
            self._gemini_client = None
    
    def extract_and_categorize(
        self,
        ocr_text: str,
        receipt_id: str,
        user_id: str,
        categories: List[Dict[str, str]]
    ) -> Dict[str, Any]:
        """
        Extract structured data AND categorize in ONE Gemini API call
        
        Args:
            ocr_text: Raw OCR extracted text
            receipt_id: Receipt identifier
            user_id: User identifier
            categories: List of available categories with id and name
            
        Returns:
            Dict with extracted_data and category_prediction
            
        Raises:
            GeminiServiceException: If Gemini API fails
            DataExtractionException: If extraction fails
        """
        try:
            # Check if client is initialized
            if not self._gemini_client:
                raise ModelLoadingException(
                    detail="Gemini client not initialized",
                    context={'error': self._initialization_error}
                )
            
            # Validate input
            if not ocr_text or len(ocr_text.strip()) < 25:

                logger.warning(
                    f"OCR text too short for receipt {receipt_id}: "
                    f"{len(ocr_text)} chars"
                ) 
                return self._get_fallback_extraction_result(
                    reason='Insufficient OCR text extracted'
                )
            
            # Build comprehensive prompt for extraction + categorization
            prompt = self._build_extraction_prompt(ocr_text, categories)
            
            logger.info(
                f"Calling Gemini for extraction+categorization (receipt: {receipt_id})"
            )
            
            # Make single API call
            try:
                response = self._gemini_client.generate_content(
                    prompt,
                    request_options={"timeout": self.timeout}
                )
            except Exception as api_error:
                logger.error(f"Gemini API error: {str(api_error)}", exc_info=True)
                return self._get_fallback_extraction_result(
                    reason=f'Gemini API error: {str(api_error)}',
                )
            
            # Check response
            if not response or not response.text:
                logger.error("Empty response from Gemini")
                return self._get_fallback_extraction_result(
                    reason='Empty response from AI'
                )
            
            # Parse response (strip markdown wrapper if present)
            response_text = self._strip_markdown(response.text)
            
            # Parse JSON
            try:
                result = json.loads(response_text)
            except json.JSONDecodeError as json_error:
                logger.error(f"Failed to parse Gemini JSON: {str(json_error)}")
                logger.debug(f"Response text: {response_text[:500]}")
                # RETURN FALLBACK, DON'T RAISE!
                return self._get_fallback_extraction_result(
                    reason='Invalid AI response format'
                )
            
            # Validate result structure
            try:
                self._validate_result(result, receipt_id)
            except Exception as validation_error:
                logger.error(f"Result validation failed: {str(validation_error)}")
                # RETURN FALLBACK, DON'T RAISE!
                return self._get_fallback_extraction_result(
                    reason='Invalid extraction result structure',
                )
            
            logger.info(
                f"[OK] Gemini extraction completed for receipt {receipt_id}: "
                f"vendor={result['extracted_data'].get('vendor_name', 'Unknown')}, "
                f"category={result['category_prediction'].get('category_name', 'Unknown')}"
            )
            
            return result
            
        except (ModelLoadingException):
            # Re-raise known exceptions
            raise
            
        except Exception as unexpected_error:
            # Catch any unexpected errors and return fallback
            logger.error(
                f"Unexpected error in Gemini extraction: {str(unexpected_error)}", 
                exc_info=True
            )
            return self._get_fallback_extraction_result(
                reason=f'Unexpected error: {str(unexpected_error)}'
            )
    
    def _get_fallback_extraction_result(
        self,
        reason: str,
        details: List[str]
    ) -> Dict[str, Any]:
        """Return fallback extraction result when extraction fails"""
        return {
            'extracted_data': {
                'vendor_name': 'Unknown',
                'receipt_date': None,
                'total_amount': None,
                'currency': 'USD',
                'tax_amount': None,
                'subtotal': None,
                'line_items': [],
            },
            'category_prediction': {
                'category_id': None,
                "category_name": None,
                'confidence': 0.0,
                'reasoning': 'OCR extracted insufficient text for analysis'
            },
            'extraction_confidence': {
                'vendor_name': 0.0,
                'date': 0.0,
                'amount': 0.0,
                'overall': 0.0
            }
        }
    
    def _build_extraction_prompt(
        self, 
        ocr_text: str, 
        categories: List[Dict[str, str]]
    ) -> str:
        """Build comprehensive prompt for extraction + categorization"""
        
        # Format categories list
        if categories:
            category_list = "\n".join([
                f"- {cat['name']} (ID: {cat['id']})"
                for cat in categories[:20]  # Limit to top 20 categories
            ])
        else:
            category_list = "- No categories available"
        
        # Truncate OCR text if too long
        max_ocr_length = 3000
        ocr_text_truncated = ocr_text[:max_ocr_length]
        if len(ocr_text) > max_ocr_length:
            ocr_text_truncated += "\n... [truncated]"
        
        prompt = f"""You are an expert at analyzing receipt text and extracting structured information with high accuracy.

**Receipt OCR Text:**
{ocr_text_truncated}

**Available Categories:**
{category_list}

**Instructions:**
1. Extract ALL relevant information from the receipt text
2. Parse dates in various formats and convert to YYYY-MM-DD
3. Identify the final total amount (after tax)
4. Detect currency from symbols ($, €, £, ₹, etc) or text
5. Choose the most appropriate category based on vendor name and context
6. If information is unclear or missing, use null (not empty strings)
7. Be careful with OCR errors: O vs 0, I/l vs 1, S vs 5, etc
8. Provide confidence scores (0.0 to 1.0) for each extracted field

**Response Format (JSON only, no additional text):**
{{
  "extracted_data": {{
    "vendor_name": "string or null",
    "receipt_date": "YYYY-MM-DD or null",
    "total_amount": number or null,
    "currency": "USD" or detected code,
    "tax_amount": number or null,
    "subtotal": number or null,
    "line_items": [
      {{"description": "string", "price": number, "quantity": number}}
    ],
  }},
  "category_prediction": {{
    "category_id": "ID from categories list or null",
    "category_name": "name from list or null",
    "confidence": 0.85,
    "reasoning": "brief explanation"
  }},
  "extraction_confidence": {{
    "vendor_name": 0.9,
    "date": 0.8,
    "amount": 0.95,
    "overall": 0.88
  }}
}}

**Important:**
- Return ONLY valid JSON
- Use null for missing data, not empty strings
- Total amount should be the final amount paid
- Category must be from the provided list or null if unsure
- Confidence scores must be between 0.0 and 1.0
- Be accurate with numbers - don't confuse 0/O or 1/I

Respond ONLY with valid JSON, no additional text."""

        return prompt
    
    def _strip_markdown(self, text: str) -> str:
        """Remove markdown code block wrapper from response"""
        text = text.strip()
        
        if text.startswith('```json'):
            text = text[7:]
        elif text.startswith('```'):
            text = text[3:]
        
        if text.endswith('```'):
            text = text[:-3]
        
        return text.strip()
    
    def _validate_result(self, result: Dict[str, Any], receipt_id: str) -> None:
        """Validate Gemini response structure"""
        required_keys = ['extracted_data', 'category_prediction', 'extraction_confidence']
        
        for key in required_keys:
            if key not in result:
                raise DataExtractionException(
                    detail=f"Missing required key in response: {key}",
                    context={'receipt_id': receipt_id, 'missing_key': key}
                )
        
        # Validate extracted_data
        extracted = result['extracted_data']
        if not isinstance(extracted, dict):
            raise DataExtractionException(
                detail="extracted_data must be a dictionary",
                context={'receipt_id': receipt_id}
            )
        
        # Validate category_prediction
        category = result['category_prediction']
        if not isinstance(category, dict):
            raise DataExtractionException(
                detail="category_prediction must be a dictionary",
                context={'receipt_id': receipt_id}
            )
        
        # Validate confidence is a number
        if 'confidence' in category:
            try:
                confidence = float(category['confidence'])
                if not 0.0 <= confidence <= 1.0:
                    logger.warning(f"Confidence out of range: {confidence}")
            except (ValueError, TypeError):
                raise DataExtractionException(
                    detail="Invalid confidence score",
                    context={'receipt_id': receipt_id}
                )


# Global instance
gemini_extractor = GeminiExtractionService()
