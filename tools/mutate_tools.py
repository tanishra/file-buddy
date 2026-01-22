import shutil
from pathlib import Path
from typing import List

from livekit.agents import function_tool, RunContext

from utils.logger import get_logger
from utils.path_utils import expand_user_path, validate_path, get_safe_destination
from core.snapshot import SnapshotManager
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
async def move_files_tool(
    context: RunContext,
    files: List[str],
    destination: str,
) -> dict:
    """Move files to destination"""
    user_id = getattr(context, 'user_id', 'default_user')
    
    try:
        dest_folder = expand_user_path(destination)
        file_paths = [expand_user_path(f) for f in files]

        # Week 2: Security validation
        try:
            validated_dest = path_validator.validate_path(
                dest_folder,
                operation="write",
                must_exist=False
            )
            validated_files = path_validator.validate_paths(
                file_paths,
                operation="modify",
                must_exist=True
            )
        except (PathSecurityError, ValidationError) as e:
            audit = AuditLogger()
            await audit.log_operation(
                operation_type="move_files",
                status="blocked",
                details={"file_count": len(files), "destination": str(dest_folder)},
                user_id=user_id,
                risk_level="blocked",
                paths=[str(f) for f in files] + [str(dest_folder)],
                error=str(e)
            )
            return ToolResult(success=False, error=f"Security: {str(e)}").to_dict()

        validate_path(validated_dest)
        validated_dest.mkdir(parents=True, exist_ok=True)

        # Safety check
        safety = SafetyChecker()
        safety.validate_operation("move", validated_files)

        # Week 2: Risk assessment & confirmation
        cm = ConfirmationManager()
        requires_conf, op_id, risk = await cm.request_confirmation(
            operation="move_files",
            paths=[str(p) for p in validated_files],
            user_id=user_id,
            destination=str(validated_dest),
            file_count=len(validated_files)
        )
        
        if requires_conf and op_id:
            message = cm.get_confirmation_message(op_id)
            return ToolResult(
                success=True,
                requires_confirmation=True,
                confirmation_message=message,
                data={"files": files, "destination": destination, "operation_id": op_id}
            ).to_dict()

        # Check if confirmation needed (legacy)
        if safety.requires_confirmation("move", validated_files):
            return ToolResult(
                success=True,
                requires_confirmation=True,
                confirmation_message=f"Move {len(files)} files to {destination}?",
                data={"files": files, "destination": destination},
            )

        # Create snapshot
        snapshot_mgr = SnapshotManager()
        file_states = {}

        # Move files
        moved = 0
        for file_path in validated_files:
            dest = get_safe_destination(file_path, validated_dest)
            file_states[str(dest)] = str(file_path)
            shutil.move(str(file_path), str(dest))
            moved += 1

        # Save snapshot
        snapshot = await snapshot_mgr.create_snapshot(
            operation_type="move",
            file_states=file_states,
            metadata={"destination": str(validated_dest)},
        )

        # Week 2: Enhanced audit log
        audit = AuditLogger()
        await audit.log_operation(
            operation_type="move_files",
            status="success",
            details={"count": moved, "destination": str(validated_dest)},
            snapshot_id=snapshot.snapshot_id,
            user_id=user_id,
            risk_level=risk.level.value if risk else "medium",
            paths=[str(p) for p in validated_files]
        )

        logger.info("files_moved", extra={"count": moved, "destination": str(validated_dest)})

        return ToolResult(
            success=True,
            data={"moved": moved},
            message=f"Moved {moved} files to {validated_dest.name}",
            snapshot_id=snapshot.snapshot_id,
        ).to_dict()

    except Exception as e:
        audit = AuditLogger()
        await audit.log_operation(
            operation_type="move_files",
            status="failed",
            details={"file_count": len(files)},
            user_id=user_id,
            risk_level="unknown",
            paths=[str(f) for f in files],
            error=str(e)
        )
        logger.error("move_failed", extra={"error": str(e)})
        return ToolResult(success=False, error=str(e)).to_dict()


@function_tool()
async def copy_files_tool(
    context: RunContext,
    files: List[str],
    destination: str,
) -> dict:
    """Copy files to destination"""
    user_id = getattr(context, 'user_id', 'default_user')
    
    try:
        dest_folder = expand_user_path(destination)
        file_paths = [expand_user_path(f) for f in files]

        # Week 2: Security validation
        try:
            validated_dest = path_validator.validate_path(
                dest_folder,
                operation="write",
                must_exist=False
            )
            validated_files = path_validator.validate_paths(
                file_paths,
                operation="read",
                must_exist=True
            )
        except (PathSecurityError, ValidationError) as e:
            audit = AuditLogger()
            await audit.log_operation(
                operation_type="copy_files",
                status="blocked",
                details={"file_count": len(files)},
                user_id=user_id,
                risk_level="blocked",
                paths=[str(f) for f in files],
                error=str(e)
            )
            return ToolResult(success=False, error=f"Security: {str(e)}").to_dict()

        validate_path(validated_dest)
        validated_dest.mkdir(parents=True, exist_ok=True)

        # Safety check
        safety = SafetyChecker()
        safety.validate_operation("copy", validated_files)

        # Copy files
        copied = 0
        for file_path in validated_files:
            dest = get_safe_destination(file_path, validated_dest)
            shutil.copy2(str(file_path), str(dest))
            copied += 1

        # Week 2: Enhanced audit log
        audit = AuditLogger()
        await audit.log_operation(
            operation_type="copy_files",
            status="success",
            details={"count": copied, "destination": str(validated_dest)},
            user_id=user_id,
            risk_level="low",
            paths=[str(p) for p in validated_files]
        )

        logger.info("files_copied", extra={"count": copied, "destination": str(validated_dest)})

        return ToolResult(
            success=True,
            data={"copied": copied},
            message=f"Copied {copied} files to {validated_dest.name}",
        ).to_dict()

    except Exception as e:
        audit = AuditLogger()
        await audit.log_operation(
            operation_type="copy_files",
            status="failed",
            details={"file_count": len(files)},
            user_id=user_id,
            risk_level="unknown",
            paths=[str(f) for f in files],
            error=str(e)
        )
        logger.error("copy_failed", extra={"error": str(e)})
        return ToolResult(success=False, error=str(e)).to_dict()


@function_tool()
async def rename_file_tool(
    context: RunContext,
    path: str,
    new_name: str,
) -> dict:
    """Rename a file or folder"""
    user_id = getattr(context, 'user_id', 'default_user')
    
    try:
        file_path = expand_user_path(path)

        # Week 2: Security validation
        try:
            validated_path = path_validator.validate_path(
                file_path,
                operation="modify",
                must_exist=True
            )
        except (PathSecurityError, ValidationError) as e:
            audit = AuditLogger()
            await audit.log_operation(
                operation_type="rename",
                status="blocked",
                details={"path": str(file_path)},
                user_id=user_id,
                risk_level="blocked",
                paths=[str(file_path)],
                error=str(e)
            )
            return ToolResult(success=False, error=f"Security: {str(e)}").to_dict()

        validate_path(validated_path, must_exist=True)

        new_path = validated_path.parent / new_name

        # Validate new path
        try:
            validated_new_path = path_validator.validate_path(
                new_path,
                operation="write",
                must_exist=False
            )
        except (PathSecurityError, ValidationError) as e:
            audit = AuditLogger()
            await audit.log_operation(
                operation_type="rename",
                status="blocked",
                details={"new_name": new_name},
                user_id=user_id,
                risk_level="blocked",
                paths=[str(new_path)],
                error=str(e)
            )
            return ToolResult(success=False, error=f"Security: {str(e)}").to_dict()

        # Create snapshot
        snapshot_mgr = SnapshotManager()
        snapshot = await snapshot_mgr.create_snapshot(
            operation_type="rename",
            file_states={str(validated_new_path): str(validated_path)},
        )

        # Rename
        validated_path.rename(validated_new_path)

        # Week 2: Enhanced audit log
        audit = AuditLogger()
        await audit.log_operation(
            operation_type="rename",
            status="success",
            details={"old": str(validated_path), "new": str(validated_new_path)},
            snapshot_id=snapshot.snapshot_id,
            user_id=user_id,
            risk_level="low",
            paths=[str(validated_path), str(validated_new_path)]
        )

        logger.info("file_renamed", extra={"old": str(validated_path), "new": str(validated_new_path)})

        return ToolResult(
            success=True,
            data={"new_path": str(validated_new_path)},
            message=f"Renamed to {new_name}",
            snapshot_id=snapshot.snapshot_id,
        ).to_dict()

    except Exception as e:
        audit = AuditLogger()
        await audit.log_operation(
            operation_type="rename",
            status="failed",
            details={"path": str(path)},
            user_id=user_id,
            risk_level="unknown",
            paths=[str(path)],
            error=str(e)
        )
        logger.error("rename_failed", extra={"error": str(e)})
        return ToolResult(success=False, error=str(e)).to_dict()


@function_tool()
async def batch_rename_tool(
    context: RunContext,
    paths: List[str],
    mode: str,
    value: str,
) -> dict:
    """Batch rename files or folders"""
    user_id = getattr(context, 'user_id', 'default_user')
    
    try:
        file_paths = [expand_user_path(p) for p in paths]

        # Week 2: Security validation
        try:
            validated_paths = path_validator.validate_paths(
                file_paths,
                operation="modify",
                must_exist=True
            )
        except (PathSecurityError, ValidationError) as e:
            audit = AuditLogger()
            await audit.log_operation(
                operation_type="batch_rename",
                status="blocked",
                details={"count": len(paths), "mode": mode},
                user_id=user_id,
                risk_level="blocked",
                paths=[str(p) for p in paths],
                error=str(e)
            )
            return ToolResult(success=False, error=f"Security: {str(e)}").to_dict()

        snapshot_mgr = SnapshotManager()
        file_states = {}
        renamed = []

        for p in validated_paths:
            validate_path(p, must_exist=True)

            if mode == "prefix":
                new_name = value + p.name
            elif mode == "suffix":
                stem, ext = p.stem, p.suffix
                new_name = f"{stem}{value}{ext}"
            elif mode == "replace":
                old, new = value.split(":", 1)
                new_name = p.name.replace(old, new)
            else:
                return ToolResult(
                    success=False,
                    error=f"Unsupported rename mode: {mode}",
                ).to_dict()

            new_path = p.parent / new_name
            
            # Validate new path
            try:
                validated_new = path_validator.validate_path(
                    new_path,
                    operation="write",
                    must_exist=False
                )
            except (PathSecurityError, ValidationError):
                logger.warning(f"Skipping rename due to security: {new_path}")
                continue
            
            file_states[str(validated_new)] = str(p)
            p.rename(validated_new)
            renamed.append(str(validated_new))

        snapshot = await snapshot_mgr.create_snapshot(
            operation_type="batch_rename",
            file_states=file_states,
        )

        # Week 2: Enhanced audit log
        audit = AuditLogger()
        await audit.log_operation(
            operation_type="batch_rename",
            status="success",
            details={"count": len(renamed), "mode": mode},
            snapshot_id=snapshot.snapshot_id,
            user_id=user_id,
            risk_level="medium",
            paths=renamed
        )

        return ToolResult(
            success=True,
            data={"renamed": renamed},
            message=f"Renamed {len(renamed)} items",
            snapshot_id=snapshot.snapshot_id,
        ).to_dict()

    except Exception as e:
        audit = AuditLogger()
        await audit.log_operation(
            operation_type="batch_rename",
            status="failed",
            details={"count": len(paths)},
            user_id=user_id,
            risk_level="unknown",
            paths=[str(p) for p in paths],
            error=str(e)
        )
        logger.error("batch_rename_failed", extra={"error": str(e)})
        return ToolResult(success=False, error=str(e)).to_dict()


@function_tool()
async def move_folder_contents_tool(
    context: RunContext,
    source: str,
    destination: str,
) -> dict:
    """Move all contents of one folder into another"""
    user_id = getattr(context, 'user_id', 'default_user')
    
    try:
        src = expand_user_path(source)
        dst = expand_user_path(destination)

        # Week 2: Security validation
        try:
            validated_src = path_validator.validate_path(
                src,
                operation="read",
                must_exist=True
            )
            validated_dst = path_validator.validate_path(
                dst,
                operation="write",
                must_exist=False
            )
        except (PathSecurityError, ValidationError) as e:
            audit = AuditLogger()
            await audit.log_operation(
                operation_type="move_folder_contents",
                status="blocked",
                details={"source": str(src), "destination": str(dst)},
                user_id=user_id,
                risk_level="blocked",
                paths=[str(src), str(dst)],
                error=str(e)
            )
            return ToolResult(success=False, error=f"Security: {str(e)}").to_dict()

        validate_path(validated_src, must_exist=True)
        validated_dst.mkdir(parents=True, exist_ok=True)

        snapshot_mgr = SnapshotManager()
        file_states = {}
        moved = 0

        for item in validated_src.iterdir():
            dest = get_safe_destination(item, validated_dst)
            file_states[str(dest)] = str(item)
            shutil.move(str(item), str(dest))
            moved += 1

        snapshot = await snapshot_mgr.create_snapshot(
            operation_type="move_folder_contents",
            file_states=file_states,
        )

        # Week 2: Enhanced audit log
        audit = AuditLogger()
        await audit.log_operation(
            operation_type="move_folder_contents",
            status="success",
            details={"count": moved, "source": str(validated_src), "destination": str(validated_dst)},
            snapshot_id=snapshot.snapshot_id,
            user_id=user_id,
            risk_level="high",
            paths=[str(validated_src), str(validated_dst)]
        )

        return ToolResult(
            success=True,
            data={"moved": moved},
            message=f"Moved {moved} items",
            snapshot_id=snapshot.snapshot_id,
        ).to_dict()

    except Exception as e:
        audit = AuditLogger()
        await audit.log_operation(
            operation_type="move_folder_contents",
            status="failed",
            details={"source": str(source), "destination": str(destination)},
            user_id=user_id,
            risk_level="unknown",
            paths=[str(source), str(destination)],
            error=str(e)
        )
        logger.error("move_folder_contents_failed", extra={"error": str(e)})
        return ToolResult(success=False, error=str(e)).to_dict()


@function_tool()
async def copy_folder_contents_tool(
    context: RunContext,
    source: str,
    destination: str,
) -> dict:
    """Copy all contents of one folder into another"""
    user_id = getattr(context, 'user_id', 'default_user')
    
    try:
        src = expand_user_path(source)
        dst = expand_user_path(destination)

        # Week 2: Security validation
        try:
            validated_src = path_validator.validate_path(
                src,
                operation="read",
                must_exist=True
            )
            validated_dst = path_validator.validate_path(
                dst,
                operation="write",
                must_exist=False
            )
        except (PathSecurityError, ValidationError) as e:
            audit = AuditLogger()
            await audit.log_operation(
                operation_type="copy_folder_contents",
                status="blocked",
                details={"source": str(src), "destination": str(dst)},
                user_id=user_id,
                risk_level="blocked",
                paths=[str(src), str(dst)],
                error=str(e)
            )
            return ToolResult(success=False, error=f"Security: {str(e)}").to_dict()

        validate_path(validated_src, must_exist=True)
        validated_dst.mkdir(parents=True, exist_ok=True)

        copied = 0

        for item in validated_src.iterdir():
            dest = get_safe_destination(item, validated_dst)
            if item.is_dir():
                shutil.copytree(item, dest)
            else:
                shutil.copy2(item, dest)
            copied += 1

        # Week 2: Enhanced audit log
        audit = AuditLogger()
        await audit.log_operation(
            operation_type="copy_folder_contents",
            status="success",
            details={"count": copied, "source": str(validated_src), "destination": str(validated_dst)},
            user_id=user_id,
            risk_level="low",
            paths=[str(validated_src), str(validated_dst)]
        )

        return ToolResult(
            success=True,
            data={"copied": copied},
            message=f"Copied {copied} items",
        ).to_dict()

    except Exception as e:
        audit = AuditLogger()
        await audit.log_operation(
            operation_type="copy_folder_contents",
            status="failed",
            details={"source": str(source), "destination": str(destination)},
            user_id=user_id,
            risk_level="unknown",
            paths=[str(source), str(destination)],
            error=str(e)
        )
        logger.error("copy_folder_contents_failed", extra={"error": str(e)})
        return ToolResult(success=False, error=str(e)).to_dict()


@function_tool()
async def bulk_change_extension_tool(
    context: RunContext,
    path: str,
    old_ext: str,
    new_ext: str,
) -> dict:
    """Change file extensions in bulk within a folder"""
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
                operation_type="bulk_extension_change",
                status="blocked",
                details={"path": str(folder)},
                user_id=user_id,
                risk_level="blocked",
                paths=[str(folder)],
                error=str(e)
            )
            return ToolResult(success=False, error=f"Security: {str(e)}").to_dict()

        validate_path(validated_folder, must_exist=True)

        snapshot_mgr = SnapshotManager()
        file_states = {}
        changed = 0

        for file in validated_folder.iterdir():
            if file.is_file() and file.suffix == old_ext:
                new_path = file.with_suffix(new_ext)
                file_states[str(new_path)] = str(file)
                file.rename(new_path)
                changed += 1

        snapshot = await snapshot_mgr.create_snapshot(
            operation_type="bulk_extension_change",
            file_states=file_states,
        )

        # Week 2: Enhanced audit log
        audit = AuditLogger()
        await audit.log_operation(
            operation_type="bulk_extension_change",
            status="success",
            details={"count": changed, "old_ext": old_ext, "new_ext": new_ext},
            snapshot_id=snapshot.snapshot_id,
            user_id=user_id,
            risk_level="medium",
            paths=[str(validated_folder)]
        )

        return ToolResult(
            success=True,
            data={"changed": changed},
            message=f"Changed extension for {changed} files",
            snapshot_id=snapshot.snapshot_id,
        ).to_dict()

    except Exception as e:
        audit = AuditLogger()
        await audit.log_operation(
            operation_type="bulk_extension_change",
            status="failed",
            details={"path": str(path)},
            user_id=user_id,
            risk_level="unknown",
            paths=[str(path)],
            error=str(e)
        )
        logger.error("bulk_extension_change_failed", extra={"error": str(e)})
        return ToolResult(success=False, error=str(e)).to_dict()