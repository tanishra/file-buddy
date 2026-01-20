import aiosqlite
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from utils.logger import get_logger
from config.settings import DATABASE_PATH

logger = get_logger(__name__)


@dataclass
class FolderPreference:
    """User's folder preference"""
    folder_path: str
    last_strategy: Optional[str] = None
    access_count: int = 1
    favorite: bool = False
    auto_organize: bool = False


@dataclass
class FilePattern:
    """Learned file handling pattern"""
    file_extension: str
    typical_destination: Optional[str] = None
    typical_action: Optional[str] = None
    frequency: int = 1


class MemoryStore:
    """
    Intelligent memory system that learns from user behavior
    """
    
    def __init__(self, db_path: Path = DATABASE_PATH):
        self.db_path = db_path
        self.logger = logger.bind(component="MemoryStore")
        self._initialized = False
    
    async def initialize(self):
        """Initialize database schema"""
        if self._initialized:
            return
        
        async with aiosqlite.connect(self.db_path) as db:
            # Read and execute schema
            schema_file = Path(__file__).parent.parent / "data" / "schema.sql"
            
            # If schema file doesn't exist, create tables programmatically
            await db.execute("""
                CREATE TABLE IF NOT EXISTS user_preferences (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key TEXT UNIQUE NOT NULL,
                    value TEXT NOT NULL,
                    value_type TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            await db.execute("""
                CREATE TABLE IF NOT EXISTS folder_preferences (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    folder_path TEXT UNIQUE NOT NULL,
                    last_strategy TEXT,
                    access_count INTEGER DEFAULT 1,
                    last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    favorite BOOLEAN DEFAULT 0,
                    auto_organize BOOLEAN DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            await db.execute("""
                CREATE TABLE IF NOT EXISTS file_patterns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_extension TEXT NOT NULL,
                    typical_destination TEXT,
                    typical_action TEXT,
                    frequency INTEGER DEFAULT 1,
                    last_used TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            await db.execute("""
                CREATE TABLE IF NOT EXISTS quick_actions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    description TEXT,
                    action_type TEXT NOT NULL,
                    parameters TEXT NOT NULL,
                    usage_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_used TIMESTAMP
                )
            """)
            
            await db.commit()
        
        self._initialized = True
        self.logger.info("memory_initialized", db_path=str(self.db_path))
    
    # ==================== USER PREFERENCES ====================
    
    async def set_preference(self, key: str, value: Any):
        """Set a user preference"""
        await self.initialize()
        
        # Determine value type
        if isinstance(value, (dict, list)):
            value_str = json.dumps(value)
            value_type = "json"
        elif isinstance(value, int):
            value_str = str(value)
            value_type = "int"
        elif isinstance(value, bool):
            value_str = str(int(value))
            value_type = "bool"
        else:
            value_str = str(value)
            value_type = "string"
        
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO user_preferences (key, value, value_type, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    value_type = excluded.value_type,
                    updated_at = excluded.updated_at
            """, (key, value_str, value_type, datetime.utcnow()))
            
            await db.commit()
        
        self.logger.info("preference_set", key=key, type=value_type)
    
    async def get_preference(self, key: str, default: Any = None) -> Any:
        """Get a user preference"""
        await self.initialize()
        
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT value, value_type FROM user_preferences WHERE key = ?",
                (key,)
            ) as cursor:
                row = await cursor.fetchone()
                
                if not row:
                    return default
                
                value_str, value_type = row
                
                # Parse based on type
                if value_type == "json":
                    return json.loads(value_str)
                elif value_type == "int":
                    return int(value_str)
                elif value_type == "bool":
                    return bool(int(value_str))
                else:
                    return value_str
    
    # ==================== FOLDER PREFERENCES ====================
    
    async def record_folder_access(
        self,
        folder_path: str,
        strategy: Optional[str] = None
    ):
        """Record that user accessed a folder"""
        await self.initialize()
        
        async with aiosqlite.connect(self.db_path) as db:
            # Check if exists
            async with db.execute(
                "SELECT access_count FROM folder_preferences WHERE folder_path = ?",
                (folder_path,)
            ) as cursor:
                row = await cursor.fetchone()
            
            if row:
                # Update existing
                await db.execute("""
                    UPDATE folder_preferences
                    SET access_count = access_count + 1,
                        last_accessed = ?,
                        last_strategy = COALESCE(?, last_strategy)
                    WHERE folder_path = ?
                """, (datetime.utcnow(), strategy, folder_path))
            else:
                # Insert new
                await db.execute("""
                    INSERT INTO folder_preferences 
                    (folder_path, last_strategy, last_accessed)
                    VALUES (?, ?, ?)
                """, (folder_path, strategy, datetime.utcnow()))
            
            await db.commit()
        
        self.logger.info("folder_access_recorded", folder=folder_path, strategy=strategy)
    
    async def get_folder_preference(self, folder_path: str) -> Optional[FolderPreference]:
        """Get preferences for a folder"""
        await self.initialize()
        
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("""
                SELECT folder_path, last_strategy, access_count, favorite, auto_organize
                FROM folder_preferences
                WHERE folder_path = ?
            """, (folder_path,)) as cursor:
                row = await cursor.fetchone()
                
                if row:
                    return FolderPreference(
                        folder_path=row[0],
                        last_strategy=row[1],
                        access_count=row[2],
                        favorite=bool(row[3]),
                        auto_organize=bool(row[4])
                    )
        
        return None
    
    async def get_favorite_folders(self) -> List[str]:
        """Get user's favorite folders"""
        await self.initialize()
        
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("""
                SELECT folder_path FROM folder_preferences
                WHERE favorite = 1
                ORDER BY access_count DESC
            """) as cursor:
                return [row[0] for row in await cursor.fetchall()]
    
    async def get_most_used_folders(self, limit: int = 5) -> List[Dict]:
        """Get most frequently accessed folders"""
        await self.initialize()
        
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("""
                SELECT folder_path, access_count, last_strategy
                FROM folder_preferences
                ORDER BY access_count DESC
                LIMIT ?
            """, (limit,)) as cursor:
                return [
                    {
                        "path": row[0],
                        "access_count": row[1],
                        "last_strategy": row[2]
                    }
                    for row in await cursor.fetchall()
                ]
    
    # ==================== FILE PATTERNS ====================
    
    async def record_file_action(
        self,
        file_extension: str,
        action: str,
        destination: Optional[str] = None
    ):
        """Learn from user's file handling patterns"""
        await self.initialize()
        
        async with aiosqlite.connect(self.db_path) as db:
            # Check if pattern exists
            async with db.execute(
                "SELECT frequency FROM file_patterns WHERE file_extension = ?",
                (file_extension,)
            ) as cursor:
                row = await cursor.fetchone()
            
            if row:
                # Update existing pattern
                await db.execute("""
                    UPDATE file_patterns
                    SET frequency = frequency + 1,
                        typical_action = ?,
                        typical_destination = COALESCE(?, typical_destination),
                        last_used = ?
                    WHERE file_extension = ?
                """, (action, destination, datetime.utcnow(), file_extension))
            else:
                # Create new pattern
                await db.execute("""
                    INSERT INTO file_patterns
                    (file_extension, typical_action, typical_destination, last_used)
                    VALUES (?, ?, ?, ?)
                """, (file_extension, action, destination, datetime.utcnow()))
            
            await db.commit()
        
        self.logger.info(
            "file_pattern_learned",
            extension=file_extension,
            action=action
        )
    
    async def get_file_pattern(self, file_extension: str) -> Optional[FilePattern]:
        """Get learned pattern for a file type"""
        await self.initialize()
        
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("""
                SELECT file_extension, typical_destination, typical_action, frequency
                FROM file_patterns
                WHERE file_extension = ?
            """, (file_extension,)) as cursor:
                row = await cursor.fetchone()
                
                if row:
                    return FilePattern(
                        file_extension=row[0],
                        typical_destination=row[1],
                        typical_action=row[2],
                        frequency=row[3]
                    )
        
        return None
    
    async def suggest_action_for_file(self, file_extension: str) -> Optional[Dict]:
        """Suggest what to do with a file based on learned patterns"""
        pattern = await self.get_file_pattern(file_extension)
        
        if pattern and pattern.frequency >= 3:  # Need at least 3 occurrences
            return {
                "action": pattern.typical_action,
                "destination": pattern.typical_destination,
                "confidence": min(pattern.frequency / 10, 1.0)  # Max confidence at 10 uses
            }
        
        return None
    
    # ==================== QUICK ACTIONS ====================
    
    async def save_quick_action(
        self,
        name: str,
        action_type: str,
        parameters: Dict,
        description: Optional[str] = None
    ):
        """Save a custom quick action"""
        await self.initialize()
        
        params_json = json.dumps(parameters)
        
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO quick_actions (name, description, action_type, parameters)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    description = excluded.description,
                    action_type = excluded.action_type,
                    parameters = excluded.parameters
            """, (name, description, action_type, params_json))
            
            await db.commit()
        
        self.logger.info("quick_action_saved", name=name, type=action_type)
    
    async def get_quick_action(self, name: str) -> Optional[Dict]:
        """Get a quick action by name"""
        await self.initialize()
        
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("""
                SELECT action_type, parameters, usage_count
                FROM quick_actions
                WHERE name = ?
            """, (name,)) as cursor:
                row = await cursor.fetchone()
                
                if row:
                    return {
                        "action_type": row[0],
                        "parameters": json.loads(row[1]),
                        "usage_count": row[2]
                    }
        
        return None
    
    async def list_quick_actions(self) -> List[Dict]:
        """List all quick actions"""
        await self.initialize()
        
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("""
                SELECT name, description, action_type, usage_count
                FROM quick_actions
                ORDER BY usage_count DESC
            """) as cursor:
                return [
                    {
                        "name": row[0],
                        "description": row[1],
                        "action_type": row[2],
                        "usage_count": row[3]
                    }
                    for row in await cursor.fetchall()
                ]