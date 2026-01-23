import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List
from uuid import uuid4
from utils.logger import get_logger
from config.settings import settings

logger = get_logger(__name__)

class AuditLogger:
    """Logs all file operations for audit trail"""
    
    def __init__(self):
        self.logger = logger.bind(component="AuditLogger")
        self.audit_dir = settings.AUDIT_LOGS_DIR
        
        # Create daily log file
        today = datetime.utcnow().strftime("%Y-%m-%d")
        self.log_file = self.audit_dir / f"audit_{today}.jsonl"
    
    async def log_operation(
        self,
        operation_type: str,
        status: str,
        details: Dict[str, Any],
        snapshot_id: str = None,
        error: str = None
    ) -> str:
        """
        Log an operation to audit trail
        
        Args:
            operation_type: Type of operation
            status: success, failed, pending
            details: Operation details
            snapshot_id: Associated snapshot if any
            error: Error message if failed
            
        Returns:
            Audit log ID
        """
        audit_id = str(uuid4())
        
        entry = {
            "audit_id": audit_id,
            "timestamp": datetime.utcnow().isoformat(),
            "operation_type": operation_type,
            "status": status,
            "details": details,
            "snapshot_id": snapshot_id,
            "error": error
        }
        
        # Write to JSONL file (append)
        with open(self.log_file, 'a') as f:
            f.write(json.dumps(entry) + '\n')
        
        self.logger.info(
            "audit_logged",
            audit_id=audit_id,
            operation=operation_type,
            status=status
        )
        
        return audit_id
    
    async def get_recent_operations(self, limit: int = 10) -> List[Dict]:
        """Get recent operations from audit log"""
        operations = []
        
        if not self.log_file.exists():
            return operations
        
        # Read last N lines
        with open(self.log_file, 'r') as f:
            lines = f.readlines()
        
        # Parse and return most recent
        for line in reversed(lines[-limit:]):
            try:
                operations.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        
        return operations