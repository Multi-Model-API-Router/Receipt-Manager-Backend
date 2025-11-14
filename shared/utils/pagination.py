# shared/utils/pagination.py

from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework import status
from django.core.cache import cache
import hashlib
import json


class LargeResultSetPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 500
    
    def get_paginated_response(self, data, additional_metadata=None):
        response_data = {
            'message': 'Data retrieved successfully',
            'pagination': {
                'count': self.page.paginator.count,
                'next': self.get_next_link(),
                'previous': self.get_previous_link(),
                'current_page': self.page.number,
                'total_pages': self.page.paginator.num_pages,
                'page_size': self.get_page_size(self.request),
            },
            'data': data,
            'status': status.HTTP_200_OK
        }
        
        if additional_metadata:
            response_data['metadata'] = additional_metadata
        
        return Response(response_data, status=status.HTTP_200_OK)


class CachedPagination(LargeResultSetPagination):
    """Pagination with caching support"""
    cache_timeout = 300  # 5 minutes
    
    def get_cache_key(self, request):
        """
        Generate cache key including user ID to prevent data leakage
        """
        user_id = str(request.user.id) if request.user.is_authenticated else 'anonymous'
        params = dict(request.GET.items())
        path = request.path
        
        # Create deterministic cache key
        key_data = f"{user_id}:{path}:{json.dumps(params, sort_keys=True)}"
        key_hash = hashlib.md5(key_data.encode()).hexdigest()
        
        return f"pagination:{key_hash}"
    
    def get_paginated_response(self, data, additional_metadata=None):
        """
        Override to cache the full response including pagination metadata
        """
        # Build standard pagination response
        pagination_meta = {
            'count': self.page.paginator.count,
            'next': self.get_next_link(),
            'previous': self.get_previous_link(),
            'current_page': self.page.number,
            'total_pages': self.page.paginator.num_pages,
            'page_size': self.get_page_size(self.request),
        }
        
        response_data = {
            'message': 'Data retrieved successfully',
            'pagination': pagination_meta,
            'data': data,
            'status': status.HTTP_200_OK
        }
        
        if additional_metadata:
            response_data['metadata'] = additional_metadata
        
        # Cache the full response
        if hasattr(self, 'request'):
            try:
                cache_key = self.get_cache_key(self.request)
                cache.set(cache_key, response_data, timeout=self.cache_timeout)
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"Failed to cache paginated response: {str(e)}")
        
        return Response(response_data, status=status.HTTP_200_OK)
    
    def get_cached_response(self, request):
        """
        Try to get cached response for this request
        Returns None if not cached
        """
        try:
            cache_key = self.get_cache_key(request)
            cached_data = cache.get(cache_key)
            
            if cached_data:
                # Add cache indicator
                cached_data['message'] = 'Data retrieved successfully (from cache)'
                return Response(cached_data, status=status.HTTP_200_OK)
            
            return None
        except Exception:
            return None
