from typing import Dict, Any, Optional
from pathlib import Path
from utils.logger import get_logger

logger = get_logger(__name__)

class ConfirmationManager:
    """Manages user confirmation for operations"""
    
    def __init__(self):
        self.logger = logger.bind(component="ConfirmationManager")
        self.pending_operations = {}  # operation_id -> operation_details
    
    def create_confirmation_request(
        self,
        operation_type: str,
        details: Dict[str, Any]
    ) -> str:
        """
        Create a confirmation request
        
        Args:
            operation_type: Type of operation
            details: Operation details
            
        Returns:
            Confirmation message for user
        """
        from uuid import uuid4
        operation_id = str(uuid4())
        
        self.pending_operations[operation_id] = {
            "type": operation_type,
            "details": details
        }
        
        # Generate confirmation message
        message = self._generate_confirmation_message(operation_type, details)
        
        self.logger.info(
            "confirmation_requested",
            operation_id=operation_id,
            operation_type=operation_type
        )
        
        return message
    
    def _generate_confirmation_message(
        self,
        operation_type: str,
        details: Dict[str, Any]
    ) -> str:
        """Generate human-readable confirmation message"""
        
        if operation_type == "delete":
            file_count = len(details.get("files", []))
            return (
                f"⚠️  This will permanently delete {file_count} file(s).\n"
                f"Say 'confirm delete' to proceed or 'cancel' to abort."
            )
        
        elif operation_type == "organize":
            folder = details.get("folder")
            strategy = details.get("strategy")
            file_count = details.get("file_count", 0)
            folder_count = details.get("folder_count", 0)
            
            return (
                f"I'll organize {file_count} files in {folder} "
                f"by {strategy} into {folder_count} folders.\n"
                f"Say 'yes' to proceed or 'no' to cancel."
            )
        
        elif operation_type == "move" or operation_type == "copy":
            file_count = len(details.get("files", []))
            destination = details.get("destination")
            
            return (
                f"This will {operation_type} {file_count} file(s) to {destination}.\n"
                f"Say 'yes' to proceed or 'no' to cancel."
            )
        
        elif operation_type == "execute":
            file = details.get("file")
            return (
                f"⚠️  This will execute {file}. This could be dangerous.\n"
                f"Say 'confirm execute' to proceed or 'cancel' to abort."
            )
        
        else:
            return f"Proceed with {operation_type}? Say 'yes' to continue."
    
    def validate_confirmation(
        self,
        user_response: str,
        operation_type: str
    ) -> bool:
        """
        Check if user response is valid confirmation
        
        Args:
            user_response: What user said
            operation_type: Type of operation
            
        Returns:
            True if confirmed
        """
        response = user_response.lower().strip()
        
        # Strict confirmations for dangerous operations
        if operation_type == "delete":
            return "confirm delete" in response
        
        if operation_type == "execute":
            return "confirm execute" in response
        
        # Standard confirmations
        positive_words = ["yes", "yeah", "yep", "sure", "ok", "okay", "proceed", "go ahead", "do it"]
        return any(word in response for word in positive_words)