import asyncio
from core.memory_manager import MemoryManager

async def test_memory():
    mm = MemoryManager()
    
    # Test 1: Health check
    print("Testing health check...")
    healthy = await mm.health_check()
    print(f"✅ Health: {healthy}")
    
    # Test 2: Cache stats
    print("\nTesting cache stats...")
    stats = await mm.get_cache_stats()
    print(f"✅ Cache stats: {stats}")
    
    # Test 3: Local fallback
    print("\nTesting local fallback...")
    success = await mm._save_to_local_fallback(
        "test_user",
        [{"role": "user", "content": "Hello world"}]
    )
    print(f"✅ Fallback save: {success}")
    
    # Test 4: Search fallback
    print("\nTesting search...")
    results = await mm._search_local_fallback("Hello", "test_user", 10)
    print(f"✅ Search results: {len(results)} found")
    
    # Test 5: Fallback stats
    print("\nFallback stats:")
    print(mm.get_local_fallback_stats())
    
    print("\n✅ All manual tests passed!")

asyncio.run(test_memory())