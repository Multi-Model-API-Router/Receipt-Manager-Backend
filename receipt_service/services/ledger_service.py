# receipt_service/services/ledger_service.py

import logging
from typing import Dict, Any, Optional
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum, Count, Avg
from django.utils import timezone
from django.core.cache import cache
from ..utils.currency_utils import currency_manager
from .receipt_model_service import model_service
from ..utils.exceptions import (
    LedgerEntryNotFoundException,
    LedgerEntryAccessDeniedException,
    LedgerEntryUpdateException,
    LedgerEntryDeletionException,
    CategoryNotFoundException,
    ValidationException
)
from shared.utils.exceptions import DatabaseOperationException

logger = logging.getLogger(__name__)


class LedgerService:
    """
    Ledger management service for expense tracking and analytics
    """
    
    def __init__(self):
        self.currency_manager = currency_manager  # ← Store as instance attribute
        self.CACHE_TIMEOUT = 900
    
    def update_ledger_entry(
        self, 
        user, 
        entry_id: str, 
        update_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update existing ledger entry"""
        try:
            entry = model_service.ledger_entry_model.objects.select_related('category').get(
                id=entry_id
            )
            
            # Check user access
            if entry.user_id != user.id:
                raise LedgerEntryAccessDeniedException(
                    detail="Access denied to update this entry",
                    context={'entry_id': entry_id}
                )
            
            # Validate update data
            self._validate_update_data(update_data)
            
            with transaction.atomic():
                updated_fields = []
                
                if 'category_id' in update_data:
                    try:
                        category = model_service.category_model.objects.get(
                            id=update_data['category_id'],
                            is_active=True
                        )
                        entry.category = category
                        updated_fields.append('category')
                    except model_service.category_model.DoesNotExist:
                        raise CategoryNotFoundException(
                            detail="Category not found or inactive",
                            context={'category_id': update_data['category_id']}
                        )
                
                if 'date' in update_data:
                    entry.date = update_data['date']
                    updated_fields.append('date')
                
                if 'vendor' in update_data:
                    entry.vendor = update_data['vendor'].strip()
                    updated_fields.append('vendor')
                
                if 'amount' in update_data:
                    entry.amount = Decimal(str(update_data['amount']))
                    updated_fields.append('amount')
                
                if 'description' in update_data:
                    entry.description = update_data['description'].strip()
                    updated_fields.append('description')
                
                if 'is_business_expense' in update_data:
                    entry.is_business_expense = bool(update_data['is_business_expense'])
                    updated_fields.append('is_business_expense')
                
                if 'is_reimbursable' in update_data:
                    entry.is_reimbursable = bool(update_data['is_reimbursable'])
                    updated_fields.append('is_reimbursable')
                
                if 'tags' in update_data:
                    entry.tags = update_data['tags'] if isinstance(update_data['tags'], list) else []
                    updated_fields.append('tags')
                
                # Save changes
                if updated_fields:
                    updated_fields.append('updated_at')
                    entry.save(update_fields=updated_fields)
                    
                    # Invalidate caches
                    self._invalidate_user_caches(user.id)
                    
                    logger.info(f"Ledger entry {entry_id} updated by user {user.id}")
                
                return {
                    'entry_id': str(entry.id),
                    'updated_fields': updated_fields[:-1],
                    'message': 'Ledger entry updated successfully'
                }
                
        except model_service.ledger_entry_model.DoesNotExist:
            raise LedgerEntryNotFoundException(
                detail="Ledger entry not found",
                context={'entry_id': entry_id}
            )
        except (LedgerEntryAccessDeniedException, CategoryNotFoundException, ValidationException):
            raise
        except Exception as e:
            logger.error(f"Failed to update ledger entry {entry_id}: {str(e)}", exc_info=True)
            raise LedgerEntryUpdateException(
                detail="Failed to update ledger entry",
                context={'entry_id': entry_id}
            )
    
    def get_spending_summary(self, user, period: str = 'monthly') -> Dict[str, Any]:
        """
        Get spending summary for different time periods
        DRY implementation - single method for all periods
        """
        cache_key = f"spending_summary_{user.id}_{period}"
        
        try:
            summary = cache.get(cache_key)
            
            if summary is None:
                logger.info(f"Calculating spending summary for period: {period}")
                
                # Get date range based on period
                start_date, end_date = self._get_date_range_for_period(period)
                
                # Calculate summary (single unified method)
                summary = self._calculate_summary(user, period, start_date, end_date)
                
                logger.info(f"Summary calculated: {summary}")
                
                # Cache the result
                try:
                    cache.set(cache_key, summary, self.CACHE_TIMEOUT)
                except Exception as e:
                    logger.warning(f"Failed to cache summary: {str(e)}")
            
            return summary
            
        except ValidationException:
            raise
        except Exception as e:
            logger.error(f"Failed to get spending summary: {str(e)}", exc_info=True)
            raise DatabaseOperationException(
                detail="Failed to calculate spending summary",
                context={'user_id': str(user.id), 'period': period}
            )
    
    def _get_date_range_for_period(self, period: str) -> tuple:
        """
        Get start and end dates for different periods
        Returns (start_date, end_date)
        """
        today = timezone.now().date()
        
        if period == 'weekly':
            start_date = today - timedelta(days=today.weekday())  # Monday
            return start_date, today
        
        elif period == 'monthly':
            start_date = today.replace(day=1)
            return start_date, today
        
        elif period == 'yearly':
            start_date = today.replace(month=1, day=1)
            return start_date, today
        
        else:
            raise ValidationException(
                detail="Invalid period. Valid: weekly, monthly, yearly",
                context={'provided_period': period}
            )
    
    def _calculate_summary(
        self, 
        user, 
        period: str, 
        start_date, 
        end_date
    ) -> Dict[str, Any]:
        """
        Unified summary calculation method
        Works for all periods (weekly, monthly, yearly)
        """
        # Get entries for the period
        entries = model_service.ledger_entry_model.objects.filter(
            user=user,
            date__gte=start_date,
            date__lte=end_date
        )
        
        entry_count = entries.count()
        logger.info(f"Found {entry_count} entries for {period} summary")
        
        # Handle empty case
        if entry_count == 0:
            return {
                'period': period,
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat(),
                'total_entries': 0,
                'total_amount': 0.0,
                'formatted_total': currency_manager.format_amount(
                    Decimal('0'), 
                    currency_manager.BASE_CURRENCY
                ),
                'business_expenses': 0.0,
                'formatted_business': currency_manager.format_amount(
                    Decimal('0'), 
                    currency_manager.BASE_CURRENCY
                ),
                'reimbursable_expenses': 0.0,
                'formatted_reimbursable': currency_manager.format_amount(
                    Decimal('0'), 
                    currency_manager.BASE_CURRENCY
                ),
                'base_currency': currency_manager.BASE_CURRENCY,
                'currencies_breakdown': {}
            }
        
        # Calculate totals with currency conversion
        total_amount = Decimal('0')
        business_amount = Decimal('0')
        reimbursable_amount = Decimal('0')
        currencies_used = {}
        
        for entry in entries:
            # Convert to base currency
            converted = currency_manager.convert_to_base_currency(
                entry.amount,
                entry.currency
            )
            
            if converted:
                total_amount += converted
                
                if entry.is_business_expense:
                    business_amount += converted
                
                if entry.is_reimbursable:
                    reimbursable_amount += converted
                
                # Track original currencies
                if entry.currency not in currencies_used:
                    currencies_used[entry.currency] = Decimal('0')
                currencies_used[entry.currency] += entry.amount
            else:
                logger.warning(
                    f"Failed to convert {entry.currency} for entry {entry.id}"
                )
        
        # Build response
        return {
            'period': period,
            'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat(),
            'total_entries': entry_count,
            'total_amount': float(total_amount),
            'formatted_total': currency_manager.format_amount(
                total_amount,
                currency_manager.BASE_CURRENCY
            ),
            'business_expenses': float(business_amount),
            'formatted_business': currency_manager.format_amount(
                business_amount,
                currency_manager.BASE_CURRENCY
            ),
            'reimbursable_expenses': float(reimbursable_amount),
            'formatted_reimbursable': currency_manager.format_amount(
                reimbursable_amount,
                currency_manager.BASE_CURRENCY
            ),
            'base_currency': currency_manager.BASE_CURRENCY,
            'currencies_breakdown': {
                curr: {
                    'amount': float(amt),
                    'formatted': currency_manager.format_amount(amt, curr)
                }
                for curr, amt in currencies_used.items()
            }
        }
    
    def export_ledger_data(
        self, 
        user, 
        format_type: str = 'csv', 
        filters: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Export ledger data in specified format"""
        try:
            if format_type not in ['csv', 'json']:
                raise ValidationException(
                    detail="Invalid format. Supported: csv, json",
                    context={'provided_format': format_type}
                )
            
            # Get entries
            queryset = model_service.ledger_entry_model.objects.filter(user=user)
            if filters:
                queryset = self._apply_filters(queryset, filters, user)
            
            entries = queryset.select_related('category', 'receipt').order_by('-date')
            
            export_data = []
            for entry in entries:
                export_data.append({
                    'date': entry.date.isoformat(),
                    'vendor': entry.vendor,
                    'amount': float(entry.amount),
                    'currency': entry.currency,
                    'category': entry.category.name,
                    'description': entry.description,
                    'is_business_expense': entry.is_business_expense,
                    'is_reimbursable': entry.is_reimbursable,
                    'receipt_filename': entry.receipt.original_filename,
                    'created_at': entry.created_at.isoformat()
                })
            
            return {
                'format': format_type,
                'total_entries': len(export_data),
                'data': export_data,
                'exported_at': timezone.now().isoformat(),
                'filters_applied': filters or {}
            }
            
        except ValidationException:
            raise
        except Exception as e:
            logger.error(f"Failed to export data: {str(e)}", exc_info=True)
            raise DatabaseOperationException(
                detail="Failed to export ledger data",
                context={'format': format_type}
            )
    
    # Private helper methods
    
    def _apply_filters(self, queryset, filters: Dict, user):
        """Apply filters to queryset"""
        try:
            if 'start_date' in filters and filters['start_date']:
                queryset = queryset.filter(date__gte=filters['start_date'])
            
            if 'end_date' in filters and filters['end_date']:
                queryset = queryset.filter(date__lte=filters['end_date'])
            
            if 'category_id' in filters and filters['category_id']:
                queryset = queryset.filter(category_id=filters['category_id'])
            
            if 'min_amount' in filters and filters['min_amount']:
                queryset = queryset.filter(amount__gte=Decimal(str(filters['min_amount'])))
            
            if 'max_amount' in filters and filters['max_amount']:
                queryset = queryset.filter(amount__lte=Decimal(str(filters['max_amount'])))
            
            if 'vendor_search' in filters and filters['vendor_search']:
                queryset = queryset.filter(vendor__icontains=filters['vendor_search'])
            
            if 'is_business_expense' in filters:
                queryset = queryset.filter(is_business_expense=bool(filters['is_business_expense']))
            
            if 'is_reimbursable' in filters:
                queryset = queryset.filter(is_reimbursable=bool(filters['is_reimbursable']))
            
            return queryset
            
        except Exception as e:
            logger.error(f"Error applying filters: {str(e)}")
            raise ValidationException(
                detail="Invalid filter parameters",
                context={'filters': filters}
            )
    
    def _validate_update_data(self, data: Dict[str, Any]) -> None:
        """Validate update data"""
        if 'amount' in data:
            try:
                amount = Decimal(str(data['amount']))
                if amount <= 0:
                    raise ValidationException(
                        detail="Amount must be positive",
                        context={'amount': str(data['amount'])}
                    )
            except (ValueError, TypeError):
                raise ValidationException(
                    detail="Invalid amount format",
                    context={'amount': str(data.get('amount'))}
                )
        
        if 'date' in data and hasattr(data['date'], 'year'):
            current_year = timezone.now().year
            if data['date'].year < 2000 or data['date'].year > current_year:
                raise ValidationException(
                    detail=f"Date year must be 2000-{current_year}",
                    context={'date': data['date'].isoformat()}
                )
        
        if 'vendor' in data and len(str(data['vendor']).strip()) > 255:
            raise ValidationException(
                detail="Vendor name max 255 characters",
                context={'length': len(str(data['vendor']).strip())}
            )
        
        if 'description' in data and len(str(data['description']).strip()) > 1000:
            raise ValidationException(
                detail="Description max 1000 characters",
                context={'length': len(str(data['description']).strip())}
            )
    
    def _invalidate_user_caches(self, user_id) -> None:
        """Invalidate user-related caches"""
        cache_keys = [
            f"spending_summary_{user_id}_monthly",
            f"spending_summary_{user_id}_yearly",
            f"spending_summary_{user_id}_weekly",
        ]
        
        try:
            cache.delete_many(cache_keys)
        except Exception as e:
            logger.warning(f"Failed to invalidate caches: {str(e)}")
