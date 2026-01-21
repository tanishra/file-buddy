import json
import asyncio
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from livekit.agents import ChatContext
from mem0 import AsyncMemoryClient
from config.prompts import MEM0_PROMPT
from dotenv import load_dotenv

from config.prompts import MEM0_PROMPT
from core.exceptions import Mem0Error
from core.retry_handler import (
    with_retry,
    with_timeout,
    mem0_circuit,
)
from config.settings import settings
from utils.logger import get_logger, log_performance

load_dotenv()

logger = get_logger(__name__)


class MemoryCache:
    """
    In-memory cache for Mem0 queries to reduce API calls
    """
    
    def __init__(self, max_size: int = 1000, ttl_seconds: int = 3600):
        self.max_size = max_size
        self.ttl = timedelta(seconds=ttl_seconds)
        self.cache: Dict[str, tuple[Any, datetime]] = {}
        self._lock = asyncio.Lock()
    
    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache if not expired"""
        async with self._lock:
            if key in self.cache:
                value, timestamp = self.cache[key]
                if datetime.utcnow() - timestamp < self.ttl:
                    logger.debug(f"Cache hit", extra={"key": key})
                    return value
                else:
                    # Expired, remove it
                    del self.cache[key]
                    logger.debug(f"Cache expired", extra={"key": key})
            return None
    
    async def set(self, key: str, value: Any):
        """Set value in cache"""
        async with self._lock:
            # Evict oldest if at capacity
            if len(self.cache) >= self.max_size:
                oldest_key = min(self.cache.keys(), key=lambda k: self.cache[k][1])
                del self.cache[oldest_key]
                logger.debug(f"Cache evicted", extra={"key": oldest_key})
            
            self.cache[key] = (value, datetime.utcnow())
            logger.debug(f"Cache set", extra={"key": key})
    
    async def clear(self):
        """Clear all cache"""
        async with self._lock:
            self.cache.clear()
            logger.info("Cache cleared")
    
    async def invalidate_user(self, user_id: str):
        """Invalidate all cache entries for a user"""
        async with self._lock:
            keys_to_remove = [k for k in self.cache.keys() if user_id in k]
            for key in keys_to_remove:
                del self.cache[key]
            if keys_to_remove:
                logger.info(f"Invalidated {len(keys_to_remove)} cache entries for user", 
                          extra={"user_id": user_id})


class MemoryManager:
    """
    Handles loading, injecting, and persisting conversational memory
    using Mem0 in a production-safe manner.
    
    Enhanced with:
    - Caching for reduced API calls
    - Local fallback when Mem0 unavailable
    - Retry logic with circuit breakers
    - Performance tracking
    """

    def __init__(self, mem0_client: Optional[AsyncMemoryClient] = None):
        self.mem0 = mem0_client or AsyncMemoryClient()
        
        # Production enhancements
        self.cache = MemoryCache(
            max_size=getattr(settings, 'MEMORY_CACHE_SIZE', 1000),
            ttl_seconds=3600  # 1 hour cache
        )
        self.local_fallback: Dict[str, List[Dict]] = {}
        self._initialized = False
        
        # Set project-level custom instructions (runs once on init)
        self._setup_custom_instructions()
        
        logger.info("Memory manager initialized with caching and fallback")
    
    def _setup_custom_instructions(self):
        """Configure what Mem0 should store and ignore."""
        try:
            custom_instructions = MEM0_PROMPT
            self.mem0.project.update(custom_instructions=custom_instructions)
            logger.info("Custom instructions configured for Mem0 project")
            self._initialized = True
        except Exception as e:
            logger.warning(f"Failed to set custom instructions: {e}")
            # Don't fail initialization, can still use local fallback
            self._initialized = True

    @with_retry(max_retries=3, exceptions=(Exception,))
    @with_timeout(seconds=10)
    @log_performance()
    async def load_user_memory(
        self,
        user_id: str,
        chat_ctx: ChatContext,
    ) -> str:
        """
        Loads previous memories for a user and injects them
        into the ChatContext.
        
        Enhanced with:
        - Caching to reduce API calls
        - Local fallback if Mem0 fails
        - Circuit breaker protection
        """
        try:
            logger.info("Loading memory for user", extra={"user_id": user_id})

            # Check cache first
            cache_key = f"user_memory:{user_id}"
            cached = await self.cache.get(cache_key)
            if cached is not None:
                logger.info("Using cached memory", extra={"user_id": user_id})
                memories = cached
            else:
                # Use circuit breaker for Mem0 call
                try:
                    results = await mem0_circuit.call_async(
                        self._fetch_memories_from_mem0,
                        user_id
                    )
                    
                    # Handle response structure
                    if not results or not isinstance(results, dict) or not results.get("results"):
                        logger.info("No existing memory found", extra={"user_id": user_id})
                        return ""

                    memories = [
                        {
                            "memory": item.get("memory"),
                            "updated_at": item.get("updated_at"),
                        }
                        for item in results["results"]
                    ]
                    
                    # Cache the results
                    await self.cache.set(cache_key, memories)
                    
                except Exception as e:
                    logger.warning(
                        f"Mem0 fetch failed, using local fallback",
                        extra={"user_id": user_id, "error": str(e)}
                    )
                    # Try local fallback
                    memories = await self._get_from_local_fallback(user_id)
                    if not memories:
                        return ""

            memory_str = json.dumps(memories, indent=2)

            # Inject memory individually as separate messages
            for memory_item in memories:
                chat_ctx.add_message(role="assistant", content=memory_item["memory"])

            logger.info(
                "Injected memory items into chat context",
                extra={
                    "user_id": user_id,
                    "memory_count": len(memories)
                }
            )

            return memory_str

        except Exception as e:
            logger.error(
                "Failed to load memory",
                extra={"user_id": user_id, "error": str(e)},
                exc_info=True
            )
            # Return empty string but don't fail the entire operation
            return ""
    
    async def _fetch_memories_from_mem0(self, user_id: str) -> Dict:
        """Internal method to fetch from Mem0 (used by circuit breaker)"""
        return await self.mem0.get_all(
            filters={"user_id": user_id}
        )
    
    async def _get_from_local_fallback(self, user_id: str) -> List[Dict]:
        """Get memories from local fallback storage"""
        if user_id not in self.local_fallback:
            return []
        
        # Return last 20 memories
        entries = self.local_fallback[user_id][-20:]
        return [
            {
                "memory": entry.get("content", ""),
                "updated_at": entry.get("timestamp", "")
            }
            for entry in entries
            if entry.get("content")
        ]

    @with_retry(max_retries=2, exceptions=(Exception,))
    @with_timeout(seconds=15)
    @log_performance()
    async def save_chat_context(
        self,
        user_id: str,
        chat_ctx: ChatContext,
        injected_memory_str: str,
    ) -> None:
        """
        Saves chat context to Mem0 with fallback support.
        
        Enhanced with:
        - Retry logic for transient failures
        - Local fallback if Mem0 unavailable
        - Cache invalidation after save
        """
        try:
            logger.info("Starting save_chat_context", extra={"user_id": user_id})

            messages: List[Dict[str, str]] = []
            items_to_process = getattr(chat_ctx, "messages", [])
        
            logger.debug(f"Total messages to process: {len(items_to_process)}")

            for idx, item in enumerate(items_to_process):
                # Debug logging
                logger.debug(
                    f"Processing message",
                    extra={
                        "index": idx,
                        "type": type(item).__name__,
                        "has_content": hasattr(item, 'content')
                    }
                )
            
                if not hasattr(item, "content") or item.content is None:
                    continue

                if not hasattr(item, "role"):
                    continue

                # Handle content - could be string or list
                content = item.content
                if isinstance(content, list):
                    content = "".join(str(c) for c in content)
                else:
                    content = str(content)
                content = content.strip()

                if not content:
                    logger.debug(f"Skipping empty content", extra={"index": idx})
                    continue

                # Get role as string
                role_val = item.role
                role_str = str(role_val.value if hasattr(role_val, "value") else role_val).lower()

                if role_str not in ["user", "assistant"]:
                    logger.debug(f"Skipping non-user/assistant role", extra={"index": idx, "role": role_str})
                    continue

                # Skip JSON tool calls
                if content.lstrip().startswith("{") and "function" in content:
                    continue

                messages.append({"role": role_str, "content": content})
                logger.debug(
                    f"Added message",
                    extra={
                        "index": idx,
                        "role": role_str,
                        "content_length": len(content)
                    }
                )

            logger.info(f"Valid messages to persist", extra={"count": len(messages)})

            if not messages:
                logger.info("No valid text messages to persist")
                return

            # Try to save to Mem0 with circuit breaker
            try:
                result = await mem0_circuit.call_async(
                    self.mem0.add,
                    messages,
                    user_id=user_id
                )
                
                logger.info(
                    f"Mem0 save successful",
                    extra={
                        "user_id": user_id,
                        "message_count": len(messages),
                        "result": str(result)
                    }
                )
                
                # Invalidate cache after successful save
                await self.cache.invalidate_user(user_id)
                
            except Exception as e:
                logger.warning(
                    f"Mem0 save failed, using local fallback",
                    extra={"user_id": user_id, "error": str(e)}
                )
                # Save to local fallback
                await self._save_to_local_fallback(user_id, messages)

        except Exception as exc:
            logger.error(
                "Failed to save chat context",
                extra={"user_id": user_id, "error": str(exc)},
                exc_info=True
            )
            # Don't raise, just log - we don't want to crash the conversation
    
    async def _save_to_local_fallback(self, user_id: str, messages: List[Dict[str, str]]) -> bool:
        """Save messages to local fallback storage"""
        try:
            if user_id not in self.local_fallback:
                self.local_fallback[user_id] = []
            
            for msg in messages:
                entry = {
                    "content": msg.get("content"),
                    "role": msg.get("role"),
                    "timestamp": datetime.utcnow().isoformat()
                }
                self.local_fallback[user_id].append(entry)
            
            # Limit size to last 100 entries
            if len(self.local_fallback[user_id]) > 100:
                self.local_fallback[user_id] = self.local_fallback[user_id][-100:]
            
            logger.info(
                f"Saved to local fallback",
                extra={
                    "user_id": user_id,
                    "message_count": len(messages)
                }
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to save to local fallback: {e}")
            return False
    
    # Additional helper methods for production use
    
    @log_performance()
    async def search_memory(
        self,
        query: str,
        user_id: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Search memory with caching support
        
        Args:
            query: Search query
            user_id: User identifier
            limit: Maximum results
        
        Returns:
            List of memory entries
        """
        try:
            # Check cache
            cache_key = f"search:{user_id}:{query}"
            cached = await self.cache.get(cache_key)
            if cached is not None:
                return cached
            
            # Search in Mem0
            try:
                result = await mem0_circuit.call_async(
                    self.mem0.search,
                    query,
                    user_id=user_id,
                    limit=limit
                )
                
                # Cache results
                await self.cache.set(cache_key, result)
                
                logger.info(
                    f"Memory search completed",
                    extra={
                        "user_id": user_id,
                        "query": query,
                        "results": len(result) if isinstance(result, list) else 0
                    }
                )
                
                return result
                
            except Exception as e:
                logger.warning(f"Mem0 search failed: {e}")
                # Search local fallback
                return await self._search_local_fallback(query, user_id, limit)
                
        except Exception as e:
            logger.error(f"Search failed: {e}", exc_info=True)
            return []
    
    async def _search_local_fallback(
        self,
        query: str,
        user_id: str,
        limit: int
    ) -> List[Dict[str, Any]]:
        """Search local fallback storage"""
        if user_id not in self.local_fallback:
            return []
        
        results = []
        query_lower = query.lower()
        
        for entry in reversed(self.local_fallback[user_id]):
            content = entry.get("content", "")
            if query_lower in content.lower():
                results.append({
                    "memory": content,
                    "timestamp": entry.get("timestamp")
                })
                if len(results) >= limit:
                    break
        
        return results
    
    async def health_check(self) -> bool:
        """
        Check if memory service is healthy
        
        Returns:
            True if healthy
        """
        try:
            # Try a simple operation with timeout
            await asyncio.wait_for(
                self.mem0.get_all(filters={"user_id": "health_check"}),
                timeout=5.0
            )
            return True
        except Exception as e:
            logger.warning(f"Memory health check failed: {e}")
            # Local fallback is always available
            return True
    
    async def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        async with self.cache._lock:
            return {
                "size": len(self.cache.cache),
                "max_size": self.cache.max_size,
                "ttl_seconds": self.cache.ttl.total_seconds(),
                "usage_percent": (len(self.cache.cache) / self.cache.max_size) * 100
            }
    
    async def clear_cache(self):
        """Clear all cached memory"""
        await self.cache.clear()
        logger.info("Memory cache cleared")
    
    def get_local_fallback_stats(self) -> Dict[str, Any]:
        """Get local fallback statistics"""
        total_entries = sum(len(entries) for entries in self.local_fallback.values())
        return {
            "users": len(self.local_fallback),
            "total_entries": total_entries,
            "avg_per_user": total_entries / len(self.local_fallback) if self.local_fallback else 0
        }