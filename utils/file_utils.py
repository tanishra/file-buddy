from pathlib import Path
from typing import List, Dict
from dataclasses import dataclass
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
    """Categorize file by extension"""
    ext = file_path.suffix.lower()
    
    for category, extensions in FILE_TYPE_CATEGORIES.items():
        if ext in extensions:
            return category
    
    return "Other"

def scan_folder(folder: Path, recursive: bool = False) -> List[FileInfo]:
    """
    Scan folder and return file information
    
    Args:
        folder: Folder to scan
        recursive: Scan subdirectories
        
    Returns:
        List of FileInfo
    """
    files = []
    pattern = "**/*" if recursive else "*"
    
    for item in folder.glob(pattern):
        if item.is_dir() or item.name.startswith('.'):
            continue
        
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
            continue
    
    return files

def group_by_category(files: List[FileInfo]) -> Dict[str, List[FileInfo]]:
    """Group files by category"""
    groups = {}
    for file_info in files:
        cat = file_info.category
        if cat not in groups:
            groups[cat] = []
        groups[cat].append(file_info)
    return groups