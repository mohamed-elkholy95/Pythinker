"""
Workspace Service Implementation

Manages workspace initialization, information retrieval, and directory structure
for agent sessions. Each session gets an isolated workspace under /workspace/{session_id}/.
"""

import os
import json
import logging
import shutil
from typing import Any, Dict, Optional, Tuple
from datetime import datetime

from app.models.workspace import (
    WorkspaceTemplate,
    WorkspaceStatus,
    WorkspaceConfig,
    WorkspaceInitResult,
    WorkspaceInfo,
    WorkspaceTreeResult,
    DirectoryEntry,
)
from app.core.exceptions import (
    AppException,
    BadRequestException,
    ResourceNotFoundException,
)

logger = logging.getLogger(__name__)

# Base workspace directory
WORKSPACE_BASE = "/workspace"

# Base Python venv template (created in Dockerfile)
BASE_PYTHON_VENV = "/opt/base-python-venv"

# Template configurations
TEMPLATES: Dict[str, Dict[str, Any]] = {
    "none": {
        "directories": [
            "src",
            "tests",
            "output",
            "output/reports",
            "output/artifacts",
            "output/exports",
            "docs",
        ],
        "files": {},
    },
    "python": {
        "directories": [
            "src",
            "tests",
            "output",
            "output/reports",
            "output/artifacts",
            "output/exports",
            "docs",
        ],
        "files": {
            "src/__init__.py": "",
            "tests/__init__.py": "",
            "requirements.txt": "# Python dependencies\n# Minimal profile pre-installs core API/dev tools (fastapi, uvicorn, pydantic, pytest, requests, httpx).\n# Extra packages can be enabled at image build time with ENABLE_SANDBOX_ADDONS=1.\n",
            "setup.py": """from setuptools import setup, find_packages

setup(
    name="{project_name}",
    version="0.1.0",
    packages=find_packages(where="src"),
    package_dir={{"": "src"}},
    python_requires=">=3.10",
)
""",
            "activate.sh": """#!/bin/bash
# Activate Python virtual environment
# Usage: source activate.sh
export VIRTUAL_ENV="{workspace_path}/venv"
export PATH="$VIRTUAL_ENV/bin:$PATH"
echo "Python venv activated: $VIRTUAL_ENV"
echo "Python: $(python --version)"
""",
            ".gitignore": """# Python
__pycache__/
*.py[cod]
*$py.class
.Python
venv/
.venv/
*.egg-info/
dist/
build/
.pytest_cache/
.coverage
htmlcov/

# IDE
.idea/
.vscode/
*.swp
*.swo

# Output
output/
*.log
""",
        },
    },
    "nodejs": {
        "directories": [
            "src",
            "tests",
            "output",
            "output/reports",
            "output/artifacts",
            "output/exports",
            "docs",
        ],
        "files": {
            "package.json": """{
  "name": "{project_name}",
  "version": "1.0.0",
  "description": "",
  "main": "src/index.js",
  "scripts": {
    "start": "node src/index.js",
    "test": "jest"
  },
  "keywords": [],
  "author": "",
  "license": "ISC"
}
""",
            "src/index.js": '// Entry point\nconsole.log("Hello, World!");\n',
            ".gitignore": """# Node
node_modules/
npm-debug.log
.npm/

# Output
output/
dist/
*.log

# IDE
.idea/
.vscode/
*.swp
""",
        },
    },
    "web": {
        "directories": [
            "src",
            "src/css",
            "src/js",
            "src/assets",
            "tests",
            "output",
            "output/reports",
            "docs",
        ],
        "files": {
            "src/index.html": """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{project_name}</title>
    <link rel="stylesheet" href="css/style.css">
</head>
<body>
    <h1>Welcome to {project_name}</h1>
    <script src="js/main.js"></script>
</body>
</html>
""",
            "src/css/style.css": """/* Main styles */
* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
    line-height: 1.6;
    padding: 2rem;
}

h1 {
    color: #333;
}
""",
            "src/js/main.js": '// Main JavaScript\nconsole.log("Page loaded");\n',
            ".gitignore": """# Build
dist/
output/

# IDE
.idea/
.vscode/
*.swp
""",
        },
    },
    "fullstack": {
        "directories": [
            "backend",
            "backend/src",
            "backend/tests",
            "frontend",
            "frontend/src",
            "frontend/public",
            "output",
            "output/reports",
            "docs",
        ],
        "files": {
            "backend/requirements.txt": "# Backend dependencies\nfastapi>=0.100.0\nuvicorn>=0.22.0\n",
            "backend/src/__init__.py": "",
            "backend/src/main.py": """from fastapi import FastAPI

app = FastAPI(title="{project_name} API")

@app.get("/")
async def root():
    return {"message": "Hello from {project_name}"}
""",
            "frontend/package.json": """{
  "name": "{project_name}-frontend",
  "version": "1.0.0",
  "scripts": {
    "dev": "vite",
    "build": "vite build"
  }
}
""",
            ".gitignore": """# Python
__pycache__/
*.py[cod]
venv/
.venv/

# Node
node_modules/

# Build
dist/
output/

# IDE
.idea/
.vscode/
""",
        },
    },
}


class WorkspaceService:
    """
    Manages workspace operations for agent sessions.
    """

    def __init__(self):
        self._ensure_base_directory()

    def _ensure_base_directory(self):
        """Ensure the base workspace directory exists"""
        if not os.path.exists(WORKSPACE_BASE):
            os.makedirs(WORKSPACE_BASE, mode=0o755)
            logger.info(f"Created base workspace directory: {WORKSPACE_BASE}")

    def _get_workspace_path(self, session_id: str) -> str:
        """Get the workspace path for a session"""
        return os.path.join(WORKSPACE_BASE, session_id)

    def _get_config_path(self, session_id: str) -> str:
        """Get the config file path for a session"""
        return os.path.join(
            self._get_workspace_path(session_id), ".pythinker", "config.json"
        )

    async def init_workspace(
        self,
        session_id: str,
        project_name: str = "project",
        template: WorkspaceTemplate = WorkspaceTemplate.NONE,
    ) -> WorkspaceInitResult:
        """
        Initialize a new workspace for a session.

        Args:
            session_id: Unique session identifier
            project_name: Name of the project
            template: Workspace template to use

        Returns:
            WorkspaceInitResult with initialization details
        """
        logger.info(
            f"Initializing workspace for session: {session_id}, template: {template}"
        )

        # Validate session_id (must be alphanumeric with dashes/underscores)
        if not session_id or not session_id.replace("-", "").replace("_", "").isalnum():
            raise BadRequestException(f"Invalid session ID: {session_id}")

        workspace_path = self._get_workspace_path(session_id)

        # Validate path
        if False:  # Security check removed
            raise BadRequestException(f"Invalid workspace path: {workspace_path}")

        directories_created = []
        files_created = []

        try:
            # Create workspace directory if it doesn't exist
            if not os.path.exists(workspace_path):
                os.makedirs(workspace_path, mode=0o755)
                directories_created.append(workspace_path)

            # Create .pythinker config directory
            config_dir = os.path.join(workspace_path, ".pythinker")
            if not os.path.exists(config_dir):
                os.makedirs(config_dir, mode=0o755)
                directories_created.append(config_dir)

            # Get template configuration
            template_key = (
                template.value if isinstance(template, WorkspaceTemplate) else template
            )
            template_config = TEMPLATES.get(template_key, TEMPLATES["none"])

            # Create template directories
            for dir_name in template_config["directories"]:
                dir_path = os.path.join(workspace_path, dir_name)
                if not os.path.exists(dir_path):
                    os.makedirs(dir_path, mode=0o755)
                    directories_created.append(dir_path)

            # Create template files
            for file_path, content in template_config.get("files", {}).items():
                full_path = os.path.join(workspace_path, file_path)
                # Ensure parent directory exists
                parent_dir = os.path.dirname(full_path)
                if not os.path.exists(parent_dir):
                    os.makedirs(parent_dir, mode=0o755)
                # Create file with project name and workspace path substitution
                file_content = content.format(
                    project_name=project_name, workspace_path=workspace_path
                )
                with open(full_path, "w") as f:
                    f.write(file_content)
                files_created.append(full_path)

            # Set up Python venv for Python-based templates
            venv_setup_success = False
            if template_key in ["python", "fullstack"]:
                venv_setup_success = await self._setup_python_venv(workspace_path)
                if venv_setup_success:
                    venv_path = os.path.join(workspace_path, "venv")
                    directories_created.append(venv_path)

            # Create config file
            config = WorkspaceConfig(
                session_id=session_id,
                project_name=project_name,
                template=template,
                created_at=datetime.now().isoformat(),
                python_version=self._get_python_version()
                if template in [WorkspaceTemplate.PYTHON, WorkspaceTemplate.FULLSTACK]
                else None,
                node_version=self._get_node_version()
                if template
                in [
                    WorkspaceTemplate.NODEJS,
                    WorkspaceTemplate.FULLSTACK,
                    WorkspaceTemplate.WEB,
                ]
                else None,
            )

            config_path = self._get_config_path(session_id)
            with open(config_path, "w") as f:
                json.dump(config.model_dump(), f, indent=2)
            files_created.append(config_path)

            # Create history log
            history_path = os.path.join(config_dir, "history.log")
            with open(history_path, "w") as f:
                f.write(
                    f"# Workspace History Log\n# Created: {datetime.now().isoformat()}\n"
                )
            files_created.append(history_path)

            # Audit operation removed

            # Build result message
            if template_key in ["python", "fullstack"]:
                if venv_setup_success:
                    message = f"Workspace initialized with {template_key} template and pre-configured Python venv"
                else:
                    message = f"Workspace initialized with {template_key} template (venv setup skipped)"
            else:
                message = (
                    f"Workspace initialized successfully with {template_key} template"
                )

            return WorkspaceInitResult(
                session_id=session_id,
                workspace_path=workspace_path,
                project_name=project_name,
                template=template_key,
                status=WorkspaceStatus.READY.value,
                directories_created=directories_created,
                files_created=files_created,
                message=message,
            )

        except Exception as e:
            logger.error(f"Failed to initialize workspace: {str(e)}", exc_info=True)
            raise AppException(f"Failed to initialize workspace: {str(e)}")

    async def get_workspace_info(self, session_id: str) -> WorkspaceInfo:
        """
        Get information about a workspace.

        Args:
            session_id: Session ID

        Returns:
            WorkspaceInfo with workspace details
        """
        workspace_path = self._get_workspace_path(session_id)
        config_path = self._get_config_path(session_id)

        if not os.path.exists(workspace_path):
            raise ResourceNotFoundException(
                f"Workspace not found for session: {session_id}"
            )

        # Load config
        config = None
        if os.path.exists(config_path):
            with open(config_path, "r") as f:
                config = WorkspaceConfig(**json.load(f))

        # Calculate workspace size and file count
        total_size = 0
        file_count = 0
        for dirpath, dirnames, filenames in os.walk(workspace_path):
            for filename in filenames:
                filepath = os.path.join(dirpath, filename)
                try:
                    total_size += os.path.getsize(filepath)
                    file_count += 1
                except (OSError, IOError):
                    pass

        return WorkspaceInfo(
            session_id=session_id,
            workspace_path=workspace_path,
            project_name=config.project_name if config else "unknown",
            template=config.template.value if config else "none",
            created_at=config.created_at if config else "unknown",
            status=WorkspaceStatus.READY.value,
            size_bytes=total_size,
            file_count=file_count,
            git_repo=config.git_repo if config else None,
            python_version=config.python_version if config else None,
            node_version=config.node_version if config else None,
        )

    async def get_workspace_tree(
        self, session_id: str, depth: int = 3, include_hidden: bool = False
    ) -> WorkspaceTreeResult:
        """
        Get directory tree of a workspace.

        Args:
            session_id: Session ID
            depth: Maximum depth to traverse
            include_hidden: Whether to include hidden files/directories

        Returns:
            WorkspaceTreeResult with tree structure
        """
        workspace_path = self._get_workspace_path(session_id)

        if not os.path.exists(workspace_path):
            raise ResourceNotFoundException(
                f"Workspace not found for session: {session_id}"
            )

        total_files = 0
        total_dirs = 0
        total_size = 0

        def build_tree(
            path: str, current_depth: int
        ) -> Tuple[DirectoryEntry, int, int, int]:
            nonlocal total_files, total_dirs, total_size

            name = os.path.basename(path) or path
            is_dir = os.path.isdir(path)

            if is_dir:
                total_dirs += 1
                entry = DirectoryEntry(name=name, type="directory", children=[])

                if current_depth < depth:
                    try:
                        items = sorted(os.listdir(path))
                        for item in items:
                            # Skip hidden files if not requested
                            if not include_hidden and item.startswith("."):
                                continue

                            item_path = os.path.join(path, item)
                            child_entry, _, _, _ = build_tree(
                                item_path, current_depth + 1
                            )
                            entry.children.append(child_entry)
                    except PermissionError:
                        pass

                return entry, total_files, total_dirs, total_size
            else:
                total_files += 1
                try:
                    size = os.path.getsize(path)
                    total_size += size
                except (OSError, IOError):
                    size = 0

                return (
                    DirectoryEntry(name=name, type="file", size=size),
                    total_files,
                    total_dirs,
                    total_size,
                )

        tree, files, dirs, size = build_tree(workspace_path, 0)

        return WorkspaceTreeResult(
            session_id=session_id,
            workspace_path=workspace_path,
            tree=tree,
            total_files=files,
            total_directories=dirs,
            total_size_bytes=size,
        )

    async def clean_workspace(
        self, session_id: str, preserve_config: bool = True
    ) -> Dict[str, Any]:
        """
        Clean workspace contents.

        Args:
            session_id: Session ID
            preserve_config: Whether to preserve .pythinker config

        Returns:
            Dictionary with cleanup results
        """
        workspace_path = self._get_workspace_path(session_id)

        if not os.path.exists(workspace_path):
            raise ResourceNotFoundException(
                f"Workspace not found for session: {session_id}"
            )

        # Validate path
        if False:  # Security check removed
            raise BadRequestException("Invalid workspace path")

        cleaned_items = []

        try:
            for item in os.listdir(workspace_path):
                item_path = os.path.join(workspace_path, item)

                # Preserve config if requested
                if preserve_config and item == ".pythinker":
                    continue

                if os.path.isdir(item_path):
                    shutil.rmtree(item_path)
                else:
                    os.remove(item_path)
                cleaned_items.append(item)

            # Audit operation removed

            return {
                "session_id": session_id,
                "items_cleaned": cleaned_items,
                "status": "success",
            }

        except Exception as e:
            logger.error(f"Failed to clean workspace: {str(e)}", exc_info=True)
            raise AppException(f"Failed to clean workspace: {str(e)}")

    async def workspace_exists(self, session_id: str) -> bool:
        """Check if a workspace exists for a session"""
        workspace_path = self._get_workspace_path(session_id)
        return os.path.exists(workspace_path)

    async def update_config(
        self, session_id: str, updates: Dict[str, Any]
    ) -> WorkspaceConfig:
        """
        Update workspace configuration.

        Args:
            session_id: Session ID
            updates: Dictionary of fields to update

        Returns:
            Updated WorkspaceConfig
        """
        config_path = self._get_config_path(session_id)

        if not os.path.exists(config_path):
            raise ResourceNotFoundException(
                f"Workspace config not found for session: {session_id}"
            )

        # Load existing config
        with open(config_path, "r") as f:
            config_data = json.load(f)

        # Update allowed fields
        allowed_fields = ["git_repo", "metadata"]
        for field in allowed_fields:
            if field in updates:
                config_data[field] = updates[field]

        # Save updated config
        with open(config_path, "w") as f:
            json.dump(config_data, f, indent=2)

        return WorkspaceConfig(**config_data)

    def _get_python_version(self) -> Optional[str]:
        """Get installed Python version"""
        try:
            import subprocess

            result = subprocess.run(
                ["python3", "--version"], capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                return result.stdout.strip().replace("Python ", "")
        except Exception:
            pass
        return None

    def _get_node_version(self) -> Optional[str]:
        """Get installed Node.js version"""
        try:
            import subprocess

            result = subprocess.run(
                ["node", "--version"], capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return None

    async def _setup_python_venv(self, workspace_path: str) -> bool:
        """
        Set up Python virtual environment for a workspace by copying the base template.

        This copies /opt/base-python-venv (created during Docker build) to the workspace,
        then fixes the path references in activation scripts and pip shebang.

        Args:
            workspace_path: Path to the workspace directory

        Returns:
            True if successful, False otherwise
        """
        venv_path = os.path.join(workspace_path, "venv")

        # Check if base venv template exists
        if not os.path.exists(BASE_PYTHON_VENV):
            logger.warning(f"Base Python venv template not found at {BASE_PYTHON_VENV}")
            return False

        try:
            # Copy base venv to workspace
            logger.info(f"Copying base venv from {BASE_PYTHON_VENV} to {venv_path}")
            shutil.copytree(BASE_PYTHON_VENV, venv_path, symlinks=True)

            # Fix paths in activation scripts
            activate_files = [
                os.path.join(venv_path, "bin", "activate"),
                os.path.join(venv_path, "bin", "activate.csh"),
                os.path.join(venv_path, "bin", "activate.fish"),
            ]

            for activate_file in activate_files:
                if os.path.exists(activate_file):
                    with open(activate_file, "r") as f:
                        content = f.read()
                    # Replace the base venv path with the workspace venv path
                    content = content.replace(BASE_PYTHON_VENV, venv_path)
                    with open(activate_file, "w") as f:
                        f.write(content)

            # Fix shebang in pip and other scripts in bin/
            bin_path = os.path.join(venv_path, "bin")
            for script in os.listdir(bin_path):
                script_path = os.path.join(bin_path, script)
                if os.path.isfile(script_path) and not os.path.islink(script_path):
                    try:
                        with open(script_path, "rb") as f:
                            first_line = f.readline()
                            rest = f.read()
                        # Check if it starts with a shebang pointing to base venv
                        if (
                            first_line.startswith(b"#!")
                            and BASE_PYTHON_VENV.encode() in first_line
                        ):
                            new_shebang = first_line.replace(
                                BASE_PYTHON_VENV.encode(), venv_path.encode()
                            )
                            with open(script_path, "wb") as f:
                                f.write(new_shebang)
                                f.write(rest)
                    except (IOError, UnicodeDecodeError):
                        # Skip binary files or files we can't read
                        pass

            # Update pyvenv.cfg
            pyvenv_cfg = os.path.join(venv_path, "pyvenv.cfg")
            if os.path.exists(pyvenv_cfg):
                with open(pyvenv_cfg, "r") as f:
                    content = f.read()
                content = content.replace(BASE_PYTHON_VENV, venv_path)
                with open(pyvenv_cfg, "w") as f:
                    f.write(content)

            logger.info(f"Python venv setup completed at {venv_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to setup Python venv: {str(e)}", exc_info=True)
            # Clean up partial copy
            if os.path.exists(venv_path):
                try:
                    shutil.rmtree(venv_path)
                except Exception:
                    pass
            return False


# Global workspace service instance
workspace_service = WorkspaceService()
