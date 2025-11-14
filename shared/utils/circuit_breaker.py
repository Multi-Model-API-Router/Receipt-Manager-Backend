import time
import threading
from enum import Enum
from typing import Callable, Any, Optional, Dict
from dataclasses import dataclass
from django.core.cache import cache
from django.conf import settings
import logging
from functools import wraps


logger = logging.getLogger(__name__)


class CircuitBreakerState(Enum):
    """Circuit breaker states"""
    CLOSED = "closed"       # Normal operation
    OPEN = "open"          # Failing, blocking requests
    HALF_OPEN = "half_open" # Testing if service recovered


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker"""
    failure_threshold: int = 5              # Number of failures before opening
    recovery_timeout: int = 60              # Seconds before trying half-open
    success_threshold: int = 3              # Successes needed to close from half-open
    timeout: int = 30                       # Request timeout in seconds
    expected_exceptions: tuple = (Exception,) # Exceptions that count as failures
    name: str = "default"                   # Circuit breaker name for logging/monitoring


class CircuitBreakerError(Exception):
    """Raised when circuit breaker is open"""
    pass


class CircuitBreaker:
    """
    Production-ready Circuit Breaker implementation with:
    - Thread safety
    - Distributed state via Django cache
    - Configurable thresholds and timeouts
    - Comprehensive monitoring and logging
    - Support for async operations
    """
    
    def __init__(self, config: CircuitBreakerConfig):
        self.config = config
        self.name = config.name
        self._lock = threading.RLock()
        
        # Cache keys for distributed state
        self._state_key = f"circuit_breaker:{self.name}:state"
        self._failure_count_key = f"circuit_breaker:{self.name}:failures"
        self._success_count_key = f"circuit_breaker:{self.name}:successes"
        self._last_failure_time_key = f"circuit_breaker:{self.name}:last_failure"
        self._metrics_key = f"circuit_breaker:{self.name}:metrics"
        
        # Initialize state if not exists
        self._initialize_state()
    
    def _initialize_state(self):
        """Initialize circuit breaker state in cache if not exists"""
        try:
            if cache.get(self._state_key) is None:
                cache.set(self._state_key, CircuitBreakerState.CLOSED.value, None)
                cache.set(self._failure_count_key, 0, None)
                cache.set(self._success_count_key, 0, None)
                cache.set(self._last_failure_time_key, 0, None)
                self._initialize_metrics()
                logger.info(f"Initialized circuit breaker: {self.name}")
        except Exception as e:
            logger.error(f"Failed to initialize circuit breaker {self.name}: {e}")
    
    def _initialize_metrics(self):
        """Initialize metrics tracking"""
        metrics = {
            'total_requests': 0,
            'total_failures': 0,
            'total_successes': 0,
            'total_timeouts': 0,
            'total_circuit_opens': 0,
            'total_circuit_closes': 0,
            'last_opened_at': None,
            'last_closed_at': None,
            'average_response_time': 0.0,
            'created_at': time.time()
        }
        cache.set(self._metrics_key, metrics, None)
    
    @property
    def state(self) -> CircuitBreakerState:
        """Get current circuit breaker state"""
        try:
            state_value = cache.get(self._state_key, CircuitBreakerState.CLOSED.value)
            return CircuitBreakerState(state_value)
        except Exception as e:
            logger.error(f"Error getting circuit breaker state for {self.name}: {e}")
            return CircuitBreakerState.CLOSED
    
    @state.setter
    def state(self, new_state: CircuitBreakerState):
        """Set circuit breaker state with logging"""
        try:
            old_state = self.state
            cache.set(self._state_key, new_state.value, None)
            
            if old_state != new_state:
                self._update_state_change_metrics(old_state, new_state)
                logger.info(f"Circuit breaker {self.name} state changed: {old_state.value} -> {new_state.value}")
        except Exception as e:
            logger.error(f"Error setting circuit breaker state for {self.name}: {e}")
    
    def _update_state_change_metrics(self, old_state: CircuitBreakerState, new_state: CircuitBreakerState):
        """Update metrics when state changes"""
        try:
            metrics = cache.get(self._metrics_key, {})
            current_time = time.time()
            
            if new_state == CircuitBreakerState.OPEN:
                metrics['total_circuit_opens'] = metrics.get('total_circuit_opens', 0) + 1
                metrics['last_opened_at'] = current_time
            elif new_state == CircuitBreakerState.CLOSED and old_state != CircuitBreakerState.CLOSED:
                metrics['total_circuit_closes'] = metrics.get('total_circuit_closes', 0) + 1
                metrics['last_closed_at'] = current_time
            
            cache.set(self._metrics_key, metrics, None)
        except Exception as e:
            logger.error(f"Error updating state change metrics for {self.name}: {e}")
    
    @property
    def failure_count(self) -> int:
        """Get current failure count"""
        return cache.get(self._failure_count_key, 0)
    
    @property
    def success_count(self) -> int:
        """Get current success count (for half-open state)"""
        return cache.get(self._success_count_key, 0)
    
    @property
    def last_failure_time(self) -> float:
        """Get timestamp of last failure"""
        return cache.get(self._last_failure_time_key, 0)
    
    def _can_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset"""
        if self.state != CircuitBreakerState.OPEN:
            return False
        
        time_since_failure = time.time() - self.last_failure_time
        return time_since_failure >= self.config.recovery_timeout
    
    def _record_success(self, response_time: float = 0.0):
        """Record successful operation"""
        with self._lock:
            try:
                current_state = self.state
                
                if current_state == CircuitBreakerState.HALF_OPEN:
                    # Increment success count in half-open state
                    success_count = self.success_count + 1
                    cache.set(self._success_count_key, success_count, None)
                    
                    if success_count >= self.config.success_threshold:
                        # Close the circuit
                        self.state = CircuitBreakerState.CLOSED
                        cache.set(self._failure_count_key, 0, None)
                        cache.set(self._success_count_key, 0, None)
                        logger.info(f"Circuit breaker {self.name} closed after {success_count} successes")
                
                elif current_state == CircuitBreakerState.OPEN:
                    # This shouldn't happen, but reset if it does
                    logger.warning(f"Success recorded while circuit breaker {self.name} is open")
                
                # Update metrics
                self._update_success_metrics(response_time)
                
            except Exception as e:
                logger.error(f"Error recording success for {self.name}: {e}")
    
    def _record_failure(self, exception: Exception):
        """Record failed operation"""
        with self._lock:
            try:
                # Only count expected exceptions as failures
                if not isinstance(exception, self.config.expected_exceptions):
                    logger.debug(f"Circuit breaker {self.name} ignoring exception: {type(exception).__name__}")
                    return
                
                current_state = self.state
                failure_count = self.failure_count + 1
                
                cache.set(self._failure_count_key, failure_count, None)
                cache.set(self._last_failure_time_key, time.time(), None)
                
                if current_state == CircuitBreakerState.CLOSED:
                    if failure_count >= self.config.failure_threshold:
                        # Open the circuit
                        self.state = CircuitBreakerState.OPEN
                        cache.set(self._success_count_key, 0, None)
                        logger.warning(f"Circuit breaker {self.name} opened after {failure_count} failures")
                
                elif current_state == CircuitBreakerState.HALF_OPEN:
                    # Go back to open state
                    self.state = CircuitBreakerState.OPEN
                    cache.set(self._success_count_key, 0, None)
                    logger.warning(f"Circuit breaker {self.name} returned to open state after failure")
                
                # Update metrics
                self._update_failure_metrics(exception)
                
            except Exception as e:
                logger.error(f"Error recording failure for {self.name}: {e}")
    
    def _update_success_metrics(self, response_time: float):
        """Update success metrics"""
        try:
            metrics = cache.get(self._metrics_key, {})
            metrics['total_requests'] = metrics.get('total_requests', 0) + 1
            metrics['total_successes'] = metrics.get('total_successes', 0) + 1
            
            # Update average response time
            if response_time > 0:
                current_avg = metrics.get('average_response_time', 0.0)
                total_successes = metrics['total_successes']
                new_avg = ((current_avg * (total_successes - 1)) + response_time) / total_successes
                metrics['average_response_time'] = new_avg
            
            cache.set(self._metrics_key, metrics, None)
        except Exception as e:
            logger.error(f"Error updating success metrics for {self.name}: {e}")
    
    def _update_failure_metrics(self, exception: Exception):
        """Update failure metrics"""
        try:
            metrics = cache.get(self._metrics_key, {})
            metrics['total_requests'] = metrics.get('total_requests', 0) + 1
            metrics['total_failures'] = metrics.get('total_failures', 0) + 1
            
            # Track timeout failures separately
            if 'timeout' in str(exception).lower():
                metrics['total_timeouts'] = metrics.get('total_timeouts', 0) + 1
            
            cache.set(self._metrics_key, metrics, None)
        except Exception as e:
            logger.error(f"Error updating failure metrics for {self.name}: {e}")
    
    def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute function with circuit breaker protection
        
        Args:
            func: Function to execute
            *args: Function arguments
            **kwargs: Function keyword arguments
            
        Returns:
            Function result
            
        Raises:
            CircuitBreakerError: When circuit is open
            Exception: Original function exceptions
        """
        # Check if we can make the call
        current_state = self.state
        
        if current_state == CircuitBreakerState.OPEN:
            if self._can_attempt_reset():
                # Try half-open state
                self.state = CircuitBreakerState.HALF_OPEN
                logger.info(f"Circuit breaker {self.name} attempting recovery (half-open)")
            else:
                # Still in open state, reject the call
                raise CircuitBreakerError(
                    f"Circuit breaker '{self.name}' is open. "
                    f"Retry after {self.config.recovery_timeout} seconds."
                )
        
        # Execute the function with timing
        start_time = time.time()
        try:
            result = func(*args, **kwargs)
            response_time = time.time() - start_time
            self._record_success(response_time)
            return result
            
        except Exception as e:
            self._record_failure(e)
            raise
    
    def __call__(self, func: Callable) -> Callable:
        """Decorator usage of circuit breaker"""
        @wraps(func)
        def wrapper(*args, **kwargs):
            return self.call(func, *args, **kwargs)
        return wrapper
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get comprehensive circuit breaker metrics"""
        try:
            metrics = cache.get(self._metrics_key, {})
            
            # Add current state information
            current_metrics = {
                **metrics,
                'name': self.name,
                'current_state': self.state.value,
                'failure_count': self.failure_count,
                'success_count': self.success_count,
                'last_failure_time': self.last_failure_time,
                'config': {
                    'failure_threshold': self.config.failure_threshold,
                    'recovery_timeout': self.config.recovery_timeout,
                    'success_threshold': self.config.success_threshold,
                    'timeout': self.config.timeout
                },
                'health': {
                    'is_healthy': self.state == CircuitBreakerState.CLOSED,
                    'can_attempt_reset': self._can_attempt_reset(),
                    'time_until_retry': max(0, self.config.recovery_timeout - (time.time() - self.last_failure_time))
                }
            }
            
            return current_metrics
            
        except Exception as e:
            logger.error(f"Error getting metrics for {self.name}: {e}")
            return {'error': str(e)}
    
    def reset(self):
        """Manually reset circuit breaker to closed state"""
        with self._lock:
            try:
                self.state = CircuitBreakerState.CLOSED
                cache.set(self._failure_count_key, 0, None)
                cache.set(self._success_count_key, 0, None)
                cache.set(self._last_failure_time_key, 0, None)
                logger.info(f"Circuit breaker {self.name} manually reset")
            except Exception as e:
                logger.error(f"Error resetting circuit breaker {self.name}: {e}")


class CircuitBreakerManager:
    """
    Manager for multiple circuit breakers with centralized configuration
    """
    
    def __init__(self):
        self._breakers: Dict[str, CircuitBreaker] = {}
        self._lock = threading.RLock()
    
    def get_breaker(self, name: str, config: Optional[CircuitBreakerConfig] = None) -> CircuitBreaker:
        """
        Get or create a circuit breaker with given name and configuration
        """
        with self._lock:
            if name not in self._breakers:
                if config is None:
                    # Use default configuration
                    config = CircuitBreakerConfig(name=name)
                
                self._breakers[name] = CircuitBreaker(config)
                logger.info(f"Created new circuit breaker: {name}")
            
            return self._breakers[name]
    
    def get_all_metrics(self) -> Dict[str, Dict[str, Any]]:
        """Get metrics for all circuit breakers"""
        return {name: breaker.get_metrics() for name, breaker in self._breakers.items()}
    
    def reset_all(self):
        """Reset all circuit breakers"""
        for breaker in self._breakers.values():
            breaker.reset()
        logger.info("Reset all circuit breakers")
    
    def get_health_summary(self) -> Dict[str, Any]:
        """Get overall health summary of all circuit breakers"""
        total_breakers = len(self._breakers)
        healthy_breakers = sum(1 for b in self._breakers.values() if b.state == CircuitBreakerState.CLOSED)
        
        return {
            'total_circuit_breakers': total_breakers,
            'healthy': healthy_breakers,
            'unhealthy': total_breakers - healthy_breakers,
            'overall_health': healthy_breakers / total_breakers if total_breakers > 0 else 1.0,
            'breakers': {name: breaker.state.value for name, breaker in self._breakers.items()}
        }


# Global circuit breaker manager
circuit_breaker_manager = CircuitBreakerManager()


# Convenience function for quick usage
def circuit_breaker(name: str, 
                   failure_threshold: int = 5,
                   recovery_timeout: int = 60,
                   success_threshold: int = 3,
                   timeout: int = 30,
                   expected_exceptions: tuple = (Exception,)):
    """
    Decorator for easy circuit breaker usage
    
    Usage:
        @circuit_breaker('my_service', failure_threshold=3)
        def call_external_service():
            # your code here
            pass
    """
    config = CircuitBreakerConfig(
        name=name,
        failure_threshold=failure_threshold,
        recovery_timeout=recovery_timeout,
        success_threshold=success_threshold,
        timeout=timeout,
        expected_exceptions=expected_exceptions
    )
    
    breaker = circuit_breaker_manager.get_breaker(name, config)
    return breaker
