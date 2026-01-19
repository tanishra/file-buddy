from pathlib import Path
from typing import Dict, Any

from livekit.agents import function_tool, RunContext

from utils.logger import get_logger
from utils.path_utils import expand_user_path, validate_path
from utils.file_utils import scan_folder, categorize_file, FileInfo
from models.tool_results import ToolResult

logger = get_logger(__name__)


@function_tool()
async def scan_folder_tool(
    context: RunContext,
    path: str,
    recursive: bool = False,
) -> dict:
    """Scan folder and return file information"""
    try:
        folder = expand_user_path(path)
        validate_path(folder, must_exist=True)

        files = scan_folder(folder, recursive)

        # Group by category
        categories = {}
        for f in files:
            cat = f.category
            if cat not in categories:
                categories[cat] = []
            categories[cat].append({
                "name": f.path.name,
                "size": f.size_human,
                "sensitive": f.is_sensitive,
            })

        logger.info(
            "scan_complete",
            folder=str(folder),
            file_count=len(files),
        )

        return ToolResult(
            success=True,
            data={
                "total_files": len(files),
                "total_size": sum(f.size_bytes for f in files),
                "categories": {k: len(v) for k, v in categories.items()},
                "files_by_category": categories,
            },
            message=f"Found {len(files)} files in {len(categories)} categories",
        ).to_dict()

    except Exception as e:
        logger.error("scan_failed", error=str(e))
        return ToolResult(success=False, error=str(e)).to_dict()


@function_tool()
async def search_files_tool(
    context: RunContext,
    path: str,
    pattern: str | None = None,
    file_type: str | None = None,
) -> dict:
    """Search for files"""
    try:
        folder = expand_user_path(path)
        validate_path(folder, must_exist=True)

        files = scan_folder(folder, recursive=True)

        # Filter by pattern
        if pattern:
            import fnmatch
            files = [
                f for f in files
                if fnmatch.fnmatch(f.path.name.lower(), pattern.lower())
            ]

        # Filter by type
        if file_type:
            files = [f for f in files if f.category == file_type]

        results = [
            {
                "path": str(f.path),
                "size": f.size_human,
                "category": f.category,
            }
            for f in files
        ]

        logger.info(
            "search_complete",
            pattern=pattern,
            results=len(results),
        )

        return ToolResult(
            success=True,
            data={
                "files": results,
                "count": len(results),
            },
            message=f"Found {len(results)} matching files",
        ).to_dict()

    except Exception as e:
        logger.error("search_failed", error=str(e))
        return ToolResult(success=False, error=str(e)).to_dict()


@function_tool()
async def get_file_info_tool(
    context: RunContext,
    path: str,
) -> dict:
    """Get detailed file information"""
    try:
        file_path = expand_user_path(path)
        validate_path(file_path, must_exist=True)

        stat = file_path.stat()

        info = {
            "name": file_path.name,
            "size_bytes": stat.st_size,
            "size_human": FileInfo(
                file_path,
                stat.st_size,
                "",
                False,
                0,
            ).size_human,
            "category": categorize_file(file_path),
            "extension": file_path.suffix,
            "modified": stat.st_mtime,
            "is_file": file_path.is_file(),
            "is_dir": file_path.is_dir(),
        }

        logger.info("file_info_retrieved", path=str(file_path))

        return ToolResult(success=True, data=info).to_dict()

    except Exception as e:
        logger.error("file_info_failed", error=str(e))
        return ToolResult(success=False, error=str(e)).to_dict()

MAX_READ_SIZE = 1024 * 10000  # 10MB safety limit


@function_tool()
async def read_file_content_tool(
    context: RunContext,
    path: str,
    max_lines: int = 200,
) -> dict:
    """Read text file content safely (size + line limited)"""
    try:
        file_path = expand_user_path(path)
        validate_path(file_path, must_exist=True)

        if file_path.stat().st_size > MAX_READ_SIZE:
            return ToolResult(
                success=False,
                error="File too large to read safely",
            ).to_dict()

        try:
            lines = file_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except Exception:
            return ToolResult(
                success=False,
                error="File is not readable as text",
            ).to_dict()

        preview = lines[:max_lines]

        logger.info("file_read", path=str(file_path), lines=len(preview))

        return ToolResult(
            success=True,
            data={
                "path": str(file_path),
                "total_lines": len(lines),
                "preview_lines": len(preview),
                "content": preview,
            },
            message=f"Read {len(preview)} lines from file",
        ).to_dict()

    except Exception as e:
        logger.error("file_read_failed", error=str(e))
        return ToolResult(success=False, error=str(e)).to_dict()


@function_tool()
async def preview_file_tool(
    context: RunContext,
    path: str,
    mode: str = "head",
    lines: int = 50,
) -> dict:
    """Preview first or last N lines of a file"""
    try:
        file_path = expand_user_path(path)
        validate_path(file_path, must_exist=True)

        content = file_path.read_text(encoding="utf-8", errors="ignore").splitlines()

        if mode == "tail":
            preview = content[-lines:]
        else:
            preview = content[:lines]

        return ToolResult(
            success=True,
            data={
                "path": str(file_path),
                "mode": mode,
                "lines": len(preview),
                "content": preview,
            },
            message=f"Showing {mode} {len(preview)} lines",
        ).to_dict()

    except Exception as e:
        logger.error("file_preview_failed", error=str(e))
        return ToolResult(success=False, error=str(e)).to_dict()


@function_tool()
async def read_folder_tree_tool(
    context: RunContext,
    path: str,
    depth: int = 3,
) -> dict:
    """Read folder structure (tree view, no file content)"""
    try:
        root = expand_user_path(path)
        validate_path(root, must_exist=True)

        tree = []

        def walk(current: Path, level: int):
            if level > depth:
                return
            for item in sorted(current.iterdir()):
                tree.append({
                    "path": str(item),
                    "type": "dir" if item.is_dir() else "file",
                    "level": level,
                })
                if item.is_dir():
                    walk(item, level + 1)

        walk(root, 0)

        return ToolResult(
            success=True,
            data={"tree": tree},
            message=f"Read folder tree up to depth {depth}",
        ).to_dict()

    except Exception as e:
        logger.error("folder_tree_failed", error=str(e))
        return ToolResult(success=False, error=str(e)).to_dict()


@function_tool()
async def search_file_contents_tool(
    context: RunContext,
    path: str,
    query: str,
    case_sensitive: bool = False,
) -> dict:
    """Search text inside files (grep-style)"""
    try:
        root = expand_user_path(path)
        validate_path(root, must_exist=True)

        matches = []

        for file in root.rglob("*"):
            if not file.is_file():
                continue

            if file.stat().st_size > MAX_READ_SIZE:
                continue

            try:
                text = file.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            haystack = text if case_sensitive else text.lower()
            needle = query if case_sensitive else query.lower()

            if needle in haystack:
                matches.append(str(file))

        return ToolResult(
            success=True,
            data={"query": query, "matches": matches, "count": len(matches)},
            message=f"Found matches in {len(matches)} files",
        ).to_dict()

    except Exception as e:
        logger.error("content_search_failed", error=str(e))
        return ToolResult(success=False, error=str(e)).to_dict()


@function_tool()
async def detect_project_type_tool(
    context: RunContext,
    path: str,
) -> dict:
    """Detect project type from folder contents (read-only)"""
    try:
        root = expand_user_path(path)
        validate_path(root, must_exist=True)

        files = {f.name.lower() for f in root.iterdir() if f.is_file()}

        project_type = "unknown"

        if "package.json" in files and "next.config.js" in files:
            project_type = "nextjs"
        elif "package.json" in files:
            project_type = "nodejs"
        elif "requirements.txt" in files or "pyproject.toml" in files:
            project_type = "python"
        elif "environment.yml" in files:
            project_type = "conda_ml"
        elif "dockerfile" in files:
            project_type = "dockerized_app"

        return ToolResult(
            success=True,
            data={"path": str(root), "project_type": project_type},
            message=f"Detected project type: {project_type}",
        ).to_dict()

    except Exception as e:
        logger.error("project_detection_failed", error=str(e))
        return ToolResult(success=False, error=str(e)).to_dict()