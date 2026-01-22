import json
import shutil
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
from uuid import uuid4
from utils.logger import get_logger
from config.settings import SNAPSHOTS_DIR, SNAPSHOT_RETENTION_HOURS

logger = get_logger(__name__)

@dataclass
class Snapshot:
    """Snapshot of file states for rollback"""
    snapshot_id: str
    operation_type: str
    file_states: Dict[str, str]  # current_path -> original_path
    folders_created: List[str]
    metadata: Dict
    created_at: str
    
    @property
    def is_expired(self) -> bool:
        """Check if snapshot expired"""
        created = datetime.fromisoformat(self.created_at)
        age_hours = (datetime.utcnow() - created).total_seconds() / 3600
        return age_hours > SNAPSHOT_RETENTION_HOURS

class SnapshotManager:
    """Manages snapshots for rollback"""
    
    def __init__(self):
        self.logger = logger.bind(component="SnapshotManager")
        self.snapshots_dir = SNAPSHOTS_DIR
    
    async def create_snapshot(
        self,
        operation_type: str,
        file_states: Dict[Path, Path],
        folders_created: List[Path] = None,
        metadata: Dict = None
    ) -> Snapshot:
        """
        Create a new snapshot
        
        Args:
            operation_type: Type of operation
            file_states: Mapping of current -> original paths
            folders_created: Folders created during operation
            metadata: Additional metadata
            
        Returns:
            Snapshot object
        """
        snapshot_id = str(uuid4())
        
        snapshot = Snapshot(
            snapshot_id=snapshot_id,
            operation_type=operation_type,
            file_states={str(k): str(v) for k, v in file_states.items()},
            folders_created=[str(f) for f in (folders_created or [])],
            metadata=metadata or {},
            created_at=datetime.utcnow().isoformat()
        )
        
        # Save to disk
        snapshot_path = self.snapshots_dir / f"{snapshot_id}.json"
        with open(snapshot_path, 'w') as f:
            json.dump(asdict(snapshot), f, indent=2)
        
        self.logger.info(
            "snapshot_created",
            snapshot_id=snapshot_id,
            operation=operation_type,
            file_count=len(file_states)
        )
        
        return snapshot
    
    async def load_snapshot(self, snapshot_id: str) -> Optional[Snapshot]:
        """Load a snapshot by ID"""
        snapshot_path = self.snapshots_dir / f"{snapshot_id}.json"
        
        if not snapshot_path.exists():
            self.logger.warning("snapshot_not_found", snapshot_id=snapshot_id)
            return None
        
        with open(snapshot_path, 'r') as f:
            data = json.load(f)
        
        return Snapshot(**data)
    
    async def rollback(self, snapshot_id: str) -> Dict:
        """
        Rollback using a snapshot
        
        Args:
            snapshot_id: Snapshot to restore
            
        Returns:
            Result dictionary
        """
        self.logger.info("rollback_start", snapshot_id=snapshot_id)
        
        snapshot = await self.load_snapshot(snapshot_id)
        if not snapshot:
            return {
                "success": False,
                "error": "Snapshot not found"
            }
        
        if snapshot.is_expired:
            return {
                "success": False,
                "error": "Snapshot expired (>24 hours)"
            }
        
        restored = 0
        failed = 0
        errors = []
        
        # Restore files
        for current_str, original_str in snapshot.file_states.items():
            current = Path(current_str)
            original = Path(original_str)
            
            try:
                if current.exists():
                    shutil.move(str(current), str(original))
                    restored += 1
                    self.logger.debug(
                        "file_restored",
                        from_path=str(current),
                        to_path=str(original)
                    )
            except Exception as e:
                failed += 1
                error_msg = f"Failed to restore {current}: {e}"
                errors.append(error_msg)
                self.logger.error("file_restore_failed", error=error_msg)
        
        # Remove created folders (if empty)
        for folder_str in reversed(snapshot.folders_created):
            folder = Path(folder_str)
            try:
                if folder.exists() and not any(folder.iterdir()):
                    folder.rmdir()
                    self.logger.debug("folder_removed", folder=str(folder))
            except Exception as e:
                self.logger.warning("folder_removal_failed", error=str(e))
        
        self.logger.info(
            "rollback_complete",
            snapshot_id=snapshot_id,
            restored=restored,
            failed=failed
        )
        
        return {
            "success": failed == 0,
            "restored": restored,
            "failed": failed,
            "errors": errors
        }
    
    async def cleanup_expired(self) -> int:
        """Remove expired snapshots"""
        removed = 0
        
        for snapshot_file in self.snapshots_dir.glob("*.json"):
            try:
                with open(snapshot_file, 'r') as f:
                    data = json.load(f)
                
                snapshot = Snapshot(**data)
                if snapshot.is_expired:
                    snapshot_file.unlink()
                    removed += 1
                    self.logger.info(
                        "snapshot_removed",
                        snapshot_id=snapshot.snapshot_id
                    )
            except Exception as e:
                self.logger.error("cleanup_failed", error=str(e))
        
        return removed