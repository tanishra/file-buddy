from pathlib import Path
from typing import Optional
from config.policies import is_path_safe, is_sensitive_file

class PathValidationError(Exception):
    """Path validation failed"""
    pass

def validate_path(path: Path, must_exist: bool = False) -> Path:
    """
    Validate path for safety
    
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
                f"Path {resolved} is in a protected system directory"
            )
        
        if must_exist and not resolved.exists():
            raise PathValidationError(f"Path {resolved} does not exist")
        
        return resolved
    
    except (OSError, RuntimeError) as e:
        raise PathValidationError(f"Invalid path: {e}")

HOME_ALIASES = {
    "downloads": "Downloads",
    "download": "Downloads",
    "desktop": "Desktop",
    "documents": "Documents",
    "docs": "Documents",
}

def expand_user_path(path: str) -> Path:
    """
    Expand user-friendly paths like:
    - downloads/file.txt
    - desktop
    - documents/projects
    - ~/Downloads
    - absolute paths
    """
    path = path.strip()

    lower = path.lower()

    # Handle implicit home aliases
    for alias, folder in HOME_ALIASES.items():
        if lower == alias or lower.startswith(alias + "/"):
            remainder = path[len(alias):].lstrip("/")

            resolved = Path.home() / folder
            if remainder:
                resolved = resolved / remainder

            return resolved.expanduser().resolve()

    # Fallback: normal expansion
    return Path(path).expanduser().resolve()

def get_safe_destination(source: Path, dest_folder: Path, counter: int = 0) -> Path:
    """
    Get safe destination path, handling name conflicts
    
    Args:
        source: Source file
        dest_folder: Destination folder
        counter: Conflict counter
        
    Returns:
        Safe destination path
    """
    dest_folder = validate_path(dest_folder)
    dest_folder.mkdir(parents=True, exist_ok=True)
    
    if counter == 0:
        dest_path = dest_folder / source.name
    else:
        stem = source.stem
        suffix = source.suffix
        dest_path = dest_folder / f"{stem}_{counter}{suffix}"
    
    if dest_path.exists():
        return get_safe_destination(source, dest_folder, counter + 1)
    
    return dest_path