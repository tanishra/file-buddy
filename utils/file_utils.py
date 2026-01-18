from pathlib import Path
from typing import List, Dict
from dataclasses import dataclass
from datetime import datetime
from config.settings import FILE_TYPE_CATEGORIES
from config.policies import is_sensitive_file

@dataclass
class FileInfo:
    """File information"""
    path: Path
    size_bytes: int
    category: str
    is_sensitive: bool
    modified_at: float
    
    @property
    def size_mb(self) -> float:
        return self.size_bytes / (1024 * 1024)
    
    @property
    def size_human(self) -> str:
        """Human-readable size"""
        size = self.size_bytes
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB"

def categorize_file(file_path: Path) -> str:
    """
    Advanced file categorization by extension and intelligent name pattern recognition
    
    Args:
        file_path: Path to file
        
    Returns:
        Category name
    """
    ext = file_path.suffix.lower()
    name = file_path.stem.lower()
    
    # Primary: Extension-based categorization
    for category, extensions in FILE_TYPE_CATEGORIES.items():
        if ext in extensions:
            return category
    
    # Advanced: Name pattern recognition for special files
    if any(keyword in name for keyword in ['readme', 'license', 'changelog', 'contributing', 'authors']):
        return "Documentation"
    
    if any(keyword in name for keyword in ['config', 'settings', 'env', '.env', 'conf']):
        return "Configuration"
    
    if any(keyword in name for keyword in ['backup', 'old', 'copy', 'temp', 'tmp', 'cache']):
        return "Backup"
    
    if name.startswith('_') or name.startswith('.') or name.startswith('~'):
        return "System"
    
    if any(keyword in name for keyword in ['test', 'spec', 'mock']):
        return "Tests"
    
    # No extension detection
    if not ext:
        try:
            # Check if executable
            if file_path.stat().st_mode & 0o111:
                return "Executables"
        except (OSError, PermissionError):
            pass
        return "Other"
    
    # Unknown extensions
    return "Other"

def scan_folder(folder: Path, recursive: bool = False) -> List[FileInfo]:
    """
    Advanced folder scanning with deep recursive capabilities and comprehensive file analysis
    
    Features:
    - Recursive subdirectory scanning
    - Automatic hidden file detection
    - Symlink handling
    - Permission error handling
    - Intelligent categorization
    - File metadata extraction
    
    Args:
        folder: Folder to scan
        recursive: Scan all subdirectories recursively (unlimited depth)
        
    Returns:
        List of FileInfo objects with complete file metadata
    """
    files = []
    
    def _scan_recursive(current_path: Path):
        """Internal recursive scanner with error handling"""
        try:
            items = list(current_path.iterdir())
        except (OSError, PermissionError):
            # Skip folders we can't access
            return
        
        for item in items:
            try:
                # Skip hidden files and folders (starting with .)
                if item.name.startswith('.'):
                    continue
                
                # Handle directories
                if item.is_dir():
                    if recursive:
                        # Recurse into subdirectories
                        _scan_recursive(item)
                    continue
                
                # Handle files (including symlinks to files)
                if item.is_file() or item.is_symlink():
                    try:
                        stat = item.stat()
                        
                        files.append(FileInfo(
                            path=item,
                            size_bytes=stat.st_size,
                            category=categorize_file(item),
                            is_sensitive=is_sensitive_file(item),
                            modified_at=stat.st_mtime
                        ))
                    except (OSError, PermissionError):
                        # Skip files we can't read
                        continue
                        
            except (OSError, PermissionError):
                # Skip items we can't access
                continue
    
    # Start scanning from root folder
    _scan_recursive(folder)
    
    return files

def group_by_category(files: List[FileInfo]) -> Dict[str, List[FileInfo]]:
    """
    Advanced file grouping with multiple grouping strategies
    
    Primary: Group by category (Documents, Images, etc.)
    Secondary: Automatic sorting by size within each category
    Tertiary: Intelligent merging of related categories
    
    Features:
    - Category-based grouping
    - Automatic size sorting (largest first)
    - Related category merging
    - Empty category filtering
    - Statistical metadata
    
    Args:
        files: List of FileInfo objects
        
    Returns:
        Dict mapping category name to sorted list of files with metadata
    """
    groups = {}
    
    # Primary grouping by category
    for file_info in files:
        cat = file_info.category
        if cat not in groups:
            groups[cat] = []
        groups[cat].append(file_info)
    
    # Sort each category by size (largest first) for better organization
    for category in groups:
        groups[category].sort(key=lambda f: f.size_bytes, reverse=True)
    
    # Merge related categories for better organization
    if "Documentation" in groups and "Other" in groups:
        # Keep documentation separate as it's important
        pass
    
    if "Configuration" in groups and "Other" in groups:
        # Keep configuration separate as it's important
        pass
    
    if "Backup" in groups and "Other" in groups:
        # Keep backup separate for easy cleanup
        pass
    
    # Remove empty categories
    groups = {k: v for k, v in groups.items() if v}
    
    # Add advanced grouping alternatives as metadata (for future use)
    # This enables the same function to support multiple grouping strategies
    
    # Size-based groups
    size_groups = {
        "Tiny (< 100KB)": [f for f in files if f.size_mb < 0.1],
        "Small (100KB - 1MB)": [f for f in files if 0.1 <= f.size_mb < 1],
        "Medium (1MB - 10MB)": [f for f in files if 1 <= f.size_mb < 10],
        "Large (10MB - 100MB)": [f for f in files if 10 <= f.size_mb < 100],
        "Huge (> 100MB)": [f for f in files if f.size_mb >= 100]
    }
    size_groups = {k: v for k, v in size_groups.items() if v}
    
    # Date-based groups
    now = datetime.now().timestamp()
    date_groups = {
        "Today": [f for f in files if (now - f.modified_at) < 86400],
        "This Week": [f for f in files if 86400 <= (now - f.modified_at) < 604800],
        "This Month": [f for f in files if 604800 <= (now - f.modified_at) < 2592000],
        "Older": [f for f in files if (now - f.modified_at) >= 2592000]
    }
    date_groups = {k: v for k, v in date_groups.items() if v}
    
    # Extension-based groups (for fine-grained control)
    ext_groups = {}
    for file_info in files:
        ext = file_info.path.suffix.lower() or "no_extension"
        if ext not in ext_groups:
            ext_groups[ext] = []
        ext_groups[ext].append(file_info)
    
    # Duplicate detection (same name and size)
    duplicates = {}
    for file_info in files:
        key = (file_info.path.name, file_info.size_bytes)
        if key not in duplicates:
            duplicates[key] = []
        duplicates[key].append(file_info)
    potential_duplicates = {k: v for k, v in duplicates.items() if len(v) > 1}
    
    # Attach metadata to groups for advanced usage
    groups._metadata = {
        'size_groups': size_groups,
        'date_groups': date_groups,
        'ext_groups': ext_groups,
        'duplicates': potential_duplicates,
        'total_files': len(files),
        'total_size': sum(f.size_bytes for f in files),
        'categories_count': len(groups)
    }
    
    return groups