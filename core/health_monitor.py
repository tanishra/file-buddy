import asyncio
import psutil
import platform
from datetime import datetime
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict
from enum import Enum

from core.exceptions import HealthCheckError
from config.settings import settings
from utils.logger import get_logger

logger = get_logger(__name__)


class HealthStatus(Enum):
    """Health check status"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class ComponentHealth:
    """Health status of a component"""
    name: str
    status: HealthStatus
    message: str
    response_time_ms: Optional[float] = None
    details: Optional[Dict[str, Any]] = None
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()
        if self.details is None:
            self.details = {}
    
    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data['status'] = self.status.value
        data['timestamp'] = self.timestamp.isoformat()
        return data


@dataclass
class SystemHealth:
    """Overall system health"""
    status: HealthStatus
    components: Dict[str, ComponentHealth]
    system_info: Dict[str, Any]
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'status': self.status.value,
            'components': {k: v.to_dict() for k, v in self.components.items()},
            'system_info': self.system_info,
            'timestamp': self.timestamp.isoformat()
        }
    
    def is_healthy(self) -> bool:
        """Check if system is healthy"""
        return self.status == HealthStatus.HEALTHY
    
    def is_degraded(self) -> bool:
        """Check if system is degraded"""
        return self.status == HealthStatus.DEGRADED


class HealthMonitor:
    """
    Monitors system health and component status
    """
    
    def __init__(self):
        self.last_check: Optional[SystemHealth] = None
        self.check_interval = settings.HEALTH_CHECK_INTERVAL
        self._monitoring = False
        self._task: Optional[asyncio.Task] = None
        
        logger.info("Health monitor initialized")
    
    async def check_filesystem(self) -> ComponentHealth:
        """Check filesystem health"""
        start = asyncio.get_event_loop().time()
        
        try:
            disk = psutil.disk_usage('/')
            
            # Check disk space
            free_percent = (disk.free / disk.total) * 100
            
            if free_percent < 5:
                status = HealthStatus.UNHEALTHY
                message = f"Critical: Only {free_percent:.1f}% disk space remaining"
            elif free_percent < 15:
                status = HealthStatus.DEGRADED
                message = f"Warning: {free_percent:.1f}% disk space remaining"
            else:
                status = HealthStatus.HEALTHY
                message = f"Disk space: {free_percent:.1f}% free"
            
            response_time = (asyncio.get_event_loop().time() - start) * 1000
            
            return ComponentHealth(
                name="filesystem",
                status=status,
                message=message,
                response_time_ms=response_time,
                details={
                    "total_gb": disk.total / (1024**3),
                    "used_gb": disk.used / (1024**3),
                    "free_gb": disk.free / (1024**3),
                    "percent_used": disk.percent
                }
            )
            
        except Exception as e:
            logger.error(f"Filesystem check failed: {e}")
            return ComponentHealth(
                name="filesystem",
                status=HealthStatus.UNHEALTHY,
                message=f"Check failed: {str(e)}"
            )
    
    async def check_memory(self) -> ComponentHealth:
        """Check memory health"""
        start = asyncio.get_event_loop().time()
        
        try:
            memory = psutil.virtual_memory()
            
            if memory.percent > 90:
                status = HealthStatus.UNHEALTHY
                message = f"Critical: {memory.percent}% memory used"
            elif memory.percent > 80:
                status = HealthStatus.DEGRADED
                message = f"Warning: {memory.percent}% memory used"
            else:
                status = HealthStatus.HEALTHY
                message = f"Memory usage: {memory.percent}%"
            
            response_time = (asyncio.get_event_loop().time() - start) * 1000
            
            return ComponentHealth(
                name="memory",
                status=status,
                message=message,
                response_time_ms=response_time,
                details={
                    "total_gb": memory.total / (1024**3),
                    "available_gb": memory.available / (1024**3),
                    "percent_used": memory.percent
                }
            )
            
        except Exception as e:
            logger.error(f"Memory check failed: {e}")
            return ComponentHealth(
                name="memory",
                status=HealthStatus.UNHEALTHY,
                message=f"Check failed: {str(e)}"
            )
    
    async def check_cpu(self) -> ComponentHealth:
        """Check CPU health"""
        start = asyncio.get_event_loop().time()
        
        try:
            # Get CPU usage over 1 second
            cpu_percent = psutil.cpu_percent(interval=1)
            cpu_count = psutil.cpu_count()
            
            if cpu_percent > 90:
                status = HealthStatus.DEGRADED
                message = f"High CPU usage: {cpu_percent}%"
            else:
                status = HealthStatus.HEALTHY
                message = f"CPU usage: {cpu_percent}%"
            
            response_time = (asyncio.get_event_loop().time() - start) * 1000
            
            return ComponentHealth(
                name="cpu",
                status=status,
                message=message,
                response_time_ms=response_time,
                details={
                    "percent": cpu_percent,
                    "count": cpu_count
                }
            )
            
        except Exception as e:
            logger.error(f"CPU check failed: {e}")
            return ComponentHealth(
                name="cpu",
                status=HealthStatus.UNHEALTHY,
                message=f"Check failed: {str(e)}"
            )
    
    async def check_openai(self) -> ComponentHealth:
        """Check OpenAI API connectivity"""
        start = asyncio.get_event_loop().time()
        
        try:
            # Simple connectivity check - you can enhance this
            # with actual API call if needed
            import openai
            
            # Just verify API key is set
            if not settings.OPENAI_API_KEY:
                return ComponentHealth(
                    name="openai",
                    status=HealthStatus.UNHEALTHY,
                    message="API key not configured"
                )
            
            response_time = (asyncio.get_event_loop().time() - start) * 1000
            
            return ComponentHealth(
                name="openai",
                status=HealthStatus.HEALTHY,
                message="API key configured",
                response_time_ms=response_time
            )
            
        except Exception as e:
            logger.error(f"OpenAI check failed: {e}")
            return ComponentHealth(
                name="openai",
                status=HealthStatus.DEGRADED,
                message=f"Check failed: {str(e)}"
            )
    
    async def check_mem0(self) -> ComponentHealth:
        """Check Mem0 service"""
        start = asyncio.get_event_loop().time()
        
        try:
            if not settings.MEM0_API_KEY:
                return ComponentHealth(
                    name="mem0",
                    status=HealthStatus.DEGRADED,
                    message="API key not configured (optional)"
                )
            
            response_time = (asyncio.get_event_loop().time() - start) * 1000
            
            return ComponentHealth(
                name="mem0",
                status=HealthStatus.HEALTHY,
                message="API key configured",
                response_time_ms=response_time
            )
            
        except Exception as e:
            logger.error(f"Mem0 check failed: {e}")
            return ComponentHealth(
                name="mem0",
                status=HealthStatus.DEGRADED,
                message=f"Check failed: {str(e)}"
            )
    
    def get_system_info(self) -> Dict[str, Any]:
        """Get system information"""
        return {
            "platform": platform.system(),
            "platform_version": platform.version(),
            "architecture": platform.machine(),
            "python_version": platform.python_version(),
            "hostname": platform.node(),
            "app_version": settings.APP_VERSION,
            "environment": settings.ENVIRONMENT
        }
    
    async def perform_health_check(self) -> SystemHealth:
        """Perform complete health check"""
        logger.debug("Performing health check")
        
        # Run all checks concurrently
        checks = await asyncio.gather(
            self.check_filesystem(),
            self.check_memory(),
            self.check_cpu(),
            self.check_openai(),
            self.check_mem0(),
            return_exceptions=True
        )
        
        # Build components dict
        components = {}
        for check in checks:
            if isinstance(check, ComponentHealth):
                components[check.name] = check
            else:
                logger.error(f"Health check exception: {check}")
        
        # Determine overall status
        if all(c.status == HealthStatus.HEALTHY for c in components.values()):
            overall_status = HealthStatus.HEALTHY
        elif any(c.status == HealthStatus.UNHEALTHY for c in components.values()):
            overall_status = HealthStatus.UNHEALTHY
        else:
            overall_status = HealthStatus.DEGRADED
        
        system_health = SystemHealth(
            status=overall_status,
            components=components,
            system_info=self.get_system_info()
        )
        
        self.last_check = system_health
        
        logger.info(
            f"Health check completed",
            extra={
                "status": overall_status.value,
                "components": len(components)
            }
        )
        
        return system_health
    
    async def start_monitoring(self):
        """Start continuous health monitoring"""
        if self._monitoring:
            logger.warning("Health monitoring already running")
            return
        
        self._monitoring = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info("Health monitoring started")
    
    async def stop_monitoring(self):
        """Stop health monitoring"""
        self._monitoring = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Health monitoring stopped")
    
    async def _monitor_loop(self):
        """Continuous monitoring loop"""
        while self._monitoring:
            try:
                health = await self.perform_health_check()
                
                if not health.is_healthy():
                    logger.warning(
                        "System health degraded",
                        extra={"health": health.to_dict()}
                    )
                
                await asyncio.sleep(self.check_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health monitoring error: {e}")
                await asyncio.sleep(self.check_interval)


# Global health monitor instance
health_monitor = HealthMonitor()