import logging
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional
from datetime import datetime
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
import structlog
from config.settings import settings, get_log_level


class JSONFormatter(logging.Formatter):
    """
    JSON formatter for structured logging
    """
    
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        # Add extra fields
        if hasattr(record, "extra"):
            log_data.update(record.extra)
        
        # Add any custom attributes
        for key, value in record.__dict__.items():
            if key not in [
                "name", "msg", "args", "created", "filename", "funcName",
                "levelname", "levelno", "lineno", "module", "msecs",
                "message", "pathname", "funcName", "process", "processName", "relativeCreated",
                "thread", "threadName", "exc_info", "exc_text", "stack_info"
            ]:
                log_data[key] = value
        
        # Add application context
        log_data["app"] = settings.APP_NAME
        log_data["version"] = settings.APP_VERSION
        log_data["environment"] = settings.ENVIRONMENT
        
        return json.dumps(log_data)


class TextFormatter(logging.Formatter):
    """
    Human-readable text formatter
    """
    
    # Color codes for different log levels
    COLORS = {
        'DEBUG': '\033[36m',      # Cyan
        'INFO': '\033[32m',       # Green
        'WARNING': '\033[33m',    # Yellow
        'ERROR': '\033[31m',      # Red
        'CRITICAL': '\033[35m',   # Magenta
    }
    RESET = '\033[0m'
    
    def __init__(self, use_colors: bool = True):
        super().__init__()
        self.use_colors = use_colors and sys.stdout.isatty()
    
    def format(self, record: logging.LogRecord) -> str:
        # Format timestamp
        timestamp = datetime.fromtimestamp(record.created).strftime('%Y-%m-%d %H:%M:%S')
        
        # Get color for level
        color = self.COLORS.get(record.levelname, '')
        reset = self.RESET if self.use_colors else ''
        
        # Build base message
        if self.use_colors:
            message = (
                f"{color}{timestamp}{reset} "
                f"[{color}{record.levelname:8}{reset}] "
                f"{record.name:20} | {record.getMessage()}"
            )
        else:
            message = (
                f"{timestamp} "
                f"[{record.levelname:8}] "
                f"{record.name:20} | {record.getMessage()}"
            )
        
        # Add extra fields if present
        extra_fields = []
        for key, value in record.__dict__.items():
            if key not in [
                "name", "msg", "args", "created", "filename", "funcName",
                "levelname", "levelno", "lineno", "module", "msecs",
                "message", "pathname", "process", "processName", "relativeCreated",
                "thread", "threadName", "exc_info", "exc_text", "stack_info"
            ]:
                extra_fields.append(f"{key}={value}")
        
        if extra_fields:
            message += f" | {', '.join(extra_fields)}"
        
        # Add exception info
        if record.exc_info:
            message += "\n" + self.formatException(record.exc_info)
        
        return message


def setup_logger(
    name: str,
    level: Optional[str] = None,
    log_file: Optional[str] = None,
    console: bool = True,
    json_format: bool = None
) -> logging.Logger:
    """
    Setup a logger with appropriate handlers and formatters
    
    Args:
        name: Logger name
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Path to log file (optional)
        console: Whether to log to console
        json_format: Use JSON format (default: based on settings)
    
    Returns:
        Configured logger
    """
    logger = logging.getLogger(name)
    
    # Set level
    log_level = level or get_log_level()
    logger.setLevel(getattr(logging, log_level.upper()))
    
    # Clear existing handlers
    logger.handlers.clear()
    
    # Determine format
    if json_format is None:
        json_format = settings.LOG_FORMAT == "json"
    
    formatter = JSONFormatter() if json_format else TextFormatter()
    
    # Console handler
    if console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    
    # File handler
    if log_file or settings.LOG_FILE:
        file_path = Path(log_file or settings.LOG_FILE)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Use rotating file handler
        file_handler = RotatingFileHandler(
            file_path,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5
        )
        file_handler.setFormatter(JSONFormatter())  # Always use JSON for files
        logger.addHandler(file_handler)
    
    # Prevent propagation to root logger
    logger.propagate = False
    
    return logger


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance with standard configuration
    
    Args:
        name: Logger name (usually __name__)
    
    Returns:
        Configured logger
    """
    return setup_logger(name)


class LoggerAdapter(logging.LoggerAdapter):
    """
    Logger adapter for adding contextual information
    """
    
    def process(self, msg: str, kwargs: Dict[str, Any]) -> tuple:
        """Add extra context to log messages"""
        extra = kwargs.get('extra', {})
        extra.update(self.extra)
        kwargs['extra'] = extra
        return msg, kwargs


def get_context_logger(name: str, **context) -> LoggerAdapter:
    """
    Get a logger with additional context
    
    Args:
        name: Logger name
        **context: Additional context to include in all logs
    
    Returns:
        Logger adapter with context
    """
    logger = get_logger(name)
    return LoggerAdapter(logger, context)


# Performance logging decorator
def log_performance(logger: Optional[logging.Logger] = None):
    """
    Decorator to log function execution time
    
    Args:
        logger: Logger to use (default: creates one from function name)
    """
    import time
    from functools import wraps
    
    def decorator(func):
        nonlocal logger
        if logger is None:
            logger = get_logger(func.__module__)
        
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start = time.time()
            try:
                result = await func(*args, **kwargs)
                duration = (time.time() - start) * 1000
                logger.debug(
                    f"{func.__name__} completed",
                    extra={
                        "function": func.__name__,
                        "duration_ms": duration,
                        "status": "success"
                    }
                )
                return result
            except Exception as e:
                duration = (time.time() - start) * 1000
                logger.error(
                    f"{func.__name__} failed",
                    extra={
                        "function": func.__name__,
                        "duration_ms": duration,
                        "status": "error",
                        "error": str(e)
                    },
                    exc_info=True
                )
                raise
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start = time.time()
            try:
                result = func(*args, **kwargs)
                duration = (time.time() - start) * 1000
                logger.debug(
                    f"{func.__name__} completed",
                    extra={
                        "function": func.__name__,
                        "duration_ms": duration,
                        "status": "success"
                    }
                )
                return result
            except Exception as e:
                duration = (time.time() - start) * 1000
                logger.error(
                    f"{func.__name__} failed",
                    extra={
                        "function": func.__name__,
                        "duration_ms": duration,
                        "status": "error",
                        "error": str(e)
                    },
                    exc_info=True
                )
                raise
        
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    
    return decorator


# Setup root logger on import
_root_logger = setup_logger("filebuddy")


def setup_logging():
    """Configure structured logging using structlog"""
    
    # Configure structlog
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.filter_by_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer() if settings.LOG_FORMAT == "json"
            else structlog.dev.ConsoleRenderer(colors=True),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    
    # Configure standard logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, get_log_level().upper()),
    )


def get_structlog_logger(name: str):
    """Get a structlog logger instance"""
    return structlog.get_logger(name)


# Initialize structlog logging on import
setup_logging()