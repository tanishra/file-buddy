"""
Path validation and intelligent path resolution utilities
"""
from pathlib import Path
from typing import Optional
from config.policies import is_path_safe, is_sensitive_file
import os

class PathValidationError(Exception):
    """Path validation failed"""
    pass


# User's specific home directories (auto-detected from environment)
USER_HOME = Path.home()
USER_PATHS = {
    "downloads": USER_HOME / "Downloads",
    "desktop": USER_HOME / "Desktop", 
    "documents": USER_HOME / "Documents",
}


# Intelligent aliases for natural language understanding
PATH_ALIASES = {
    # Downloads variations 
    "downloads": "downloads",
    "download": "downloads",
    "download folder": "downloads",
    "downloads folder": "downloads",
    "my downloads": "downloads",
    "in downloads": "downloads",
    "to downloads": "downloads",
    "from downloads": "downloads",
    "inside downloads": "downloads",
    "downloads directory": "downloads",
    "downloads dir": "downloads",
    "downloads path": "downloads",
    "my download folder": "downloads",
    "local downloads": "downloads",
    "mac downloads": "downloads",

    # Desktop variations 
    "desktop": "desktop",
    "my desktop": "desktop",
    "desktop folder": "desktop",
    "on desktop": "desktop",
    "on my desktop": "desktop",
    "to desktop": "desktop",
    "in desktop": "desktop",
    "from desktop": "desktop",
    "inside desktop": "desktop",
    "desktop directory": "desktop",
    "desktop dir": "desktop",
    "desktop path": "desktop",
    "mac desktop": "desktop",
    "local desktop": "desktop",
    "home desktop": "desktop",

    # Documents variations
    "documents": "documents",
    "document": "documents",
    "docs": "documents",
    "my documents": "documents",
    "documents folder": "documents",
    "my docs": "documents",
    "in documents": "documents",
    "to documents": "documents",
    "from documents": "documents",
    "inside documents": "documents",
    "documents directory": "documents",
    "documents dir": "documents",
    "documents path": "documents",
    "mac documents": "documents",
    "local documents": "documents",
    "home documents": "documents",

    # Home variations
    "home": "home",
    "~": "home",
    "my home": "home",
    "home folder": "home",
    "home directory": "home",
    "user home": "home",
    "my home folder": "home",
    "root of home": "home",
    "base folder": "home",
    "user directory": "home",
    "my user folder": "home",
}

def validate_path(path: Path, must_exist: bool = False) -> Path:
    """
    Validate path for safety with intelligent error messages
    
    Args:
        path: Path to validate
        must_exist: If True, path must exist
        
    Returns:
        Resolved absolute path
        
    Raises:
        PathValidationError: If invalid or unsafe
    """
    try:
        resolved = path.resolve()
        
        if not is_path_safe(resolved):
            raise PathValidationError(
                f"Cannot access '{resolved}' - it's a protected system directory. "
                f"Try Downloads, Desktop, or Documents instead."
            )
        
        if must_exist and not resolved.exists():
            # Provide helpful suggestions
            parent = resolved.parent
            if parent.exists():
                raise PathValidationError(
                    f"'{resolved.name}' not found in {parent}. "
                    f"Check the name and try again."
                )
            else:
                raise PathValidationError(
                    f"Path '{resolved}' does not exist. "
                    f"The parent directory '{parent}' is also missing."
                )
        
        return resolved
    
    except (OSError, RuntimeError) as e:
        raise PathValidationError(f"Invalid path: {e}")


def expand_user_path(path_input: str) -> Path:
    """
    Intelligently expand user-friendly paths with natural language understanding
    
    Handles:
    - Natural phrases: "my desktop", "on desktop", "downloads folder"
    - Aliases: "downloads", "docs", "desktop"
    - Relative paths: "downloads/file.txt", "desktop/project"
    - Absolute paths: "/Users/tanishrajput/Downloads"
    - Tilde expansion: "~/Downloads"
    - Case-insensitive matching
    - User-specific paths (auto-detects your home directories)
    
    Examples:
        "my desktop" → /Users/tanishrajput/Desktop
        "downloads/report.pdf" → /Users/tanishrajput/Downloads/report.pdf
        "on desktop" → /Users/tanishrajput/Desktop
        "docs/projects" → /Users/tanishrajput/Documents/projects
    
    Args:
        path_input: User's path string (can be natural language)
        
    Returns:
        Resolved absolute Path object
    """
    path_str = path_input.strip()
    
    # Handle empty input
    if not path_str:
        return USER_HOME
    
    # Quick check: if it's already a valid absolute path, use it
    if path_str.startswith("/") and Path(path_str).exists():
        return Path(path_str).resolve()
    
    # Quick check: if it starts with ~, expand it
    if path_str.startswith("~"):
        return Path(path_str).expanduser().resolve()
    
    # Normalize for matching
    lower_input = path_str.lower().strip()
    
    # Remove common prefixes for better matching
    for prefix in ["go to ", "open ", "on ", "in ", "at ", "to ", "the "]:
        if lower_input.startswith(prefix):
            lower_input = lower_input[len(prefix):].strip()
            break
    
    # Try to match against aliases first (most common case)
    for alias, key in PATH_ALIASES.items():
        # Exact match
        if lower_input == alias:
            if key == "home":
                return USER_HOME
            return USER_PATHS.get(key, USER_HOME)
        
        # Match with path continuation (e.g., "desktop/file.txt")
        if lower_input.startswith(alias + "/"):
            remainder = path_str[len(alias):].lstrip("/")
            base_path = USER_PATHS.get(key, USER_HOME) if key != "home" else USER_HOME
            return (base_path / remainder).resolve()
    
    # Check if input is just a folder name that exists in user paths
    # e.g., user says "Projects" and it exists in Documents
    potential_name = Path(path_str).parts[0] if "/" in path_str else path_str
    
    for base_path in USER_PATHS.values():
        potential_full = base_path / path_str
        if potential_full.exists():
            return potential_full.resolve()
    
    # Try relative to Downloads (most common default)
    downloads_path = USER_PATHS["downloads"] / path_str
    if downloads_path.exists():
        return downloads_path.resolve()
    
    # Try relative to current working directory
    cwd_path = Path.cwd() / path_str
    if cwd_path.exists():
        return cwd_path.resolve()
    
    # Fallback: standard expansion and resolution
    try:
        expanded = Path(path_str).expanduser().resolve()
        return expanded
    except Exception:
        # Last resort: assume they meant Downloads
        return USER_PATHS["downloads"] / path_str


def get_safe_destination(source: Path, dest_folder: Path, counter: int = 0) -> Path:
    """
    Get safe destination path with intelligent conflict resolution
    
    Features:
    - Automatic numbering for duplicates (file_1.txt, file_2.txt)
    - Preserves file extensions
    - Creates destination folder if needed
    - Handles deep recursion gracefully
    
    Args:
        source: Source file
        dest_folder: Destination folder
        counter: Conflict counter (internal use)
        
    Returns:
        Safe destination path that doesn't conflict
    """
    dest_folder = validate_path(dest_folder)
    dest_folder.mkdir(parents=True, exist_ok=True)
    
    if counter == 0:
        dest_path = dest_folder / source.name
    else:
        stem = source.stem
        suffix = source.suffix
        dest_path = dest_folder / f"{stem}_{counter}{suffix}"
    
    # Check for conflicts
    if dest_path.exists():
        # Safety limit: prevent infinite recursion
        if counter > 1000:
            raise PathValidationError(
                f"Too many conflicts for '{source.name}'. "
                f"Please clean up the destination folder."
            )
        return get_safe_destination(source, dest_folder, counter + 1)
    
    return dest_path


def smart_path_match(user_input: str, candidates: list[Path]) -> Optional[Path]:
    """
    Match user's natural language input to actual paths
    
    Useful for disambiguation when multiple matches exist
    
    Args:
        user_input: What user said (e.g., "the pdf in downloads")
        candidates: List of possible paths
        
    Returns:
        Best matching path or None
    """
    lower_input = user_input.lower()
    
    # Score each candidate
    scores = []
    for path in candidates:
        score = 0
        path_str = str(path).lower()
        name_lower = path.name.lower()
        
        # Exact name match
        if lower_input == name_lower:
            score += 100
        
        # Name contains input
        if lower_input in name_lower:
            score += 50
        
        # Path contains input
        if lower_input in path_str:
            score += 25
        
        # Check for common folder mentions
        for key, folder_path in USER_PATHS.items():
            if key in lower_input and str(folder_path) in path_str:
                score += 30
        
        scores.append((score, path))
    
    # Return highest scoring path
    scores.sort(reverse=True, key=lambda x: x[0])
    
    if scores and scores[0][0] > 0:
        return scores[0][1]
    
    return None


def get_user_folder(folder_name: str) -> Path:
    """
    Get user's common folder by name
    
    Args:
        folder_name: "downloads", "desktop", or "documents"
        
    Returns:
        Path to the folder
    """
    key = folder_name.lower().strip()
    
    # Normalize through aliases
    normalized = PATH_ALIASES.get(key, key)
    
    if normalized in USER_PATHS:
        return USER_PATHS[normalized]
    
    # Fallback to home
    return USER_HOME


def is_user_folder(path: Path) -> bool:
    """
    Check if path is one of user's main folders
    
    Args:
        path: Path to check
        
    Returns:
        True if it's Downloads, Desktop, or Documents
    """
    try:
        resolved = path.resolve()
        return resolved in USER_PATHS.values()
    except:
        return False