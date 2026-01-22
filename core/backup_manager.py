import shutil
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import hashlib

from config.security_config import security_config
from core.exceptions import FileSystemError
from utils.logger import get_logger

logger = get_logger(__name__)


class BackupManager:
    """
    Manages backups before destructive operations
    """
    
    def __init__(self):
        self.backup_dir = security_config.get_backup_directory()
        self.metadata_file = self.backup_dir / "metadata.json"
        self._load_metadata()
        logger.info(f"BackupManager initialized", extra={"backup_dir": str(self.backup_dir)})
    
    def _load_metadata(self):
        """Load backup metadata"""
        try:
            if self.metadata_file.exists():
                with open(self.metadata_file, 'r') as f:
                    self.metadata = json.load(f)
            else:
                self.metadata = {"backups": []}
        except Exception as e:
            logger.error(f"Failed to load backup metadata: {e}")
            self.metadata = {"backups": []}
    
    def _save_metadata(self):
        """Save backup metadata"""
        try:
            with open(self.metadata_file, 'w') as f:
                json.dump(self.metadata, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save backup metadata: {e}")
    
    def create_backup(
        self,
        paths: List[Path],
        operation: str,
        user_id: str
    ) -> Optional[str]:
        """
        Create backup of paths before operation
        
        Args:
            paths: Paths to backup
            operation: Operation name
            user_id: User identifier
            
        Returns:
            Backup ID if successful, None otherwise
        """
        try:
            # Generate backup ID
            timestamp = datetime.utcnow().isoformat()
            backup_id = self._generate_backup_id(operation, timestamp)
            backup_path = self.backup_dir / backup_id
            backup_path.mkdir(parents=True, exist_ok=True)
            
            # Track backup info
            backup_info = {
                "id": backup_id,
                "timestamp": timestamp,
                "operation": operation,
                "user_id": user_id,
                "paths": [],
                "total_size": 0,
                "file_count": 0
            }
            
            # Backup each path
            for path in paths:
                try:
                    if not path.exists():
                        logger.warning(f"Path does not exist, skipping backup: {path}")
                        continue
                    
                    # Create backup of this path
                    relative_path = self._get_safe_relative_path(path)
                    target_path = backup_path / relative_path
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    if path.is_file():
                        shutil.copy2(path, target_path)
                        size = path.stat().st_size
                        backup_info["total_size"] += size
                        backup_info["file_count"] += 1
                    elif path.is_dir():
                        shutil.copytree(path, target_path)
                        size = self._get_directory_size(path)
                        file_count = self._count_files(path)
                        backup_info["total_size"] += size
                        backup_info["file_count"] += file_count
                    
                    backup_info["paths"].append({
                        "original": str(path),
                        "backup": str(target_path),
                        "type": "file" if path.is_file() else "directory"
                    })
                    
                except Exception as e:
                    logger.error(f"Failed to backup {path}: {e}")
                    continue
            
            # Save backup metadata
            self.metadata["backups"].append(backup_info)
            self._save_metadata()
            
            logger.info(
                "Backup created",
                extra={
                    "backup_id": backup_id,
                    "file_count": backup_info["file_count"],
                    "size_mb": backup_info["total_size"] / (1024 * 1024)
                }
            )
            
            # Cleanup old backups if needed
            self._cleanup_if_needed()
            
            return backup_id
            
        except Exception as e:
            logger.error(f"Failed to create backup: {e}", exc_info=True)
            return None
    
    def restore_backup(self, backup_id: str) -> bool:
        """
        Restore a backup
        
        Args:
            backup_id: Backup identifier
            
        Returns:
            True if successful
        """
        try:
            # Find backup info
            backup_info = None
            for backup in self.metadata["backups"]:
                if backup["id"] == backup_id:
                    backup_info = backup
                    break
            
            if not backup_info:
                logger.error(f"Backup not found: {backup_id}")
                return False
            
            backup_path = self.backup_dir / backup_id
            if not backup_path.exists():
                logger.error(f"Backup directory not found: {backup_path}")
                return False
            
            # Restore each path
            restored_count = 0
            for path_info in backup_info["paths"]:
                try:
                    backup_file = Path(path_info["backup"])
                    original_path = Path(path_info["original"])
                    
                    if not backup_file.exists():
                        logger.warning(f"Backup file missing: {backup_file}")
                        continue
                    
                    # Remove current version if exists
                    if original_path.exists():
                        if original_path.is_file():
                            original_path.unlink()
                        elif original_path.is_dir():
                            shutil.rmtree(original_path)
                    
                    # Restore from backup
                    if backup_file.is_file():
                        shutil.copy2(backup_file, original_path)
                    elif backup_file.is_dir():
                        shutil.copytree(backup_file, original_path)
                    
                    restored_count += 1
                    
                except Exception as e:
                    logger.error(f"Failed to restore {path_info['original']}: {e}")
                    continue
            
            logger.info(
                "Backup restored",
                extra={
                    "backup_id": backup_id,
                    "restored_count": restored_count
                }
            )
            
            return restored_count > 0
            
        except Exception as e:
            logger.error(f"Failed to restore backup: {e}", exc_info=True)
            return False
    
    def list_backups(
        self,
        user_id: Optional[str] = None,
        days: int = 30
    ) -> List[Dict[str, Any]]:
        """List available backups"""
        try:
            cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
            
            backups = []
            for backup in self.metadata["backups"]:
                if backup["timestamp"] < cutoff:
                    continue
                
                if user_id and backup["user_id"] != user_id:
                    continue
                
                backups.append({
                    "id": backup["id"],
                    "timestamp": backup["timestamp"],
                    "operation": backup["operation"],
                    "file_count": backup["file_count"],
                    "size_mb": round(backup["total_size"] / (1024 * 1024), 2),
                    "paths": [p["original"] for p in backup["paths"]]
                })
            
            return backups
            
        except Exception as e:
            logger.error(f"Failed to list backups: {e}")
            return []
    
    def delete_backup(self, backup_id: str) -> bool:
        """Delete a backup"""
        try:
            # Remove from metadata
            self.metadata["backups"] = [
                b for b in self.metadata["backups"]
                if b["id"] != backup_id
            ]
            self._save_metadata()
            
            # Remove backup directory
            backup_path = self.backup_dir / backup_id
            if backup_path.exists():
                shutil.rmtree(backup_path)
            
            logger.info(f"Backup deleted", extra={"backup_id": backup_id})
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete backup: {e}")
            return False
    
    def _generate_backup_id(self, operation: str, timestamp: str) -> str:
        """Generate unique backup ID"""
        # Use timestamp + operation hash
        hash_input = f"{operation}_{timestamp}".encode()
        hash_suffix = hashlib.md5(hash_input).hexdigest()[:8]
        
        # Format: backup_YYYYMMDD_HHMMSS_operation_hash
        dt = datetime.fromisoformat(timestamp)
        date_str = dt.strftime("%Y%m%d_%H%M%S")
        
        return f"backup_{date_str}_{operation}_{hash_suffix}"
    
    def _get_safe_relative_path(self, path: Path) -> Path:
        """Get safe relative path for backup"""
        # Convert absolute path to safe relative path
        # Replace drive letters and root
        path_str = str(path)
        
        # Remove drive letter on Windows
        if ":" in path_str:
            path_str = path_str.split(":", 1)[1]
        
        # Remove leading slashes
        path_str = path_str.lstrip("/\\")
        
        return Path(path_str)
    
    def _get_directory_size(self, path: Path) -> int:
        """Calculate total size of directory"""
        total = 0
        try:
            for item in path.rglob("*"):
                if item.is_file():
                    total += item.stat().st_size
        except:
            pass
        return total
    
    def _count_files(self, path: Path) -> int:
        """Count files in directory"""
        count = 0
        try:
            for item in path.rglob("*"):
                if item.is_file():
                    count += 1
        except:
            pass
        return count
    
    def _cleanup_if_needed(self):
        """Cleanup old backups if storage limit exceeded"""
        try:
            # Calculate total backup size
            total_size = sum(b["total_size"] for b in self.metadata["backups"])
            
            if total_size > security_config.MAX_BACKUP_SIZE:
                logger.info("Backup storage limit exceeded, cleaning up old backups")
                
                # Sort by timestamp (oldest first)
                sorted_backups = sorted(
                    self.metadata["backups"],
                    key=lambda b: b["timestamp"]
                )
                
                # Remove oldest until under limit
                while total_size > security_config.MAX_BACKUP_SIZE and sorted_backups:
                    oldest = sorted_backups.pop(0)
                    self.delete_backup(oldest["id"])
                    total_size -= oldest["total_size"]
            
            # Also cleanup by age
            cutoff = (
                datetime.utcnow() - 
                timedelta(days=security_config.BACKUP_RETENTION_DAYS)
            ).isoformat()
            
            old_backups = [
                b for b in self.metadata["backups"]
                if b["timestamp"] < cutoff
            ]
            
            for backup in old_backups:
                self.delete_backup(backup["id"])
            
            if old_backups:
                logger.info(f"Cleaned up {len(old_backups)} old backups")
            
        except Exception as e:
            logger.error(f"Cleanup failed: {e}")
    
    def get_storage_info(self) -> Dict[str, Any]:
        """Get backup storage information"""
        try:
            total_size = sum(b["total_size"] for b in self.metadata["backups"])
            total_files = sum(b["file_count"] for b in self.metadata["backups"])
            
            return {
                "backup_count": len(self.metadata["backups"]),
                "total_files": total_files,
                "total_size_bytes": total_size,
                "total_size_mb": round(total_size / (1024 * 1024), 2),
                "storage_limit_mb": security_config.MAX_BACKUP_SIZE / (1024 * 1024),
                "usage_percent": (total_size / security_config.MAX_BACKUP_SIZE) * 100
            }
        except Exception as e:
            logger.error(f"Failed to get storage info: {e}")
            return {}


# Global instance
backup_manager = BackupManager()