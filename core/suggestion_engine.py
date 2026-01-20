"""
Suggestion Engine - Provides intelligent recommendations based on user behavior
"""
from typing import List, Dict, Optional
from pathlib import Path
from datetime import datetime, timedelta
from dataclasses import dataclass
from utils.logger import get_logger
from core.memory_store import MemoryStore
from utils.file_utils import scan_folder, FileInfo

logger = get_logger(__name__)


@dataclass
class Suggestion:
    """A suggestion for the user"""
    type: str  # 'organize', 'cleanup', 'quick_action', 'reminder'
    title: str
    description: str
    action: str  # Tool to execute
    parameters: Dict
    confidence: float
    reason: str  # Why this suggestion?
    
    def to_dict(self) -> Dict:
        return {
            "type": self.type,
            "title": self.title,
            "description": self.description,
            "action": self.action,
            "parameters": self.parameters,
            "confidence": self.confidence,
            "reason": self.reason
        }


class SuggestionEngine:
    """
    Intelligent suggestion system that learns from user behavior
    
    Provides:
    - Proactive suggestions based on patterns
    - Cleanup recommendations
    - Quick action suggestions
    - Time-based reminders
    """
    
    def __init__(self, memory: Optional[MemoryStore] = None):
        self.logger = logger.bind(component="SuggestionEngine")
        self.memory = memory or MemoryStore()
    
    async def get_suggestions(
        self,
        context: Optional[Dict] = None,
        max_suggestions: int = 5
    ) -> List[Suggestion]:
        """
        Get personalized suggestions for the user
        
        Args:
            context: Current context (folder, last action, etc.)
            max_suggestions: Maximum number of suggestions
            
        Returns:
            List of Suggestion objects
        """
        await self.memory.initialize()
        
        suggestions = []
        
        # Get organization suggestions
        org_suggestions = await self._get_organization_suggestions()
        suggestions.extend(org_suggestions)
        
        # Get cleanup suggestions
        cleanup_suggestions = await self._get_cleanup_suggestions()
        suggestions.extend(cleanup_suggestions)
        
        # Get pattern-based suggestions
        pattern_suggestions = await self._get_pattern_suggestions(context)
        suggestions.extend(pattern_suggestions)
        
        # Get quick action suggestions
        quick_suggestions = await self._get_quick_action_suggestions()
        suggestions.extend(quick_suggestions)
        
        # Sort by confidence and return top N
        suggestions.sort(key=lambda s: s.confidence, reverse=True)
        
        self.logger.info(
            "suggestions_generated",
            total=len(suggestions),
            returned=min(len(suggestions), max_suggestions)
        )
        
        return suggestions[:max_suggestions]
    
    async def _get_organization_suggestions(self) -> List[Suggestion]:
        """Suggest folders that need organization"""
        suggestions = []
        
        # Get most used folders
        top_folders = await self.memory.get_most_used_folders(limit=3)
        
        for folder_data in top_folders:
            folder_path = Path(folder_data["path"])
            
            if not folder_path.exists():
                continue
            
            # Scan folder to check if messy
            try:
                files = scan_folder(folder_path, recursive=False)
                
                # Suggest organization if many files at root level
                if len(files) > 20:
                    strategy = folder_data.get("last_strategy", "by_file_type")
                    
                    suggestions.append(Suggestion(
                        type="organize",
                        title=f"Organize {folder_path.name}",
                        description=f"You have {len(files)} files in {folder_path.name}. Want me to organize them?",
                        action="organize_folder",
                        parameters={
                            "path": str(folder_path),
                            "strategy": strategy
                        },
                        confidence=0.8,
                        reason=f"Many files detected ({len(files)})"
                    ))
            
            except Exception as e:
                self.logger.warning("scan_failed_for_suggestion", folder=str(folder_path), error=str(e))
        
        return suggestions
    
    async def _get_cleanup_suggestions(self) -> List[Suggestion]:
        """Suggest files to cleanup (old, duplicate, etc.)"""
        suggestions = []
        
        # Check Downloads folder for old files
        downloads = Path.home() / "Downloads"
        
        if downloads.exists():
            try:
                files = scan_folder(downloads, recursive=False)
                
                # Find old files (>30 days)
                old_files = [f for f in files if not f.is_folder and f.age_days > 30]
                
                if len(old_files) > 10:
                    total_size = sum(f.size_bytes for f in old_files) / (1024 * 1024 * 1024)  # GB
                    
                    suggestions.append(Suggestion(
                        type="cleanup",
                        title="Clean up old Downloads",
                        description=f"You have {len(old_files)} files older than 30 days ({total_size:.1f} GB). Want to review and delete them?",
                        action="search_files",
                        parameters={
                            "path": str(downloads),
                            "max_age_days": 30
                        },
                        confidence=0.7,
                        reason="Many old files accumulating"
                    ))
            
            except Exception as e:
                self.logger.warning("cleanup_scan_failed", error=str(e))
        
        return suggestions
    
    async def _get_pattern_suggestions(self, context: Optional[Dict]) -> List[Suggestion]:
        """Suggest based on learned patterns"""
        suggestions = []
        
        if not context or "current_folder" not in context:
            return suggestions
        
        current_folder = context["current_folder"]
        
        # Get folder preference
        folder_pref = await self.memory.get_folder_preference(current_folder)
        
        if folder_pref and folder_pref.access_count > 5:
            # User accesses this folder frequently
            
            if folder_pref.last_strategy and not folder_pref.auto_organize:
                suggestions.append(Suggestion(
                    type="quick_action",
                    title=f"Auto-organize {Path(current_folder).name}?",
                    description=f"You usually organize this folder by {folder_pref.last_strategy}. Want to do it automatically from now on?",
                    action="set_auto_organize",
                    parameters={
                        "folder": current_folder,
                        "strategy": folder_pref.last_strategy
                    },
                    confidence=0.85,
                    reason="Frequent manual organization detected"
                ))
        
        return suggestions
    
    async def _get_quick_action_suggestions(self) -> List[Suggestion]:
        """Suggest creating quick actions for common tasks"""
        suggestions = []
        
        # Get most used folders
        top_folders = await self.memory.get_most_used_folders(limit=2)
        
        for folder_data in top_folders:
            if folder_data["access_count"] > 10 and folder_data["last_strategy"]:
                folder_path = Path(folder_data["path"])
                
                # Check if quick action already exists
                action_name = f"organize_{folder_path.name.lower()}"
                existing = await self.memory.get_quick_action(action_name)
                
                if not existing:
                    suggestions.append(Suggestion(
                        type="quick_action",
                        title=f"Create shortcut for {folder_path.name}",
                        description=f"Save 'Organize {folder_path.name}' as a quick action?",
                        action="save_quick_action",
                        parameters={
                            "name": action_name,
                            "action_type": "organize_folder",
                            "parameters": {
                                "path": str(folder_path),
                                "strategy": folder_data["last_strategy"]
                            }
                        },
                        confidence=0.75,
                        reason="Frequently performed action"
                    ))
        
        return suggestions
    
    async def suggest_for_file_type(self, file_extension: str) -> Optional[Suggestion]:
        """
        Suggest what to do with a specific file type
        
        Args:
            file_extension: File extension (e.g., '.pdf')
            
        Returns:
            Suggestion or None
        """
        action_data = await self.memory.suggest_action_for_file(file_extension)
        
        if not action_data:
            return None
        
        return Suggestion(
            type="pattern",
            title=f"Usual action for {file_extension} files",
            description=f"You usually {action_data['action']} {file_extension} files",
            action=action_data["action"],
            parameters={"destination": action_data.get("destination")},
            confidence=action_data["confidence"],
            reason="Based on past behavior"
        )
    
    async def suggest_next_step(
        self,
        last_action: str,
        last_result: Optional[Dict] = None
    ) -> Optional[Suggestion]:
        """
        Suggest next logical step after an action
        
        Args:
            last_action: Last action performed
            last_result: Result of last action
            
        Returns:
            Suggestion or None
        """
        if last_action == "scan_folder" and last_result:
            file_count = last_result.get("total_files", 0)
            
            if file_count > 20:
                return Suggestion(
                    type="followup",
                    title="Organize this folder?",
                    description=f"You have {file_count} files. Want me to organize them?",
                    action="organize_folder",
                    parameters={"strategy": "by_file_type"},
                    confidence=0.8,
                    reason="Many files detected after scan"
                )
        
        elif last_action == "search_files" and last_result:
            found_count = last_result.get("count", 0)
            
            if found_count > 0:
                return Suggestion(
                    type="followup",
                    title="What to do with found files?",
                    description=f"I found {found_count} files. Would you like to move, delete, or organize them?",
                    action="wait_for_user",
                    parameters={},
                    confidence=0.7,
                    reason="Files found matching search"
                )
        
        elif last_action in ["organize_folder", "move_files"]:
            return Suggestion(
                type="followup",
                title="Undo available",
                description="Say 'undo' if you want to revert this action.",
                action="undo_last_action",
                parameters={},
                confidence=1.0,
                reason="Reversible action completed"
            )
        
        return None
    
    async def get_smart_defaults(self, action: str, parameters: Dict) -> Dict:
        """
        Provide smart default values based on memory
        
        Args:
            action: Action being performed
            parameters: Current parameters
            
        Returns:
            Enhanced parameters with smart defaults
        """
        enhanced = parameters.copy()
        
        # For organize action without strategy
        if action == "organize_folder" and "path" in parameters and not parameters.get("strategy"):
            folder_pref = await self.memory.get_folder_preference(parameters["path"])
            
            if folder_pref and folder_pref.last_strategy:
                enhanced["strategy"] = folder_pref.last_strategy
                self.logger.info(
                    "smart_default_applied",
                    parameter="strategy",
                    value=folder_pref.last_strategy
                )
        
        return enhanced
    
    async def learn_from_action(
        self,
        action: str,
        parameters: Dict,
        success: bool
    ):
        """
        Learn from user actions to improve suggestions
        
        Args:
            action: Action performed
            parameters: Parameters used
            success: Whether action succeeded
        """
        if not success:
            return
        
        # Record folder access
        if "path" in parameters:
            await self.memory.record_folder_access(
                folder_path=parameters["path"],
                strategy=parameters.get("strategy")
            )
        
        # Record file patterns
        if "files" in parameters and "destination" in parameters:
            # Learn file movement patterns
            for file_path in parameters["files"]:
                ext = Path(file_path).suffix
                if ext:
                    await self.memory.record_file_action(
                        file_extension=ext,
                        action="move",
                        destination=parameters["destination"]
                    )
        
        self.logger.info("learned_from_action", action=action, success=success)