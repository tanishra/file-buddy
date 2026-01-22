from pathlib import Path
from typing import List, Tuple, Optional
import os

from config.security_config import security_config
from core.exceptions import PathSecurityError, ValidationError
from utils.logger import get_logger

logger = get_logger(__name__)


class PathValidator:
    """
    Validates and sanitizes file paths for security
    """
    
    def __init__(self):
        self.allowed_paths = security_config.get_allowed_base_paths()
        self.forbidden_paths = security_config.get_forbidden_paths()
        self.forbidden_patterns = security_config.get_forbidden_patterns()
        self.forbidden_extensions = security_config.get_forbidden_extensions()
        
        logger.info(
            "PathValidator initialized",
            extra={
                "allowed_bases": len(self.allowed_paths),
                "forbidden_paths": len(self.forbidden_paths)
            }
        )
    
    def validate_path(
        self,
        path: str | Path,
        operation: str = "access",
        must_exist: bool = False
    ) -> Path:
        """
        Validate a path for security
        
        Args:
            path: Path to validate
            operation: Operation type (read, write, delete)
            must_exist: Whether path must exist
            
        Returns:
            Validated Path object
            
        Raises:
            PathSecurityError: If path violates security rules
            ValidationError: If path is invalid
        """
        try:
            # Convert to Path and resolve
            if isinstance(path, str):
                path = Path(path).expanduser()
            else:
                path = path.expanduser()
            
            # Resolve to absolute path (follows symlinks)
            try:
                resolved = path.resolve(strict=must_exist)
            except (OSError, RuntimeError) as e:
                if must_exist:
                    raise ValidationError(
                        f"Path does not exist: {path}",
                        field="path"
                    )
                resolved = path.resolve(strict=False)
            
            # Check if path is under allowed directories
            if not self._is_under_allowed_paths(resolved):
                raise PathSecurityError(
                    f"Path '{resolved}' is outside allowed directories",
                    path=str(resolved)
                )
            
            # Check if path is in forbidden directories
            if self._is_forbidden_path(resolved):
                raise PathSecurityError(
                    f"Path '{resolved}' is in a forbidden directory",
                    path=str(resolved)
                )
            
            # Check for forbidden patterns in path
            if self._contains_forbidden_pattern(resolved):
                raise PathSecurityError(
                    f"Path '{resolved}' contains forbidden patterns",
                    path=str(resolved)
                )
            
            # Check file extension for delete operations
            if operation == "delete" and resolved.is_file():
                if resolved.suffix.lower() in self.forbidden_extensions:
                    raise PathSecurityError(
                        f"Cannot delete files with extension {resolved.suffix}",
                        path=str(resolved)
                    )
            
            # Check if protected file
            if operation in ["delete", "modify"] and resolved.is_file():
                if security_config.is_protected_file(resolved):
                    raise PathSecurityError(
                        f"File '{resolved.name}' is protected",
                        path=str(resolved)
                    )
            
            # Check if sensitive directory
            if security_config.is_sensitive_directory(resolved):
                logger.warning(
                    "Accessing sensitive directory",
                    extra={
                        "path": str(resolved),
                        "operation": operation
                    }
                )
            
            logger.debug(
                f"Path validated",
                extra={
                    "path": str(resolved),
                    "operation": operation
                }
            )
            
            return resolved
            
        except (PathSecurityError, ValidationError):
            raise
        except Exception as e:
            logger.error(f"Path validation error: {e}", exc_info=True)
            raise ValidationError(
                f"Invalid path: {e}",
                field="path"
            )
    
    def validate_paths(
        self,
        paths: List[str | Path],
        operation: str = "access",
        must_exist: bool = False
    ) -> List[Path]:
        """
        Validate multiple paths
        
        Returns:
            List of validated Path objects
        """
        validated = []
        errors = []
        
        for path in paths:
            try:
                validated.append(
                    self.validate_path(path, operation, must_exist)
                )
            except (PathSecurityError, ValidationError) as e:
                errors.append((path, str(e)))
        
        if errors:
            error_msg = "\n".join([f"- {p}: {e}" for p, e in errors])
            raise ValidationError(
                f"Path validation failed:\n{error_msg}",
                field="paths"
            )
        
        return validated
    
    def _is_under_allowed_paths(self, path: Path) -> bool:
        """Check if path is under any allowed base path"""
        try:
            for allowed in self.allowed_paths:
                try:
                    allowed_resolved = allowed.resolve(strict=False)
                    if path.is_relative_to(allowed_resolved):
                        return True
                except (ValueError, OSError):
                    continue
            return False
        except Exception as e:
            logger.error(f"Error checking allowed paths: {e}")
            return False
    
    def _is_forbidden_path(self, path: Path) -> bool:
        """Check if path is in forbidden directories"""
        try:
            for forbidden in self.forbidden_paths:
                try:
                    forbidden_resolved = forbidden.resolve(strict=False)
                    if path.is_relative_to(forbidden_resolved):
                        return True
                except (ValueError, OSError):
                    continue
            return False
        except Exception as e:
            logger.error(f"Error checking forbidden paths: {e}")
            return True  # Fail secure
    
    def _contains_forbidden_pattern(self, path: Path) -> bool:
        """Check if path contains forbidden patterns"""
        path_str = str(path).lower()
        path_parts = set(path.parts)
        
        for pattern in self.forbidden_patterns:
            if pattern.lower() in path_str:
                return True
            if pattern in path_parts:
                return True
        
        return False
    
    def get_safe_operation_summary(
        self,
        paths: List[Path],
        operation: str
    ) -> dict:
        """
        Get summary of operation for user confirmation
        
        Returns:
            Dictionary with operation details
        """
        total_size = 0
        file_count = 0
        dir_count = 0
        
        for path in paths:
            if path.is_file():
                file_count += 1
                try:
                    total_size += path.stat().st_size
                except:
                    pass
            elif path.is_dir():
                dir_count += 1
                # Count directory contents
                try:
                    for item in path.rglob("*"):
                        if item.is_file():
                            file_count += 1
                            total_size += item.stat().st_size
                except:
                    pass
        
        return {
            "operation": operation,
            "path_count": len(paths),
            "file_count": file_count,
            "dir_count": dir_count,
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "paths_preview": [str(p) for p in paths[:5]]
        }


class SecurityEnforcer:
    """
    Enforces security policies on file operations
    """
    
    def __init__(self):
        self.validator = PathValidator()
        logger.info("SecurityEnforcer initialized")
    
    def check_operation_allowed(
        self,
        operation: str,
        paths: List[str | Path],
        **kwargs
    ) -> Tuple[bool, str]:
        """
        Check if operation is allowed
        
        Args:
            operation: Operation name
            paths: Paths involved
            **kwargs: Additional operation parameters
            
        Returns:
            Tuple of (allowed, reason)
        """
        try:
            # Validate all paths
            validated_paths = self.validator.validate_paths(
                paths,
                operation=self._map_operation_to_action(operation),
                must_exist=operation not in ["create_file", "create_folder"]
            )
            
            # Check batch size limits
            if len(validated_paths) > security_config.MAX_BATCH_SIZE:
                return False, f"Batch size exceeds limit ({security_config.MAX_BATCH_SIZE})"
            
            # Check total size for batch operations
            if operation in ["move_files", "copy_files", "delete_files"]:
                total_size = self._calculate_total_size(validated_paths)
                if total_size > security_config.MAX_BATCH_TOTAL_SIZE:
                    size_mb = total_size / (1024 * 1024)
                    limit_mb = security_config.MAX_BATCH_TOTAL_SIZE / (1024 * 1024)
                    return False, f"Total size {size_mb:.0f}MB exceeds limit {limit_mb:.0f}MB"
            
            # Check recursion depth for recursive operations
            if kwargs.get("recursive"):
                max_depth = self._check_recursion_depth(validated_paths)
                if max_depth > security_config.MAX_RECURSION_DEPTH:
                    return False, f"Recursion depth {max_depth} exceeds limit"
            
            return True, "Operation allowed"
            
        except (PathSecurityError, ValidationError) as e:
            return False, str(e)
        except Exception as e:
            logger.error(f"Security check error: {e}", exc_info=True)
            return False, f"Security check failed: {e}"
    
    def _map_operation_to_action(self, operation: str) -> str:
        """Map operation name to security action"""
        if "delete" in operation:
            return "delete"
        elif "create" in operation or "write" in operation:
            return "write"
        elif "move" in operation or "rename" in operation:
            return "modify"
        else:
            return "read"
    
    def _calculate_total_size(self, paths: List[Path]) -> int:
        """Calculate total size of paths"""
        total = 0
        for path in paths:
            try:
                if path.is_file():
                    total += path.stat().st_size
                elif path.is_dir():
                    for item in path.rglob("*"):
                        if item.is_file():
                            total += item.stat().st_size
            except:
                pass
        return total
    
    def _check_recursion_depth(self, paths: List[Path]) -> int:
        """Check maximum recursion depth"""
        max_depth = 0
        for path in paths:
            if path.is_dir():
                try:
                    for item in path.rglob("*"):
                        depth = len(item.relative_to(path).parts)
                        max_depth = max(max_depth, depth)
                except:
                    pass
        return max_depth


# Global instances
path_validator = PathValidator()
security_enforcer = SecurityEnforcer()