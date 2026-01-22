import shutil
from pathlib import Path
from typing import List

from livekit.agents import function_tool, RunContext

from utils.logger import get_logger
from utils.path_utils import expand_user_path, validate_path, get_safe_destination
from core.snapshot import SnapshotManager
from core.audit_logger import AuditLogger
from core.safety import SafetyChecker
from models.tool_results import ToolResult

logger = get_logger(__name__)


@function_tool()
async def move_files_tool(
    context: RunContext,
    files: List[str],
    destination: str,
) -> dict:
    """Move files to destination"""
    try:
        dest_folder = expand_user_path(destination)
        validate_path(dest_folder)
        dest_folder.mkdir(parents=True, exist_ok=True)

        file_paths = [expand_user_path(f) for f in files]

        # Safety check
        safety = SafetyChecker()
        safety.validate_operation("move", file_paths)

        # Check if confirmation needed
        if safety.requires_confirmation("move", file_paths):
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
        for file_path in file_paths:
            dest = get_safe_destination(file_path, dest_folder)
            file_states[str(dest)] = str(file_path)
            shutil.move(str(file_path), str(dest))
            moved += 1

        # Save snapshot
        snapshot = await snapshot_mgr.create_snapshot(
            operation_type="move",
            file_states=file_states,
            metadata={"destination": str(dest_folder)},
        )

        # Audit log
        audit = AuditLogger()
        await audit.log_operation(
            operation_type="move_files",
            status="success",
            details={"count": moved, "destination": str(dest_folder)},
            snapshot_id=snapshot.snapshot_id,
        )

        logger.info("files_moved", count=moved, destination=str(dest_folder))

        return ToolResult(
            success=True,
            data={"moved": moved},
            message=f"Moved {moved} files to {dest_folder.name}",
            snapshot_id=snapshot.snapshot_id,
        ).to_dict()

    except Exception as e:
        logger.error("move_failed", error=str(e))
        return ToolResult(success=False, error=str(e)).to_dict()


@function_tool()
async def copy_files_tool(
    context: RunContext,
    files: List[str],
    destination: str,
) -> dict:
    """Copy files to destination"""
    try:
        dest_folder = expand_user_path(destination)
        validate_path(dest_folder)
        dest_folder.mkdir(parents=True, exist_ok=True)

        file_paths = [expand_user_path(f) for f in files]

        # Safety check
        safety = SafetyChecker()
        safety.validate_operation("copy", file_paths)

        # Copy files
        copied = 0
        for file_path in file_paths:
            dest = get_safe_destination(file_path, dest_folder)
            shutil.copy2(str(file_path), str(dest))
            copied += 1

        # Audit log
        audit = AuditLogger()
        await audit.log_operation(
            operation_type="copy_files",
            status="success",
            details={"count": copied, "destination": str(dest_folder)},
        )

        logger.info("files_copied", count=copied, destination=str(dest_folder))

        return ToolResult(
            success=True,
            data={"copied": copied},
            message=f"Copied {copied} files to {dest_folder.name}",
        ).to_dict()

    except Exception as e:
        logger.error("copy_failed", error=str(e))
        return ToolResult(success=False, error=str(e)).to_dict()


@function_tool()
async def rename_file_tool(
    context: RunContext,
    path: str,
    new_name: str,
) -> dict:
    """Rename a file or folder"""
    try:
        file_path = expand_user_path(path)
        validate_path(file_path, must_exist=True)

        new_path = file_path.parent / new_name

        # Create snapshot
        snapshot_mgr = SnapshotManager()
        snapshot = await snapshot_mgr.create_snapshot(
            operation_type="rename",
            file_states={str(new_path): str(file_path)},
        )

        # Rename
        file_path.rename(new_path)

        # Audit log
        audit = AuditLogger()
        await audit.log_operation(
            operation_type="rename",
            status="success",
            details={"old": str(file_path), "new": str(new_path)},
            snapshot_id=snapshot.snapshot_id,
        )

        logger.info("file_renamed", old=str(file_path), new=str(new_path))

        return ToolResult(
            success=True,
            data={"new_path": str(new_path)},
            message=f"Renamed to {new_name}",
            snapshot_id=snapshot.snapshot_id,
        ).to_dict()

    except Exception as e:
        logger.error("rename_failed", error=str(e))
        return ToolResult(success=False, error=str(e)).to_dict()
    
@function_tool()
async def batch_rename_tool(
    context: RunContext,
    paths: List[str],
    mode: str,
    value: str,
) -> dict:
    """
    Batch rename files or folders.

    mode:
    - prefix
    - suffix
    - replace (value = "old:new")
    """
    try:
        file_paths = [expand_user_path(p) for p in paths]

        snapshot_mgr = SnapshotManager()
        file_states = {}
        renamed = []

        for p in file_paths:
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
            file_states[str(new_path)] = str(p)
            p.rename(new_path)
            renamed.append(str(new_path))

        snapshot = await snapshot_mgr.create_snapshot(
            operation_type="batch_rename",
            file_states=file_states,
        )

        audit = AuditLogger()
        await audit.log_operation(
            operation_type="batch_rename",
            status="success",
            details={"count": len(renamed)},
            snapshot_id=snapshot.snapshot_id,
        )

        return ToolResult(
            success=True,
            data={"renamed": renamed},
            message=f"Renamed {len(renamed)} items",
            snapshot_id=snapshot.snapshot_id,
        ).to_dict()

    except Exception as e:
        logger.error("batch_rename_failed", error=str(e))
        return ToolResult(success=False, error=str(e)).to_dict()


@function_tool()
async def move_folder_contents_tool(
    context: RunContext,
    source: str,
    destination: str,
) -> dict:
    """Move all contents of one folder into another"""
    try:
        src = expand_user_path(source)
        dst = expand_user_path(destination)

        validate_path(src, must_exist=True)
        dst.mkdir(parents=True, exist_ok=True)

        snapshot_mgr = SnapshotManager()
        file_states = {}
        moved = 0

        for item in src.iterdir():
            dest = get_safe_destination(item, dst)
            file_states[str(dest)] = str(item)
            shutil.move(str(item), str(dest))
            moved += 1

        snapshot = await snapshot_mgr.create_snapshot(
            operation_type="move_folder_contents",
            file_states=file_states,
        )

        audit = AuditLogger()
        await audit.log_operation(
            operation_type="move_folder_contents",
            status="success",
            details={"count": moved},
            snapshot_id=snapshot.snapshot_id,
        )

        return ToolResult(
            success=True,
            data={"moved": moved},
            message=f"Moved {moved} items",
            snapshot_id=snapshot.snapshot_id,
        ).to_dict()

    except Exception as e:
        logger.error("move_folder_contents_failed", error=str(e))
        return ToolResult(success=False, error=str(e)).to_dict()


@function_tool()
async def copy_folder_contents_tool(
    context: RunContext,
    source: str,
    destination: str,
) -> dict:
    """Copy all contents of one folder into another"""
    try:
        src = expand_user_path(source)
        dst = expand_user_path(destination)

        validate_path(src, must_exist=True)
        dst.mkdir(parents=True, exist_ok=True)

        copied = 0

        for item in src.iterdir():
            dest = get_safe_destination(item, dst)
            if item.is_dir():
                shutil.copytree(item, dest)
            else:
                shutil.copy2(item, dest)
            copied += 1

        audit = AuditLogger()
        await audit.log_operation(
            operation_type="copy_folder_contents",
            status="success",
            details={"count": copied},
        )

        return ToolResult(
            success=True,
            data={"copied": copied},
            message=f"Copied {copied} items",
        ).to_dict()

    except Exception as e:
        logger.error("copy_folder_contents_failed", error=str(e))
        return ToolResult(success=False, error=str(e)).to_dict()


@function_tool()
async def bulk_change_extension_tool(
    context: RunContext,
    path: str,
    old_ext: str,
    new_ext: str,
) -> dict:
    """Change file extensions in bulk within a folder"""
    try:
        folder = expand_user_path(path)
        validate_path(folder, must_exist=True)

        snapshot_mgr = SnapshotManager()
        file_states = {}
        changed = 0

        for file in folder.iterdir():
            if file.is_file() and file.suffix == old_ext:
                new_path = file.with_suffix(new_ext)
                file_states[str(new_path)] = str(file)
                file.rename(new_path)
                changed += 1

        snapshot = await snapshot_mgr.create_snapshot(
            operation_type="bulk_extension_change",
            file_states=file_states,
        )

        audit = AuditLogger()
        await audit.log_operation(
            operation_type="bulk_extension_change",
            status="success",
            details={"count": changed},
            snapshot_id=snapshot.snapshot_id,
        )

        return ToolResult(
            success=True,
            data={"changed": changed},
            message=f"Changed extension for {changed} files",
            snapshot_id=snapshot.snapshot_id,
        ).to_dict()

    except Exception as e:
        logger.error("bulk_extension_change_failed", error=str(e))
        return ToolResult(success=False, error=str(e)).to_dict()