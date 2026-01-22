import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4
from dataclasses import dataclass, asdict

from config.security_config import security_config
from config.settings import settings
from utils.logger import get_logger

logger = get_logger(__name__)

# Try to get AUDIT_LOGS_DIR from settings, fallback to security_config
try:
    from config.settings import AUDIT_LOGS_DIR
    AUDIT_DIR = AUDIT_LOGS_DIR
except (ImportError, AttributeError):
    AUDIT_DIR = security_config.get_audit_directory()


@dataclass
class AuditEntry:
    """Single audit log entry"""
    timestamp: str
    user_id: str
    operation: str
    risk_level: str
    paths: List[str]
    success: bool
    details: Dict[str, Any]
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class AuditLogger:
    """
    Comprehensive audit logging with dual backend support
    - SQLite database for queryable audit trail (Week 2)
    - JSONL files for legacy compatibility (preserved)
    """
    
    def __init__(self):
        self.logger = logger
        self.audit_dir = AUDIT_DIR
        
        # Ensure audit directory exists
        self.audit_dir.mkdir(parents=True, exist_ok=True)
        
        # SQLite database (Week 2)
        self.db_path = self.audit_dir / "audit.db"
        self._init_database()
        
        # JSONL file (Legacy - preserved)
        today = datetime.utcnow().strftime("%Y-%m-%d")
        self.log_file = self.audit_dir / f"audit_{today}.jsonl"
        
        self.logger.info(
            "AuditLogger initialized",
            extra={
                "db_path": str(self.db_path),
                "log_file": str(self.log_file)
            }
        )
    
    def _init_database(self):
        """Initialize SQLite database for audit logs (Week 2)"""
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            
            # Create audit table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    audit_id TEXT UNIQUE,
                    timestamp TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    operation_type TEXT,
                    risk_level TEXT NOT NULL,
                    status TEXT NOT NULL,
                    paths TEXT NOT NULL,
                    file_count INTEGER,
                    total_size INTEGER,
                    success BOOLEAN NOT NULL,
                    details TEXT,
                    snapshot_id TEXT,
                    error TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create indexes for fast queries
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_timestamp 
                ON audit_log(timestamp)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_user_id 
                ON audit_log(user_id)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_operation 
                ON audit_log(operation)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_risk_level 
                ON audit_log(risk_level)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_status 
                ON audit_log(status)
            """)
            
            conn.commit()
            conn.close()
            
            self.logger.info("Audit database initialized successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize audit database: {e}", exc_info=True)
    
    # ==================== LEGACY METHOD (Preserved) ====================
    
    async def log_operation(
        self,
        operation_type: str,
        status: str,
        details: Dict[str, Any],
        snapshot_id: str = None,
        error: str = None,
        user_id: str = "default_user",
        risk_level: str = "unknown",
        paths: List[str] = None
    ) -> str:
        """
        Log an operation to audit trail (Legacy method - preserved and enhanced)
        
        Args:
            operation_type: Type of operation
            status: success, failed, pending
            details: Operation details
            snapshot_id: Associated snapshot if any
            error: Error message if failed
            user_id: User identifier (Week 2 addition)
            risk_level: Risk level (Week 2 addition)
            paths: Paths involved (Week 2 addition)
            
        Returns:
            Audit log ID
        """
        audit_id = str(uuid4())
        timestamp = datetime.utcnow().isoformat()
        
        # Prepare paths
        if paths is None:
            paths = details.get("paths", [])
        if isinstance(paths, (str, Path)):
            paths = [str(paths)]
        else:
            paths = [str(p) for p in paths]
        
        # Calculate file count and size from details
        file_count = details.get("file_count", len(paths))
        total_size = details.get("total_size_bytes", 0)
        
        # Determine success from status
        success = status.lower() in ["success", "completed"]
        
        # Legacy JSONL entry (preserved)
        jsonl_entry = {
            "audit_id": audit_id,
            "timestamp": timestamp,
            "operation_type": operation_type,
            "status": status,
            "details": details,
            "snapshot_id": snapshot_id,
            "error": error,
            # Week 2 additions
            "user_id": user_id,
            "risk_level": risk_level,
            "paths": paths
        }
        
        # Write to JSONL file (legacy compatibility)
        try:
            with open(self.log_file, 'a') as f:
                f.write(json.dumps(jsonl_entry) + '\n')
        except Exception as e:
            self.logger.error(f"Failed to write JSONL audit log: {e}")
        
        # Write to SQLite database (Week 2)
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO audit_log 
                (audit_id, timestamp, user_id, operation, operation_type, 
                 risk_level, status, paths, file_count, total_size, 
                 success, details, snapshot_id, error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                audit_id,
                timestamp,
                user_id,
                operation_type,  # operation column
                operation_type,  # operation_type column for compatibility
                risk_level,
                status,
                json.dumps(paths),
                file_count,
                total_size,
                success,
                json.dumps(details),
                snapshot_id,
                error
            ))
            
            conn.commit()
            conn.close()
        except Exception as e:
            self.logger.error(f"Failed to write database audit log: {e}", exc_info=True)
        
        self.logger.info(
            "audit_logged",
            extra={
                "audit_id": audit_id,
                "operation": operation_type,
                "status": status,
                "user_id": user_id
            }
        )
        
        return audit_id
    
    # ==================== LEGACY METHOD (Preserved) ====================
    
    async def get_recent_operations(self, limit: int = 10) -> List[Dict]:
        """
        Get recent operations from audit log (Legacy method - enhanced)
        Now reads from SQLite if available, falls back to JSONL
        """
        try:
            # Try SQLite first (Week 2)
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT * FROM audit_log 
                ORDER BY timestamp DESC
                LIMIT ?
            """, (limit,))
            
            rows = cursor.fetchall()
            conn.close()
            
            if rows:
                return [dict(row) for row in rows]
        except Exception as e:
            self.logger.warning(f"Failed to read from database, falling back to JSONL: {e}")
        
        # Fallback to JSONL (legacy)
        operations = []
        
        if not self.log_file.exists():
            return operations
        
        try:
            # Read last N lines
            with open(self.log_file, 'r') as f:
                lines = f.readlines()
            
            # Parse and return most recent
            for line in reversed(lines[-limit:]):
                try:
                    operations.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        except Exception as e:
            self.logger.error(f"Failed to read JSONL audit log: {e}")
        
        return operations
    
    # ==================== WEEK 2 ENHANCED METHODS ====================
    
    def log_operation_sync(
        self,
        user_id: str,
        operation: str,
        risk_level: str,
        paths: List[str],
        success: bool,
        details: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None
    ) -> bool:
        """
        Synchronous version of log_operation for Week 2 compatibility
        
        Args:
            user_id: User identifier
            operation: Operation name
            risk_level: Risk level (safe, low, medium, high, critical)
            paths: List of paths involved
            success: Whether operation succeeded
            details: Additional operation details
            error: Error message if failed
            
        Returns:
            True if logged successfully
        """
        try:
            audit_id = str(uuid4())
            timestamp = datetime.utcnow().isoformat()
            
            # Prepare data
            if isinstance(paths, (str, Path)):
                paths = [str(paths)]
            else:
                paths = [str(p) for p in paths]
            
            file_count = details.get("file_count", 0) if details else 0
            total_size = details.get("total_size_bytes", 0) if details else 0
            status = "success" if success else "failed"
            
            # Write to SQLite
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO audit_log 
                (audit_id, timestamp, user_id, operation, operation_type,
                 risk_level, status, paths, file_count, total_size, 
                 success, details, error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                audit_id,
                timestamp,
                user_id,
                operation,
                operation,
                risk_level,
                status,
                json.dumps(paths),
                file_count,
                total_size,
                success,
                json.dumps(details or {}),
                error
            ))
            
            conn.commit()
            conn.close()
            
            # Also write to JSONL for compatibility
            try:
                jsonl_entry = {
                    "audit_id": audit_id,
                    "timestamp": timestamp,
                    "user_id": user_id,
                    "operation_type": operation,
                    "risk_level": risk_level,
                    "status": status,
                    "paths": paths,
                    "success": success,
                    "details": details or {},
                    "error": error
                }
                with open(self.log_file, 'a') as f:
                    f.write(json.dumps(jsonl_entry) + '\n')
            except:
                pass  # JSONL is optional
            
            self.logger.info(
                "Operation audited",
                extra={
                    "user_id": user_id,
                    "operation": operation,
                    "risk_level": risk_level,
                    "success": success
                }
            )
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to log audit entry: {e}", exc_info=True)
            return False
    
    def get_user_operations(
        self,
        user_id: str,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Get operations for a user"""
        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT * FROM audit_log 
                WHERE user_id = ?
                ORDER BY timestamp DESC
                LIMIT ? OFFSET ?
            """, (user_id, limit, offset))
            
            rows = cursor.fetchall()
            conn.close()
            
            return [dict(row) for row in rows]
            
        except Exception as e:
            self.logger.error(f"Failed to get user operations: {e}")
            return []
    
    def get_operations_by_timeframe(
        self,
        hours: int = 24,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get recent operations within timeframe"""
        try:
            cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
            
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT * FROM audit_log 
                WHERE timestamp > ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (cutoff, limit))
            
            rows = cursor.fetchall()
            conn.close()
            
            return [dict(row) for row in rows]
            
        except Exception as e:
            self.logger.error(f"Failed to get recent operations: {e}")
            return []
    
    def get_high_risk_operations(
        self,
        days: int = 7,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get high-risk operations"""
        try:
            cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
            
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT * FROM audit_log 
                WHERE timestamp > ? 
                AND risk_level IN ('high', 'critical')
                ORDER BY timestamp DESC
                LIMIT ?
            """, (cutoff, limit))
            
            rows = cursor.fetchall()
            conn.close()
            
            return [dict(row) for row in rows]
            
        except Exception as e:
            self.logger.error(f"Failed to get high-risk operations: {e}")
            return []
    
    def get_failed_operations(
        self,
        days: int = 7,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get failed operations"""
        try:
            cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
            
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT * FROM audit_log 
                WHERE timestamp > ? 
                AND success = 0
                ORDER BY timestamp DESC
                LIMIT ?
            """, (cutoff, limit))
            
            rows = cursor.fetchall()
            conn.close()
            
            return [dict(row) for row in rows]
            
        except Exception as e:
            self.logger.error(f"Failed to get failed operations: {e}")
            return []
    
    def get_statistics(
        self,
        user_id: Optional[str] = None,
        days: int = 30
    ) -> Dict[str, Any]:
        """Get operation statistics"""
        try:
            cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
            
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            
            # Build query
            if user_id:
                where_clause = "WHERE timestamp > ? AND user_id = ?"
                params = (cutoff, user_id)
            else:
                where_clause = "WHERE timestamp > ?"
                params = (cutoff,)
            
            # Total operations
            cursor.execute(f"""
                SELECT COUNT(*) FROM audit_log {where_clause}
            """, params)
            total_ops = cursor.fetchone()[0]
            
            # Success rate
            cursor.execute(f"""
                SELECT COUNT(*) FROM audit_log 
                {where_clause} AND success = 1
            """, params)
            successful_ops = cursor.fetchone()[0]
            
            # Operations by risk level
            cursor.execute(f"""
                SELECT risk_level, COUNT(*) FROM audit_log 
                {where_clause}
                GROUP BY risk_level
            """, params)
            risk_distribution = dict(cursor.fetchall())
            
            # Most common operations
            cursor.execute(f"""
                SELECT operation, COUNT(*) as count FROM audit_log 
                {where_clause}
                GROUP BY operation
                ORDER BY count DESC
                LIMIT 10
            """, params)
            top_operations = dict(cursor.fetchall())
            
            # Total files processed
            cursor.execute(f"""
                SELECT SUM(file_count) FROM audit_log {where_clause}
            """, params)
            total_files = cursor.fetchone()[0] or 0
            
            # Total size processed
            cursor.execute(f"""
                SELECT SUM(total_size) FROM audit_log {where_clause}
            """, params)
            total_size = cursor.fetchone()[0] or 0
            
            conn.close()
            
            return {
                "period_days": days,
                "total_operations": total_ops,
                "successful_operations": successful_ops,
                "success_rate": (successful_ops / total_ops * 100) if total_ops > 0 else 0,
                "risk_distribution": risk_distribution,
                "top_operations": top_operations,
                "total_files_processed": total_files,
                "total_size_bytes": total_size,
                "total_size_mb": round(total_size / (1024 * 1024), 2)
            }
            
        except Exception as e:
            self.logger.error(f"Failed to get statistics: {e}")
            return {}
    
    def cleanup_old_logs(self, days: int = None):
        """Clean up old audit logs"""
        try:
            days = days or getattr(security_config, 'AUDIT_RETENTION_DAYS', 90)
            cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
            
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            
            cursor.execute("""
                DELETE FROM audit_log WHERE timestamp < ?
            """, (cutoff,))
            
            deleted = cursor.rowcount
            conn.commit()
            conn.close()
            
            self.logger.info(f"Cleaned up {deleted} old audit logs")
            
        except Exception as e:
            self.logger.error(f"Failed to cleanup old logs: {e}")
    
    def export_to_json(
        self,
        output_path: Path,
        user_id: Optional[str] = None,
        days: int = 30
    ) -> bool:
        """Export audit logs to JSON"""
        try:
            cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
            
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            if user_id:
                cursor.execute("""
                    SELECT * FROM audit_log 
                    WHERE timestamp > ? AND user_id = ?
                    ORDER BY timestamp DESC
                """, (cutoff, user_id))
            else:
                cursor.execute("""
                    SELECT * FROM audit_log 
                    WHERE timestamp > ?
                    ORDER BY timestamp DESC
                """, (cutoff,))
            
            rows = cursor.fetchall()
            conn.close()
            
            # Convert to list of dicts
            data = [dict(row) for row in rows]
            
            # Write to file
            with open(output_path, 'w') as f:
                json.dump(data, f, indent=2)
            
            self.logger.info(f"Exported {len(data)} audit entries to {output_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to export audit logs: {e}")
            return False


# Global instance
audit_logger = AuditLogger()