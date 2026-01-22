import shutil
from pathlib import Path
from typing import List, Dict, Optional
from typing_extensions import TypedDict

from livekit.agents import function_tool, RunContext

from utils.logger import get_logger
from utils.path_utils import expand_user_path, validate_path
from core.snapshot import SnapshotManager
from core.audit_logger import AuditLogger
from models.tool_results import ToolResult

# Week 2 Security Imports
from core.security import path_validator
from core.risk_assessment import risk_assessor
from core.confirmation import ConfirmationManager
from core.exceptions import PathSecurityError, ValidationError

logger = get_logger(__name__)

# File templates
FILE_TEMPLATES = {
    "python": "#!/usr/bin/env python3\n# -*- coding: utf-8 -*-\n\"\"\"\nCreated with File Organizer AI\n\"\"\"\n\n",
    "javascript": "// Created with File Organizer AI\n\n",
    "html": "<!DOCTYPE html>\n<html>\n<head>\n    <title>Document</title>\n</head>\n<body>\n    \n</body>\n</html>\n",
    "markdown": "# Document\n\nCreated with File Organizer AI\n\n",
    "text": "",
}


@function_tool()
async def create_file_tool(
    context: RunContext,
    path: str,
    content: str = "",
    file_type: str = "text",
) -> dict:
    """Create a new file"""
    user_id = getattr(context, 'user_id', 'default_user')
    
    try:
        file_path = expand_user_path(path)
        
        # Week 2: Security validation
        try:
            validated_path = path_validator.validate_path(
                file_path,
                operation="write",
                must_exist=False
            )
        except (PathSecurityError, ValidationError) as e:
            audit = AuditLogger()
            await audit.log_operation(
                operation_type="create_file",
                status="blocked",
                details={"path": str(file_path), "error": str(e)},
                user_id=user_id,
                risk_level="blocked",
                paths=[str(file_path)],
                error=str(e)
            )
            logger.warning("Security violation", extra={"path": str(file_path), "error": str(e)})
            return ToolResult(success=False, error=f"Security: {str(e)}").to_dict()
        
        validate_path(file_path.parent, must_exist=True)

        template = FILE_TEMPLATES.get(file_type, FILE_TEMPLATES["text"])
        full_content = template + content

        file_path.write_text(full_content, encoding="utf-8")

        # Week 2: Enhanced audit logging
        audit = AuditLogger()
        await audit.log_operation(
            operation_type="create_file",
            status="success",
            details={"path": str(file_path), "size": len(full_content), "file_type": file_type},
            user_id=user_id,
            risk_level="low",
            paths=[str(validated_path)]
        )

        logger.info("file_created", extra={"path": str(file_path), "type": file_type})

        return ToolResult(
            success=True,
            data={"path": str(file_path)},
            message=f"Created {file_path.name}",
        ).to_dict()

    except Exception as e:
        audit = AuditLogger()
        await audit.log_operation(
            operation_type="create_file",
            status="failed",
            details={"path": str(path)},
            user_id=user_id,
            risk_level="unknown",
            paths=[str(path)],
            error=str(e)
        )
        logger.error("file_creation_failed", extra={"error": str(e)})
        return ToolResult(success=False, error=str(e)).to_dict()


@function_tool()
async def create_folder_tool(
    context: RunContext,
    path: str,
) -> dict:
    """Create a new folder"""
    user_id = getattr(context, 'user_id', 'default_user')
    
    try:
        folder_path = expand_user_path(path)
        
        # Week 2: Security validation
        try:
            validated_path = path_validator.validate_path(
                folder_path,
                operation="write",
                must_exist=False
            )
        except (PathSecurityError, ValidationError) as e:
            audit = AuditLogger()
            await audit.log_operation(
                operation_type="create_folder",
                status="blocked",
                details={"path": str(folder_path)},
                user_id=user_id,
                risk_level="blocked",
                paths=[str(folder_path)],
                error=str(e)
            )
            return ToolResult(success=False, error=f"Security: {str(e)}").to_dict()
        
        validate_path(folder_path.parent, must_exist=True)

        folder_path.mkdir(parents=True, exist_ok=True)

        # Week 2: Enhanced audit logging
        audit = AuditLogger()
        await audit.log_operation(
            operation_type="create_folder",
            status="success",
            details={"path": str(folder_path)},
            user_id=user_id,
            risk_level="low",
            paths=[str(validated_path)]
        )

        logger.info("folder_created", extra={"path": str(folder_path)})

        return ToolResult(
            success=True,
            data={"path": str(folder_path)},
            message=f"Created folder {folder_path.name}",
        ).to_dict()

    except Exception as e:
        audit = AuditLogger()
        await audit.log_operation(
            operation_type="create_folder",
            status="failed",
            details={"path": str(path)},
            user_id=user_id,
            risk_level="unknown",
            paths=[str(path)],
            error=str(e)
        )
        logger.error("folder_creation_failed", extra={"error": str(e)})
        return ToolResult(success=False, error=str(e)).to_dict()


# Canonical extension → template map
UNIVERSAL_EXTENSION_TEMPLATES: Dict[str, str] = {
    # Programming languages
    "py": FILE_TEMPLATES["python"],
    "js": FILE_TEMPLATES["javascript"],
    "ts": "// TypeScript file\n\n",
    "tsx": "// React TypeScript component\n\n",
    "jsx": "// React JavaScript component\n\n",
    "java": "// Java class\n\n",
    "cpp": "// C++ source\n\n",
    "c": "// C source\n\n",
    "cs": "// C# source\n\n",
    "go": "// Go source\n\n",
    "rs": "// Rust source\n\n",
    "php": "<?php\n\n",
    "rb": "# Ruby file\n\n",
    "swift": "// Swift file\n\n",
    "kt": "// Kotlin file\n\n",

    # Web / markup
    "html": FILE_TEMPLATES["html"],
    "css": "/* CSS file */\n\n",
    "scss": "// SCSS file\n\n",
    "xml": "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n",
    "json": "{\n}\n",
    "yaml": "",
    "yml": "",
    "md": FILE_TEMPLATES["markdown"],

    # Config / infra
    "env": "",
    "gitignore": "__pycache__/\nnode_modules/\n.env\n.DS_Store\n",
    "dockerfile": "FROM alpine:latest\n",
    "toml": "",
    "ini": "",
    "cfg": "",
    "conf": "",

    # Data
    "csv": "",
    "tsv": "",
    "txt": "",
    "log": "",

    # Shell / scripts
    "sh": "#!/usr/bin/env bash\n\n",
    "zsh": "#!/usr/bin/env zsh\n\n",
    "ps1": "# PowerShell script\n\n",

    # Build / tooling
    "makefile": "",
    "gradle": "",
    "bat": "",
}


def _resolve_template_for_file(filename: str) -> str:
    """Return best template for any filename"""
    suffix = filename.lower()

    # Special filenames without extensions
    if suffix == "dockerfile":
        return UNIVERSAL_EXTENSION_TEMPLATES["dockerfile"]
    if suffix == "makefile":
        return UNIVERSAL_EXTENSION_TEMPLATES["makefile"]

    if "." in filename:
        ext = filename.rsplit(".", 1)[-1].lower()
        return UNIVERSAL_EXTENSION_TEMPLATES.get(ext, "")

    return ""


class FileSpec(TypedDict):
    name: str
    content: Optional[str]


@function_tool()
async def create_any_files_tool(
    context: RunContext,
    base_path: str,
    files: List[FileSpec],
) -> dict:
    """Create ANY files of ANY type"""
    user_id = getattr(context, 'user_id', 'default_user')
    
    try:
        base_dir = expand_user_path(base_path)
        
        # Week 2: Security validation
        try:
            validated_base = path_validator.validate_path(
                base_dir,
                operation="write",
                must_exist=False
            )
        except (PathSecurityError, ValidationError) as e:
            audit = AuditLogger()
            await audit.log_operation(
                operation_type="create_any_files",
                status="blocked",
                details={"base_path": str(base_dir), "file_count": len(files)},
                user_id=user_id,
                risk_level="blocked",
                paths=[str(base_dir)],
                error=str(e)
            )
            return ToolResult(success=False, error=f"Security: {str(e)}").to_dict()
        
        validate_path(base_dir, must_exist=True)
        base_dir.mkdir(parents=True, exist_ok=True)

        created_files: List[str] = []

        for f in files:
            name = f["name"]
            content = f.get("content", "")

            target = base_dir / name
            
            # Validate each file path
            try:
                validated_file = path_validator.validate_path(
                    target,
                    operation="write",
                    must_exist=False
                )
            except (PathSecurityError, ValidationError) as e:
                logger.warning(f"Skipping file due to security: {target} - {e}")
                continue
            
            target.parent.mkdir(parents=True, exist_ok=True)

            template = _resolve_template_for_file(target.name)
            target.write_text(template + content, encoding="utf-8")

            created_files.append(str(target))

        # Week 2: Enhanced audit logging
        audit = AuditLogger()
        await audit.log_operation(
            operation_type="create_any_files",
            status="success",
            details={"count": len(created_files), "files": created_files},
            user_id=user_id,
            risk_level="low",
            paths=created_files
        )

        logger.info("any_files_created", extra={"count": len(created_files)})

        return ToolResult(
            success=True,
            data={"files": created_files},
            message=f"Created {len(created_files)} files",
        ).to_dict()

    except Exception as e:
        audit = AuditLogger()
        await audit.log_operation(
            operation_type="create_any_files",
            status="failed",
            details={"base_path": str(base_path)},
            user_id=user_id,
            risk_level="unknown",
            paths=[str(base_path)],
            error=str(e)
        )
        logger.error("any_file_creation_failed", extra={"error": str(e)})
        return ToolResult(success=False, error=str(e)).to_dict()


PROJECT_TEMPLATES: Dict[str, List[str]] = {
    # GenAI / LLM Project (Production)
    "genai": [
        "src/agents/",
        "src/prompts/",
        "src/tools/",
        "src/memory/",
        "src/retrieval/",
        "src/models/",
        "src/evaluation/",
        "src/api/",
        "src/utils/",
        "data/raw/",
        "data/processed/",
        "configs/",
        "scripts/",
        "tests/",
        "notebooks/",
        "README.md",
        "requirements.txt",
        ".env",
        ".gitignore",
    ],

    # Deep Learning / ML Project
    "deep_learning": [
        "src/models/",
        "src/datasets/",
        "src/training/",
        "src/inference/",
        "src/losses/",
        "src/metrics/",
        "src/utils/",
        "configs/",
        "experiments/",
        "checkpoints/",
        "logs/",
        "notebooks/",
        "data/raw/",
        "data/processed/",
        "README.md",
        "requirements.txt",
        ".env",
        ".gitignore",
    ],

    # React.js Production App
    "react": [
        "src/components/",
        "src/pages/",
        "src/hooks/",
        "src/context/",
        "src/services/",
        "src/styles/",
        "src/utils/",
        "public/",
        "tests/",
        "package.json",
        "README.md",
        ".env",
        ".gitignore",
    ],

    # Next.js Production App
    "nextjs": [
        "app/",
        "app/api/",
        "app/(auth)/",
        "components/",
        "hooks/",
        "lib/",
        "services/",
        "styles/",
        "public/",
        "middleware.ts",
        "next.config.js",
        "package.json",
        "README.md",
        ".env",
        ".gitignore",
    ],

    # Backend API (FastAPI / Express style)
    "backend_api": [
        "src/api/",
        "src/routes/",
        "src/controllers/",
        "src/services/",
        "src/models/",
        "src/schemas/",
        "src/middleware/",
        "src/utils/",
        "configs/",
        "tests/",
        "scripts/",
        "README.md",
        ".env",
        ".gitignore",
    ],

    # Research / Paper Project
    "research": [
        "paper/",
        "experiments/",
        "figures/",
        "tables/",
        "data/",
        "references/",
        "notes/",
        "README.md",
        ".gitignore",
    ],
}


def _create_structure(root: Path, structure: List[str]) -> List[str]:
    """Create folders and files from a structure list"""
    created = []

    for item in structure:
        target = root / item
        if item.endswith("/"):
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("", encoding="utf-8")
        created.append(str(target))

    return created


@function_tool()
async def create_project_structure_tool(
    context: RunContext,
    path: str,
    project_type: str,
) -> dict:
    """Create an industry-grade project structure"""
    user_id = getattr(context, 'user_id', 'default_user')
    
    try:
        root = expand_user_path(path)
        
        # Week 2: Security validation
        try:
            validated_root = path_validator.validate_path(
                root,
                operation="write",
                must_exist=False
            )
        except (PathSecurityError, ValidationError) as e:
            audit = AuditLogger()
            await audit.log_operation(
                operation_type="create_project_structure",
                status="blocked",
                details={"path": str(root), "project_type": project_type},
                user_id=user_id,
                risk_level="blocked",
                paths=[str(root)],
                error=str(e)
            )
            return ToolResult(success=False, error=f"Security: {str(e)}").to_dict()
        
        validate_path(root.parent, must_exist=True)
        root.mkdir(parents=True, exist_ok=True)

        if project_type not in PROJECT_TEMPLATES:
            return ToolResult(
                success=False,
                error=f"Unsupported project type: {project_type}",
            ).to_dict()

        created_items = _create_structure(root, PROJECT_TEMPLATES[project_type])

        # Week 2: Enhanced audit logging
        audit = AuditLogger()
        await audit.log_operation(
            operation_type="create_project_structure",
            status="success",
            details={
                "project_type": project_type,
                "path": str(root),
                "items_created": len(created_items),
            },
            user_id=user_id,
            risk_level="low",
            paths=[str(root)]
        )

        logger.info(
            "project_structure_created",
            extra={
                "type": project_type,
                "path": str(root),
                "count": len(created_items)
            }
        )

        return ToolResult(
            success=True,
            data={
                "project_type": project_type,
                "path": str(root),
                "items": created_items,
            },
            message=f"{project_type} project structure created",
        ).to_dict()

    except Exception as e:
        audit = AuditLogger()
        await audit.log_operation(
            operation_type="create_project_structure",
            status="failed",
            details={"path": str(path), "project_type": project_type},
            user_id=user_id,
            risk_level="unknown",
            paths=[str(path)],
            error=str(e)
        )
        logger.error("project_structure_failed", extra={"error": str(e)})
        return ToolResult(success=False, error=str(e)).to_dict()