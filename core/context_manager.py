from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from pathlib import Path
from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ConversationContext:
    """Current conversation state"""
    session_id: str
    last_folder: Optional[str] = None
    last_files: List[str] = field(default_factory=list)
    last_action: Optional[str] = None
    last_result: Optional[Dict] = None
    pending_confirmation: Optional[Dict] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    
    def is_expired(self, minutes: int = 30) -> bool:
        """Check if context is too old"""
        age = datetime.utcnow() - self.created_at
        return age > timedelta(minutes=minutes)


class ContextManager:
    """
    Manages conversation context for multi-turn interactions
    
    Handles:
    - Reference resolution ("that folder", "those files", "the last one")
    - Follow-up questions
    - Confirmation flows
    - Multi-step operations
    """
    
    def __init__(self, session_id: str = "default"):
        self.logger = logger.bind(component="ContextManager", session=session_id)
        self.context = ConversationContext(session_id=session_id)
        self._history: List[Dict] = []
    
    def update_last_folder(self, folder_path: str):
        """Update last accessed folder"""
        self.context.last_folder = folder_path
        self.logger.info("context_updated", last_folder=folder_path)
    
    def update_last_files(self, file_paths: List[str]):
        """Update last operated files"""
        self.context.last_files = file_paths
        self.logger.info("context_updated", file_count=len(file_paths))
    
    def update_last_action(self, action: str, result: Optional[Dict] = None):
        """Update last performed action"""
        self.context.last_action = action
        self.context.last_result = result
        
        # Add to history
        self._history.append({
            "action": action,
            "result": result,
            "timestamp": datetime.utcnow()
        })
        
        # Keep only last 10 actions
        if len(self._history) > 10:
            self._history.pop(0)
        
        self.logger.info("action_recorded", action=action)
    
    def set_pending_confirmation(self, confirmation_data: Dict):
        """Set a pending confirmation"""
        self.context.pending_confirmation = confirmation_data
        self.logger.info("confirmation_pending", type=confirmation_data.get("type"))
    
    def clear_pending_confirmation(self):
        """Clear pending confirmation"""
        self.context.pending_confirmation = None
    
    def has_pending_confirmation(self) -> bool:
        """Check if there's a pending confirmation"""
        return self.context.pending_confirmation is not None
    
    def resolve_reference(self, text: str) -> Optional[str]:
        """
        Resolve references like "that folder", "those files", etc.
        
        Args:
            text: User's text with potential reference
            
        Returns:
            Resolved reference or None
        """
        text_lower = text.lower()
        
        # Folder references
        if any(ref in text_lower for ref in ["that folder", "this folder", "the folder", "it"]):
            if self.context.last_folder:
                self.logger.info("reference_resolved", type="folder", value=self.context.last_folder)
                return self.context.last_folder
        
        # File references
        if any(ref in text_lower for ref in ["those files", "these files", "them", "the files"]):
            if self.context.last_files:
                self.logger.info("reference_resolved", type="files", count=len(self.context.last_files))
                return f"{len(self.context.last_files)} files"
        
        # Action references
        if any(ref in text_lower for ref in ["that", "it", "last one", "previous"]):
            if self.context.last_action:
                self.logger.info("reference_resolved", type="action", value=self.context.last_action)
                return self.context.last_action
        
        return None
    
    def is_follow_up_question(self, text: str) -> bool:
        """
        Determine if text is a follow-up to previous conversation
        
        Returns True for:
        - "And then..." 
        - "Also..."
        - "What about..."
        - Questions with references
        """
        text_lower = text.lower().strip()
        
        follow_up_indicators = [
            "and then", "also", "what about", "how about",
            "can you also", "now", "next", "after that"
        ]
        
        return any(indicator in text_lower for indicator in follow_up_indicators)
    
    def get_context_summary(self) -> Dict[str, Any]:
        """Get summary of current context"""
        return {
            "session_id": self.context.session_id,
            "last_folder": self.context.last_folder,
            "last_files_count": len(self.context.last_files),
            "last_action": self.context.last_action,
            "has_pending_confirmation": self.has_pending_confirmation(),
            "history_count": len(self._history),
            "age_minutes": (datetime.utcnow() - self.context.created_at).total_seconds() / 60
        }
    
    def suggest_next_action(self) -> Optional[str]:
        """
        Suggest what user might want to do next based on context
        
        Returns suggestion text or None
        """
        if not self.context.last_action:
            return None
        
        # After organizing
        if self.context.last_action == "organize":
            return "Would you like me to organize another folder?"
        
        # After searching
        if self.context.last_action == "search":
            if self.context.last_files:
                return "Would you like to move or delete these files?"
        
        # After deletion
        if self.context.last_action == "delete":
            return "Say 'undo' if you want to restore them."
        
        return None
    
    def reset(self):
        """Reset context (new conversation)"""
        old_session = self.context.session_id
        self.context = ConversationContext(session_id=old_session)
        self._history = []
        self.logger.info("context_reset")