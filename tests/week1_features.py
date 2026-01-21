"""
Test suite for Week 1 production features
"""
import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock

from core.exceptions import (
    FileBuddyError,
    RateLimitError,
    CircuitBreakerOpenError,
    PathSecurityError
)
from core.retry_handler import (
    CircuitBreaker,
    CircuitState,
    with_retry,
    RateLimiter
)
from core.health_monitor import HealthMonitor, HealthStatus
# from core.memory_manager import MemoryManager, MemoryCache
from config.settings import settings


class TestExceptions:
    """Test custom exception hierarchy"""
    
    def test_base_exception(self):
        """Test base FileBuddy exception"""
        error = FileBuddyError(
            message="Test error",
            error_code="TEST_001",
            details={"key": "value"},
            recoverable=True
        )
        
        assert error.message == "Test error"
        assert error.error_code == "TEST_001"
        assert error.details["key"] == "value"
        assert error.recoverable is True
        
        error_dict = error.to_dict()
        assert error_dict["error_type"] == "FileBuddyError"
        assert error_dict["message"] == "Test error"
    
    def test_rate_limit_error(self):
        """Test rate limit error with retry_after"""
        error = RateLimitError(
            message="Too many requests",
            retry_after=60
        )
        
        assert error.retry_after == 60
        assert error.details["retry_after"] == 60
    
    def test_path_security_error(self):
        """Test path security error"""
        error = PathSecurityError(
            message="Forbidden path",
            path="/etc/passwd"
        )
        
        assert error.path == "/etc/passwd"
        assert error.recoverable is False


class TestCircuitBreaker:
    """Test circuit breaker implementation"""
    
    def test_circuit_starts_closed(self):
        """Test circuit breaker starts in closed state"""
        breaker = CircuitBreaker("test", failure_threshold=3)
        assert breaker.state == CircuitState.CLOSED
    
    def test_circuit_opens_after_failures(self):
        """Test circuit opens after threshold failures"""
        breaker = CircuitBreaker("test", failure_threshold=3)
        
        # Simulate failures
        for i in range(3):
            try:
                breaker.call(lambda: 1/0)
            except ZeroDivisionError:
                pass
        
        assert breaker.state == CircuitState.OPEN
        assert breaker.failure_count == 3
    
    def test_circuit_rejects_when_open(self):
        """Test circuit rejects calls when open"""
        breaker = CircuitBreaker("test", failure_threshold=1, recovery_timeout=100)
        
        # Trigger failure
        try:
            breaker.call(lambda: 1/0)
        except ZeroDivisionError:
            pass
        
        # Circuit should be open
        with pytest.raises(CircuitBreakerOpenError) as exc_info:
            breaker.call(lambda: "should fail")
        
        assert "Circuit breaker open" in str(exc_info.value)
    
    def test_circuit_resets_on_success(self):
        """Test circuit resets failure count on success"""
        breaker = CircuitBreaker("test", failure_threshold=5)
        
        # One failure
        try:
            breaker.call(lambda: 1/0)
        except ZeroDivisionError:
            pass
        
        assert breaker.failure_count == 1
        
        # Success
        result = breaker.call(lambda: "success")
        
        assert result == "success"
        assert breaker.failure_count == 0
        assert breaker.state == CircuitState.CLOSED
    
    @pytest.mark.asyncio
    async def test_async_circuit_breaker(self):
        """Test async circuit breaker"""
        breaker = CircuitBreaker("test_async", failure_threshold=2)
        
        async def failing_function():
            raise ValueError("Test error")
        
        # Trigger failures
        for _ in range(2):
            try:
                await breaker.call_async(failing_function)
            except ValueError:
                pass
        
        assert breaker.state == CircuitState.OPEN


class TestRetryDecorator:
    """Test retry decorator"""
    
    @pytest.mark.asyncio
    async def test_retry_on_failure(self):
        """Test retry mechanism on transient failures"""
        call_count = 0
        
        @with_retry(max_retries=3, delay=0.01, backoff=1)
        async def flaky_function():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("Temporary error")
            return "success"
        
        result = await flaky_function()
        
        assert result == "success"
        assert call_count == 3
    
    @pytest.mark.asyncio
    async def test_retry_exhaustion(self):
        """Test retry gives up after max attempts"""
        call_count = 0
        
        @with_retry(max_retries=2, delay=0.01, backoff=1)
        async def always_fails():
            nonlocal call_count
            call_count += 1
            raise ValueError("Permanent error")
        
        with pytest.raises(ValueError):
            await always_fails()
        
        # Should try initial + 2 retries = 3 total
        assert call_count == 3


class TestRateLimiter:
    """Test rate limiter"""
    
    @pytest.mark.asyncio
    async def test_rate_limiter_allows_under_limit(self):
        """Test rate limiter allows requests under limit"""
        limiter = RateLimiter(max_requests=5, time_window=60)
        
        # Should allow 5 requests
        for _ in range(5):
            assert await limiter.acquire() is True
    
    @pytest.mark.asyncio
    async def test_rate_limiter_blocks_over_limit(self):
        """Test rate limiter blocks requests over limit"""
        limiter = RateLimiter(max_requests=2, time_window=60)
        
        # Use up tokens
        assert await limiter.acquire() is True
        assert await limiter.acquire() is True
        
        # Should be blocked
        assert await limiter.acquire() is False
    
    @pytest.mark.asyncio
    async def test_rate_limiter_refills(self):
        """Test rate limiter refills tokens over time"""
        limiter = RateLimiter(max_requests=1, time_window=1)
        
        # Use token
        assert await limiter.acquire() is True
        
        # Wait for refill
        await asyncio.sleep(1.1)
        
        # Should have refilled
        assert await limiter.acquire() is True


class TestHealthMonitor:
    """Test health monitoring"""
    
    @pytest.mark.asyncio
    async def test_filesystem_check(self):
        """Test filesystem health check"""
        monitor = HealthMonitor()
        
        result = await monitor.check_filesystem()
        
        assert result.name == "filesystem"
        assert result.status in [HealthStatus.HEALTHY, HealthStatus.DEGRADED]
        assert result.response_time_ms is not None
        assert "free_gb" in result.details
    
    @pytest.mark.asyncio
    async def test_memory_check(self):
        """Test memory health check"""
        monitor = HealthMonitor()
        
        result = await monitor.check_memory()
        
        assert result.name == "memory"
        assert result.status in [HealthStatus.HEALTHY, HealthStatus.DEGRADED]
        assert "total_gb" in result.details
    
    @pytest.mark.asyncio
    async def test_full_health_check(self):
        """Test complete health check"""
        monitor = HealthMonitor()
        
        health = await monitor.perform_health_check()
        
        assert health.status in [HealthStatus.HEALTHY, HealthStatus.DEGRADED, HealthStatus.UNHEALTHY]
        assert "filesystem" in health.components
        assert "memory" in health.components
        assert health.system_info["app_version"] == settings.APP_VERSION


# class TestMemoryCache:
#     """Test memory caching"""
    
#     @pytest.mark.asyncio
#     async def test_cache_set_and_get(self):
#         """Test setting and getting cache values"""
#         cache = MemoryCache(max_size=10, ttl_seconds=60)
        
#         await cache.set("key1", "value1")
#         result = await cache.get("key1")
        
#         assert result == "value1"
    
#     @pytest.mark.asyncio
#     async def test_cache_expiration(self):
#         """Test cache expiration"""
#         cache = MemoryCache(max_size=10, ttl_seconds=1)
        
#         await cache.set("key1", "value1")
        
#         # Wait for expiration
#         await asyncio.sleep(1.1)
        
#         result = await cache.get("key1")
#         assert result is None
    
#     @pytest.mark.asyncio
#     async def test_cache_eviction(self):
#         """Test cache eviction when full"""
#         cache = MemoryCache(max_size=2, ttl_seconds=60)
        
#         await cache.set("key1", "value1")
#         await cache.set("key2", "value2")
        
#         # This should evict oldest
#         await cache.set("key3", "value3")
        
#         # key1 should be evicted
#         assert await cache.get("key1") is None
#         assert await cache.get("key2") == "value2"
#         assert await cache.get("key3") == "value3"


# class TestMemoryManager:
#     """Test enhanced memory manager"""
    
#     @pytest.mark.asyncio
#     async def test_memory_manager_initialization(self):
#         """Test memory manager initializes correctly"""
#         manager = MemoryManager()
        
#         assert manager.cache is not None
#         assert manager.local_fallback == {}
#         assert manager._initialized is False
    
#     @pytest.mark.asyncio
#     async def test_local_fallback_on_failure(self):
#         """Test local fallback when Mem0 fails"""
#         manager = MemoryManager()
#         manager.mem0 = None  # Simulate no Mem0
        
#         # Should use local fallback
#         result = await manager.add_memory(
#             messages=[{"role": "user", "content": "test"}],
#             user_id="test_user"
#         )
        
#         assert result is True
#         assert "test_user" in manager.local_fallback
    
#     @pytest.mark.asyncio
#     async def test_search_local_fallback(self):
#         """Test searching local fallback"""
#         manager = MemoryManager()
#         manager.mem0 = None
        
#         # Add to fallback
#         await manager.add_memory(
#             messages=[{"role": "user", "content": "test message about projects"}],
#             user_id="test_user"
#         )
        
#         # Search
#         results = await manager.search_memory(
#             query="projects",
#             user_id="test_user"
#         )
        
#         assert len(results) > 0
#         assert "projects" in results[0]["memory"]


class TestIntegration:
    """Integration tests"""
    
    @pytest.mark.asyncio
    async def test_retry_with_circuit_breaker(self):
        """Test retry mechanism works with circuit breaker"""
        breaker = CircuitBreaker("test", failure_threshold=3)
        call_count = 0
        
        @with_retry(max_retries=2, delay=0.01)
        async def function_with_breaker():
            nonlocal call_count
            call_count += 1
            return await breaker.call_async(lambda: "success")
        
        result = await function_with_breaker()
        assert result == "success"
    
    # @pytest.mark.asyncio
    # async def test_health_monitor_with_memory_manager(self):
    #     """Test health monitor checks memory manager"""
    #     manager = MemoryManager()
    #     health = await manager.health_check()
        
    #     # Should return True even without Mem0 (fallback available)
    #     assert health is True


# Performance benchmarks
# class TestPerformance:
#     """Performance tests"""
    
#     @pytest.mark.asyncio
#     async def test_cache_performance(self):
#         """Test cache lookup performance"""
#         cache = MemoryCache(max_size=1000)
        
#         # Add many items
#         for i in range(100):
#             await cache.set(f"key{i}", f"value{i}")
        
#         # Test lookup speed
#         import time
#         start = time.time()
        
#         for i in range(100):
#             await cache.get(f"key{i}")
        
#         duration = time.time() - start
        
#         # Should be very fast
#         assert duration < 0.1  # 100 lookups in < 100ms


if __name__ == "__main__":
    pytest.main([__file__, "-v"])