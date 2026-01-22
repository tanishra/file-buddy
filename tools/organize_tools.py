import shutil
from pathlib import Path

from livekit.agents import function_tool, RunContext

from utils.logger import get_logger
from utils.path_utils import expand_user_path, validate_path, get_safe_destination
from utils.file_utils import scan_folder, group_by_category
from config.greetings import get_confirmation_message, get_success_message
from core.snapshot import SnapshotManager
from core.audit_logger import AuditLogger
from models.tool_results import ToolResult

# Week 2 Security Imports
from core.security import path_validator, security_enforcer
from core.risk_assesment import risk_assessor
from core.confirmation import ConfirmationManager
from core.backup_manager import backup_manager
from core.exceptions import PathSecurityError, ValidationError

logger = get_logger(__name__)


@function_tool()
async def organize_folder_tool(
    context: RunContext,
    path: str,
    strategy: str = "by_file_type",
) -> dict:
    """Organize folder by strategy"""
    user_id = getattr(context, 'user_id', 'default_user')
    
    try:
        folder = expand_user_path(path)

        # Week 2: Security validation
        try:
            validated_folder = path_validator.validate_path(
                folder,
                operation="modify",
                must_exist=True
            )
        except (PathSecurityError, ValidationError) as e:
            audit = AuditLogger()
            await audit.log_operation(
                operation_type="organize_folder",
                status="blocked",
                details={"path": str(folder), "strategy": strategy},
                user_id=user_id,
                risk_level="blocked",
                paths=[str(folder)],
                error=str(e)
            )
            return ToolResult(success=False, error=f"Security: {str(e)}").to_dict()

        validate_path(validated_folder, must_exist=True)

        # Scan folder
        files = scan_folder(validated_folder, recursive=False)

        if not files:
            return ToolResult(success=True, message="Folder is empty")

        # Group by strategy
        if strategy == "by_file_type":
            groups = group_by_category(files)
        elif strategy == "by_date":
            from datetime import datetime

            groups = {}
            for f in files:
                date = datetime.fromtimestamp(f.modified_at)
                month_key = date.strftime("%Y-%m")
                if month_key not in groups:
                    groups[month_key] = []
                groups[month_key].append(f)
        else:
            return ToolResult(success=False, error=f"Unknown strategy: {strategy}")

        # Week 2: Risk assessment & confirmation
        cm = ConfirmationManager()
        requires_conf, op_id, risk = await cm.request_confirmation(
            operation="organize_folder",
            paths=[str(validated_folder)],
            user_id=user_id,
            file_count=len(files),
            folder_count=len(groups),
            strategy=strategy
        )
        
        if requires_conf and op_id:
            message = cm.get_confirmation_message(op_id)
            return ToolResult(
                success=True,
                requires_confirmation=True,
                confirmation_message=message,
                data={
                    "path": str(validated_folder),
                    "strategy": strategy,
                    "file_count": len(files),
                    "folder_count": len(groups),
                    "groups": {k: len(v) for k, v in groups.items()},
                    "operation_id": op_id
                },
            ).to_dict()

        # Legacy confirmation fallback
        return ToolResult(
            success=True,
            requires_confirmation=True,
            confirmation_message=(
                f"Organize {len(files)} files into {len(groups)} folders "
                f"using strategy '{strategy}'?"
            ),
            data={
                "path": str(validated_folder),
                "strategy": strategy,
                "file_count": len(files),
                "folder_count": len(groups),
                "groups": {k: len(v) for k, v in groups.items()},
            },
        ).to_dict()

    except Exception as e:
        audit = AuditLogger()
        await audit.log_operation(
            operation_type="organize_folder",
            status="failed",
            details={"path": str(path), "strategy": strategy},
            user_id=user_id,
            risk_level="unknown",
            paths=[str(path)],
            error=str(e)
        )
        logger.error("organize_failed", extra={"error": str(e)})
        return ToolResult(success=False, error=str(e)).to_dict()


@function_tool()
async def execute_organize(
    context: RunContext,
    path: str,
    strategy: str,
) -> dict:
    """Execute organization (after confirmation)"""
    user_id = getattr(context, 'user_id', 'default_user')
    
    try:
        folder = expand_user_path(path)

        # Week 2: Security validation
        try:
            validated_folder = path_validator.validate_path(
                folder,
                operation="modify",
                must_exist=True
            )
        except (PathSecurityError, ValidationError) as e:
            audit = AuditLogger()
            await audit.log_operation(
                operation_type="execute_organize",
                status="blocked",
                details={"path": str(folder), "strategy": strategy},
                user_id=user_id,
                risk_level="blocked",
                paths=[str(folder)],
                error=str(e)
            )
            return ToolResult(success=False, error=f"Security: {str(e)}").to_dict()

        files = scan_folder(validated_folder, recursive=False)

        # Group files
        if strategy == "by_file_type":
            groups = group_by_category(files)
        elif strategy == "by_date":
            from datetime import datetime

            groups = {}
            for f in files:
                date = datetime.fromtimestamp(f.modified_at)
                month_key = date.strftime("%Y-%m")
                if month_key not in groups:
                    groups[month_key] = []
                groups[month_key].append(f)
        else:
            groups = {}

        # Create snapshot
        snapshot_mgr = SnapshotManager()
        file_states = {}
        folders_created = []

        # Move files
        moved = 0
        for group_name, group_files in groups.items():
            group_folder = validated_folder / group_name
            group_folder.mkdir(exist_ok=True)
            folders_created.append(group_folder)

            for file_info in group_files:
                dest = get_safe_destination(file_info.path, group_folder)
                file_states[dest] = file_info.path
                shutil.move(str(file_info.path), str(dest))
                moved += 1

        # Save snapshot
        snapshot = await snapshot_mgr.create_snapshot(
            operation_type="organize",
            file_states=file_states,
            folders_created=folders_created,
            metadata={"strategy": strategy},
        )

        # Week 2: Enhanced audit log
        audit = AuditLogger()
        await audit.log_operation(
            operation_type="organize_folder",
            status="success",
            details={"path": str(validated_folder), "strategy": strategy, "moved": moved},
            snapshot_id=snapshot.snapshot_id,
            user_id=user_id,
            risk_level="medium",
            paths=[str(validated_folder)]
        )

        logger.info("folder_organized", extra={"path": str(validated_folder), "moved": moved})

        return ToolResult(
            success=True,
            data={"moved": moved, "folders": len(groups)},
            message=f"Organized {moved} files into {len(groups)} folders",
            snapshot_id=snapshot.snapshot_id,
        ).to_dict()

    except Exception as e:
        audit = AuditLogger()
        await audit.log_operation(
            operation_type="execute_organize",
            status="failed",
            details={"path": str(path), "strategy": strategy},
            user_id=user_id,
            risk_level="unknown",
            paths=[str(path)],
            error=str(e)
        )
        logger.error("organize_execution_failed", extra={"error": str(e)})
        return ToolResult(success=False, error=str(e)).to_dict()


@function_tool()
async def organize_by_size_tool(
    context: RunContext,
    path: str,
) -> dict:
    """Organize files into Small / Medium / Large folders"""
    user_id = getattr(context, 'user_id', 'default_user')
    
    try:
        folder = expand_user_path(path)

        # Week 2: Security validation
        try:
            validated_folder = path_validator.validate_path(
                folder,
                operation="modify",
                must_exist=True
            )
        except (PathSecurityError, ValidationError) as e:
            audit = AuditLogger()
            await audit.log_operation(
                operation_type="organize_by_size",
                status="blocked",
                details={"path": str(folder)},
                user_id=user_id,
                risk_level="blocked",
                paths=[str(folder)],
                error=str(e)
            )
            return ToolResult(success=False, error=f"Security: {str(e)}").to_dict()

        validate_path(validated_folder, must_exist=True)

        files = scan_folder(validated_folder, recursive=False)

        groups = {
            "Small": [],
            "Medium": [],
            "Large": [],
        }

        for f in files:
            if f.size_bytes < 1_000_000:
                groups["Small"].append(f)
            elif f.size_bytes < 100_000_000:
                groups["Medium"].append(f)
            else:
                groups["Large"].append(f)

        # Week 2: Enhanced audit
        audit = AuditLogger()
        await audit.log_operation(
            operation_type="organize_by_size",
            status="pending",
            details={"path": str(validated_folder), "file_count": len(files)},
            user_id=user_id,
            risk_level="medium",
            paths=[str(validated_folder)]
        )

        return ToolResult(
            success=True,
            requires_confirmation=True,
            confirmation_message=f"Organize {len(files)} files by size?",
            data={
                "path": str(validated_folder),
                "groups": {k: len(v) for k, v in groups.items()},
                "strategy": "by_size",
            },
        ).to_dict()

    except Exception as e:
        audit = AuditLogger()
        await audit.log_operation(
            operation_type="organize_by_size",
            status="failed",
            details={"path": str(path)},
            user_id=user_id,
            risk_level="unknown",
            paths=[str(path)],
            error=str(e)
        )
        logger.error("organize_by_size_failed", extra={"error": str(e)})
        return ToolResult(success=False, error=str(e)).to_dict()


@function_tool()
async def organize_by_extension_tool(
    context: RunContext,
    path: str,
) -> dict:
    """Organize files by file extension"""
    user_id = getattr(context, 'user_id', 'default_user')
    
    try:
        folder = expand_user_path(path)

        # Week 2: Security validation
        try:
            validated_folder = path_validator.validate_path(
                folder,
                operation="modify",
                must_exist=True
            )
        except (PathSecurityError, ValidationError) as e:
            audit = AuditLogger()
            await audit.log_operation(
                operation_type="organize_by_extension",
                status="blocked",
                details={"path": str(folder)},
                user_id=user_id,
                risk_level="blocked",
                paths=[str(folder)],
                error=str(e)
            )
            return ToolResult(success=False, error=f"Security: {str(e)}").to_dict()

        validate_path(validated_folder, must_exist=True)

        files = scan_folder(validated_folder, recursive=False)
        groups = {}

        for f in files:
            ext = f.path.suffix.lower().lstrip(".") or "no_extension"
            groups.setdefault(ext, []).append(f)

        # Week 2: Enhanced audit
        audit = AuditLogger()
        await audit.log_operation(
            operation_type="organize_by_extension",
            status="pending",
            details={"path": str(validated_folder), "file_count": len(files)},
            user_id=user_id,
            risk_level="medium",
            paths=[str(validated_folder)]
        )

        return ToolResult(
            success=True,
            requires_confirmation=True,
            confirmation_message=f"Organize {len(files)} files by extension?",
            data={
                "path": str(validated_folder),
                "strategy": "by_extension",
                "groups": {k: len(v) for k, v in groups.items()},
            },
        ).to_dict()

    except Exception as e:
        audit = AuditLogger()
        await audit.log_operation(
            operation_type="organize_by_extension",
            status="failed",
            details={"path": str(path)},
            user_id=user_id,
            risk_level="unknown",
            paths=[str(path)],
            error=str(e)
        )
        logger.error("organize_by_extension_failed", extra={"error": str(e)})
        return ToolResult(success=False, error=str(e)).to_dict()


@function_tool()
async def normalize_filenames_tool(
    context: RunContext,
    path: str,
) -> dict:
    """Normalize filenames (lowercase, underscores, safe chars)"""
    user_id = getattr(context, 'user_id', 'default_user')
    
    try:
        folder = expand_user_path(path)

        # Week 2: Security validation
        try:
            validated_folder = path_validator.validate_path(
                folder,
                operation="modify",
                must_exist=True
            )
        except (PathSecurityError, ValidationError) as e:
            audit = AuditLogger()
            await audit.log_operation(
                operation_type="normalize_filenames",
                status="blocked",
                details={"path": str(folder)},
                user_id=user_id,
                risk_level="blocked",
                paths=[str(folder)],
                error=str(e)
            )
            return ToolResult(success=False, error=f"Security: {str(e)}").to_dict()

        validate_path(validated_folder, must_exist=True)

        files = scan_folder(validated_folder, recursive=False)

        preview = {}
        for f in files:
            new_name = (
                f.path.name.lower()
                .replace(" ", "_")
                .replace("-", "_")
            )
            if new_name != f.path.name:
                preview[f.path.name] = new_name

        # Week 2: Enhanced audit
        audit = AuditLogger()
        await audit.log_operation(
            operation_type="normalize_filenames",
            status="pending",
            details={"path": str(validated_folder), "changes": len(preview)},
            user_id=user_id,
            risk_level="low",
            paths=[str(validated_folder)]
        )

        return ToolResult(
            success=True,
            requires_confirmation=True,
            confirmation_message=f"Normalize {len(preview)} filenames?",
            data={
                "path": str(validated_folder),
                "changes": preview,
                "strategy": "normalize_names",
            },
        ).to_dict()

    except Exception as e:
        audit = AuditLogger()
        await audit.log_operation(
            operation_type="normalize_filenames",
            status="failed",
            details={"path": str(path)},
            user_id=user_id,
            risk_level="unknown",
            paths=[str(path)],
            error=str(e)
        )
        logger.error("normalize_preview_failed", extra={"error": str(e)})
        return ToolResult(success=False, error=str(e)).to_dict()


@function_tool()
async def flatten_folder_tool(
    context: RunContext,
    path: str,
) -> dict:
    """Flatten nested folder structure into one level"""
    user_id = getattr(context, 'user_id', 'default_user')
    
    try:
        folder = expand_user_path(path)

        # Week 2: Security validation
        try:
            validated_folder = path_validator.validate_path(
                folder,
                operation="modify",
                must_exist=True
            )
        except (PathSecurityError, ValidationError) as e:
            audit = AuditLogger()
            await audit.log_operation(
                operation_type="flatten_folder",
                status="blocked",
                details={"path": str(folder)},
                user_id=user_id,
                risk_level="blocked",
                paths=[str(folder)],
                error=str(e)
            )
            return ToolResult(success=False, error=f"Security: {str(e)}").to_dict()

        validate_path(validated_folder, must_exist=True)

        files = scan_folder(validated_folder, recursive=True)
        preview = [str(f.path) for f in files if f.path.parent != validated_folder]

        # Week 2: Enhanced audit
        audit = AuditLogger()
        await audit.log_operation(
            operation_type="flatten_folder",
            status="pending",
            details={"path": str(validated_folder), "file_count": len(preview)},
            user_id=user_id,
            risk_level="high",
            paths=[str(validated_folder)]
        )

        return ToolResult(
            success=True,
            requires_confirmation=True,
            confirmation_message=f"Flatten folder by moving {len(preview)} files?",
            data={
                "path": str(validated_folder),
                "file_count": len(preview),
                "strategy": "flatten",
            },
        ).to_dict()

    except Exception as e:
        audit = AuditLogger()
        await audit.log_operation(
            operation_type="flatten_folder",
            status="failed",
            details={"path": str(path)},
            user_id=user_id,
            risk_level="unknown",
            paths=[str(path)],
            error=str(e)
        )
        logger.error("flatten_preview_failed", extra={"error": str(e)})
        return ToolResult(success=False, error=str(e)).to_dict()


@function_tool()
async def clean_empty_folders_tool(
    context: RunContext,
    path: str,
) -> dict:
    """Remove empty folders"""
    user_id = getattr(context, 'user_id', 'default_user')
    
    try:
        folder = expand_user_path(path)

        # Week 2: Security validation
        try:
            validated_folder = path_validator.validate_path(
                folder,
                operation="delete",
                must_exist=True
            )
        except (PathSecurityError, ValidationError) as e:
            audit = AuditLogger()
            await audit.log_operation(
                operation_type="clean_empty_folders",
                status="blocked",
                details={"path": str(folder)},
                user_id=user_id,
                risk_level="blocked",
                paths=[str(folder)],
                error=str(e)
            )
            return ToolResult(success=False, error=f"Security: {str(e)}").to_dict()

        validate_path(validated_folder, must_exist=True)

        empty_folders = [
            str(p) for p in validated_folder.rglob("*")
            if p.is_dir() and not any(p.iterdir())
        ]

        # Week 2: Enhanced audit
        audit = AuditLogger()
        await audit.log_operation(
            operation_type="clean_empty_folders",
            status="pending",
            details={"path": str(validated_folder), "empty_count": len(empty_folders)},
            user_id=user_id,
            risk_level="low",
            paths=[str(validated_folder)]
        )

        return ToolResult(
            success=True,
            requires_confirmation=True,
            confirmation_message=f"Remove {len(empty_folders)} empty folders?",
            data={
                "path": str(validated_folder),
                "empty_folders": empty_folders,
                "strategy": "clean_empty",
            },
        ).to_dict()

    except Exception as e:
        audit = AuditLogger()
        await audit.log_operation(
            operation_type="clean_empty_folders",
            status="failed",
            details={"path": str(path)},
            user_id=user_id,
            risk_level="unknown",
            paths=[str(path)],
            error=str(e)
        )
        logger.error("clean_empty_preview_failed", extra={"error": str(e)})
        return ToolResult(success=False, error=str(e)).to_dict()