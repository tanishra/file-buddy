import shutil
from pathlib import Path

from livekit.agents import function_tool, RunContext

from utils.logger import get_logger
from utils.path_utils import expand_user_path, validate_path, get_safe_destination
from utils.file_utils import scan_folder, group_by_category
from config.greetings import get_confirmation_message, get_success_message
from core.snapshot import SnapshotManager
from core.audit import AuditLogger
from models.tool_results import ToolResult

logger = get_logger(__name__)


@function_tool()
async def organize_folder_tool(
    context: RunContext,
    path: str,
    strategy: str = "by_file_type",
) -> dict:
    """Organize folder by strategy"""
    try:
        folder = expand_user_path(path)
        validate_path(folder, must_exist=True)

        # Scan folder
        files = scan_folder(folder, recursive=False)

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
            return ToolResult(success=False, error=f"Unknown strategy: {strategy}",confirmation_message=(
                f"Organize {len(files)} files into {len(groups)} folders "
                f"using strategy '{strategy}'?"
            ))

        # Confirmation required
        return ToolResult(
            success=True,
            requires_confirmation=True,
            confirmation_message=(
                f"Organize {len(files)} files into {len(groups)} folders "
                f"using strategy '{strategy}'?"
            ),
            data={
                "path": str(folder),
                "strategy": strategy,
                "file_count": len(files),
                "folder_count": len(groups),
                "groups": {k: len(v) for k, v in groups.items()},
            },
        ).to_dict()

    except Exception as e:
        logger.error("organize_failed", error=str(e))
        return ToolResult(success=False, error=str(e)).to_dict()


@function_tool()
async def execute_organize(
    context: RunContext,
    path: str,
    strategy: str,
) -> dict:
    """Execute organization (after confirmation)"""
    try:
        folder = expand_user_path(path)
        files = scan_folder(folder, recursive=False)

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

        # Create snapshot
        snapshot_mgr = SnapshotManager()
        file_states = {}
        folders_created = []

        # Move files
        moved = 0
        for group_name, group_files in groups.items():
            group_folder = folder / group_name
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

        # Audit log
        audit = AuditLogger()
        await audit.log_operation(
            operation_type="organize_folder",
            status="success",
            details={"path": str(folder), "strategy": strategy, "moved": moved},
            snapshot_id=snapshot.snapshot_id,
        )

        logger.info("folder_organized", path=str(folder), moved=moved)

        return ToolResult(
            success=True,
            data={"moved": moved, "folders": len(groups)},
            message=f"Organized {moved} files into {len(groups)} folders",
            snapshot_id=snapshot.snapshot_id,
        ).to_dict()

    except Exception as e:
        logger.error("organize_execution_failed", error=str(e))
        return ToolResult(success=False, error=str(e)).to_dict()

@function_tool()
async def organize_by_size_tool(
    context: RunContext,
    path: str,
) -> dict:
    """Organize files into Small / Medium / Large folders"""
    try:
        folder = expand_user_path(path)
        validate_path(folder, must_exist=True)

        files = scan_folder(folder, recursive=False)

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

        return ToolResult(
            success=True,
            requires_confirmation=True,
            confirmation_message=f"Organize {len(files)} files by size?",
            data={
                "path": str(folder),
                "groups": {k: len(v) for k, v in groups.items()},
                "strategy": "by_size",
            },
        ).to_dict()

    except Exception as e:
        logger.error("organize_by_size_failed", error=str(e))
        return ToolResult(success=False, error=str(e)).to_dict()


@function_tool()
async def organize_by_extension_tool(
    context: RunContext,
    path: str,
) -> dict:
    """Organize files by file extension"""
    try:
        folder = expand_user_path(path)
        validate_path(folder, must_exist=True)

        files = scan_folder(folder, recursive=False)
        groups = {}

        for f in files:
            ext = f.path.suffix.lower().lstrip(".") or "no_extension"
            groups.setdefault(ext, []).append(f)

        return ToolResult(
            success=True,
            requires_confirmation=True,
            confirmation_message=f"Organize {len(files)} files by extension?",
            data={
                "path": str(folder),
                "strategy": "by_extension",
                "groups": {k: len(v) for k, v in groups.items()},
            },
        ).to_dict()

    except Exception as e:
        logger.error("organize_by_extension_failed", error=str(e))
        return ToolResult(success=False, error=str(e)).to_dict()


@function_tool()
async def normalize_filenames_tool(
    context: RunContext,
    path: str,
) -> dict:
    """Normalize filenames (lowercase, underscores, safe chars)"""
    try:
        folder = expand_user_path(path)
        validate_path(folder, must_exist=True)

        files = scan_folder(folder, recursive=False)

        preview = {}
        for f in files:
            new_name = (
                f.path.name.lower()
                .replace(" ", "_")
                .replace("-", "_")
            )
            if new_name != f.path.name:
                preview[f.path.name] = new_name

        return ToolResult(
            success=True,
            requires_confirmation=True,
            confirmation_message=f"Normalize {len(preview)} filenames?",
            data={
                "path": str(folder),
                "changes": preview,
                "strategy": "normalize_names",
            },
        ).to_dict()

    except Exception as e:
        logger.error("normalize_preview_failed", error=str(e))
        return ToolResult(success=False, error=str(e)).to_dict()


@function_tool()
async def flatten_folder_tool(
    context: RunContext,
    path: str,
) -> dict:
    """Flatten nested folder structure into one level"""
    try:
        folder = expand_user_path(path)
        validate_path(folder, must_exist=True)

        files = scan_folder(folder, recursive=True)
        preview = [str(f.path) for f in files if f.path.parent != folder]

        return ToolResult(
            success=True,
            requires_confirmation=True,
            confirmation_message=f"Flatten folder by moving {len(preview)} files?",
            data={
                "path": str(folder),
                "file_count": len(preview),
                "strategy": "flatten",
            },
        ).to_dict()

    except Exception as e:
        logger.error("flatten_preview_failed", error=str(e))
        return ToolResult(success=False, error=str(e)).to_dict()


@function_tool()
async def clean_empty_folders_tool(
    context: RunContext,
    path: str,
) -> dict:
    """Remove empty folders"""
    try:
        folder = expand_user_path(path)
        validate_path(folder, must_exist=True)

        empty_folders = [
            str(p) for p in folder.rglob("*")
            if p.is_dir() and not any(p.iterdir())
        ]

        return ToolResult(
            success=True,
            requires_confirmation=True,
            confirmation_message=f"Remove {len(empty_folders)} empty folders?",
            data={
                "path": str(folder),
                "empty_folders": empty_folders,
                "strategy": "clean_empty",
            },
        ).to_dict()

    except Exception as e:
        logger.error("clean_empty_preview_failed", error=str(e))
        return ToolResult(success=False, error=str(e)).to_dict()