import asyncio
import time
from typing import Callable, Optional, TypeVar, Any
from functools import wraps
from enum import Enum

from core.exceptions import (
    CircuitBreakerOpenError,
    RateLimitError,
    TimeoutError as FileBuddyTimeoutError
)
from config.settings import settings
from utils.logger import get_logger

logger = get_logger(__name__)

T = TypeVar('T')


class CircuitState(Enum):
    """Circuit breaker states"""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if service recovered


class CircuitBreaker:
    """
    Circuit breaker pattern implementation
    Prevents cascading failures by failing fast when service is down
    """
    
    def __init__(
        self,
        name: str,
        failure_threshold: int = None,
        recovery_timeout: int = None,
        expected_exception: type = Exception
    ):
        self.name = name
        self.failure_threshold = failure_threshold or settings.CIRCUIT_BREAKER_THRESHOLD
        self.recovery_timeout = recovery_timeout or settings.CIRCUIT_BREAKER_TIMEOUT
        self.expected_exception = expected_exception
        
        self.failure_count = 0
        self.last_failure_time = None
        self.state = CircuitState.CLOSED
        
        logger.info(
            f"Circuit breaker initialized",
            extra={
                "circuit": name,
                "threshold": self.failure_threshold,
                "timeout": self.recovery_timeout
            }
        )
    
    def call(self, func: Callable[..., T], *args, **kwargs) -> T:
        """Execute function with circuit breaker protection"""
        
        if self.state == CircuitState.OPEN:
            if self._should_attempt_reset():
                self.state = CircuitState.HALF_OPEN
                logger.info(f"Circuit breaker half-open", extra={"circuit": self.name})
            else:
                raise CircuitBreakerOpenError(
                    f"Circuit breaker open for {self.name}",
                    service=self.name,
                    retry_after=self.recovery_timeout
                )
        
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except self.expected_exception as e:
            self._on_failure()
            raise
    
    async def call_async(self, func: Callable[..., T], *args, **kwargs) -> T:
        """Execute async function with circuit breaker protection"""
        
        if self.state == CircuitState.OPEN:
            if self._should_attempt_reset():
                self.state = CircuitState.HALF_OPEN
                logger.info(f"Circuit breaker half-open", extra={"circuit": self.name})
            else:
                raise CircuitBreakerOpenError(
                    f"Circuit breaker open for {self.name}",
                    service=self.name,
                    retry_after=self.recovery_timeout
                )
        
        try:
            result = await func(*args, **kwargs)
            self._on_success()
            return result
        except self.expected_exception as e:
            self._on_failure()
            raise
    
    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt recovery"""
        if self.last_failure_time is None:
            return True
        return (time.time() - self.last_failure_time) >= self.recovery_timeout
    
    def _on_success(self):
        """Reset circuit breaker on successful call"""
        self.failure_count = 0
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.CLOSED
            logger.info(f"Circuit breaker closed", extra={"circuit": self.name})
    
    def _on_failure(self):
        """Handle failure - increment counter and potentially open circuit"""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        logger.warning(
            f"Circuit breaker failure",
            extra={
                "circuit": self.name,
                "failures": self.failure_count,
                "threshold": self.failure_threshold
            }
        )
        
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
            logger.error(
                f"Circuit breaker opened",
                extra={
                    "circuit": self.name,
                    "recovery_timeout": self.recovery_timeout
                }
            )
    
    def reset(self):
        """Manually reset circuit breaker"""
        self.failure_count = 0
        self.last_failure_time = None
        self.state = CircuitState.CLOSED
        logger.info(f"Circuit breaker manually reset", extra={"circuit": self.name})


def with_retry(
    max_retries: Optional[int] = None,
    delay: Optional[float] = None,
    backoff: Optional[float] = None,
    exceptions: tuple = (Exception,),
    on_retry: Optional[Callable] = None
):
    """
    Decorator for automatic retry with exponential backoff
    
    Args:
        max_retries: Maximum number of retry attempts
        delay: Initial delay between retries in seconds
        backoff: Backoff multiplier for delay
        exceptions: Tuple of exceptions to catch and retry
        on_retry: Optional callback function called before each retry
    """
    max_retries = max_retries or settings.MAX_RETRIES
    delay = delay or settings.RETRY_DELAY
    backoff = backoff or settings.RETRY_BACKOFF
    
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            current_delay = delay
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    
                    if attempt == max_retries:
                        logger.error(
                            f"Max retries exceeded for {func.__name__}",
                            extra={
                                "function": func.__name__,
                                "attempts": attempt + 1,
                                "error": str(e)
                            }
                        )
                        raise
                    
                    logger.warning(
                        f"Retry attempt {attempt + 1}/{max_retries}",
                        extra={
                            "function": func.__name__,
                            "attempt": attempt + 1,
                            "delay": current_delay,
                            "error": str(e)
                        }
                    )
                    
                    if on_retry:
                        await on_retry(attempt, e)
                    
                    await asyncio.sleep(current_delay)
                    current_delay *= backoff
            
            raise last_exception
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            current_delay = delay
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    
                    if attempt == max_retries:
                        logger.error(
                            f"Max retries exceeded for {func.__name__}",
                            extra={
                                "function": func.__name__,
                                "attempts": attempt + 1,
                                "error": str(e)
                            }
                        )
                        raise
                    
                    logger.warning(
                        f"Retry attempt {attempt + 1}/{max_retries}",
                        extra={
                            "function": func.__name__,
                            "attempt": attempt + 1,
                            "delay": current_delay,
                            "error": str(e)
                        }
                    )
                    
                    if on_retry:
                        on_retry(attempt, e)
                    
                    time.sleep(current_delay)
                    current_delay *= backoff
            
            raise last_exception
        
        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    
    return decorator


def with_timeout(seconds: Optional[int] = None):
    """
    Decorator to add timeout to async functions
    
    Args:
        seconds: Timeout in seconds
    """
    seconds = seconds or settings.API_TIMEOUT
    
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await asyncio.wait_for(func(*args, **kwargs), timeout=seconds)
            except asyncio.TimeoutError:
                logger.error(
                    f"Function timeout",
                    extra={
                        "function": func.__name__,
                        "timeout": seconds
                    }
                )
                raise FileBuddyTimeoutError(
                    f"{func.__name__} timed out after {seconds} seconds",
                    timeout_seconds=seconds
                )
        
        return wrapper
    
    return decorator


class RateLimiter:
    """
    Token bucket rate limiter
    """
    
    def __init__(self, max_requests: int, time_window: int = 60):
        """
        Args:
            max_requests: Maximum requests allowed
            time_window: Time window in seconds
        """
        self.max_requests = max_requests
        self.time_window = time_window
        self.tokens = max_requests
        self.last_update = time.time()
        self._lock = asyncio.Lock()
    
    async def acquire(self, tokens: int = 1) -> bool:
        """
        Attempt to acquire tokens
        
        Args:
            tokens: Number of tokens to acquire
            
        Returns:
            True if tokens acquired, False otherwise
        """
        async with self._lock:
            self._refill()
            
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            
            return False
    
    def _refill(self):
        """Refill tokens based on elapsed time"""
        now = time.time()
        elapsed = now - self.last_update
        
        # Calculate tokens to add based on elapsed time
        tokens_to_add = (elapsed / self.time_window) * self.max_requests
        self.tokens = min(self.max_requests, self.tokens + tokens_to_add)
        self.last_update = now
    
    async def wait_for_token(self, tokens: int = 1):
        """Wait until token is available"""
        while not await self.acquire(tokens):
            await asyncio.sleep(0.1)


# Global circuit breakers for external services
openai_circuit = CircuitBreaker("openai", expected_exception=Exception)
deepgram_circuit = CircuitBreaker("deepgram", expected_exception=Exception)
mem0_circuit = CircuitBreaker("mem0", expected_exception=Exception)
livekit_circuit = CircuitBreaker("livekit", expected_exception=Exception)

# Global rate limiters
api_rate_limiter = RateLimiter(settings.MAX_REQUESTS_PER_MINUTE, time_window=60)
file_op_rate_limiter = RateLimiter(settings.MAX_FILE_OPERATIONS_PER_MINUTE, time_window=60)