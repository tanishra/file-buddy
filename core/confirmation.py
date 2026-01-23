from typing import Dict, Any, Optional, List, Tuple
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime
import asyncio

from core.risk_assesment import risk_assessor, RiskLevel, RiskAssessment
from core.audit_logger import audit_logger
from core.backup_manager import backup_manager
from config.security_config import security_config
from config.settings import settings
from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ConfirmationRequest:
    """Pending confirmation request"""
    operation_id: str
    operation_type: str
    paths: List[str]
    risk_assessment: RiskAssessment
    user_id: str
    timestamp: str
    details: Dict[str, Any]
    backup_id: Optional[str] = None


class ConfirmationManager:
    """
    Manages user confirmation for operations
    
    Enhanced with Week 2 features:
    - Risk assessment integration
    - Automatic backup before high-risk operations
    - Audit logging
    - Timeout handling
    - Risk-based confirmation phrases
    """
    
    def __init__(self):
        self.logger = logger
        self.pending_operations = {}  # Legacy support: operation_id -> operation_details
        self.pending = {}  # Week 2: operation_id -> ConfirmationRequest
        self.confirmation_timeout = getattr(settings, 'CONFIRMATION_TIMEOUT', 300)  # 5 minutes
        
        self.logger.info("ConfirmationManager initialized with risk assessment")
    
    # ==================== LEGACY METHODS (Preserved) ====================
    
    def create_confirmation_request(
        self,
        operation_type: str,
        details: Dict[str, Any]
    ) -> str:
        """
        Create a confirmation request (Legacy method - preserved for compatibility)
        
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
            extra={
                "operation_id": operation_id,
                "operation_type": operation_type
            }
        )
        
        return message
    
    def _generate_confirmation_message(
        self,
        operation_type: str,
        details: Dict[str, Any]
    ) -> str:
        """Generate human-readable confirmation message (Legacy method)"""
        
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
        Check if user response is valid confirmation (Legacy method - preserved)
        
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
    
    # ==================== WEEK 2 ENHANCED METHODS ====================
    
    async def request_confirmation(
        self,
        operation: str,
        paths: List[str],
        user_id: str,
        **kwargs
    ) -> Tuple[bool, Optional[str], Optional[RiskAssessment]]:
        """
        Request confirmation for an operation (Week 2 enhanced)
        
        Args:
            operation: Operation name
            paths: Paths involved
            user_id: User identifier
            **kwargs: Additional operation parameters
            
        Returns:
            Tuple of (requires_confirmation, operation_id, risk_assessment)
        """
        try:
            # Convert paths to Path objects
            path_objects = [Path(p) for p in paths]
            
            # Assess risk
            risk = risk_assessor.assess_operation(
                operation=operation,
                paths=path_objects,
                **kwargs
            )
            
            self.logger.info(
                "Risk assessment completed",
                extra={
                    "operation": operation,
                    "risk_level": risk.level.value,
                    "requires_confirmation": risk.requires_confirmation,
                    "requires_backup": risk.requires_backup
                }
            )
            
            # Check if confirmation needed
            if not risk.requires_confirmation:
                # Low risk, no confirmation needed
                self.logger.info("Operation approved without confirmation")
                return False, None, risk
            
            # Generate operation ID
            operation_id = self._generate_operation_id(operation)
            
            # Create backup if required
            backup_id = None
            if risk.requires_backup and getattr(settings, 'ENABLE_AUTO_BACKUP', True):
                self.logger.info("Creating backup before operation")
                backup_id = backup_manager.create_backup(
                    paths=path_objects,
                    operation=operation,
                    user_id=user_id
                )
                
                if backup_id:
                    self.logger.info(
                        "Backup created",
                        extra={"backup_id": backup_id}
                    )
                else:
                    self.logger.warning("Failed to create backup")
            
            # Create confirmation request
            request = ConfirmationRequest(
                operation_id=operation_id,
                operation_type=operation,
                paths=paths,
                risk_assessment=risk,
                user_id=user_id,
                timestamp=datetime.utcnow().isoformat(),
                details=kwargs,
                backup_id=backup_id
            )
            
            self.pending[operation_id] = request
            
            # Set timeout for cleanup
            asyncio.create_task(self._timeout_handler(operation_id))
            
            return True, operation_id, risk
            
        except Exception as e:
            self.logger.error(f"Error requesting confirmation: {e}", exc_info=True)
            # Fail secure - require confirmation on error
            return True, None, None
    
    def get_confirmation_message(self, operation_id: str) -> Optional[str]:
        """
        Get confirmation message for user (Week 2 enhanced)
        
        Returns:
            Formatted message for user
        """
        if operation_id not in self.pending:
            return None
        
        request = self.pending[operation_id]
        risk = request.risk_assessment
        
        # Build message based on risk level
        message_parts = [
            f"🔔 Confirmation Required",
            f"",
            f"{risk.recommendation}",
            f"",
            f"📋 Operation: {request.operation_type}",
            f"📁 Paths: {len(request.paths)} items",
        ]
        
        # Add path preview
        if len(request.paths) <= 5:
            for path in request.paths:
                message_parts.append(f"   • {path}")
        else:
            for path in request.paths[:3]:
                message_parts.append(f"   • {path}")
            message_parts.append(f"   ... and {len(request.paths) - 3} more")
        
        message_parts.append("")
        
        # Add risk factors
        if risk.factors:
            message_parts.append(f"⚠️ Risk Factors:")
            for factor in risk.factors[:3]:  # Show top 3 factors
                message_parts.append(f"   • {factor}")
        
        # Add backup info if available
        if request.backup_id:
            message_parts.append("")
            message_parts.append(f"💾 Backup created: {request.backup_id}")
        
        message_parts.append("")
        
        # Add confirmation instruction based on risk
        if risk.level == RiskLevel.CRITICAL:
            message_parts.append("⚠️ CRITICAL: Please review very carefully")
            message_parts.append("Say 'YES I CONFIRM' to proceed or 'CANCEL' to abort")
        elif risk.level == RiskLevel.HIGH:
            message_parts.append("⚠️ Say 'CONFIRM' to proceed or 'CANCEL' to abort")
        else:
            message_parts.append("Say 'YES' to proceed or 'NO' to cancel")
        
        return "\n".join(message_parts)
    
    def confirm_operation(
        self,
        operation_id: str,
        user_response: str
    ) -> Tuple[bool, Optional[ConfirmationRequest]]:
        """
        Process user confirmation (Week 2 enhanced)
        
        Args:
            operation_id: Operation ID
            user_response: User's response
            
        Returns:
            Tuple of (confirmed, request)
        """
        if operation_id not in self.pending:
            self.logger.warning(f"Unknown operation ID: {operation_id}")
            return False, None
        
        request = self.pending[operation_id]
        response_lower = user_response.lower().strip()
        
        # Determine if confirmed based on risk level
        confirmed = False
        
        if request.risk_assessment.level == RiskLevel.CRITICAL:
            # Require exact phrase
            if "yes i confirm" in response_lower:
                confirmed = True
        elif request.risk_assessment.level == RiskLevel.HIGH:
            # Require "confirm"
            if "confirm" in response_lower and "cancel" not in response_lower:
                confirmed = True
        else:
            # Require "yes"
            if ("yes" in response_lower or "confirm" in response_lower) and \
               "no" not in response_lower and "cancel" not in response_lower:
                confirmed = True
        
        # Log the confirmation if audit is enabled
        if getattr(settings, 'ENABLE_AUDIT_LOG', True):
            audit_logger.log_operation(
                user_id=request.user_id,
                operation=f"{request.operation_type}_confirmation",
                risk_level=request.risk_assessment.level.value,
                paths=request.paths,
                success=confirmed,
                details={
                    "operation_id": operation_id,
                    "user_response": user_response,
                    "confirmed": confirmed
                }
            )
        
        self.logger.info(
            "Confirmation processed",
            extra={
                "operation_id": operation_id,
                "confirmed": confirmed,
                "risk_level": request.risk_assessment.level.value
            }
        )
        
        # Remove from pending
        del self.pending[operation_id]
        
        return confirmed, request
    
    def cancel_operation(self, operation_id: str) -> bool:
        """Cancel a pending operation (Week 2 enhanced)"""
        if operation_id not in self.pending:
            return False
        
        request = self.pending[operation_id]
        
        # Log cancellation if audit is enabled
        if getattr(settings, 'ENABLE_AUDIT_LOG', True):
            audit_logger.log_operation(
                user_id=request.user_id,
                operation=f"{request.operation_type}_cancelled",
                risk_level=request.risk_assessment.level.value,
                paths=request.paths,
                success=True,
                details={"operation_id": operation_id, "reason": "user_cancelled"}
            )
        
        # Remove from pending
        del self.pending[operation_id]
        
        self.logger.info("Operation cancelled", extra={"operation_id": operation_id})
        return True
    
    def get_pending_operation(
        self,
        operation_id: str
    ) -> Optional[ConfirmationRequest]:
        """Get pending operation details"""
        return self.pending.get(operation_id)
    
    def has_pending_operations(self, user_id: Optional[str] = None) -> bool:
        """Check if there are pending operations"""
        if user_id:
            return any(
                req.user_id == user_id
                for req in self.pending.values()
            )
        return len(self.pending) > 0
    
    def list_pending_operations(
        self,
        user_id: Optional[str] = None
    ) -> List[ConfirmationRequest]:
        """List pending operations"""
        if user_id:
            return [
                req for req in self.pending.values()
                if req.user_id == user_id
            ]
        return list(self.pending.values())
    
    async def _timeout_handler(self, operation_id: str):
        """Handle confirmation timeout"""
        await asyncio.sleep(self.confirmation_timeout)
        
        if operation_id in self.pending:
            request = self.pending[operation_id]
            
            self.logger.warning(
                "Confirmation timeout",
                extra={"operation_id": operation_id}
            )
            
            # Log timeout if audit is enabled
            if getattr(settings, 'ENABLE_AUDIT_LOG', True):
                audit_logger.log_operation(
                    user_id=request.user_id,
                    operation=f"{request.operation_type}_timeout",
                    risk_level=request.risk_assessment.level.value,
                    paths=request.paths,
                    success=False,
                    details={"operation_id": operation_id, "reason": "timeout"}
                )
            
            # Remove from pending
            del self.pending[operation_id]
    
    def _generate_operation_id(self, operation: str) -> str:
        """Generate unique operation ID"""
        import hashlib
        timestamp = datetime.utcnow().isoformat()
        hash_input = f"{operation}_{timestamp}".encode()
        return hashlib.md5(hash_input).hexdigest()[:12]
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get confirmation statistics"""
        return {
            "pending_count": len(self.pending),
            "legacy_pending_count": len(self.pending_operations),
            "timeout_seconds": self.confirmation_timeout,
            "by_risk_level": {
                level.value: sum(
                    1 for req in self.pending.values()
                    if req.risk_assessment.level == level
                )
                for level in RiskLevel
            }
        }