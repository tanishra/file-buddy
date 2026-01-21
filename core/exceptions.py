from typing import Optional, Dict, Any


class FileBuddyError(Exception):
    """Base exception for all FileBuddy errors"""
    
    def __init__(
        self,
        message: str,
        error_code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        recoverable: bool = True
    ):
        self.message = message
        self.error_code = error_code or self.__class__.__name__
        self.details = details or {}
        self.recoverable = recoverable
        super().__init__(self.message)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for logging"""
        return {
            "error_type": self.__class__.__name__,
            "error_code": self.error_code,
            "message": self.message,
            "details": self.details,
            "recoverable": self.recoverable
        }


# API Related Errors
class APIError(FileBuddyError):
    """Base class for API-related errors"""
    pass


class OpenAIError(APIError):
    """OpenAI API errors"""
    pass


class DeepgramError(APIError):
    """Deepgram API errors"""
    pass


class Mem0Error(APIError):
    """Mem0 memory service errors"""
    pass


class LiveKitError(APIError):
    """LiveKit connection errors"""
    pass


class RateLimitError(APIError):
    """Rate limit exceeded"""
    
    def __init__(self, message: str, retry_after: Optional[int] = None, **kwargs):
        super().__init__(message, **kwargs)
        self.retry_after = retry_after
        self.details["retry_after"] = retry_after


class QuotaExceededError(APIError):
    """API quota exceeded"""
    
    def __init__(self, message: str, quota_limit: Optional[int] = None, **kwargs):
        super().__init__(message, recoverable=False, **kwargs)
        self.quota_limit = quota_limit
        self.details["quota_limit"] = quota_limit


# File System Errors
class FileSystemError(FileBuddyError):
    """Base class for filesystem errors"""
    pass


class FileNotFoundError(FileSystemError):
    """File or directory not found"""
    pass


class PermissionError(FileSystemError):
    """Insufficient permissions"""
    
    def __init__(self, message: str, path: Optional[str] = None, **kwargs):
        super().__init__(message, recoverable=False, **kwargs)
        self.path = path
        self.details["path"] = path


class PathSecurityError(FileSystemError):
    """Path is outside allowed directories"""
    
    def __init__(self, message: str, path: str, **kwargs):
        super().__init__(message, recoverable=False, **kwargs)
        self.path = path
        self.details["path"] = path


class DiskSpaceError(FileSystemError):
    """Insufficient disk space"""
    
    def __init__(self, message: str, required_space: Optional[int] = None, **kwargs):
        super().__init__(message, recoverable=False, **kwargs)
        self.required_space = required_space
        self.details["required_space"] = required_space


class FileOperationError(FileSystemError):
    """Generic file operation failed"""
    pass


# Operation Errors
class OperationError(FileBuddyError):
    """Base class for operation errors"""
    pass


class ConfirmationRequiredError(OperationError):
    """Operation requires user confirmation"""
    
    def __init__(self, message: str, operation_id: str, **kwargs):
        super().__init__(message, recoverable=True, **kwargs)
        self.operation_id = operation_id
        self.details["operation_id"] = operation_id


class OperationCancelledError(OperationError):
    """User cancelled the operation"""
    
    def __init__(self, message: str = "Operation cancelled by user", **kwargs):
        super().__init__(message, recoverable=False, **kwargs)


class UndoError(OperationError):
    """Failed to undo operation"""
    pass


class ValidationError(OperationError):
    """Input validation failed"""
    
    def __init__(self, message: str, field: Optional[str] = None, **kwargs):
        super().__init__(message, recoverable=True, **kwargs)
        self.field = field
        self.details["field"] = field


# System Errors
class SystemError(FileBuddyError):
    """System-level errors"""
    pass


class CircuitBreakerOpenError(SystemError):
    """Circuit breaker is open"""
    
    def __init__(self, message: str, service: str, retry_after: int, **kwargs):
        super().__init__(message, recoverable=True, **kwargs)
        self.service = service
        self.retry_after = retry_after
        self.details.update({"service": service, "retry_after": retry_after})


class TimeoutError(SystemError):
    """Operation timed out"""
    
    def __init__(self, message: str, timeout_seconds: Optional[int] = None, **kwargs):
        super().__init__(message, recoverable=True, **kwargs)
        self.timeout_seconds = timeout_seconds
        self.details["timeout_seconds"] = timeout_seconds


class ConfigurationError(SystemError):
    """Configuration error"""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(message, recoverable=False, **kwargs)


class HealthCheckError(SystemError):
    """Health check failed"""
    
    def __init__(self, message: str, component: str, **kwargs):
        super().__init__(message, recoverable=True, **kwargs)
        self.component = component
        self.details["component"] = component