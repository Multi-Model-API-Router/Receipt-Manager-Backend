from rest_framework.pagination import PageNumberPagination, CursorPagination
from rest_framework.response import Response
from rest_framework import status
from django.core.cache import cache
from django.db import connection
from django.core.paginator import Paginator
import hashlib
import json
from typing import Dict
import logging

logger = logging.getLogger(__name__)

class OptimizedPageNumberPagination(PageNumberPagination):
    """
    Optimized page number pagination with caching and performance improvements
    """
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100
    page_query_param = 'page'
    
    def __init__(self):
        super().__init__()
        self.cache_timeout = 300  # 5 minutes default
        self.use_count_cache = True
        self.count_cache_timeout = 600  # 10 minutes for count cache
    
    def get_cache_key(self, request, queryset_hash: str = None) -> str:
        """Generate cache key for pagination"""
        params = request.GET.dict()
        # Remove page from params for base cache key
        params.pop('page', None)
        
        path = request.path
        user_id = getattr(request.user, 'id', 'anonymous')
        
        key_components = [
            path,
            str(user_id),
            json.dumps(sorted(params.items()), sort_keys=True)
        ]
        
        if queryset_hash:
            key_components.append(queryset_hash)
        
        key_str = ":".join(key_components)
        return f"pagination:{hashlib.md5(key_str.encode()).hexdigest()}"
    
    def get_count_cache_key(self, base_cache_key: str) -> str:
        """Generate cache key for count"""
        return f"{base_cache_key}:count"
    
    def get_paginated_count(self, queryset, base_cache_key: str) -> int:
        """
        Get count with caching optimization
        """
        if not self.use_count_cache:
            return queryset.count()
        
        count_cache_key = self.get_count_cache_key(base_cache_key)
        cached_count = cache.get(count_cache_key)
        
        if cached_count is not None:
            return cached_count
        
        # Use optimized count query
        count = self._get_optimized_count(queryset)
        
        # Cache the count
        cache.set(count_cache_key, count, timeout=self.count_cache_timeout)
        
        return count
    
    def _get_optimized_count(self, queryset) -> int:
        """
        Optimized count query that avoids expensive operations
        """
        try:
            # For large datasets, use estimated count from PostgreSQL statistics
            if hasattr(queryset.model._meta, 'db_table'):
                table_name = queryset.model._meta.db_table
                
                # Check if we're dealing with a large table (>100k rows estimated)
                with connection.cursor() as cursor:
                    cursor.execute("""
                        SELECT reltuples::BIGINT AS estimate 
                        FROM pg_class 
                        WHERE relname = %s
                    """, [table_name])
                    
                    result = cursor.fetchone()
                    if result and result[0] > 100000:
                        # For large tables with simple filters, use estimate
                        filters = queryset.query.where
                        if not filters or len(filters.children) <= 2:
                            logger.info(f"Using estimated count for large table: {table_name}")
                            return int(result[0])
        except Exception as e:
            logger.warning(f"Could not get estimated count: {str(e)}")
        
        # Fallback to regular count
        return queryset.count()
    
    def paginate_queryset(self, queryset, request, view=None):
        """
        Enhanced paginate queryset with caching
        """
        # Generate cache key
        queryset_hash = self._get_queryset_hash(queryset)
        base_cache_key = self.get_cache_key(request, queryset_hash)
        
        page_number = request.GET.get(self.page_query_param, 1)
        cache_key = f"{base_cache_key}:page:{page_number}"
        
        # Try to get from cache
        cached_page = cache.get(cache_key)
        if cached_page:
            logger.debug(f"Returning cached page: {page_number}")
            return cached_page['results']
        
        # Get page size
        page_size = self.get_page_size(request)
        if not page_size:
            return None
        
        # Get optimized count
        count = self.get_paginated_count(queryset, base_cache_key)
        
        # Create paginator with prefetched count
        paginator = Paginator(queryset, page_size)
        paginator._count = count  # Inject cached count
        
        try:
            self.page = paginator.page(page_number)
        except Exception:
            # Return empty page for invalid page numbers
            self.page = paginator.page(1)
            return []
        
        # Cache the results
        page_data = {
            'results': list(self.page),
            'count': count,
            'num_pages': paginator.num_pages
        }
        
        cache.set(cache_key, page_data, timeout=self.cache_timeout)
        
        return list(self.page)
    
    def _get_queryset_hash(self, queryset) -> str:
        """
        Generate hash for queryset to detect changes
        """
        try:
            # Create hash from query and model
            query_str = str(queryset.query)
            model_name = queryset.model.__name__
            hash_input = f"{model_name}:{query_str}"
            return hashlib.md5(hash_input.encode()).hexdigest()[:8]
        except Exception:
            return "no_hash"
    
    def get_paginated_response(self, data, additional_metadata: Dict = None):
        """
        Enhanced paginated response with metadata
        """
        has_next = self.page.has_next() if hasattr(self, 'page') else False
        has_previous = self.page.has_previous() if hasattr(self, 'page') else False
        
        response_data = {
            'message': 'Data retrieved successfully',
            'pagination': {
                'count': self.page.paginator.count if hasattr(self, 'page') else 0,
                'page_size': self.get_page_size(self.request),
                'current_page': self.page.number if hasattr(self, 'page') else 1,
                'total_pages': self.page.paginator.num_pages if hasattr(self, 'page') else 1,
                'has_next': has_next,
                'has_previous': has_previous,
                'next_page': self.page.next_page_number() if has_next else None,
                'previous_page': self.page.previous_page_number() if has_previous else None,
                'links': {
                    'next': self.get_next_link(),
                    'previous': self.get_previous_link()
                }
            },
            'data': data,
            'status': status.HTTP_200_OK
        }
        
        if additional_metadata:
            response_data['metadata'] = additional_metadata
            
        return Response(response_data, status=status.HTTP_200_OK)

class CursorBasedPagination(CursorPagination):
    """
    High-performance cursor-based pagination for large datasets
    """
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100
    cursor_query_param = 'cursor'
    ordering = '-created_at'  # Default ordering
    
    def get_paginated_response(self, data, additional_metadata: Dict = None):
        """
        Enhanced cursor paginated response
        """
        response_data = {
            'message': 'Data retrieved successfully',
            'pagination': {
                'next_cursor': self.get_next_link(),
                'previous_cursor': self.get_previous_link(),
                'page_size': self.get_page_size(self.request),
                'has_next': bool(self.get_next_link()),
                'has_previous': bool(self.get_previous_link())
            },
            'data': data,
            'status': status.HTTP_200_OK
        }
        
        if additional_metadata:
            response_data['metadata'] = additional_metadata
            
        return Response(response_data, status=status.HTTP_200_OK)

class SmartPagination:
    """
    Smart pagination that chooses the best strategy based on data size and query
    """
    
    @staticmethod
    def get_pagination_class(queryset, request) -> type:
        """
        Choose optimal pagination strategy based on dataset characteristics
        """
        try:
            # Estimate dataset size
            model = queryset.model
            table_name = model._meta.db_table
            
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT reltuples::BIGINT AS estimate 
                    FROM pg_class 
                    WHERE relname = %s
                """, [table_name])
                
                result = cursor.fetchone()
                estimated_count = result[0] if result else 1000
            
            # Choose pagination strategy
            page_number = request.GET.get('page', 1)
            
            # For large datasets and high page numbers, use cursor pagination
            if estimated_count > 50000 and int(page_number) > 100:
                logger.info("Using cursor pagination for large dataset")
                return CursorBasedPagination
            else:
                logger.debug("Using optimized page number pagination")
                return OptimizedPageNumberPagination
                
        except Exception as e:
            logger.warning(f"Could not determine optimal pagination: {str(e)}")
            return OptimizedPageNumberPagination

# Backward compatibility aliases
LargeResultSetPagination = OptimizedPageNumberPagination
CachedPagination = OptimizedPageNumberPagination
