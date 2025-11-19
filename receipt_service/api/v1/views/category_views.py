from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from shared.utils.responses import success_response
from ....services.receipt_import_service import service_import
from receipt_service.utils.exceptions import (
    CategoryNotFoundException,
    CategoryInactiveException,
    DatabaseOperationException,
    QuotaCalculationException,
    ValidationException
)
from ..serializers.category_serializers import (
    CategorySerializer,
    CategoryPreferenceSerializer,
    CategoryStatisticsSerializer,
    CategorySuggestionSerializer
)
import logging


logger = logging.getLogger(__name__)


class CategoryListView(APIView):
    """Get all available categories (matches API flow: GET /categories/v1)"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """Get all active categories"""
        try:
            category_service = service_import.category_service
            categories_data = category_service.get_all_categories(include_inactive=False)
            
            # Use serializer to format the response consistently
            categories = []
            for category_dict in categories_data:
                # Convert dict to mock object for serializer
                class MockCategory:
                    def __init__(self, data):
                        for key, value in data.items():
                            setattr(self, key, value)
                
                mock_category = MockCategory(category_dict)
                serializer = CategorySerializer(mock_category)
                categories.append(serializer.data)
            
            return success_response(
                message="Categories retrieved successfully",
                data={
                    'categories': categories,
                    'count': len(categories)
                }
            )
            
        except DatabaseOperationException as e:
            raise e
        except Exception as e:
            logger.error(f"Unexpected error getting categories: {str(e)}")
            raise DatabaseOperationException(
                detail="Failed to retrieve categories"
            )


class CategoryDetailView(APIView):
    """Get single category details"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request, category_id):
        """Get category details by ID"""
        try:
            # category_id is ALREADY a UUID object from DRF!
            # Don't convert it again!
            
            category_service = service_import.category_service
            
            # Just use category_id directly (or convert to string if service needs it)
            category = category_service.get_category_by_id(
                str(category_id),  # Convert UUID to string for service
                check_active=True
            )
            
            if not category:
                raise CategoryNotFoundException(
                    detail="Category not found",
                    context={'category_id': str(category_id)}
                )
            
            serializer = CategorySerializer(category)
            
            return success_response(
                message="Category retrieved successfully",
                data=serializer.data
            )
            
        except CategoryNotFoundException:
            raise
        except CategoryInactiveException:
            raise
        except Exception as e:
            logger.error(
                f"Unexpected error getting category details: {str(e)}", 
                exc_info=True
            )
            raise DatabaseOperationException(
                detail="Failed to retrieve category details",
                context={'category_id': str(category_id)}
            )

class CategoryUsageStatsView(APIView):
    """Get category usage statistics (matches API flow: GET /categories/v1usage-stats/)"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """Get comprehensive category usage statistics"""
        try:
            # Validate months parameter
            months = int(request.GET.get('months', 12))
            if months < 1 or months > 24:
                raise ValidationException(
                    detail="Months parameter must be between 1 and 24",
                    context={'provided_months': months, 'valid_range': '1-24'}
                )
            
            category_service = service_import.category_service
            statistics = category_service.get_category_statistics(
                request.user, 
                months=months
            )
            
            # Format statistics using serializer
            formatted_categories = []
            for category_stat in statistics.get('categories', []):
                # Create mock objects for serializer
                class MockCategoryStats:
                    def __init__(self, data):
                        self.category = type('Category', (), category_stat['category'])()
                        self.total_amount = data['total_amount']
                        self.entry_count = data['entry_count']
                        self.percentage = data['percentage']
                        self.average_amount = data['average_amount']
                
                mock_stats = MockCategoryStats(category_stat)
                serializer = CategoryStatisticsSerializer(mock_stats)
                formatted_categories.append(serializer.data)
            
            response_data = {
                'statistics': {
                    'period_months': statistics['period_months'],
                    'total_spending': statistics['total_spending'],
                    'total_entries': statistics['total_entries'],
                    'categories': formatted_categories,
                    'generated_at': statistics['generated_at']
                }
            }
            
            return success_response(
                message="Category usage statistics retrieved successfully",
                data=response_data
            )
            
        except ValidationException as e:
            raise e
        except QuotaCalculationException as e:
            raise e
        except Exception as e:
            logger.error(f"Unexpected error getting category statistics: {str(e)}")
            raise QuotaCalculationException(
                detail="Failed to calculate category statistics"
            )


class UserCategoryPreferencesView(APIView):
    """Get user's category preferences (GET /categories/v1preferences/)"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """Get user's most used categories"""
        try:
            # Validate limit parameter
            limit = int(request.GET.get('limit', 10))
            if limit < 1 or limit > 50:
                raise ValidationException(
                    detail="Limit parameter must be between 1 and 50",
                    context={'provided_limit': limit, 'valid_range': '1-50'}
                )
            
            category_service = service_import.category_service
            preferences_data = category_service.get_user_category_preferences(
                request.user, 
                limit=limit
            )
            
            # Format preferences using serializer
            preferences = []
            for pref_data in preferences_data:
                class MockPreference:
                    def __init__(self, data):
                        self.category = type('Category', (), data['category'])()
                        self.usage_count = data['usage_count']
                        self.last_used = data['last_used']
                
                mock_pref = MockPreference(pref_data)
                serializer = CategoryPreferenceSerializer(mock_pref)
                preferences.append(serializer.data)
            
            return success_response(
                message="Category preferences retrieved successfully",
                data={
                    'preferences': preferences,
                    'count': len(preferences),
                    'limit': limit
                }
            )
            
        except ValidationException as e:
            raise e
        except DatabaseOperationException as e:
            raise e
        except Exception as e:
            logger.error(f"Unexpected error getting category preferences: {str(e)}")
            raise DatabaseOperationException(
                detail="Failed to retrieve category preferences"
            )

class CategorySuggestView(APIView):
    """
    AI-powered category suggestions based on vendor name
    GET /categories/v1suggest/?vendor=Starbucks
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """Get AI category suggestions based on vendor name"""
        try:
            # Get vendor from query params
            vendor_name = request.GET.get('vendor', '').strip()
            
            if not vendor_name:
                raise ValidationException(
                    detail="Vendor name is required",
                    context={'hint': 'Add ?vendor=<vendor_name> to the URL'}
                )
            
            if len(vendor_name) < 2:
                raise ValidationException(
                    detail="Vendor name too short (minimum 2 characters)",
                    context={'provided': vendor_name}
                )
            
            # Get suggestions from service
            category_service = service_import.category_service
            suggestions = category_service.suggest_category_for_vendor(
                vendor_name=vendor_name,
                user=request.user
            )
            
            return success_response(
                message=f"Category suggestions for '{vendor_name}'",
                data={
                    'vendor': vendor_name,
                    'suggestions': suggestions
                }
            )
            
        except ValidationException:
            # Re-raise validation errors (will return 400)
            raise
        except Exception as e:
            logger.error(
                f"Error getting category suggestions: {str(e)}", 
                exc_info=True
            )
            raise DatabaseOperationException(
                detail="Failed to get category suggestions",
                context={'vendor': vendor_name if 'vendor_name' in locals() else None}
            )

class CategoryValidateView(APIView):
    """
    Validate if category exists and is active
    GET /categories/v1{category_id}/validate/
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request, category_id):
        """Validate category exists and is active"""
        try:
            # category_id is ALREADY a UUID object from DRF!
            # Just convert to string for service
            category_id_str = str(category_id)
            
            category_service = service_import.category_service
            
            # Check if category exists and is active
            try:
                category = category_service.get_category_by_id(
                    category_id_str,
                    check_active=True
                )
                
                if not category:
                    return success_response(
                        message="Category not found",
                        data={
                            'valid': False,
                            'category_id': category_id_str,
                            'reason': 'Category does not exist'
                        }
                    )
                
                # Category exists and is active
                return success_response(
                    message="Category is valid",
                    data={
                        'valid': True,
                        'category_id': category_id_str,
                        'category': {
                            'id': str(category.id),
                            'name': category.name,
                            'slug': category.slug,
                            'is_active': category.is_active,
                            'icon': category.icon,
                            'color': category.color
                        }
                    }
                )
                
            except CategoryNotFoundException:
                return success_response(
                    message="Category not found",
                    data={
                        'valid': False,
                        'category_id': category_id_str,
                        'reason': 'Category does not exist'
                    }
                )
            except CategoryInactiveException:
                return success_response(
                    message="Category is inactive",
                    data={
                        'valid': False,
                        'category_id': category_id_str,
                        'reason': 'Category is inactive/archived'
                    }
                )
            
        except Exception as e:
            logger.error(
                f"Unexpected error validating category: {str(e)}", 
                exc_info=True
            )
            raise DatabaseOperationException(
                detail="Failed to validate category",
                context={'category_id': str(category_id)}
            )
