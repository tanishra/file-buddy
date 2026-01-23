from pathlib import Path
from typing import Dict, Any

from livekit.agents import function_tool, RunContext

from utils.logger import get_logger
from utils.path_utils import expand_user_path, validate_path
from utils.file_utils import scan_folder, categorize_file, FileInfo
from models.tool_results import ToolResult

from core.security import path_validator
from core.audit import AuditLogger
from core.exceptions import PathSecurityError, ValidationError

logger = get_logger(__name__)

MAX_READ_SIZE = 1024 * 10000  # 10MB safety limit


@function_tool()
async def scan_folder_tool(
    context: RunContext,
    path: str,
    recursive: bool = False,
) -> dict:
    """Scan folder and return file information"""
    user_id = getattr(context, 'user_id', 'default_user')
    
    try:
        folder = expand_user_path(path)

        # Week 2: Security validation
        try:
            validated_folder = path_validator.validate_path(
                folder,
                operation="read",
                must_exist=True
            )
        except (PathSecurityError, ValidationError) as e:
            audit = AuditLogger()
            await audit.log_operation(
                operation_type="scan_folder",
                status="blocked",
                details={"path": str(folder)},
                user_id=user_id,
                risk_level="blocked",
                paths=[str(folder)],
                error=str(e)
            )
            return ToolResult(success=False, error=f"Security: {str(e)}").to_dict()

        validate_path(validated_folder, must_exist=True)

        files = scan_folder(validated_folder, recursive)

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

        # Week 2: Enhanced audit log
        audit = AuditLogger()
        await audit.log_operation(
            operation_type="scan_folder",
            status="success",
            details={"file_count": len(files), "recursive": recursive},
            user_id=user_id,
            risk_level="safe",
            paths=[str(validated_folder)]
        )

        logger.info(
            "scan_complete",
            extra={
                "folder": str(validated_folder),
                "file_count": len(files)
            }
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
        audit = AuditLogger()
        await audit.log_operation(
            operation_type="scan_folder",
            status="failed",
            details={"path": str(path)},
            user_id=user_id,
            risk_level="unknown",
            paths=[str(path)],
            error=str(e)
        )
        logger.error("scan_failed", extra={"error": str(e)})
        return ToolResult(success=False, error=str(e)).to_dict()


@function_tool()
async def search_files_tool(
    context: RunContext,
    path: str,
    pattern: str | None = None,
    file_type: str | None = None,
) -> dict:
    """Search for files"""
    user_id = getattr(context, 'user_id', 'default_user')
    
    try:
        folder = expand_user_path(path)

        # Week 2: Security validation
        try:
            validated_folder = path_validator.validate_path(
                folder,
                operation="read",
                must_exist=True
            )
        except (PathSecurityError, ValidationError) as e:
            audit = AuditLogger()
            await audit.log_operation(
                operation_type="search_files",
                status="blocked",
                details={"path": str(folder), "pattern": pattern},
                user_id=user_id,
                risk_level="blocked",
                paths=[str(folder)],
                error=str(e)
            )
            return ToolResult(success=False, error=f"Security: {str(e)}").to_dict()

        validate_path(validated_folder, must_exist=True)

        files = scan_folder(validated_folder, recursive=True)

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

        # Week 2: Enhanced audit log
        audit = AuditLogger()
        await audit.log_operation(
            operation_type="search_files",
            status="success",
            details={"pattern": pattern, "file_type": file_type, "results": len(results)},
            user_id=user_id,
            risk_level="safe",
            paths=[str(validated_folder)]
        )

        logger.info(
            "search_complete",
            extra={
                "pattern": pattern,
                "results": len(results)
            }
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
        audit = AuditLogger()
        await audit.log_operation(
            operation_type="search_files",
            status="failed",
            details={"path": str(path)},
            user_id=user_id,
            risk_level="unknown",
            paths=[str(path)],
            error=str(e)
        )
        logger.error("search_failed", extra={"error": str(e)})
        return ToolResult(success=False, error=str(e)).to_dict()


@function_tool()
async def get_file_info_tool(
    context: RunContext,
    path: str,
) -> dict:
    """Get detailed file information"""
    user_id = getattr(context, 'user_id', 'default_user')
    
    try:
        file_path = expand_user_path(path)

        # Week 2: Security validation
        try:
            validated_path = path_validator.validate_path(
                file_path,
                operation="read",
                must_exist=True
            )
        except (PathSecurityError, ValidationError) as e:
            audit = AuditLogger()
            await audit.log_operation(
                operation_type="get_file_info",
                status="blocked",
                details={"path": str(file_path)},
                user_id=user_id,
                risk_level="blocked",
                paths=[str(file_path)],
                error=str(e)
            )
            return ToolResult(success=False, error=f"Security: {str(e)}").to_dict()

        validate_path(validated_path, must_exist=True)

        stat = validated_path.stat()

        info = {
            "name": validated_path.name,
            "size_bytes": stat.st_size,
            "size_human": FileInfo(
                validated_path,
                stat.st_size,
                "",
                False,
                0,
            ).size_human,
            "category": categorize_file(validated_path),
            "extension": validated_path.suffix,
            "modified": stat.st_mtime,
            "is_file": validated_path.is_file(),
            "is_dir": validated_path.is_dir(),
        }

        # Week 2: Enhanced audit log
        audit = AuditLogger()
        await audit.log_operation(
            operation_type="get_file_info",
            status="success",
            details={"size": stat.st_size},
            user_id=user_id,
            risk_level="safe",
            paths=[str(validated_path)]
        )

        logger.info("file_info_retrieved", extra={"path": str(validated_path)})

        return ToolResult(success=True, data=info).to_dict()

    except Exception as e:
        audit = AuditLogger()
        await audit.log_operation(
            operation_type="get_file_info",
            status="failed",
            details={"path": str(path)},
            user_id=user_id,
            risk_level="unknown",
            paths=[str(path)],
            error=str(e)
        )
        logger.error("file_info_failed", extra={"error": str(e)})
        return ToolResult(success=False, error=str(e)).to_dict()


@function_tool()
async def read_file_content_tool(
    context: RunContext,
    path: str,
    max_lines: int = 200,
) -> dict:
    """Read text file content safely (size + line limited)"""
    user_id = getattr(context, 'user_id', 'default_user')
    
    try:
        file_path = expand_user_path(path)

        # Week 2: Security validation
        try:
            validated_path = path_validator.validate_path(
                file_path,
                operation="read",
                must_exist=True
            )
        except (PathSecurityError, ValidationError) as e:
            audit = AuditLogger()
            await audit.log_operation(
                operation_type="read_file_content",
                status="blocked",
                details={"path": str(file_path)},
                user_id=user_id,
                risk_level="blocked",
                paths=[str(file_path)],
                error=str(e)
            )
            return ToolResult(success=False, error=f"Security: {str(e)}").to_dict()

        validate_path(validated_path, must_exist=True)

        if validated_path.stat().st_size > MAX_READ_SIZE:
            return ToolResult(
                success=False,
                error="File too large to read safely",
            ).to_dict()

        try:
            lines = validated_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except Exception:
            return ToolResult(
                success=False,
                error="File is not readable as text",
            ).to_dict()

        preview = lines[:max_lines]

        # Week 2: Enhanced audit log
        audit = AuditLogger()
        await audit.log_operation(
            operation_type="read_file_content",
            status="success",
            details={"lines_read": len(preview), "max_lines": max_lines},
            user_id=user_id,
            risk_level="safe",
            paths=[str(validated_path)]
        )

        logger.info("file_read", extra={"path": str(validated_path), "lines": len(preview)})

        return ToolResult(
            success=True,
            data={
                "path": str(validated_path),
                "total_lines": len(lines),
                "preview_lines": len(preview),
                "content": preview,
            },
            message=f"Read {len(preview)} lines from file",
        ).to_dict()

    except Exception as e:
        audit = AuditLogger()
        await audit.log_operation(
            operation_type="read_file_content",
            status="failed",
            details={"path": str(path)},
            user_id=user_id,
            risk_level="unknown",
            paths=[str(path)],
            error=str(e)
        )
        logger.error("file_read_failed", extra={"error": str(e)})
        return ToolResult(success=False, error=str(e)).to_dict()


@function_tool()
async def preview_file_tool(
    context: RunContext,
    path: str,
    mode: str = "head",
    lines: int = 50,
) -> dict:
    """Preview first or last N lines of a file"""
    user_id = getattr(context, 'user_id', 'default_user')
    
    try:
        file_path = expand_user_path(path)

        # Week 2: Security validation
        try:
            validated_path = path_validator.validate_path(
                file_path,
                operation="read",
                must_exist=True
            )
        except (PathSecurityError, ValidationError) as e:
            audit = AuditLogger()
            await audit.log_operation(
                operation_type="preview_file",
                status="blocked",
                details={"path": str(file_path)},
                user_id=user_id,
                risk_level="blocked",
                paths=[str(file_path)],
                error=str(e)
            )
            return ToolResult(success=False, error=f"Security: {str(e)}").to_dict()

        validate_path(validated_path, must_exist=True)

        content = validated_path.read_text(encoding="utf-8", errors="ignore").splitlines()

        if mode == "tail":
            preview = content[-lines:]
        else:
            preview = content[:lines]

        # Week 2: Enhanced audit log
        audit = AuditLogger()
        await audit.log_operation(
            operation_type="preview_file",
            status="success",
            details={"mode": mode, "lines": lines},
            user_id=user_id,
            risk_level="safe",
            paths=[str(validated_path)]
        )

        return ToolResult(
            success=True,
            data={
                "path": str(validated_path),
                "mode": mode,
                "lines": len(preview),
                "content": preview,
            },
            message=f"Showing {mode} {len(preview)} lines",
        ).to_dict()

    except Exception as e:
        audit = AuditLogger()
        await audit.log_operation(
            operation_type="preview_file",
            status="failed",
            details={"path": str(path)},
            user_id=user_id,
            risk_level="unknown",
            paths=[str(path)],
            error=str(e)
        )
        logger.error("file_preview_failed", extra={"error": str(e)})
        return ToolResult(success=False, error=str(e)).to_dict()


@function_tool()
async def read_folder_tree_tool(
    context: RunContext,
    path: str,
    depth: int = 3,
) -> dict:
    """Read folder structure (tree view, no file content)"""
    user_id = getattr(context, 'user_id', 'default_user')
    
    try:
        root = expand_user_path(path)

        # Week 2: Security validation
        try:
            validated_root = path_validator.validate_path(
                root,
                operation="read",
                must_exist=True
            )
        except (PathSecurityError, ValidationError) as e:
            audit = AuditLogger()
            await audit.log_operation(
                operation_type="read_folder_tree",
                status="blocked",
                details={"path": str(root)},
                user_id=user_id,
                risk_level="blocked",
                paths=[str(root)],
                error=str(e)
            )
            return ToolResult(success=False, error=f"Security: {str(e)}").to_dict()

        validate_path(validated_root, must_exist=True)

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

        walk(validated_root, 0)

        # Week 2: Enhanced audit log
        audit = AuditLogger()
        await audit.log_operation(
            operation_type="read_folder_tree",
            status="success",
            details={"depth": depth, "items": len(tree)},
            user_id=user_id,
            risk_level="safe",
            paths=[str(validated_root)]
        )

        return ToolResult(
            success=True,
            data={"tree": tree},
            message=f"Read folder tree up to depth {depth}",
        ).to_dict()

    except Exception as e:
        audit = AuditLogger()
        await audit.log_operation(
            operation_type="read_folder_tree",
            status="failed",
            details={"path": str(path)},
            user_id=user_id,
            risk_level="unknown",
            paths=[str(path)],
            error=str(e)
        )
        logger.error("folder_tree_failed", extra={"error": str(e)})
        return ToolResult(success=False, error=str(e)).to_dict()


@function_tool()
async def search_file_contents_tool(
    context: RunContext,
    path: str,
    query: str,
    case_sensitive: bool = False,
) -> dict:
    """Search text inside files (grep-style)"""
    user_id = getattr(context, 'user_id', 'default_user')
    
    try:
        root = expand_user_path(path)

        # Week 2: Security validation
        try:
            validated_root = path_validator.validate_path(
                root,
                operation="read",
                must_exist=True
            )
        except (PathSecurityError, ValidationError) as e:
            audit = AuditLogger()
            await audit.log_operation(
                operation_type="search_file_contents",
                status="blocked",
                details={"path": str(root), "query": query},
                user_id=user_id,
                risk_level="blocked",
                paths=[str(root)],
                error=str(e)
            )
            return ToolResult(success=False, error=f"Security: {str(e)}").to_dict()

        validate_path(validated_root, must_exist=True)

        matches = []

        for file in validated_root.rglob("*"):
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

        # Week 2: Enhanced audit log
        audit = AuditLogger()
        await audit.log_operation(
            operation_type="search_file_contents",
            status="success",
            details={"query": query, "matches": len(matches)},
            user_id=user_id,
            risk_level="safe",
            paths=[str(validated_root)]
        )

        return ToolResult(
            success=True,
            data={"query": query, "matches": matches, "count": len(matches)},
            message=f"Found matches in {len(matches)} files",
        ).to_dict()

    except Exception as e:
        audit = AuditLogger()
        await audit.log_operation(
            operation_type="search_file_contents",
            status="failed",
            details={"path": str(path), "query": query},
            user_id=user_id,
            risk_level="unknown",
            paths=[str(path)],
            error=str(e)
        )
        logger.error("content_search_failed", extra={"error": str(e)})
        return ToolResult(success=False, error=str(e)).to_dict()


@function_tool()
async def detect_project_type_tool(
    context: RunContext,
    path: str,
) -> dict:
    """Detect project type from folder contents (read-only)"""
    user_id = getattr(context, 'user_id', 'default_user')
    
    try:
        root = expand_user_path(path)

        # Week 2: Security validation
        try:
            validated_root = path_validator.validate_path(
                root,
                operation="read",
                must_exist=True
            )
        except (PathSecurityError, ValidationError) as e:
            audit = AuditLogger()
            await audit.log_operation(
                operation_type="detect_project_type",
                status="blocked",
                details={"path": str(root)},
                user_id=user_id,
                risk_level="blocked",
                paths=[str(root)],
                error=str(e)
            )
            return ToolResult(success=False, error=f"Security: {str(e)}").to_dict()

        validate_path(validated_root, must_exist=True)

        files = {f.name.lower() for f in validated_root.iterdir() if f.is_file()}

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

        # Week 2: Enhanced audit log
        audit = AuditLogger()
        await audit.log_operation(
            operation_type="detect_project_type",
            status="success",
            details={"project_type": project_type},
            user_id=user_id,
            risk_level="safe",
            paths=[str(validated_root)]
        )

        return ToolResult(
            success=True,
            data={"path": str(validated_root), "project_type": project_type},
            message=f"Detected project type: {project_type}",
        ).to_dict()

    except Exception as e:
        audit = AuditLogger()
        await audit.log_operation(
            operation_type="detect_project_type",
            status="failed",
            details={"path": str(path)},
            user_id=user_id,
            risk_level="unknown",
            paths=[str(path)],
            error=str(e)
        )
        logger.error("project_detection_failed", extra={"error": str(e)})
        return ToolResult(success=False, error=str(e)).to_dict()