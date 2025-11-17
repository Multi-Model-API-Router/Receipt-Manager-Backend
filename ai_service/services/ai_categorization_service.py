import json
import time
from typing import Dict, Any, List, Optional
from django.conf import settings
from decimal import Decimal
import logging
from shared.utils.circuit_breaker import circuit_breaker, CircuitBreakerError
from ..utils.exceptions import (
    GeminiServiceException,
    CategoryPredictionException,
    ModelLoadingException,
    ModelPredictionException,
    ExternalServiceException,
)
from shared.utils.exceptions import DatabaseOperationException
from .cache_service import ai_cache_service  # ADD THIS IMPORT
from ..utils.rate_limiter import rate_limiter  # ADD THIS IMPORT
from .ai_import_service import service_import


logger = logging.getLogger(__name__)


class AICategorizationService:
    """
    AI-powered receipt categorization service using Google Gemini
    With graceful fallback when AI is unavailable
    """
    
    def __init__(self):
        self.confidence_scorer = ConfidenceScorer()
        
        # Configuration - USE AI_SERVICE SETTINGS
        ai_config = getattr(settings, 'AI_SERVICE', {})
        self.model_name = ai_config.get('CATEGORIZATION_MODEL', 'gemini-2.5-flash')
        self.min_confidence_threshold = ai_config.get('CONFIDENCE_THRESHOLD_CATEGORIZATION', 0.5)  # Lowered for fallback
        self.enable_caching = ai_config.get('ENABLE_CACHING', True)
        
        # Specific categorization timeout
        self.categorization_timeout = 30  # 30 seconds for free tier
        
        # Initialize Gemini client (may fail, that's OK)
        self._gemini_client = None
        self._available_categories = None
        
        try:
            self._initialize_gemini_client()
            logger.info(" Gemini client initialized successfully")
        except Exception as e:
            logger.warning(f"Gemini initialization failed, will use fallback: {str(e)}")
            self._gemini_client = None
        
        # Lenient circuit breaker for free tier
        self.circuit_breaker = circuit_breaker(
            name='gemini_categorization',
            failure_threshold=3,
            recovery_timeout=60,  # 1 minute (was 5 minutes)
            expected_exceptions=(ExternalServiceException, GeminiServiceException)
        )
    
    def _initialize_gemini_client(self):
        """Initialize Google Gemini API client (NO TEST CALL)"""
        try:
            import google.generativeai as genai
            
            api_key = getattr(settings, 'GOOGLE_GEMINI_API_KEY', None)
            if not api_key:
                raise ModelLoadingException(
                    detail="Google Gemini API key not configured"
                )
            
            genai.configure(api_key=api_key)
            
            # Optimized config
            generation_config = {
                "temperature": 0.2,
                "top_p": 0.8,
                "top_k": 20,
                "max_output_tokens": 500,
                "response_mime_type": "application/json",
            }
            
            # Lenient safety
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
            
            # NO TEST - just log success
            logger.info(f" Gemini client initialized: {self.model_name}")
            
        except ImportError:
            raise ModelLoadingException(detail="google-generativeai not installed")
        except Exception as e:
            logger.error(f"Failed to init Gemini: {str(e)}")
            raise ModelLoadingException(detail="Gemini init failed")
    
    def predict_category(
        self, 
        receipt_text: str, 
        vendor_name: Optional[str] = None,
        amount: Optional[Decimal] = None, 
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Predict category for receipt using AI (NEVER FAILS - uses fallback if needed)
        
        Args:
            receipt_text: Cleaned OCR text from receipt
            vendor_name: Extracted vendor name (optional)
            amount: Receipt amount (optional)
            user_id: User ID for personalization (optional)
            
        Returns:
            Dictionary containing prediction results and metadata
            ALWAYS returns a valid prediction (uses fallback if AI fails)
        """
        start_time = time.time()
        
        try:
            # Validate input
            if not receipt_text or len(receipt_text.strip()) < 10:
                logger.warning("Insufficient receipt text, using fallback")
                return self._fallback_prediction(receipt_text, vendor_name, amount)
            
            # Create content hash for caching
            text_hash = ai_cache_service.create_content_hash(receipt_text)
            
            # Check cache first (if enabled)
            if self.enable_caching:
                cached_result = ai_cache_service.get_categorization_result(text_hash, user_id)
                if cached_result:
                    logger.info(f"Category prediction retrieved from cache")
                    cached_result['from_cache'] = True
                    return cached_result
            
            # Check if Gemini is available
            if not self._gemini_client:
                logger.warning("Gemini client not available, using fallback")
                return self._fallback_prediction(receipt_text, vendor_name, amount)
            
            # Check rate limits
            rate_check = rate_limiter.check_rate_limit('gemini_api', user_id)
            if not rate_check['allowed']:
                logger.warning(f"Rate limit exceeded, using fallback")
                return self._fallback_prediction(receipt_text, vendor_name, amount)
            
            # Get available categories
            categories = self._get_available_categories()
            if not categories:
                logger.warning("No categories available, using fallback")
                return self._fallback_prediction(receipt_text, vendor_name, amount)
            
            # Get user preferences
            user_preferences = self._get_user_category_preferences(user_id) if user_id else None
            
            # Try AI prediction
            try:
                raw_prediction = self._generate_prediction_with_gemini(
                    receipt_text[:500],  # Limit for free tier
                    vendor_name, 
                    amount, 
                    categories[:20],  # Limit categories
                    user_preferences
                )
                
                # Process prediction
                processed_prediction = self._process_prediction_result(raw_prediction, categories)
                
                # Calculate confidence
                confidence_scores = self._calculate_categorization_confidence(
                    processed_prediction, receipt_text, vendor_name
                )
                
                # Build result
                processing_time = time.time() - start_time
                result = {
                    'predicted_category_id': processed_prediction['category_id'],
                    'confidence_score': round(confidence_scores['overall_confidence'], 3),
                    'reasoning': processed_prediction['reasoning'],
                    'alternative_predictions': processed_prediction.get('alternatives', []),
                    'model_version': self.model_name,
                    'processing_time_seconds': round(processing_time, 2),
                    'input_features': {
                        'text_length': len(receipt_text),
                        'has_vendor': bool(vendor_name),
                        'has_amount': bool(amount),
                        'personalized': bool(user_preferences)
                    },
                    'confidence_breakdown': confidence_scores,
                    'from_cache': False,
                    'text_hash': text_hash,
                    'method': 'gemini_ai',
                    'processed_at': time.time()
                }
                
                # Cache result
                if self.enable_caching:
                    try:
                        ai_cache_service.set_categorization_result(text_hash, result, user_id)
                    except Exception as cache_error:
                        logger.warning(f"Failed to cache result: {str(cache_error)}")
                
                logger.info(
                    f"Gemini prediction: {processed_prediction.get('category_name', 'Unknown')} "
                    f"(confidence: {confidence_scores['overall_confidence']:.2f})"
                )
                
                return result
                
            except CircuitBreakerError as e:
                logger.warning(f"Circuit breaker open, using fallback: {str(e)}")
                return self._fallback_prediction(receipt_text, vendor_name, amount)
                
            except (GeminiServiceException, ModelPredictionException) as e:
                logger.warning(f"Gemini prediction failed, using fallback: {str(e)}")
                return self._fallback_prediction(receipt_text, vendor_name, amount)
            
        except Exception as e:
            # Catch-all: NEVER let categorization fail the pipeline
            logger.error(f"Unexpected categorization error: {str(e)}", exc_info=True)
            return self._fallback_prediction(receipt_text, vendor_name, amount)
    
    def _fallback_prediction(
        self,
        receipt_text: str,
        vendor_name: Optional[str],
        amount: Optional[Decimal]
    ) -> Dict[str, Any]:
        """
        Simple keyword-based fallback categorization
        """
        text_lower = (receipt_text + ' ' + (vendor_name or '')).lower()
        
        # Simple keyword rules for your categories
        category_keywords = {
            'Food & Dining': ['restaurant', 'cafe', 'pizza', 'burger', 'starbucks', 'mcdonald', 'dining'],
            'Groceries': ['grocery', 'supermarket', 'walmart', 'target', 'kroger', 'food', 'market'],
            'Transportation': ['uber', 'lyft', 'taxi', 'transit', 'bus', 'parking'],
            'Gas & Fuel': ['gas', 'fuel', 'shell', 'chevron', 'exxon', 'bp'],
            'Healthcare': ['pharmacy', 'cvs', 'walgreens', 'doctor', 'hospital', 'medical'],
            'Shopping': ['amazon', 'mall', 'store', 'retail', 'ebay', 'best buy'],
            'Utilities': ['electric', 'water', 'utility', 'power', 'bill'],
            'Entertainment': ['movie', 'netflix', 'spotify', 'theater', 'game'],
            'Travel': ['hotel', 'airline', 'flight', 'airbnb', 'booking'],
            'Office Supplies': ['staples', 'office depot', 'paper', 'printer'],
            'Insurance': ['insurance', 'geico', 'state farm', 'allstate', 'policy'],
            'Education': ['school', 'university', 'tuition', 'textbook', 'course'],
            'Personal Care': ['salon', 'spa', 'barber', 'beauty', 'cosmetic'],
            'Home & Garden': ['home depot', 'lowes', 'hardware', 'garden', 'furniture'],
            'Subscriptions': ['subscription', 'monthly', 'membership', 'prime'],
        }
        
        # Get available categories
        categories = self._get_available_categories()
        if not categories:
            return self._default_other_category()
        
        # Score each category
        best_category = None
        max_score = 0
        
        for category in categories:
            category_name = category.get('name', '')
            keywords = category_keywords.get(category_name, [])
            
            score = sum(1 for keyword in keywords if keyword in text_lower)
            
            if score > max_score:
                max_score = score
                best_category = category
        
        # Use 'Other' if no match found
        if not best_category or max_score == 0:
            best_category = next(
                (cat for cat in categories if cat.get('name') == 'Other'),
                categories[0] if categories else None
            )
            max_score = 0
        
        if not best_category:
            return self._default_other_category()
        
        # Calculate confidence
        confidence = min(0.75, 0.40 + (max_score * 0.10))
        
        logger.info(
            f"Fallback: {best_category.get('name')} "
            f"(confidence: {confidence:.2f}, matches: {max_score})"
        )
        
        return {
            'predicted_category_id': best_category.get('id'),
            'confidence_score': round(confidence, 3),
            'reasoning': f"Keyword match: {best_category.get('name')} ({max_score} keywords matched)",
            'alternative_predictions': [],
            'model_version': 'fallback-keyword',
            'processing_time_seconds': 0,
            'input_features': {
                'text_length': len(receipt_text) if receipt_text else 0,
                'has_vendor': bool(vendor_name),
                'has_amount': bool(amount),
            },
            'from_cache': False,
            'method': 'keyword_fallback',
            'processed_at': time.time()
        }

    def _default_other_category(self) -> Dict[str, Any]:
        """Return default 'Other' category prediction"""
        return {
            'predicted_category_id': None,
            'confidence_score': 0.30,
            'reasoning': 'Default category (no match found)',
            'alternative_predictions': [],
            'model_version': 'fallback-default',
            'processing_time_seconds': 0,
            'from_cache': False,
            'method': 'default_fallback',
            'processed_at': time.time()
        }
    
    def _get_available_categories(self) -> List[Dict[str, Any]]:
        """
        Get available categories for prediction with caching
        
        Raises:
            DatabaseOperationException: If category retrieval fails
        """
        try:
            # Check cache first
            if self.enable_caching and self._available_categories is None:
                cached_categories = ai_cache_service.get_available_categories()
                if cached_categories:
                    self._available_categories = cached_categories
                    return self._available_categories
            
            # Return cached in-memory categories
            if self._available_categories is not None:
                return self._available_categories
            
            # Get categories from receipt service
            category_service = service_import.category_service
            categories = category_service.get_all_categories(include_inactive=False)
            
            # Cache the result
            self._available_categories = categories
            if self.enable_caching:
                ai_cache_service.set_available_categories(categories)
            
            return categories
            
        except Exception as e:
            logger.error(f"Failed to get available categories: {str(e)}")
            raise DatabaseOperationException(
                detail="Failed to retrieve categories for prediction",
                context={'error': str(e)}
            )
    
    def _get_user_category_preferences(self, user_id: str) -> Optional[List[Dict]]:
        """
        Get user category preferences for personalization with caching
        Does not raise exceptions - returns None if unavailable
        """
        try:
            # Check cache first
            if self.enable_caching:
                cached_prefs = ai_cache_service.get_user_category_preferences(user_id)
                if cached_prefs:
                    return cached_prefs
            
            # Get user preferences from receipt service
            from auth_service.services.auth_model_service import model_service
            user_model = model_service.user_model
            user = user_model.objects.get(id=user_id)
            
            category_service = service_import.category_service
            preferences = category_service.get_user_category_preferences(user, limit=10)
            
            # Cache preferences
            if self.enable_caching:
                ai_cache_service.set_user_category_preferences(user_id, preferences)
            
            return preferences
            
        except Exception as e:
            logger.warning(f"Failed to get user preferences for {user_id}: {str(e)}")
            return None
    
    def _generate_prediction_with_gemini(
        self, 
        receipt_text: str, 
        vendor_name: Optional[str],
        amount: Optional[Decimal], 
        categories: List[Dict],
        user_preferences: Optional[List[Dict]]
    ) -> Dict[str, Any]:
        """
        Generate category prediction using Gemini API with circuit breaker
        
        Raises:
            CircuitBreakerError: If circuit breaker is open
            GeminiServiceException: If Gemini API fails
            ModelPredictionException: If prediction generation fails
        """
        try:
            return self.circuit_breaker.call(
                self._perform_gemini_api_call,
                receipt_text, vendor_name, amount, categories, user_preferences
            )
        except CircuitBreakerError:
            # Let circuit breaker errors propagate (will use fallback)
            raise
        except Exception as e:
            if "circuit breaker" in str(e).lower():
                raise CircuitBreakerError(
                    circuit_name='gemini_categorization',
                    message="Gemini service unavailable"
                )
            raise GeminiServiceException(
                detail="Gemini AI service error",
                context={'error': str(e)}
            )
    
    def _perform_gemini_api_call(
    self, 
    receipt_text: str, 
    vendor_name: Optional[str],
    amount: Optional[Decimal], 
    categories: List[Dict],
    user_preferences: Optional[List[Dict]]
) -> Dict[str, Any]:
        """Perform actual Gemini API call"""
        try:
            from google.api_core import exceptions as gcp_exceptions
            
            # Build prompt
            prompt = self._build_categorization_prompt(
                receipt_text, vendor_name, amount, categories, user_preferences
            )
            
            # Generate response
            response = self._gemini_client.generate_content(
                prompt,
                request_options={"timeout": self.categorization_timeout}
            )
            
            # Check for blocking
            if hasattr(response, 'prompt_feedback'):
                feedback = response.prompt_feedback
                if hasattr(feedback, 'block_reason') and feedback.block_reason:
                    logger.error(f"Content blocked: {feedback.block_reason}")
                    raise ModelPredictionException(
                        detail=f"Content blocked: {feedback.block_reason}"
                    )
            
            # Check response
            if not response.text:
                logger.error("Empty Gemini response")
                raise ModelPredictionException(detail="Empty response")
            
            # Strip markdown formatting (``````)
            response_text = response.text.strip()

            if response_text.startswith('```json'):
                response_text = response_text[7:]  # Remove ```json

            if response_text.startswith('```'):
                response_text = response_text[3:]  # Remove starting ```

            if response_text.endswith('```'):
                response_text = response_text[:-3]  # Remove ending ```

            response_text = response_text.strip()
            
            # Parse JSON
            try:
                parsed = json.loads(response_text)
                logger.info("Successfully parsed JSON")
                return parsed
            except json.JSONDecodeError as e:
                logger.warning(f"JSON parse failed: {str(e)}")
                logger.debug(f"Response text: {response_text[:200]}")
                return self._fallback_parse_gemini_response(response_text)
                
        except gcp_exceptions.ServiceUnavailable:
            raise GeminiServiceException(detail="Gemini API unavailable")
        except gcp_exceptions.DeadlineExceeded:
            raise GeminiServiceException(detail=f"Timeout ({self.categorization_timeout}s)")
        except gcp_exceptions.ResourceExhausted:
            raise GeminiServiceException(detail="API quota exhausted")
        except gcp_exceptions.NotFound:
            raise GeminiServiceException(detail=f"Model {self.model_name} not found")
        except Exception as e:
            logger.error(f"Gemini error: {str(e)}", exc_info=True)
            raise GeminiServiceException(detail=f"Gemini error: {str(e)}")
    
    def _build_categorization_prompt(self, receipt_text: str, vendor_name: Optional[str],
                                   amount: Optional[Decimal], categories: List[Dict],
                                   user_preferences: Optional[List[Dict]]) -> str:
        """Build optimized prompt for Gemini categorization"""
        
        # Build category list (limit to prevent token overflow)
        category_list = []
        for cat in categories[:50]:  # Limit to 50 categories
            desc = cat.get('description', 'General category')
            category_list.append(f"- {cat['name']} (ID: {cat['id']}): {desc[:100]}")  # Truncate descriptions
        
        # Build user preferences context
        preference_context = ""
        if user_preferences:
            top_categories = [pref['category']['name'] for pref in user_preferences[:5]]
            preference_context = f"\n\nUser's frequently used categories: {', '.join(top_categories)}"
        
        # Additional context
        context_info = []
        if vendor_name:
            context_info.append(f"Vendor: {vendor_name}")
        if amount:
            context_info.append(f"Amount: ${amount}")
        
        context_str = "\n".join(context_info) if context_info else "No additional context provided"
        
        # Truncate receipt text if too long
        max_text_length = 2000
        truncated_text = receipt_text[:max_text_length]
        if len(receipt_text) > max_text_length:
            truncated_text += "... (truncated)"
        
        prompt = f"""You are an expert at categorizing receipts and expenses. Analyze the receipt text and categorize it appropriately.

Available Categories:
{chr(10).join(category_list)}

Receipt Text:
{truncated_text}

Additional Context:
{context_str}{preference_context}

Please analyze this receipt and provide a categorization in the following JSON format:
{{
    "category_id": "UUID of the most appropriate category",
    "confidence": 0.85,
    "reasoning": "Brief explanation of why this category was chosen",
    "alternatives": [
        {{
            "category_id": "UUID of alternative category",
            "confidence": 0.65,
            "reasoning": "Why this could also be appropriate"
        }}
    ],
    "key_indicators": ["list of text patterns that influenced the decision"]
}}

Guidelines:
1. Choose the most specific and appropriate category
2. Confidence should reflect how certain you are (0.0 to 1.0)
3. Provide 1-3 alternative categories if applicable
4. Base your decision on vendor name, receipt content, and amount when available
5. Consider user preferences but prioritize accuracy
6. If unsure, prefer broader categories over specific ones

Response (JSON only, no additional text):"""
        
        return prompt
    
    def _fallback_parse_gemini_response(self, response_text: str) -> Dict[str, Any]:
        """
        Fallback parser for non-JSON Gemini responses
        Extracts category info from text
        """
        try:
            import re
            
            # Try to extract category info from text
            categories = self._get_available_categories()
            
            # Look for category names in response
            response_lower = response_text.lower()
            
            for category in categories:
                name = category.get('name', '').lower()
                if name in response_lower:
                    logger.info(f"Fallback parser found category: {category.get('name')}")
                    return {
                        'category_id': category.get('id'),
                        'confidence': 0.7,
                        'reasoning': f"Extracted from text: {name}",
                        'alternatives': []
                    }
            
            # If nothing found, return first category
            if categories:
                logger.warning("Fallback parser using default category")
                return {
                    'category_id': categories[0].get('id'),
                    'confidence': 0.5,
                    'reasoning': 'Default (parsing failed)',
                    'alternatives': []
                }
            
            # Ultimate fallback
            raise ModelPredictionException(detail="Could not parse response")
            
        except Exception as e:
            logger.error(f"Fallback parser failed: {str(e)}")
            raise ModelPredictionException(detail="Response parsing failed")
    
    def _process_prediction_result(self, raw_prediction: Dict, categories: List[Dict]) -> Dict[str, Any]:
        """
        Process and validate prediction result
        
        Raises:
            CategoryPredictionException: If prediction is invalid
        """
        try:
            # Validate required fields
            if 'category_id' not in raw_prediction:
                raise CategoryPredictionException(
                    detail="Missing category_id in prediction result",
                    context={'prediction_keys': list(raw_prediction.keys())}
                )
            
            predicted_category_id = str(raw_prediction['category_id']).strip()
            
            # Validate category exists
            category_exists = any(str(cat['id']) == predicted_category_id for cat in categories)
            if not category_exists:
                # Fallback to first available category
                fallback_category = categories[0] if categories else None
                if fallback_category:
                    logger.warning(f"Invalid category ID {predicted_category_id}, using fallback: {fallback_category['id']}")
                    predicted_category_id = str(fallback_category['id'])
                else:
                    raise CategoryPredictionException(
                        detail="Invalid category ID and no fallback available",
                        context={'predicted_id': predicted_category_id, 'available_count': len(categories)}
                    )
            
            # Process alternatives
            alternatives = []
            for alt in raw_prediction.get('alternatives', [])[:3]:  # Max 3 alternatives
                if isinstance(alt, dict) and 'category_id' in alt:
                    alt_id = str(alt['category_id']).strip()
                    # Validate alternative category exists
                    if any(str(cat['id']) == alt_id for cat in categories):
                        alternatives.append({
                            'category_id': alt_id,
                            'confidence': float(alt.get('confidence', 0.5)),
                            'reasoning': alt.get('reasoning', '')[:200]  # Truncate reasoning
                        })
            
            return {
                'category_id': predicted_category_id,
                'confidence': min(1.0, max(0.0, float(raw_prediction.get('confidence', 0.5)))),  # Clamp to 0-1
                'reasoning': raw_prediction.get('reasoning', 'AI categorization')[:500],  # Truncate reasoning
                'alternatives': alternatives,
                'key_indicators': raw_prediction.get('key_indicators', [])[:10]  # Limit indicators
            }
            
        except CategoryPredictionException:
            raise
        except Exception as e:
            raise CategoryPredictionException(
                detail="Failed to process prediction result",
                context={'error': str(e), 'raw_prediction': str(raw_prediction)[:200]}
            )
    
    def _calculate_categorization_confidence(self, prediction: Dict, receipt_text: str, 
                                           vendor_name: Optional[str]) -> Dict[str, float]:
        """Calculate confidence scores - does not raise exceptions"""
        try:
            model_confidence = prediction.get('confidence', 0.5)
            
            # Text relevance score
            text_relevance = self._calculate_text_relevance(receipt_text, prediction.get('key_indicators', []))
            
            # Pattern matches
            pattern_matches = prediction.get('key_indicators', [])
            
            # Historical accuracy (could be enhanced with actual feedback data)
            historical_accuracy = 0.8
            
            overall_confidence = self.confidence_scorer.calculate_categorization_confidence(
                model_confidence, text_relevance, pattern_matches, historical_accuracy
            )
            
            return {
                'overall_confidence': round(overall_confidence, 3),
                'model_confidence': round(model_confidence, 3),
                'text_relevance': round(text_relevance, 3),
                'pattern_strength': round(min(1.0, len(pattern_matches) / 3), 3),
                'historical_accuracy': round(historical_accuracy, 3)
            }
        except Exception as e:
            logger.warning(f"Confidence calculation failed: {str(e)}")
            return {
                'overall_confidence': round(prediction.get('confidence', 0.5), 3),
                'model_confidence': round(prediction.get('confidence', 0.5), 3),
                'text_relevance': 0.5,
                'pattern_strength': 0.5,
                'historical_accuracy': 0.5
            }
    
    def _calculate_text_relevance(self, receipt_text: str, key_indicators: List[str]) -> float:
        """Calculate how relevant the text is to the prediction"""
        if not key_indicators:
            return 0.5
        
        try:
            text_lower = receipt_text.lower()
            relevant_indicators = sum(1 for indicator in key_indicators if indicator.lower() in text_lower)
            return min(1.0, relevant_indicators / len(key_indicators))
        except Exception:
            return 0.5
    
    def health_check(self) -> Dict[str, Any]:
        """Perform health check for categorization service"""
        health_status = {
            'service': 'ai_categorization_service',
            'status': 'healthy',
            'checks': {},
            'timestamp': time.time()
        }
        
        try:
            # Check Gemini client
            if self._gemini_client:
                health_status['checks']['gemini_client'] = 'initialized'
            else:
                health_status['checks']['gemini_client'] = 'not_initialized'
                health_status['status'] = 'unhealthy'
            
            # Check circuit breaker
            try:
                circuit_metrics = self.circuit_breaker.get_metrics()
                health_status['checks']['circuit_breaker'] = {
                    'state': circuit_metrics.get('current_state', 'unknown'),
                    'is_healthy': circuit_metrics.get('health', {}).get('is_healthy', False)
                }
                
                if not circuit_metrics.get('health', {}).get('is_healthy', False):
                    health_status['status'] = 'degraded'
            except Exception as e:
                health_status['checks']['circuit_breaker'] = f'error: {str(e)}'
                health_status['status'] = 'degraded'
            
            # Check categories availability
            try:
                categories = self._get_available_categories()
                health_status['checks']['categories'] = f"available ({len(categories)} categories)"
            except Exception as e:
                health_status['checks']['categories'] = f'error: {str(e)}'
                health_status['status'] = 'degraded'
            
            # Check cache
            if self.enable_caching:
                try:
                    test_hash = ai_cache_service.create_content_hash("test")
                    health_status['checks']['cache'] = 'enabled and functional'
                except Exception as e:
                    health_status['checks']['cache'] = f'enabled but error: {str(e)}'
                    health_status['status'] = 'degraded'
            else:
                health_status['checks']['cache'] = 'disabled'
            
            # Check rate limiter
            try:
                usage_stats = rate_limiter.get_usage_stats('gemini_api')
                health_status['checks']['rate_limiter'] = {
                    'remaining_minute': usage_stats.get('remaining_minute', 'unknown'),
                    'remaining_daily': usage_stats.get('remaining_daily', 'unknown'),
                    'usage_percentage': round((usage_stats.get('current_daily', 0) / usage_stats.get('limit_daily', 1)) * 100, 2)
                }
                
                # Warn if usage is high
                if usage_stats.get('remaining_daily', 1000) < 100:
                    health_status['warnings'] = health_status.get('warnings', [])
                    health_status['warnings'].append('Daily API quota running low')
                    
            except Exception as e:
                health_status['checks']['rate_limiter'] = f'error: {str(e)}'
            
            return health_status
            
        except Exception as e:
            logger.error(f"Categorization service health check failed: {str(e)}")
            return {
                'service': 'ai_categorization_service',
                'status': 'unhealthy',
                'error': str(e),
                'timestamp': time.time()
            }
