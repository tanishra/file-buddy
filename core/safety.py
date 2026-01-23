from pathlib import Path
from typing import List
from utils.logger import get_logger
from utils.path_utils import validate_path
from config.policies import is_executable_file, is_sensitive_file
from config.settings import settings

logger = get_logger(__name__)

class SafetyViolation(Exception):
    """Safety check failed"""
    pass

class SafetyChecker:
    """Validates operations for safety"""
    
    def __init__(self):
        self.logger = logger.bind(component="SafetyChecker")
    
    def validate_operation(
        self,
        operation_type: str,
        paths: List[Path],
        **kwargs
    ) -> None:
        """
        Validate an operation for safety
        
        Args:
            operation_type: Type of operation
            paths: Paths involved
            **kwargs: Additional parameters
            
        Raises:
            SafetyViolation: If operation is unsafe
        """
        self.logger.info(
            "validating_operation",
            operation=operation_type,
            path_count=len(paths)
        )
        
        # Check path count
        if len(paths) > settings.MAX_FILES_PER_OPERATION:
            raise SafetyViolation(
                f"Operation exceeds maximum file limit "
                f"({settings.MAX_FILES_PER_OPERATION})"
            )
        
        # Validate each path
        for path in paths:
            try:
                validate_path(path, must_exist=(operation_type != "create"))
            except Exception as e:
                raise SafetyViolation(f"Path validation failed: {e}")
        
        # Operation-specific checks
        if operation_type == "delete":
            self._validate_delete(paths)
        elif operation_type == "execute":
            self._validate_execute(paths)
        
        self.logger.info("operation_validated", operation=operation_type)
    
    def _validate_delete(self, paths: List[Path]) -> None:
        """Validate delete operation"""
        for path in paths:
            if path.is_dir() and any(path.iterdir()):
                raise SafetyViolation(
                    f"Cannot delete non-empty directory: {path}"
                )
    
    def _validate_execute(self, paths: List[Path]) -> None:
        """Validate execute operation"""
        for path in paths:
            if not is_executable_file(path):
                raise SafetyViolation(
                    f"File is not executable: {path}"
                )
    
    def requires_confirmation(
        self,
        operation_type: str,
        paths: List[Path]
    ) -> bool:
        """
        Check if operation requires user confirmation
        
        Args:
            operation_type: Type of operation
            paths: Paths involved
            
        Returns:
            True if confirmation needed
        """
        # Always confirm dangerous operations
        if operation_type in ["delete", "execute"]:
            return True
        
        # Confirm if operating on many files
        from config.settings import REQUIRE_CONFIRMATION_FILE_COUNT
        if len(paths) > REQUIRE_CONFIRMATION_FILE_COUNT:
            return True
        
        # Confirm if any sensitive files
        if any(is_sensitive_file(p) for p in paths):
            return True
        
        return False