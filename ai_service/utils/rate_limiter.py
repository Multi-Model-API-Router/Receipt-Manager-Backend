import time
from typing import Dict, Any, Optional
from django.core.cache import cache
from django.conf import settings
import logging


logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Rate limiter for external API calls with multiple strategies
    Only used for external services (Gemini API), not for local services (Tesseract OCR)
    """
    
    def __init__(self):
        self.limits = {
            'gemini_api': {
                'requests_per_minute': getattr(settings, 'GEMINI_RPM', 60),
                'requests_per_day': getattr(settings, 'GEMINI_RPD', 1000),
                'burst_limit': getattr(settings, 'GEMINI_BURST', 5),
                'enabled': True
            },
            # Tesseract is local - no rate limiting needed
            'tesseract': {
                'enabled': False  # No rate limiting for local OCR
            }
        }
    
    def check_rate_limit(self, service: str, user_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Check if request is within rate limits
        
        Args:
            service: Service identifier ('gemini_api', 'tesseract', etc.)
            user_id: Optional user ID for per-user rate limiting
        
        Returns:
            Dict with 'allowed' boolean and limit info
        """
        try:
            service_limits = self.limits.get(service, {})
            
            # If service not configured or rate limiting disabled, allow request
            if not service_limits or not service_limits.get('enabled', False):
                return {
                    'allowed': True, 
                    'reason': 'no_limits_configured' if not service_limits else 'rate_limiting_disabled',
                    'service': service
                }
            
            current_time = int(time.time())
            
            # Check different time windows
            checks = [
                self._check_minute_limit(service, current_time, service_limits),
                self._check_daily_limit(service, current_time, service_limits),
                self._check_burst_limit(service, current_time, service_limits, user_id)
            ]
            
            # If any check fails, request is denied
            for check in checks:
                if not check['allowed']:
                    logger.warning(
                        f"Rate limit exceeded for {service}: {check['reason']} "
                        f"(user: {user_id or 'system'})"
                    )
                    return check
            
            # All checks passed - record the request
            self._record_request(service, current_time, user_id)
            
            return {
                'allowed': True,
                'service': service,
                'remaining_minute': self._get_remaining_requests(service, current_time, 'minute'),
                'remaining_daily': self._get_remaining_requests(service, current_time, 'daily')
            }
            
        except Exception as e:
            logger.error(f"Rate limit check failed for {service}: {str(e)}")
            # Fail open - allow request if rate limiter fails
            return {'allowed': True, 'error': str(e), 'failsafe': True}
    
    def is_rate_limiting_enabled(self, service: str) -> bool:
        """Check if rate limiting is enabled for a service"""
        service_limits = self.limits.get(service, {})
        return service_limits.get('enabled', False)
    
    def get_service_limits(self, service: str) -> Dict[str, Any]:
        """Get rate limit configuration for a service"""
        return self.limits.get(service, {})
    
    def _check_minute_limit(self, service: str, current_time: int, limits: Dict) -> Dict:
        """Check per-minute rate limit"""
        minute_key = f"rate_limit:{service}:minute:{current_time // 60}"
        current_count = cache.get(minute_key, 0)
        
        rpm_limit = limits.get('requests_per_minute', 0)
        if current_count >= rpm_limit:
            return {
                'allowed': False,
                'reason': 'minute_limit_exceeded',
                'limit': rpm_limit,
                'current': current_count,
                'reset_in': 60 - (current_time % 60),
                'window': 'minute'
            }
        
        return {'allowed': True}
    
    def _check_daily_limit(self, service: str, current_time: int, limits: Dict) -> Dict:
        """Check per-day rate limit"""
        day_key = f"rate_limit:{service}:day:{current_time // 86400}"
        current_count = cache.get(day_key, 0)
        
        rpd_limit = limits.get('requests_per_day', 0)
        if current_count >= rpd_limit:
            return {
                'allowed': False,
                'reason': 'daily_limit_exceeded',
                'limit': rpd_limit,
                'current': current_count,
                'reset_in': 86400 - (current_time % 86400),
                'window': 'daily'
            }
        
        return {'allowed': True}
    
    def _check_burst_limit(self, service: str, current_time: int, limits: Dict, user_id: Optional[str] = None) -> Dict:
        """Check burst limit (requests in last 10 seconds)"""
        burst_window = 10
        burst_key = f"rate_limit:{service}:burst:{current_time // burst_window}"
        if user_id:
            burst_key += f":{user_id}"
        
        current_count = cache.get(burst_key, 0)
        
        burst_limit = limits.get('burst_limit', 0)
        if current_count >= burst_limit:
            return {
                'allowed': False,
                'reason': 'burst_limit_exceeded',
                'limit': burst_limit,
                'current': current_count,
                'reset_in': burst_window - (current_time % burst_window),
                'window': 'burst',
                'user_id': user_id
            }
        
        return {'allowed': True}
    
    def _record_request(self, service: str, current_time: int, user_id: Optional[str] = None):
        """Record a request in all rate limit counters"""
        try:
            # Minute counter
            minute_key = f"rate_limit:{service}:minute:{current_time // 60}"
            current_minute = cache.get(minute_key, 0)
            cache.set(minute_key, current_minute + 1, 120)  # 2 minute TTL
            
            # Daily counter  
            day_key = f"rate_limit:{service}:day:{current_time // 86400}"
            current_day = cache.get(day_key, 0)
            cache.set(day_key, current_day + 1, 90000)  # 25 hour TTL
            
            # Burst counter
            burst_key = f"rate_limit:{service}:burst:{current_time // 10}"
            if user_id:
                burst_key += f":{user_id}"
            current_burst = cache.get(burst_key, 0)
            cache.set(burst_key, current_burst + 1, 20)  # 20 second TTL
            
            logger.debug(
                f"Rate limit recorded for {service}: "
                f"minute={current_minute + 1}, day={current_day + 1}, burst={current_burst + 1}"
            )
            
        except Exception as e:
            logger.warning(f"Failed to record request for {service}: {str(e)}")
    
    def _get_remaining_requests(self, service: str, current_time: int, window: str) -> int:
        """Get remaining requests for a time window"""
        try:
            service_limits = self.limits.get(service, {})
            
            if window == 'minute':
                key = f"rate_limit:{service}:minute:{current_time // 60}"
                limit = service_limits.get('requests_per_minute', 0)
            elif window == 'daily':
                key = f"rate_limit:{service}:day:{current_time // 86400}"
                limit = service_limits.get('requests_per_day', 0)
            else:
                return 0
            
            current = cache.get(key, 0)
            return max(0, limit - current)
            
        except Exception:
            return 0
    
    def get_usage_stats(self, service: str) -> Dict[str, Any]:
        """Get current usage statistics for a service"""
        try:
            current_time = int(time.time())
            service_limits = self.limits.get(service, {})
            
            minute_key = f"rate_limit:{service}:minute:{current_time // 60}"
            day_key = f"rate_limit:{service}:day:{current_time // 86400}"
            
            minute_count = cache.get(minute_key, 0)
            day_count = cache.get(day_key, 0)
            
            return {
                'service': service,
                'enabled': service_limits.get('enabled', False),
                'current_minute': minute_count,
                'limit_minute': service_limits.get('requests_per_minute', 0),
                'remaining_minute': max(0, service_limits.get('requests_per_minute', 0) - minute_count),
                'current_daily': day_count,
                'limit_daily': service_limits.get('requests_per_day', 0),
                'remaining_daily': max(0, service_limits.get('requests_per_day', 0) - day_count),
                'timestamp': current_time
            }
        except Exception as e:
            logger.error(f"Failed to get usage stats for {service}: {str(e)}")
            return {'error': str(e)}
    
    def reset_limits(self, service: str):
        """Reset all rate limits for a service (admin/testing use)"""
        try:
            current_time = int(time.time())
            
            minute_key = f"rate_limit:{service}:minute:{current_time // 60}"
            day_key = f"rate_limit:{service}:day:{current_time // 86400}"
            burst_key_pattern = f"rate_limit:{service}:burst:*"
            
            cache.delete(minute_key)
            cache.delete(day_key)
            
            # Note: Pattern deletion depends on cache backend
            # Redis supports this, others may not
            try:
                cache.delete_pattern(burst_key_pattern)
            except AttributeError:
                logger.warning(f"Pattern deletion not supported for {service}")
            
            logger.info(f"Rate limits reset for {service}")
            
        except Exception as e:
            logger.error(f"Failed to reset limits for {service}: {str(e)}")


# Global rate limiter instance
rate_limiter = RateLimiter()
