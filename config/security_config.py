from pathlib import Path
from typing import List, Set
import os
import platform


class SecurityConfig:
    """
    Centralized security configuration
    """
    
    # ==================== PATH SECURITY ====================
    
    @staticmethod
    def get_allowed_base_paths() -> List[Path]:
        """
        Get list of allowed base directories
        Users can only operate within these directories
        """
        home = Path.home()
        
        # Platform-specific safe directories
        if platform.system() == "Windows":
            return [
                home / "Documents",
                home / "Desktop",
                home / "Downloads",
                home / "Pictures",
                home / "Videos",
                home / "Music",
                Path("C:/Users") / os.getlogin() / "Projects",
            ]
        else:  # Unix-like (macOS, Linux)
            return [
                home / "Documents",
                home / "Desktop",
                home / "Downloads",
                home / "Pictures",
                home / "Videos",
                home / "Music",
                home / "Projects",
                home / "workspace",
                Path("/tmp/filebuddy"),  # Temp directory
            ]
    
    @staticmethod
    def get_forbidden_paths() -> List[Path]:
        """
        Paths that are NEVER allowed, even if under allowed base paths
        """
        if platform.system() == "Windows":
            return [
                Path("C:/Windows"),
                Path("C:/Program Files"),
                Path("C:/Program Files (x86)"),
                Path("C:/ProgramData"),
                Path.home() / "AppData",
            ]
        else:  # Unix-like
            return [
                Path("/System"),
                Path("/Library"),
                Path("/bin"),
                Path("/sbin"),
                Path("/usr/bin"),
                Path("/usr/sbin"),
                Path("/etc"),
                Path("/var"),
                Path("/private"),
                Path.home() / ".ssh",
                Path.home() / ".aws",
                Path.home() / ".config",
            ]
    
    @staticmethod
    def get_forbidden_patterns() -> Set[str]:
        """
        File/directory name patterns that are forbidden
        """
        return {
            ".env",
            ".env.local",
            ".env.production",
            "id_rsa",
            "id_ed25519",
            ".pem",
            ".key",
            "credentials",
            "password",
            "secret",
            ".git",
            ".svn",
            "node_modules",
            "__pycache__",
        }
    
    @staticmethod
    def get_forbidden_extensions() -> Set[str]:
        """
        File extensions that cannot be modified/deleted
        """
        return {
            ".dll",
            ".sys",
            ".exe",  # Allow creation but not deletion
            ".so",
            ".dylib",
            ".pem",
            ".key",
            ".p12",
            ".pfx",
        }
    
    # ==================== OPERATION LIMITS ====================
    
    # Maximum number of files in a single operation
    MAX_BATCH_SIZE = 1000
    
    # Maximum file size to process (in bytes)
    MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB
    
    # Maximum total size for batch operations
    MAX_BATCH_TOTAL_SIZE = 1024 * 1024 * 1024  # 1GB
    
    # Maximum depth for recursive operations
    MAX_RECURSION_DEPTH = 10
    
    # ==================== RISK THRESHOLDS ====================
    
    # File count thresholds for risk assessment
    RISK_LOW_FILE_COUNT = 10
    RISK_MEDIUM_FILE_COUNT = 50
    RISK_HIGH_FILE_COUNT = 200
    
    # Size thresholds (in bytes)
    RISK_LOW_SIZE = 10 * 1024 * 1024      # 10MB
    RISK_MEDIUM_SIZE = 100 * 1024 * 1024  # 100MB
    RISK_HIGH_SIZE = 500 * 1024 * 1024    # 500MB
    
    # ==================== BACKUP SETTINGS ====================
    
    # Enable automatic backups before destructive operations
    ENABLE_AUTO_BACKUP = True
    
    # Backup directory
    @staticmethod
    def get_backup_directory() -> Path:
        """Get backup directory path"""
        backup_dir = Path.home() / ".filebuddy" / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        return backup_dir
    
    # Maximum backup retention (days)
    BACKUP_RETENTION_DAYS = 30
    
    # Maximum backup storage size (bytes)
    MAX_BACKUP_SIZE = 5 * 1024 * 1024 * 1024  # 5GB
    
    # ==================== AUDIT SETTINGS ====================
    
    # Enable audit logging
    ENABLE_AUDIT_LOG = True
    
    # Audit log directory
    @staticmethod
    def get_audit_directory() -> Path:
        """Get audit log directory"""
        audit_dir = Path.home() / ".filebuddy" / "audit"
        audit_dir.mkdir(parents=True, exist_ok=True)
        return audit_dir
    
    # Audit log retention (days)
    AUDIT_RETENTION_DAYS = 90
    
    # ==================== CONFIRMATION REQUIREMENTS ====================
    
    # Operations that always require confirmation (regardless of risk)
    ALWAYS_CONFIRM_OPERATIONS = {
        "delete_files",
        "delete_folder",
        "delete_multiple_folders",
        "delete_mixed_items",
        "move_folder_contents",
        "flatten_folder",
    }
    
    # Operations that never require confirmation (read-only)
    NEVER_CONFIRM_OPERATIONS = {
        "scan_folder",
        "search_files",
        "get_file_info",
        "read_file_content",
        "preview_file",
        "read_folder_tree",
        "search_file_contents",
        "detect_project_type",
        "show_history",
        "peek_last_action",
        "system_state",
        "list_available_snapshots",
    }
    
    # ==================== SENSITIVE DIRECTORIES ====================
    
    @staticmethod
    def is_sensitive_directory(path: Path) -> bool:
        """
        Check if directory contains sensitive data
        """
        sensitive_names = {
            "passwords",
            "credentials",
            "keys",
            "certificates",
            ".ssh",
            ".gnupg",
            ".aws",
            "wallet",
            "private",
        }
        
        path_str = str(path).lower()
        return any(name in path_str for name in sensitive_names)
    
    # ==================== SPECIAL FILE PROTECTIONS ====================
    
    @staticmethod
    def is_protected_file(path: Path) -> bool:
        """
        Check if file is protected from modification/deletion
        """
        protected_files = {
            ".gitignore",
            ".dockerignore",
            "requirements.txt",
            "package.json",
            "Cargo.toml",
            "go.mod",
            "pom.xml",
            "README.md",
            "LICENSE",
        }
        
        return path.name in protected_files
    
    # ==================== USER PERMISSIONS ====================
    
    # Require authentication for high-risk operations
    REQUIRE_AUTH_FOR_HIGH_RISK = False  # Set to True in production
    
    # PIN/password for critical operations
    CRITICAL_OPERATION_PIN = None  # Set via environment variable
    
    # Session timeout (seconds)
    SESSION_TIMEOUT = 3600  # 1 hour


# Global instance
security_config = SecurityConfig()