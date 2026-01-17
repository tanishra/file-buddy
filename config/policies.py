"""
Safety policies and forbidden paths
"""
from pathlib import Path
import platform

def get_forbidden_paths() -> list[str]:
    """Get platform-specific forbidden paths"""
    system = platform.system()
    
    common = [
        "/System", "/usr", "/bin", "/sbin", "/etc", 
        "/var", "/boot", "/dev", "/proc", "/sys", "/tmp"
    ]
    
    if system == "Darwin":  # macOS
        return common + [
            "/Library",
            "/Applications",
            str(Path.home() / "Library"),
            str(Path.home() / ".Trash"),
        ]
    elif system == "Windows":
        return [
            "C:\\Windows",
            "C:\\Program Files",
            "C:\\Program Files (x86)",
            "C:\\ProgramData",
            str(Path.home() / "AppData"),
        ]
    else:  # Linux
        return common + ["/root"]

FORBIDDEN_PATHS = get_forbidden_paths()

# Extensions requiring extra confirmation
SENSITIVE_EXTENSIONS = [
    ".exe", ".dmg", ".app", ".sh", ".bat", ".cmd",
    ".dll", ".so", ".dylib", ".msi"
]

# Extensions that are dangerous to execute
EXECUTABLE_EXTENSIONS = [
    ".exe", ".dmg", ".app", ".sh", ".bat", ".cmd", ".msi", ".run"
]

# Default safe folders
DEFAULT_ALLOWED_FOLDERS = [
    str(Path.home() / "Downloads"),
    str(Path.home() / "Desktop"),
    str(Path.home() / "Documents"),
]

def is_path_safe(path: Path) -> bool:
    """Check if path is safe to operate on"""
    path_str = str(path.resolve())
    
    # Check forbidden paths
    for forbidden in FORBIDDEN_PATHS:
        if path_str.startswith(forbidden):
            return False
    
    # No hidden system directories
    if any(part.startswith('.') and part not in ['.', '..'] for part in path.parts[:-1]):
        return False
    
    return True

def is_sensitive_file(path: Path) -> bool:
    """Check if file needs extra confirmation"""
    return path.suffix.lower() in SENSITIVE_EXTENSIONS

def is_executable_file(path: Path) -> bool:
    """Check if file is executable"""
    return path.suffix.lower() in EXECUTABLE_EXTENSIONS