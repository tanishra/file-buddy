from enum import Enum
from pathlib import Path
from typing import List, Dict, Any
from dataclasses import dataclass

from config.security_config import security_config
from utils.logger import get_logger

logger = get_logger(__name__)


class RiskLevel(Enum):
    """Risk levels for operations"""
    SAFE = "safe"              # Read-only, no confirmation needed
    LOW = "low"                # Minor changes, verbal confirmation
    MEDIUM = "medium"          # Moderate changes, detailed confirmation
    HIGH = "high"              # Significant changes, double confirmation
    CRITICAL = "critical"      # Dangerous operations, PIN required


@dataclass
class RiskAssessment:
    """Risk assessment result"""
    level: RiskLevel
    score: int  # 0-100
    factors: List[str]  # Risk factors identified
    recommendation: str  # What to tell the user
    requires_confirmation: bool
    requires_backup: bool
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "level": self.level.value,
            "score": self.score,
            "factors": self.factors,
            "recommendation": self.recommendation,
            "requires_confirmation": self.requires_confirmation,
            "requires_backup": self.requires_backup
        }


class RiskAssessor:
    """
    Assesses risk level of file operations
    """
    
    def __init__(self):
        logger.info("RiskAssessor initialized")
    
    def assess_operation(
        self,
        operation: str,
        paths: List[Path],
        **kwargs
    ) -> RiskAssessment:
        """
        Assess risk of an operation
        
        Args:
            operation: Operation name
            paths: Paths involved
            **kwargs: Additional parameters
            
        Returns:
            RiskAssessment object
        """
        score = 0
        factors = []
        
        # Base risk by operation type
        base_risk = self._get_base_operation_risk(operation)
        score += base_risk
        factors.append(f"Operation type: {operation}")
        
        # Number of files risk
        file_count = len(paths)
        if file_count > security_config.RISK_HIGH_FILE_COUNT:
            score += 40
            factors.append(f"High file count ({file_count} files)")
        elif file_count > security_config.RISK_MEDIUM_FILE_COUNT:
            score += 25
            factors.append(f"Medium file count ({file_count} files)")
        elif file_count > security_config.RISK_LOW_FILE_COUNT:
            score += 10
            factors.append(f"Low file count ({file_count} files)")
        
        # Total size risk
        total_size = self._calculate_total_size(paths)
        size_mb = total_size / (1024 * 1024)
        
        if total_size > security_config.RISK_HIGH_SIZE:
            score += 30
            factors.append(f"Large total size ({size_mb:.1f}MB)")
        elif total_size > security_config.RISK_MEDIUM_SIZE:
            score += 20
            factors.append(f"Medium total size ({size_mb:.1f}MB)")
        elif total_size > security_config.RISK_LOW_SIZE:
            score += 10
            factors.append(f"Small total size ({size_mb:.1f}MB)")
        
        # Sensitive directories
        if any(security_config.is_sensitive_directory(p) for p in paths):
            score += 25
            factors.append("Operating on sensitive directories")
        
        # Protected files
        if any(security_config.is_protected_file(p) for p in paths if p.is_file()):
            score += 20
            factors.append("Protected files involved")
        
        # Recursive operations
        if kwargs.get("recursive"):
            score += 15
            factors.append("Recursive operation")
        
        # System files
        if any(self._is_system_file(p) for p in paths):
            score += 30
            factors.append("System files involved")
        
        # Determine risk level
        level = self._score_to_level(score)
        
        # Generate recommendation
        recommendation = self._generate_recommendation(level, operation, file_count, size_mb)
        
        # Determine requirements
        requires_confirmation = self._requires_confirmation(operation, level)
        requires_backup = self._requires_backup(operation, level)
        
        assessment = RiskAssessment(
            level=level,
            score=min(score, 100),
            factors=factors,
            recommendation=recommendation,
            requires_confirmation=requires_confirmation,
            requires_backup=requires_backup
        )
        
        logger.info(
            "Risk assessment completed",
            extra={
                "operation": operation,
                "risk_level": level.value,
                "score": score,
                "file_count": file_count,
                "requires_confirmation": requires_confirmation
            }
        )
        
        return assessment
    
    def _get_base_operation_risk(self, operation: str) -> int:
        """Get base risk score for operation type"""
        # Critical operations (50-60 points)
        if operation in ["delete_folder", "delete_multiple_folders", "flatten_folder"]:
            return 60
        
        if operation in ["delete_files", "delete_mixed_items"]:
            return 50
        
        # High risk operations (30-40 points)
        if operation in ["move_folder_contents", "copy_folder_contents"]:
            return 35
        
        # Medium risk operations (15-25 points)
        if operation in ["move_files", "rename_file", "batch_rename"]:
            return 20
        
        if operation in ["organize_folder", "organize_by_size", "organize_by_extension"]:
            return 15
        
        # Low risk operations (5-10 points)
        if operation in ["copy_files", "create_folder", "create_file"]:
            return 5
        
        # Safe operations (0 points)
        if operation in security_config.NEVER_CONFIRM_OPERATIONS:
            return 0
        
        # Default for unknown operations
        return 25
    
    def _calculate_total_size(self, paths: List[Path]) -> int:
        """Calculate total size of all paths"""
        total = 0
        for path in paths:
            try:
                if path.is_file():
                    total += path.stat().st_size
                elif path.is_dir():
                    for item in path.rglob("*"):
                        if item.is_file():
                            total += item.stat().st_size
            except:
                pass
        return total
    
    def _is_system_file(self, path: Path) -> bool:
        """Check if path is a system file"""
        system_indicators = {
            ".dll", ".sys", ".exe", ".so", ".dylib",
            "system32", "windows", "program files"
        }
        
        path_str = str(path).lower()
        return any(indicator in path_str for indicator in system_indicators)
    
    def _score_to_level(self, score: int) -> RiskLevel:
        """Convert score to risk level"""
        if score >= 80:
            return RiskLevel.CRITICAL
        elif score >= 60:
            return RiskLevel.HIGH
        elif score >= 35:
            return RiskLevel.MEDIUM
        elif score >= 15:
            return RiskLevel.LOW
        else:
            return RiskLevel.SAFE
    
    def _generate_recommendation(
        self,
        level: RiskLevel,
        operation: str,
        file_count: int,
        size_mb: float
    ) -> str:
        """Generate user-friendly recommendation"""
        if level == RiskLevel.CRITICAL:
            return (
                f"⚠️ CRITICAL: This operation affects {file_count} items ({size_mb:.1f}MB). "
                "Please review carefully before proceeding."
            )
        elif level == RiskLevel.HIGH:
            return (
                f"⚠️ HIGH RISK: This will modify {file_count} items ({size_mb:.1f}MB). "
                "A backup will be created automatically."
            )
        elif level == RiskLevel.MEDIUM:
            return (
                f"⚠️ MODERATE: This will affect {file_count} items ({size_mb:.1f}MB). "
                "Please confirm to proceed."
            )
        elif level == RiskLevel.LOW:
            return (
                f"ℹ️ LOW RISK: This will modify {file_count} items ({size_mb:.1f}MB)."
            )
        else:
            return f"✓ SAFE: Read-only operation, no changes will be made."
    
    def _requires_confirmation(self, operation: str, level: RiskLevel) -> bool:
        """Determine if confirmation is required"""
        # Always confirm these operations
        if operation in security_config.ALWAYS_CONFIRM_OPERATIONS:
            return True
        
        # Never confirm these operations
        if operation in security_config.NEVER_CONFIRM_OPERATIONS:
            return False
        
        # Confirm based on risk level
        return level in [RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL]
    
    def _requires_backup(self, operation: str, level: RiskLevel) -> bool:
        """Determine if backup is required"""
        if not security_config.ENABLE_AUTO_BACKUP:
            return False
        
        # Backup for destructive operations at medium risk or higher
        destructive_ops = {
            "delete_files", "delete_folder", "delete_multiple_folders",
            "delete_mixed_items", "move_files", "move_folder_contents"
        }
        
        return (
            operation in destructive_ops and
            level in [RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL]
        )


# Global instance
risk_assessor = RiskAssessor()