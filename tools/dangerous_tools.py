import send2trash
from pathlib import Path
from typing import List

from livekit.agents import function_tool, RunContext

from utils.logger import get_logger
from utils.path_utils import expand_user_path, validate_path
from core.audit import AuditLogger
from core.safety import SafetyChecker
from models.tool_results import ToolResult

# Week 2 Security Imports
from core.security import path_validator, security_enforcer
from core.risk_assessment import risk_assessor
from core.confirmation import ConfirmationManager
from core.backup_manager import backup_manager
from core.exceptions import PathSecurityError, ValidationError

logger = get_logger(__name__)


@function_tool()
async def delete_files_tool(
    context: RunContext,
    files: List[str],
) -> dict:
    """Delete files (move to trash)"""
    user_id = getattr(context, 'user_id', 'default_user')
    
    try:
        file_paths = [expand_user_path(f) for f in files]

        # Week 2: Security validation
        try:
            validated_paths = path_validator.validate_paths(
                file_paths,
                operation="delete",
                must_exist=True
            )
        except (PathSecurityError, ValidationError) as e:
            audit = AuditLogger()
            await audit.log_operation(
                operation_type="delete_files",
                status="blocked",
                details={"file_count": len(files)},
                user_id=user_id,
                risk_level="blocked",
                paths=[str(f) for f in files],
                error=str(e)
            )
            logger.warning("Security violation", extra={"error": str(e)})
            return ToolResult(success=False, error=f"Security: {str(e)}").to_dict()

        # Safety check
        safety = SafetyChecker()
        safety.validate_operation("delete", validated_paths)

        # Week 2: Risk assessment & confirmation
        cm = ConfirmationManager()
        requires_conf, op_id, risk = await cm.request_confirmation(
            operation="delete_files",
            paths=[str(p) for p in validated_paths],
            user_id=user_id
        )
        
        if requires_conf and op_id:
            message = cm.get_confirmation_message(op_id)
            return ToolResult(
                success=True,
                requires_confirmation=True,
                confirmation_message=message,
                data={"files": files, "operation_id": op_id},
            ).to_dict()

        # Legacy confirmation fallback
        return ToolResult(
            success=True,
            requires_confirmation=True,
            confirmation_message=(
                f"⚠️  This will permanently delete {len(files)} file(s). "
                f"Say 'confirm delete' to proceed."
            ),
            data={"files": files},
        ).to_dict()
        
    except Exception as e:
        audit = AuditLogger()
        await audit.log_operation(
            operation_type="delete_files",
            status="failed",
            details={"file_count": len(files)},
            user_id=user_id,
            risk_level="unknown",
            paths=[str(f) for f in files],
            error=str(e)
        )
        logger.error("delete_validation_failed", extra={"error": str(e)})
        return ToolResult(success=False, error=str(e)).to_dict()


@function_tool()
async def execute_delete(
    context: RunContext,
    files: List[str],
) -> dict:
    """Execute delete (after confirmation)"""
    user_id = getattr(context, 'user_id', 'default_user')
    
    try:
        file_paths = [expand_user_path(f) for f in files]

        # Week 2: Security validation
        try:
            validated_paths = path_validator.validate_paths(
                file_paths,
                operation="delete",
                must_exist=True
            )
        except (PathSecurityError, ValidationError) as e:
            audit = AuditLogger()
            await audit.log_operation(
                operation_type="execute_delete",
                status="blocked",
                details={"file_count": len(files)},
                user_id=user_id,
                risk_level="blocked",
                paths=[str(f) for f in files],
                error=str(e)
            )
            return ToolResult(success=False, error=f"Security: {str(e)}").to_dict()

        # Week 2: Check operation allowed
        allowed, reason = security_enforcer.check_operation_allowed(
            operation="delete_files",
            paths=validated_paths
        )
        
        if not allowed:
            audit = AuditLogger()
            await audit.log_operation(
                operation_type="execute_delete",
                status="blocked",
                details={"file_count": len(files)},
                user_id=user_id,
                risk_level="blocked",
                paths=[str(p) for p in validated_paths],
                error=reason
            )
            return ToolResult(success=False, error=reason).to_dict()

        deleted = 0
        for file_path in validated_paths:
            send2trash.send2trash(str(file_path))
            deleted += 1

        # Week 2: Enhanced audit log
        audit = AuditLogger()
        await audit.log_operation(
            operation_type="delete_files",
            status="success",
            details={"count": deleted, "files": [str(f) for f in validated_paths]},
            user_id=user_id,
            risk_level="high",
            paths=[str(f) for f in validated_paths]
        )

        logger.info("files_deleted", extra={"count": deleted})

        return ToolResult(
            success=True,
            data={"deleted": deleted},
            message=f"Deleted {deleted} files (moved to trash)",
        ).to_dict()
        
    except Exception as e:
        audit = AuditLogger()
        await audit.log_operation(
            operation_type="execute_delete",
            status="failed",
            details={"file_count": len(files)},
            user_id=user_id,
            risk_level="unknown",
            paths=[str(f) for f in files],
            error=str(e)
        )
        logger.error("delete_failed", extra={"error": str(e)})
        return ToolResult(success=False, error=str(e)).to_dict()


@function_tool()
async def delete_folder_tool(
    context: RunContext,
    path: str,
) -> dict:
    """Delete entire folder"""
    user_id = getattr(context, 'user_id', 'default_user')
    
    try:
        folder = expand_user_path(path)
        
        # Week 2: Security validation
        try:
            validated_path = path_validator.validate_path(
                folder,
                operation="delete",
                must_exist=True
            )
        except (PathSecurityError, ValidationError) as e:
            audit = AuditLogger()
            await audit.log_operation(
                operation_type="delete_folder",
                status="blocked",
                details={"path": str(folder)},
                user_id=user_id,
                risk_level="blocked",
                paths=[str(folder)],
                error=str(e)
            )
            return ToolResult(success=False, error=f"Security: {str(e)}").to_dict()
        
        validate_path(validated_path, must_exist=True)

        # Count files
        import os
        file_count = sum(1 for _ in validated_path.rglob("*") if _.is_file())

        # Week 2: Risk assessment & confirmation
        cm = ConfirmationManager()
        requires_conf, op_id, risk = await cm.request_confirmation(
            operation="delete_folder",
            paths=[str(validated_path)],
            user_id=user_id,
            file_count=file_count
        )
        
        if requires_conf and op_id:
            message = cm.get_confirmation_message(op_id)
            return ToolResult(
                success=True,
                requires_confirmation=True,
                confirmation_message=message,
                data={"path": str(validated_path), "file_count": file_count, "operation_id": op_id},
            ).to_dict()

        # Legacy confirmation fallback
        return ToolResult(
            success=True,
            requires_confirmation=True,
            confirmation_message=(
                f"⚠️  This will delete folder '{validated_path.name}' with {file_count} files. "
                f"Say 'confirm delete' to proceed."
            ),
            data={"path": str(validated_path), "file_count": file_count},
        ).to_dict()
        
    except Exception as e:
        audit = AuditLogger()
        await audit.log_operation(
            operation_type="delete_folder",
            status="failed",
            details={"path": str(path)},
            user_id=user_id,
            risk_level="unknown",
            paths=[str(path)],
            error=str(e)
        )
        logger.error("delete_folder_validation_failed", extra={"error": str(e)})
        return ToolResult(success=False, error=str(e)).to_dict()


@function_tool()
async def delete_multiple_folders_tool(
    context: RunContext,
    paths: List[str],
) -> dict:
    """Delete multiple folders (confirmation required)"""
    user_id = getattr(context, 'user_id', 'default_user')
    
    try:
        folders = [expand_user_path(p) for p in paths]

        # Week 2: Security validation
        try:
            validated_paths = path_validator.validate_paths(
                folders,
                operation="delete",
                must_exist=True
            )
        except (PathSecurityError, ValidationError) as e:
            audit = AuditLogger()
            await audit.log_operation(
                operation_type="delete_multiple_folders",
                status="blocked",
                details={"folder_count": len(paths)},
                user_id=user_id,
                risk_level="blocked",
                paths=[str(p) for p in paths],
                error=str(e)
            )
            return ToolResult(success=False, error=f"Security: {str(e)}").to_dict()

        safety = SafetyChecker()
        safety.validate_operation("delete", validated_paths)

        counts = {}
        for folder in validated_paths:
            validate_path(folder, must_exist=True)
            counts[str(folder)] = sum(
                1 for _ in folder.rglob("*") if _.is_file()
            )

        # Week 2: Risk assessment & confirmation
        cm = ConfirmationManager()
        requires_conf, op_id, risk = await cm.request_confirmation(
            operation="delete_multiple_folders",
            paths=[str(p) for p in validated_paths],
            user_id=user_id,
            folder_count=len(validated_paths),
            total_files=sum(counts.values())
        )
        
        if requires_conf and op_id:
            message = cm.get_confirmation_message(op_id)
            return ToolResult(
                success=True,
                requires_confirmation=True,
                confirmation_message=message,
                data={"folders": counts, "operation_id": op_id},
            ).to_dict()

        # Legacy confirmation fallback
        return ToolResult(
            success=True,
            requires_confirmation=True,
            confirmation_message=(
                f"⚠️  This will delete {len(validated_paths)} folders. "
                f"Say 'confirm delete' to proceed."
            ),
            data={"folders": counts},
        ).to_dict()

    except Exception as e:
        audit = AuditLogger()
        await audit.log_operation(
            operation_type="delete_multiple_folders",
            status="failed",
            details={"folder_count": len(paths)},
            user_id=user_id,
            risk_level="unknown",
            paths=[str(p) for p in paths],
            error=str(e)
        )
        logger.error("delete_multiple_folders_failed", extra={"error": str(e)})
        return ToolResult(success=False, error=str(e)).to_dict()


@function_tool()
async def delete_mixed_items_tool(
    context: RunContext,
    paths: List[str],
) -> dict:
    """Delete mixed files and folders"""
    user_id = getattr(context, 'user_id', 'default_user')
    
    try:
        items = [expand_user_path(p) for p in paths]

        # Week 2: Security validation
        try:
            validated_paths = path_validator.validate_paths(
                items,
                operation="delete",
                must_exist=True
            )
        except (PathSecurityError, ValidationError) as e:
            audit = AuditLogger()
            await audit.log_operation(
                operation_type="delete_mixed_items",
                status="blocked",
                details={"item_count": len(paths)},
                user_id=user_id,
                risk_level="blocked",
                paths=[str(p) for p in paths],
                error=str(e)
            )
            return ToolResult(success=False, error=f"Security: {str(e)}").to_dict()

        safety = SafetyChecker()
        safety.validate_operation("delete", validated_paths)

        preview = []
        for p in validated_paths:
            if p.is_file():
                preview.append({"path": str(p), "type": "file"})
            elif p.is_dir():
                preview.append({
                    "path": str(p),
                    "type": "folder",
                    "files": sum(1 for _ in p.rglob("*") if _.is_file()),
                })

        # Week 2: Risk assessment & confirmation
        cm = ConfirmationManager()
        requires_conf, op_id, risk = await cm.request_confirmation(
            operation="delete_mixed_items",
            paths=[str(p) for p in validated_paths],
            user_id=user_id,
            item_count=len(preview)
        )
        
        if requires_conf and op_id:
            message = cm.get_confirmation_message(op_id)
            return ToolResult(
                success=True,
                requires_confirmation=True,
                confirmation_message=message,
                data={"items": preview, "operation_id": op_id},
            ).to_dict()

        # Legacy confirmation fallback
        return ToolResult(
            success=True,
            requires_confirmation=True,
            confirmation_message=(
                f"⚠️  This will delete {len(preview)} items. "
                f"Say 'confirm delete' to proceed."
            ),
            data={"items": preview},
        ).to_dict()

    except Exception as e:
        audit = AuditLogger()
        await audit.log_operation(
            operation_type="delete_mixed_items",
            status="failed",
            details={"item_count": len(paths)},
            user_id=user_id,
            risk_level="unknown",
            paths=[str(p) for p in paths],
            error=str(e)
        )
        logger.error("delete_mixed_failed", extra={"error": str(e)})
        return ToolResult(success=False, error=str(e)).to_dict()


@function_tool()
async def conditional_delete_preview_tool(
    context: RunContext,
    path: str,
    extension: str | None = None,
    older_than_days: int | None = None,
) -> dict:
    """Preview conditional delete (no execution)"""
    user_id = getattr(context, 'user_id', 'default_user')
    
    try:
        from datetime import datetime, timedelta

        folder = expand_user_path(path)
        
        # Week 2: Security validation
        try:
            validated_path = path_validator.validate_path(
                folder,
                operation="read",  # Preview is read-only
                must_exist=True
            )
        except (PathSecurityError, ValidationError) as e:
            audit = AuditLogger()
            await audit.log_operation(
                operation_type="conditional_delete_preview",
                status="blocked",
                details={"path": str(folder)},
                user_id=user_id,
                risk_level="blocked",
                paths=[str(folder)],
                error=str(e)
            )
            return ToolResult(success=False, error=f"Security: {str(e)}").to_dict()
        
        validate_path(validated_path, must_exist=True)

        cutoff = None
        if older_than_days:
            cutoff = datetime.now().timestamp() - (older_than_days * 86400)

        matched = []
        for f in validated_path.rglob("*"):
            if not f.is_file():
                continue
            if extension and f.suffix != extension:
                continue
            if cutoff and f.stat().st_mtime > cutoff:
                continue
            matched.append(str(f))

        # Week 2: Risk assessment
        risk = risk_assessor.assess_operation(
            operation="conditional_delete",
            paths=[Path(p) for p in matched]
        )

        # Week 2: Enhanced audit log
        audit = AuditLogger()
        await audit.log_operation(
            operation_type="conditional_delete_preview",
            status="success",
            details={
                "path": str(validated_path),
                "matched_count": len(matched),
                "criteria": {"extension": extension, "older_than_days": older_than_days}
            },
            user_id=user_id,
            risk_level="low",  # Preview is low risk
            paths=[str(validated_path)]
        )

        return ToolResult(
            success=True,
            requires_confirmation=True,
            confirmation_message=(
                f"⚠️  This will delete {len(matched)} files. "
                f"Say 'confirm delete' to proceed."
            ),
            data={
                "path": str(validated_path),
                "matched_files": matched,
                "criteria": {
                    "extension": extension,
                    "older_than_days": older_than_days,
                },
                "risk_level": risk.level.value,
                "risk_score": risk.score
            },
        ).to_dict()

    except Exception as e:
        audit = AuditLogger()
        await audit.log_operation(
            operation_type="conditional_delete_preview",
            status="failed",
            details={"path": str(path)},
            user_id=user_id,
            risk_level="unknown",
            paths=[str(path)],
            error=str(e)
        )
        logger.error("conditional_delete_preview_failed", extra={"error": str(e)})
        return ToolResult(success=False, error=str(e)).to_dict()


@function_tool()
async def undo_last_delete_tool(
    context: RunContext,
) -> dict:
    """Undo last delete by restoring from trash"""
    user_id = getattr(context, 'user_id', 'default_user')
    
    try:
        # Week 2: Audit log
        audit = AuditLogger()
        await audit.log_operation(
            operation_type="undo_last_delete",
            status="failed",
            details={"reason": "OS trash restore not supported"},
            user_id=user_id,
            risk_level="low",
            paths=[]
        )

        return ToolResult(
            success=False,
            error=(
                "Undo delete is supported only if OS trash restore "
                "is available. Manual restore may be required."
            ),
        ).to_dict()

    except Exception as e:
        audit = AuditLogger()
        await audit.log_operation(
            operation_type="undo_last_delete",
            status="failed",
            details={},
            user_id=user_id,
            risk_level="unknown",
            paths=[],
            error=str(e)
        )
        logger.error("undo_delete_failed", extra={"error": str(e)})
        return ToolResult(success=False, error=str(e)).to_dict()