import send2trash
from pathlib import Path
from typing import List

from livekit.agents import function_tool, RunContext

from utils.logger import get_logger
from utils.path_utils import expand_user_path, validate_path
from core.audit import AuditLogger
from core.safety import SafetyChecker
from models.tool_results import ToolResult

logger = get_logger(__name__)


@function_tool()
async def delete_files_tool(
    context: RunContext,
    files: List[str],
) -> dict:
    """Delete files (move to trash)"""
    try:
        file_paths = [expand_user_path(f) for f in files]

        # Safety check
        safety = SafetyChecker()
        safety.validate_operation("delete", file_paths)

        # ALWAYS require confirmation for delete
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
        logger.error("delete_validation_failed", error=str(e))
        return ToolResult(success=False, error=str(e)).to_dict()


@function_tool()
async def execute_delete(
    context: RunContext,
    files: List[str],
) -> dict:
    """Execute delete (after confirmation)"""
    try:
        file_paths = [expand_user_path(f) for f in files]

        deleted = 0
        for file_path in file_paths:
            send2trash.send2trash(str(file_path))
            deleted += 1

        # Audit log
        audit = AuditLogger()
        await audit.log_operation(
            operation_type="delete_files",
            status="success",
            details={"count": deleted, "files": [str(f) for f in file_paths]},
        )

        logger.info("files_deleted", count=deleted)

        return ToolResult(
            success=True,
            data={"deleted": deleted},
            message=f"Deleted {deleted} files (moved to trash)",
        ).to_dict()
    except Exception as e:
        logger.error("delete_failed", error=str(e))
        return ToolResult(success=False, error=str(e)).to_dict()


@function_tool()
async def delete_folder_tool(
    context: RunContext,
    path: str,
) -> dict:
    """Delete entire folder"""
    try:
        folder = expand_user_path(path)
        validate_path(folder, must_exist=True)

        # Count files
        import os

        file_count = sum(1 for _ in folder.rglob("*") if _.is_file())

        return ToolResult(
            success=True,
            requires_confirmation=True,
            confirmation_message=(
                f"⚠️  This will delete folder '{folder.name}' with {file_count} files. "
                f"Say 'confirm delete' to proceed."
            ),
            data={"path": str(folder), "file_count": file_count},
        ).to_dict()
    except Exception as e:
        logger.error("delete_folder_validation_failed", error=str(e))
        return ToolResult(success=False, error=str(e)).to_dict()

@function_tool()
async def delete_multiple_folders_tool(
    context: RunContext,
    paths: List[str],
) -> dict:
    """Delete multiple folders (confirmation required)"""
    try:
        folders = [expand_user_path(p) for p in paths]

        safety = SafetyChecker()
        safety.validate_operation("delete", folders)

        counts = {}
        for folder in folders:
            validate_path(folder, must_exist=True)
            counts[str(folder)] = sum(
                1 for _ in folder.rglob("*") if _.is_file()
            )

        return ToolResult(
            success=True,
            requires_confirmation=True,
            confirmation_message=(
                f"⚠️  This will delete {len(folders)} folders. "
                f"Say 'confirm delete' to proceed."
            ),
            data={"folders": counts},
        ).to_dict()

    except Exception as e:
        logger.error("delete_multiple_folders_failed", error=str(e))
        return ToolResult(success=False, error=str(e)).to_dict()


@function_tool()
async def delete_mixed_items_tool(
    context: RunContext,
    paths: List[str],
) -> dict:
    """Delete mixed files and folders"""
    try:
        items = [expand_user_path(p) for p in paths]

        safety = SafetyChecker()
        safety.validate_operation("delete", items)

        preview = []
        for p in items:
            if p.is_file():
                preview.append({"path": str(p), "type": "file"})
            elif p.is_dir():
                preview.append({
                    "path": str(p),
                    "type": "folder",
                    "files": sum(1 for _ in p.rglob("*") if _.is_file()),
                })

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
        logger.error("delete_mixed_failed", error=str(e))
        return ToolResult(success=False, error=str(e)).to_dict()


@function_tool()
async def conditional_delete_preview_tool(
    context: RunContext,
    path: str,
    extension: str | None = None,
    older_than_days: int | None = None,
) -> dict:
    """Preview conditional delete (no execution)"""
    try:
        from datetime import datetime, timedelta

        folder = expand_user_path(path)
        validate_path(folder, must_exist=True)

        cutoff = None
        if older_than_days:
            cutoff = datetime.now().timestamp() - (older_than_days * 86400)

        matched = []
        for f in folder.rglob("*"):
            if not f.is_file():
                continue
            if extension and f.suffix != extension:
                continue
            if cutoff and f.stat().st_mtime > cutoff:
                continue
            matched.append(str(f))

        return ToolResult(
            success=True,
            requires_confirmation=True,
            confirmation_message=(
                f"⚠️  This will delete {len(matched)} files. "
                f"Say 'confirm delete' to proceed."
            ),
            data={
                "path": str(folder),
                "matched_files": matched,
                "criteria": {
                    "extension": extension,
                    "older_than_days": older_than_days,
                },
            },
        ).to_dict()

    except Exception as e:
        logger.error("conditional_delete_preview_failed", error=str(e))
        return ToolResult(success=False, error=str(e)).to_dict()


@function_tool()
async def undo_last_delete_tool(
    context: RunContext,
) -> dict:
    """Undo last delete by restoring from trash"""
    try:
        # NOTE: send2trash relies on OS trash; restore is platform dependent
        # This tool assumes SnapshotManager or OS-level undo integration later

        return ToolResult(
            success=False,
            error=(
                "Undo delete is supported only if OS trash restore "
                "is available. Manual restore may be required."
            ),
        ).to_dict()

    except Exception as e:
        logger.error("undo_delete_failed", error=str(e))
        return ToolResult(success=False, error=str(e)).to_dict()