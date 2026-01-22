import asyncio
from core.health_monitor import health_monitor
from core.memory_manager import MemoryManager

async def main():
    print("🔍 System Health Check\n")
    
    # Health check
    health = await health_monitor.perform_health_check()
    print(f"Overall: {health.status.value}\n")
    
    for name, comp in health.components.items():
        symbol = "✅" if comp.status.value == "healthy" else "⚠️"
        print(f"{symbol} {name}: {comp.message}")
    
    # Memory stats
    print("\n📊 Memory Manager Stats\n")
    mm = MemoryManager()
    cache = await mm.get_cache_stats()
    print(f"Cache: {cache['size']}/{cache['max_size']} ({cache['usage_percent']:.1f}%)")
    
    fallback = mm.get_local_fallback_stats()
    print(f"Fallback: {fallback['users']} users, {fallback['total_entries']} entries")

asyncio.run(main())