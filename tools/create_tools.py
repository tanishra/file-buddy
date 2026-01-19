import shutil
from pathlib import Path
from typing import List, Dict, Optional

from livekit.agents import function_tool, RunContext

from utils.logger import get_logger
from utils.path_utils import expand_user_path, validate_path
from core.snapshot import SnapshotManager
from core.audit import AuditLogger
from models.tool_results import ToolResult

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
    try:
        file_path = expand_user_path(path)
        validate_path(file_path.parent, must_exist=True)

        template = FILE_TEMPLATES.get(file_type, FILE_TEMPLATES["text"])
        full_content = template + content

        file_path.write_text(full_content, encoding="utf-8")

        audit = AuditLogger()
        await audit.log_operation(
            operation_type="create_file",
            status="success",
            details={"path": str(file_path), "size": len(full_content)},
        )

        logger.info("file_created", path=str(file_path), type=file_type)

        return ToolResult(
            success=True,
            data={"path": str(file_path)},
            message=f"Created {file_path.name}",
        ).to_dict()

    except Exception as e:
        logger.error("file_creation_failed", error=str(e))
        return ToolResult(success=False, error=str(e)).to_dict()


@function_tool()
async def create_folder_tool(
    context: RunContext,
    path: str,
) -> dict:
    """Create a new folder"""
    try:
        folder_path = expand_user_path(path)
        validate_path(folder_path.parent, must_exist=True)

        folder_path.mkdir(parents=True, exist_ok=True)

        audit = AuditLogger()
        await audit.log_operation(
            operation_type="create_folder",
            status="success",
            details={"path": str(folder_path)},
        )

        logger.info("folder_created", path=str(folder_path))

        return ToolResult(
            success=True,
            data={"path": str(folder_path)},
            message=f"Created folder {folder_path.name}",
        ).to_dict()

    except Exception as e:
        logger.error("folder_creation_failed", error=str(e))
        return ToolResult(success=False, error=str(e)).to_dict()

# Canonical extension → template map
# This MERGES conceptually with FILE_TEMPLATES without modifying it
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

    # Catch-all handled dynamically
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

from typing import List, Optional
from typing_extensions import TypedDict
class FileSpec(TypedDict):
    name: str
    content: Optional[str]

@function_tool()
async def create_any_files_tool(
    context: RunContext,
    base_path: str,
    files: List[FileSpec],
) -> dict:
    """
    Create ANY files of ANY type.
    Each file entry:
    {
        "name": "path/relative/file.ext",
        "content": "optional content"
    }
    """
    try:
        base_dir = expand_user_path(base_path)
        validate_path(base_dir, must_exist=True)
        base_dir.mkdir(parents=True, exist_ok=True)

        created_files: List[str] = []

        for f in files:
            name = f["name"]
            content = f.get("content", "")

            target = base_dir / name
            target.parent.mkdir(parents=True, exist_ok=True)

            template = _resolve_template_for_file(target.name)
            target.write_text(template + content, encoding="utf-8")

            created_files.append(str(target))

        audit = AuditLogger()
        await audit.log_operation(
            operation_type="create_any_files",
            status="success",
            details={"count": len(created_files), "files": created_files},
        )

        logger.info("any_files_created", count=len(created_files))

        return ToolResult(
            success=True,
            data={"files": created_files},
            message=f"Created {len(created_files)} files",
        ).to_dict()

    except Exception as e:
        logger.error("any_file_creation_failed", error=str(e))
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
    """
    Create an industry-grade project structure.

    Supported project_type:
    - genai
    - deep_learning
    - react
    - nextjs
    - backend_api
    - research
    """
    try:
        root = expand_user_path(path)
        validate_path(root.parent, must_exist=True)
        root.mkdir(parents=True, exist_ok=True)

        if project_type not in PROJECT_TEMPLATES:
            return ToolResult(
                success=False,
                error=f"Unsupported project type: {project_type}",
            ).to_dict()

        created_items = _create_structure(root, PROJECT_TEMPLATES[project_type])

        audit = AuditLogger()
        await audit.log_operation(
            operation_type="create_project_structure",
            status="success",
            details={
                "project_type": project_type,
                "path": str(root),
                "items_created": len(created_items),
            },
        )

        logger.info(
            "project_structure_created",
            type=project_type,
            path=str(root),
            count=len(created_items),
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
        logger.error("project_structure_failed", error=str(e))
        return ToolResult(success=False, error=str(e)).to_dict()