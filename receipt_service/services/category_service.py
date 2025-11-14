# receipt_service/services/category_service.py

import logging
from typing import List, Dict, Any, Optional
from datetime import timedelta

from django.db.models import Count, Sum
from django.utils import timezone
from django.core.cache import cache

from .receipt_model_service import model_service
from ..utils.exceptions import (
    CategoryNotFoundException,
    CategoryInactiveException,
    QuotaCalculationException
)
from shared.utils.exceptions import DatabaseOperationException

logger = logging.getLogger(__name__)


class CategoryService:
    """Category management service with analytics and user preference tracking"""
    
    CACHE_TIMEOUT = 1800  # 30 minutes
    
    def get_all_categories(self, include_inactive: bool = False) -> List[Dict[str, Any]]:
        """Get all categories with caching"""
        cache_key = f"categories_all_{include_inactive}"
        
        try:
            categories = cache.get(cache_key)
            
            if categories is None:
                try:
                    queryset = model_service.category_model.objects.all()
                    if not include_inactive:
                        queryset = queryset.filter(is_active=True)
                    
                    categories = [
                        {
                            'id': str(cat.id),
                            'name': cat.name,
                            'slug': cat.slug,
                            'icon': cat.icon,
                            'color': cat.color,
                            'is_active': cat.is_active,
                            'display_order': cat.display_order
                        }
                        for cat in queryset.order_by('display_order', 'name')
                    ]
                    
                    try:
                        cache.set(cache_key, categories, self.CACHE_TIMEOUT)
                    except Exception as e:
                        logger.warning(f"Failed to cache categories: {str(e)}")
                    
                except Exception as e:
                    logger.error(f"Failed to fetch categories: {str(e)}", exc_info=True)
                    raise DatabaseOperationException(
                        detail="Failed to retrieve categories",
                        context={'include_inactive': include_inactive}
                    )
            
            return categories
            
        except DatabaseOperationException:
            raise
        except Exception as e:
            logger.error(f"Unexpected error retrieving categories: {str(e)}", exc_info=True)
            raise DatabaseOperationException(
                detail="Unexpected error retrieving categories"
            )
    
    def get_category_by_id(self, category_id: str, check_active: bool = True):
        """Get single category by ID"""
        try:
            query_filters = {'id': category_id}
            if check_active:
                query_filters['is_active'] = True
            
            category = model_service.category_model.objects.get(**query_filters)
            
            return category
            
        except model_service.category_model.DoesNotExist:
            if check_active:
                # Check if exists but inactive
                try:
                    inactive = model_service.category_model.objects.get(
                        id=category_id, 
                        is_active=False
                    )
                    raise CategoryInactiveException(
                        detail=f"Category '{inactive.name}' is inactive",
                        context={'category_id': category_id}
                    )
                except model_service.category_model.DoesNotExist:
                    pass
            
            raise CategoryNotFoundException(
                detail="Category not found",
                context={'category_id': category_id}
            )
    
    def get_user_category_preferences(self, user, limit: int = 10) -> List[Dict[str, Any]]:
        """Get user's most used categories"""
        cache_key = f"user_categories_{user.id}_{limit}"
        
        try:
            preferences = cache.get(cache_key)
            
            if preferences is None:
                try:
                    user_prefs = model_service.user_category_preference_model.objects.filter(
                        user=user
                    ).select_related('category').filter(
                        category__is_active=True
                    ).order_by('-usage_count', '-last_used')[:limit]
                    
                    preferences = [
                        {
                            'category': {
                                'id': str(pref.category.id),
                                'name': pref.category.name,
                                'slug': pref.category.slug,
                                'icon': pref.category.icon,
                                'color': pref.category.color
                            },
                            'usage_count': pref.usage_count,
                            'last_used': pref.last_used.isoformat() if pref.last_used else None
                        }
                        for pref in user_prefs
                    ]
                    
                    try:
                        cache.set(cache_key, preferences, self.CACHE_TIMEOUT // 2)
                    except Exception as e:
                        logger.warning(f"Failed to cache preferences: {str(e)}")
                    
                except Exception as e:
                    logger.error(f"Failed to fetch preferences for user {user.id}: {str(e)}", exc_info=True)
                    raise DatabaseOperationException(
                        detail="Failed to retrieve user preferences",
                        context={'user_id': str(user.id)}
                    )
            
            return preferences
            
        except DatabaseOperationException:
            raise
        except Exception as e:
            logger.error(f"Unexpected error getting preferences: {str(e)}", exc_info=True)
            raise DatabaseOperationException(
                detail="Unexpected error retrieving preferences"
            )
    
    def update_user_category_usage(self, user, category) -> None:
        """Update user's category usage statistics"""
        try:
            # Verify category is active
            if not category.is_active:
                raise CategoryInactiveException(
                    detail=f"Cannot update usage for inactive category '{category.name}'",
                    context={'category_id': str(category.id)}
                )
            
            preference, created = model_service.user_category_preference_model.objects.get_or_create(
                user=user,
                category=category,
                defaults={'usage_count': 0}
            )
            
            preference.increment_usage()
            
            # Invalidate caches
            cache_keys = [
                f"user_categories_{user.id}_10",
                f"user_category_stats_{user.id}_12",
                f"user_category_stats_{user.id}_6"
            ]
            
            try:
                cache.delete_many(cache_keys)
            except Exception as e:
                logger.warning(f"Failed to invalidate cache: {str(e)}")
            
            logger.info(f"Updated category usage: user {user.id}, category {category.name}")
            
        except CategoryInactiveException:
            raise
        except Exception as e:
            logger.error(f"Failed to update category usage: {str(e)}", exc_info=True)
            raise DatabaseOperationException(
                detail="Failed to update category usage",
                context={'user_id': str(user.id), 'category_id': str(category.id)}
            )
    
    def get_category_statistics(self, user, months: int = 12) -> Dict[str, Any]:
        """Get category usage statistics for user"""
        from ..utils.currency_utils import currency_manager
        from decimal import Decimal

        cache_key = f"user_category_stats_{user.id}_{months}"
        
        try:
            stats = cache.get(cache_key)
            
            if stats is None:
                # Date range
                end_date = timezone.now().date()
                start_date = end_date - timedelta(days=months * 30)
                
                # Get all ledger entries for the period
                ledger_entries = model_service.ledger_entry_model.objects.filter(
                    user=user,
                    date__gte=start_date
                ).select_related('category')
                
                # Group by category and convert currencies
                category_data = {}
                
                for entry in ledger_entries:
                    category_id = str(entry.category.id)
                    
                    if category_id not in category_data:
                        category_data[category_id] = {
                            'category': {
                                'id': category_id,
                                'name': entry.category.name,
                                'icon': entry.category.icon,
                                'color': entry.category.color
                            },
                            'total_amount': Decimal('0'),
                            'entry_count': 0,
                            'currencies': {}  # Track original currencies
                        }
                    
                    # Convert to base currency
                    converted = currency_manager.convert_to_base_currency(
                        entry.amount,
                        entry.currency
                    )
                    
                    if converted:
                        category_data[category_id]['total_amount'] += converted
                        category_data[category_id]['entry_count'] += 1
                        
                        # Track original currencies
                        if entry.currency not in category_data[category_id]['currencies']:
                            category_data[category_id]['currencies'][entry.currency] = Decimal('0')
                        category_data[category_id]['currencies'][entry.currency] += entry.amount
                    else:
                        logger.warning(
                            f"Failed to convert {entry.currency} to base currency "
                            f"for entry {entry.id}"
                        )
                
                # Calculate totals
                total_spending = sum(
                    cat['total_amount'] for cat in category_data.values()
                )
                total_entries = sum(
                    cat['entry_count'] for cat in category_data.values()
                )
                
                # Format stats with percentages
                formatted_stats = []
                for cat in category_data.values():
                    amount = cat['total_amount']
                    count = cat['entry_count']
                    percentage = (amount / total_spending * 100) if total_spending > 0 else 0
                    
                    formatted_stats.append({
                        'category': cat['category'],
                        'total_amount': float(amount),
                        'entry_count': count,
                        'percentage': round(percentage, 1),
                        'average_amount': float(amount / count) if count > 0 else 0,
                        'currencies_breakdown': {
                            curr: float(amt) 
                            for curr, amt in cat['currencies'].items()
                        }
                    })
                
                # Sort by total amount descending
                formatted_stats.sort(key=lambda x: x['total_amount'], reverse=True)
                
                stats = {
                    'period_months': months,
                    'total_spending': float(total_spending),
                    'total_entries': total_entries,
                    'categories': formatted_stats,
                    'base_currency': currency_manager.BASE_CURRENCY,
                    'generated_at': timezone.now().isoformat()
                }
                
                try:
                    cache.set(cache_key, stats, self.CACHE_TIMEOUT)
                except Exception as e:
                    logger.warning(f"Failed to cache stats: {str(e)}")
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to calculate stats: {str(e)}", exc_info=True)
            raise QuotaCalculationException(
                detail="Failed to calculate category statistics",
                context={'user_id': str(user.id), 'months': months}
            )
    
    def suggest_category_for_vendor(
        self, 
        vendor_name: str, 
        user=None
    ) -> Optional[Dict[str, Any]]:
        """Suggest category based on vendor name and user history"""
        if not vendor_name or not vendor_name.strip():
            return None
        
        vendor_lower = vendor_name.lower().strip()
        
        try:
            # Check user's history first
            if user:
                try:
                    user_category = model_service.ledger_entry_model.objects.filter(
                        user=user,
                        vendor__icontains=vendor_name
                    ).values('category').annotate(
                        count=Count('id')
                    ).order_by('-count').first()
                    
                    if user_category:
                        try:
                            category = model_service.category_model.objects.get(
                                id=user_category['category'],
                                is_active=True
                            )
                            return {
                                'id': str(category.id),
                                'name': category.name,
                                'confidence': 0.9,
                                'reason': 'Based on your previous transactions'
                            }
                        except model_service.category_model.DoesNotExist:
                            pass
                except Exception as e:
                    logger.warning(f"Failed to check user history: {str(e)}")
            
            # Fallback to keyword matching
            category_keywords = {
                'food-dining': ['restaurant', 'cafe', 'diner', 'pizza', 'burger', 'sushi', 'bar', 'grill'],
                'groceries': ['supermarket', 'grocery', 'market', 'walmart', 'target', 'costco'],
                'gas-fuel': ['shell', 'chevron', 'exxon', 'bp', 'gas', 'fuel', 'station'],
                'transportation': ['uber', 'lyft', 'taxi', 'metro', 'bus', 'train', 'parking'],
                'healthcare': ['hospital', 'clinic', 'pharmacy', 'doctor', 'medical', 'dental'],
                'shopping': ['mall', 'store', 'shop', 'amazon', 'retail', 'clothing'],
                'utilities': ['electric', 'power', 'water', 'internet', 'phone', 'cable'],
                'entertainment': ['cinema', 'movie', 'theater', 'netflix', 'spotify', 'game']
            }
            
            for category_slug, keywords in category_keywords.items():
                for keyword in keywords:
                    if keyword in vendor_lower:
                        try:
                            category = model_service.category_model.objects.get(
                                slug=category_slug,
                                is_active=True
                            )
                            return {
                                'id': str(category.id),
                                'name': category.name,
                                'confidence': 0.7,
                                'reason': f'Keyword match: "{keyword}"'
                            }
                        except model_service.category_model.DoesNotExist:
                            continue
            
            return None
            
        except Exception as e:
            logger.error(f"Error suggesting category for '{vendor_name}': {str(e)}")
            return None
