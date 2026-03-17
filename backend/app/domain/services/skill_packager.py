"""Skill packager service.

This service creates skill packages - ZIP archives containing skill definitions
with supporting files (scripts, references, templates).

Implements Pythinker-style SKILL.md format with:
- YAML frontmatter parsing
- Goal and Core Principle sections
- Feature ↔ User Value mappings
- Four-layer implementation structure
- Workflow steps
- Examples
"""

import io
import re
import uuid
import zipfile
from collections import OrderedDict
from datetime import UTC, datetime
from typing import Any

import yaml

from app.domain.exceptions.base import BusinessRuleViolation
from app.domain.models.skill_package import (
    SkillExample,
    SkillFeatureCategory,
    SkillFeatureMapping,
    SkillImplementationLayer,
    SkillPackage,
    SkillPackageFile,
    SkillPackageMetadata,
    SkillPackageType,
    SkillWorkflowStep,
)


class SkillPackager:
    """Service for creating and packaging skills.

    Supports both simple skill creation and full Pythinker-style SKILL.md
    parsing and generation.
    """

    # Regex patterns for parsing SKILL.md
    FRONTMATTER_PATTERN = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)
    SECTION_PATTERN = re.compile(r"^##\s+(.+)$", re.MULTILINE)
    TABLE_ROW_PATTERN = re.compile(r"^\|(.+)\|$", re.MULTILINE)
    FEATURE_CATEGORY_PATTERN = re.compile(r"Help Users[「「](.+?)[」」]", re.IGNORECASE)

    def __init__(self) -> None:
        """Initialize the packager."""
        pass

    def parse_skill_md(self, content: str) -> SkillPackageMetadata:
        """Parse a Pythinker-style SKILL.md file.

        Args:
            content: The raw SKILL.md content

        Returns:
            Parsed SkillPackageMetadata with all extracted sections
        """
        # Extract YAML frontmatter
        frontmatter_match = self.FRONTMATTER_PATTERN.match(content)
        if not frontmatter_match:
            raise BusinessRuleViolation("SKILL.md must have YAML frontmatter")

        frontmatter_yaml = frontmatter_match.group(1)
        frontmatter = yaml.safe_load(frontmatter_yaml) or {}

        # Extract body content (after frontmatter)
        body_start = frontmatter_match.end()
        body = content[body_start:].strip()

        # Parse basic metadata from frontmatter
        metadata = SkillPackageMetadata(
            name=frontmatter.get("name", "Untitled Skill"),
            description=frontmatter.get("description", ""),
            version=frontmatter.get("version", "1.0.0"),
            author=frontmatter.get("author"),
            category=frontmatter.get("category", "custom"),
            icon=frontmatter.get("icon", "puzzle"),
            required_tools=frontmatter.get("required_tools", []),
            optional_tools=frontmatter.get("optional_tools", []),
            tags=frontmatter.get("tags", []),
            python_dependencies=frontmatter.get("python_dependencies", []),
            system_dependencies=frontmatter.get("system_dependencies", []),
        )

        # Parse sections from body
        sections = self._parse_sections(body)

        # Extract Goal
        if "Goal" in sections:
            metadata.goal = sections["Goal"].strip()

        # Extract Core Principle
        if "Core Principle" in sections:
            metadata.core_principle = sections["Core Principle"].strip()

        # Extract Feature Categories (Pythinker-style tables)
        metadata.feature_categories = self._parse_feature_categories(body)

        # Extract Workflow Steps
        if "Workflow" in sections:
            metadata.workflow_steps = self._parse_workflow_steps(sections["Workflow"])

        # Extract Implementation Layers
        metadata.implementation_layers = self._parse_implementation_layers(sections)

        # Extract Examples
        if "Examples" in sections:
            metadata.examples = self._parse_examples(sections["Examples"])

        return metadata

    def _parse_sections(self, body: str) -> dict[str, str]:
        """Parse markdown sections from body content.

        Args:
            body: Markdown body content

        Returns:
            Dict mapping section titles to their content
        """
        sections: dict[str, str] = {}
        current_section = None
        current_content: list[str] = []

        for line in body.split("\n"):
            # Check for section header
            if line.startswith("## "):
                # Save previous section
                if current_section:
                    sections[current_section] = "\n".join(current_content).strip()
                current_section = line[3:].strip()
                current_content = []
            elif current_section:
                current_content.append(line)

        # Save last section
        if current_section:
            sections[current_section] = "\n".join(current_content).strip()

        return sections

    def _parse_feature_categories(self, body: str) -> list[SkillFeatureCategory]:
        """Parse Pythinker-style feature category tables.

        Looks for sections like "Help Users「Understand Data」" with tables.
        """
        categories: list[SkillFeatureCategory] = []

        # Find all feature category headers
        lines = body.split("\n")
        i = 0
        while i < len(lines):
            line = lines[i]

            # Look for "Help Users" pattern
            match = self.FEATURE_CATEGORY_PATTERN.search(line)
            if match:
                category_name = f"Help Users「{match.group(1)}」"
                mappings: list[SkillFeatureMapping] = []

                # Skip to table
                i += 1
                while i < len(lines) and not lines[i].strip().startswith("|"):
                    i += 1

                # Skip table header and separator
                if i < len(lines) and lines[i].strip().startswith("|"):
                    i += 2  # Skip header and separator row

                # Parse table rows
                while i < len(lines) and lines[i].strip().startswith("|"):
                    row = lines[i].strip()
                    cells = [c.strip() for c in row.split("|")[1:-1]]
                    if len(cells) >= 3:
                        mappings.append(
                            SkillFeatureMapping(
                                feature=cells[0],
                                user_value=cells[1],
                                when_to_use=cells[2],
                            )
                        )
                    i += 1

                if mappings:
                    categories.append(
                        SkillFeatureCategory(
                            category=category_name,
                            mappings=mappings,
                        )
                    )
            else:
                i += 1

        return categories

    def _parse_workflow_steps(self, workflow_content: str) -> list[SkillWorkflowStep]:
        """Parse numbered workflow steps."""
        steps: list[SkillWorkflowStep] = []
        lines = workflow_content.strip().split("\n")

        current_step = None
        current_substeps: list[str] = []

        for line in lines:
            # Check for numbered step (e.g., "1. ", "2. ")
            step_match = re.match(r"^(\d+)\.\s+(.+)$", line.strip())
            if step_match:
                # Save previous step
                if current_step:
                    steps.append(
                        SkillWorkflowStep(
                            step_number=current_step[0],
                            description=current_step[1],
                            substeps=current_substeps,
                        )
                    )
                current_step = (int(step_match.group(1)), step_match.group(2))
                current_substeps = []
            elif line.strip().startswith("- ") and current_step:
                current_substeps.append(line.strip()[2:])

        # Save last step
        if current_step:
            steps.append(
                SkillWorkflowStep(
                    step_number=current_step[0],
                    description=current_step[1],
                    substeps=current_substeps,
                )
            )

        return steps

    def _parse_implementation_layers(self, sections: dict[str, str]) -> list[SkillImplementationLayer]:
        """Parse Pythinker-style four-layer implementation sections."""
        layers: list[SkillImplementationLayer] = []

        # Standard Pythinker layer names
        layer_names = ["Structure", "Information", "Visual", "Interaction"]

        for name in layer_names:
            # Look for "Layer X: Name" pattern
            layer_key = None
            for section_name in sections:
                if name.lower() in section_name.lower():
                    layer_key = section_name
                    break

            if layer_key:
                content = sections[layer_key]
                # Extract goal (first paragraph after header)
                goal_match = re.match(r"\*\*Goal\*\*:\s*(.+?)(?:\n\n|\n#|\Z)", content, re.DOTALL)
                goal = goal_match.group(1).strip() if goal_match else ""

                # Extract code examples (fenced code blocks)
                code_examples = re.findall(r"```python\n(.*?)```", content, re.DOTALL)

                layers.append(
                    SkillImplementationLayer(
                        name=name,
                        goal=goal,
                        code_examples=code_examples,
                    )
                )

        return layers

    def _parse_examples(self, examples_content: str) -> list[SkillExample]:
        """Parse example sections."""
        examples: list[SkillExample] = []

        # Split by example headers (### or numbered)
        example_blocks = re.split(r"###\s+|\n(?=\d+\.\s+\*\*)", examples_content)

        for block in example_blocks:
            block = block.strip()
            if not block:
                continue

            # Extract title (first line or bold text)
            title_match = re.match(r"^\*\*(.+?)\*\*|^(.+?)(?:\n|$)", block)
            if title_match:
                title = title_match.group(1) or title_match.group(2) or "Example"
                description = block[title_match.end() :].strip()

                # Look for code snippet
                code_match = re.search(r"```(?:python|json)?\n(.*?)```", description, re.DOTALL)
                code_snippet = code_match.group(1).strip() if code_match else None

                examples.append(
                    SkillExample(
                        title=title.strip(),
                        description=description[:500] if len(description) > 500 else description,
                        code_snippet=code_snippet,
                    )
                )

        return examples

    def create_skill_md(
        self,
        metadata: SkillPackageMetadata,
        workflow_content: str | None = None,
    ) -> str:
        """Generate SKILL.md with YAML frontmatter.

        Generates a full Pythinker-style SKILL.md with all sections.

        Args:
            metadata: Skill metadata for frontmatter
            workflow_content: Optional workflow description (uses metadata.workflow_steps if not provided)

        Returns:
            Complete SKILL.md content with frontmatter
        """
        # Build YAML frontmatter using OrderedDict to maintain order
        frontmatter = OrderedDict(
            [
                ("name", metadata.name),
                ("description", metadata.description),
            ]
        )

        # Add optional frontmatter fields
        if metadata.version != "1.0.0":
            frontmatter["version"] = metadata.version
        if metadata.author:
            frontmatter["author"] = metadata.author
        if metadata.category != "custom":
            frontmatter["category"] = metadata.category
        if metadata.icon != "puzzle":
            frontmatter["icon"] = metadata.icon
        if metadata.required_tools:
            frontmatter["required_tools"] = metadata.required_tools
        if metadata.optional_tools:
            frontmatter["optional_tools"] = metadata.optional_tools
        if metadata.tags:
            frontmatter["tags"] = metadata.tags
        if metadata.python_dependencies:
            frontmatter["python_dependencies"] = metadata.python_dependencies
        if metadata.system_dependencies:
            frontmatter["system_dependencies"] = metadata.system_dependencies

        # Use yaml.dump with default_flow_style=False for readable output
        yaml_content = yaml.dump(
            dict(frontmatter),
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )

        # Start building the content
        content_parts: list[str] = [
            f"---\n{yaml_content.strip()}\n---\n",
            f"# {metadata.name}\n",
        ]

        # Goal section
        if metadata.goal:
            content_parts.append(f"## Goal\n\n{metadata.goal}\n")

        # Core Principle section
        if metadata.core_principle:
            content_parts.append(f"## Core Principle\n\n{metadata.core_principle}\n")

        # Overview section
        content_parts.append(f"## Overview\n\n{metadata.description}\n")

        # Feature Categories section (Pythinker-style)
        if metadata.feature_categories:
            content_parts.append("## Features\n")
            for category in metadata.feature_categories:
                content_parts.append(f"\n### {category.category}\n")
                if category.mappings:
                    content_parts.append("\n| Feature | User Value | When to Use |")
                    content_parts.append("|---------|-----------|-------------|")
                    content_parts.extend(
                        f"| {mapping.feature} | {mapping.user_value} | {mapping.when_to_use} |"
                        for mapping in category.mappings
                    )
                content_parts.append("")

        # Workflow section
        if metadata.workflow_steps:
            content_parts.append("## Workflow\n")
            for step in metadata.workflow_steps:
                content_parts.append(f"{step.step_number}. {step.description}")
                content_parts.extend(f"   - {substep}" for substep in step.substeps)
            content_parts.append("")
        elif workflow_content:
            content_parts.append(f"## Workflow\n\n{workflow_content}\n")

        # Implementation Layers section (Pythinker-style)
        if metadata.implementation_layers:
            content_parts.append("## Implementation\n")
            for layer in metadata.implementation_layers:
                content_parts.append(f"\n### Layer: {layer.name}\n")
                if layer.goal:
                    content_parts.append(f"**Goal**: {layer.goal}\n")
                content_parts.extend(f"\n```python\n{code}\n```\n" for code in layer.code_examples)

        # Examples section
        if metadata.examples:
            content_parts.append("## Examples\n")
            for i, example in enumerate(metadata.examples, 1):
                content_parts.append(f"\n### {i}. {example.title}\n")
                if example.description:
                    content_parts.append(f"{example.description}\n")
                if example.code_snippet:
                    content_parts.append(f"\n```python\n{example.code_snippet}\n```\n")

        # Resources section
        content_parts.append("\n## Resources\n")
        content_parts.append("This skill leverages various resources to enhance its capabilities:\n")
        content_parts.append("### scripts/\n\nHelper scripts for automation and analysis.\n")
        content_parts.append("### references/\n\nReference documents and guidelines.\n")
        content_parts.append("### templates/\n\nTemplate files for common outputs.\n")

        return "\n".join(content_parts)

    def build_file_tree(self, files: list[SkillPackageFile]) -> dict[str, Any]:
        """Build hierarchical tree from flat file list.

        Args:
            files: List of package files with paths

        Returns:
            Nested dictionary representing folder structure.
            Files are represented as their metadata dict, folders as nested dicts.
        """
        tree: dict[str, Any] = {}

        for file in files:
            parts = file.path.split("/")
            current = tree

            # Navigate/create folders
            for part in parts[:-1]:
                if part not in current:
                    current[part] = {}
                current = current[part]

            # Add file at leaf - store as dict with metadata
            filename = parts[-1]
            current[filename] = {
                "type": "file",
                "path": file.path,
                "size": file.size,
            }

        return tree

    def create_zip(self, package: SkillPackage) -> io.BytesIO:
        """Create ZIP archive from package files.

        Args:
            package: The skill package to archive

        Returns:
            BytesIO buffer containing the ZIP file
        """
        buffer = io.BytesIO()

        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for file in package.files:
                # Write file content to archive
                zf.writestr(file.path, file.content.encode("utf-8"))

        buffer.seek(0)
        return buffer

    def create_requirements_txt(self, dependencies: list[str]) -> str:
        """Generate requirements.txt content.

        Args:
            dependencies: List of Python package names/specs

        Returns:
            requirements.txt file content
        """
        if not dependencies:
            return ""

        lines = [
            "# Python dependencies for this skill",
            "# Generated automatically by Pythinker Skill Packager",
            "",
        ]
        lines.extend(sorted(dependencies))
        return "\n".join(lines)

    def determine_package_type(
        self,
        metadata: SkillPackageMetadata,
        has_custom_tools: bool = False,
    ) -> SkillPackageType:
        """Determine the package type based on content.

        Args:
            metadata: Skill metadata
            has_custom_tools: Whether the package has custom tool implementations

        Returns:
            Appropriate package type
        """
        # Advanced: has implementation layers (Pythinker-style) or custom tools
        if metadata.implementation_layers or has_custom_tools:
            return SkillPackageType.ADVANCED

        # Standard: has workflow steps or feature categories
        if metadata.workflow_steps or metadata.feature_categories:
            return SkillPackageType.STANDARD

        # Simple: just basic metadata
        return SkillPackageType.SIMPLE

    def create_package(
        self,
        metadata: SkillPackageMetadata,
        workflow_content: str | None = None,
        scripts: list[SkillPackageFile] | None = None,
        references: list[SkillPackageFile] | None = None,
        templates: list[SkillPackageFile] | None = None,
        tools: list[SkillPackageFile] | None = None,
        examples: list[SkillPackageFile] | None = None,
        skill_id: str | None = None,
        include_requirements: bool = True,
    ) -> SkillPackage:
        """Create a complete skill package.

        Supports full Pythinker-style packages with all optional directories.

        Args:
            metadata: Skill metadata
            workflow_content: Optional workflow description for SKILL.md
            scripts: Optional script files
            references: Optional reference files
            templates: Optional template files
            tools: Optional custom tool implementations
            examples: Optional example files
            skill_id: Optional DB skill ID
            include_requirements: Whether to generate requirements.txt

        Returns:
            Complete SkillPackage ready for delivery
        """
        files: list[SkillPackageFile] = []

        # Generate SKILL.md
        skill_md_content = self.create_skill_md(metadata, workflow_content)
        files.append(SkillPackageFile.from_content("SKILL.md", skill_md_content))

        # Generate requirements.txt if there are Python dependencies
        if include_requirements and metadata.python_dependencies:
            requirements_content = self.create_requirements_txt(metadata.python_dependencies)
            files.append(SkillPackageFile.from_content("requirements.txt", requirements_content))

        # Add scripts (ensure path prefix)
        if scripts:
            for script in scripts:
                path = script.path if script.path.startswith("scripts/") else f"scripts/{script.path}"
                files.append(
                    SkillPackageFile(
                        path=path,
                        content=script.content,
                        size=script.size,
                        file_type=script.file_type,
                    )
                )

        # Add references (ensure path prefix)
        if references:
            for ref in references:
                path = ref.path if ref.path.startswith("references/") else f"references/{ref.path}"
                files.append(
                    SkillPackageFile(
                        path=path,
                        content=ref.content,
                        size=ref.size,
                        file_type=ref.file_type,
                    )
                )

        # Add templates (ensure path prefix)
        if templates:
            for tmpl in templates:
                path = tmpl.path if tmpl.path.startswith("templates/") else f"templates/{tmpl.path}"
                files.append(
                    SkillPackageFile(
                        path=path,
                        content=tmpl.content,
                        size=tmpl.size,
                        file_type=tmpl.file_type,
                    )
                )

        # Add custom tools (ensure path prefix)
        if tools:
            for tool in tools:
                path = tool.path if tool.path.startswith("tools/") else f"tools/{tool.path}"
                files.append(
                    SkillPackageFile(
                        path=path,
                        content=tool.content,
                        size=tool.size,
                        file_type=tool.file_type,
                    )
                )

        # Add examples (ensure path prefix)
        if examples:
            for example in examples:
                path = example.path if example.path.startswith("examples/") else f"examples/{example.path}"
                files.append(
                    SkillPackageFile(
                        path=path,
                        content=example.content,
                        size=example.size,
                        file_type=example.file_type,
                    )
                )

        # Build file tree
        file_tree = self.build_file_tree(files)

        # Determine package type
        package_type = self.determine_package_type(metadata, has_custom_tools=bool(tools))

        now = datetime.now(UTC)

        # Create and return package
        return SkillPackage(
            id=str(uuid.uuid4()),
            name=metadata.name,
            description=metadata.description,
            version=metadata.version,
            icon=metadata.icon,
            category=metadata.category,
            author=metadata.author,
            package_type=package_type,
            files=files,
            file_tree=file_tree,
            metadata=metadata,
            skill_id=skill_id,
            created_at=now,
            updated_at=now,
        )

    def create_simple_package(
        self,
        name: str,
        description: str,
        system_prompt: str,
        icon: str = "puzzle",
        required_tools: list[str] | None = None,
        optional_tools: list[str] | None = None,
        skill_id: str | None = None,
    ) -> SkillPackage:
        """Create a simple skill package from basic inputs.

        This is a convenience method for creating packages from skill creation
        tool outputs without needing to manually construct metadata and files.

        Args:
            name: Skill name
            description: Skill description
            system_prompt: The system prompt addition content
            icon: Lucide icon name
            required_tools: List of required tool names
            optional_tools: List of optional tool names
            skill_id: Optional DB skill ID

        Returns:
            Complete SkillPackage ready for delivery
        """
        metadata = SkillPackageMetadata(
            name=name,
            description=description,
            version="1.0.0",
            icon=icon,
            required_tools=required_tools or [],
            optional_tools=optional_tools or [],
        )

        # Use system prompt as workflow content
        workflow_content = system_prompt

        return self.create_package(
            metadata=metadata,
            workflow_content=workflow_content,
            skill_id=skill_id,
        )

    def load_from_zip(self, zip_buffer: io.BytesIO) -> SkillPackage:
        """Load a skill package from a ZIP archive.

        Args:
            zip_buffer: BytesIO buffer containing the ZIP file

        Returns:
            Loaded SkillPackage

        Raises:
            ValueError: If SKILL.md is missing or invalid
        """
        files: list[SkillPackageFile] = []

        with zipfile.ZipFile(zip_buffer, "r") as zf:
            for name in zf.namelist():
                # Skip directories
                if name.endswith("/"):
                    continue

                content = zf.read(name).decode("utf-8")
                files.append(SkillPackageFile.from_content(name, content))

        # Find and parse SKILL.md
        skill_md_file = next((f for f in files if f.path == "SKILL.md"), None)
        if not skill_md_file:
            raise BusinessRuleViolation("Package must contain SKILL.md")

        metadata = self.parse_skill_md(skill_md_file.content)

        # Build file tree
        file_tree = self.build_file_tree(files)

        # Determine package type
        has_tools = any(f.path.startswith("tools/") for f in files)
        package_type = self.determine_package_type(metadata, has_custom_tools=has_tools)

        now = datetime.now(UTC)

        return SkillPackage(
            id=str(uuid.uuid4()),
            name=metadata.name,
            description=metadata.description,
            version=metadata.version,
            icon=metadata.icon,
            category=metadata.category,
            author=metadata.author,
            package_type=package_type,
            files=files,
            file_tree=file_tree,
            metadata=metadata,
            created_at=now,
            updated_at=now,
        )

    def load_from_skill_md(self, skill_md_content: str) -> SkillPackage:
        """Create a minimal package from just SKILL.md content.

        Args:
            skill_md_content: Raw SKILL.md file content

        Returns:
            SkillPackage with just the SKILL.md file
        """
        metadata = self.parse_skill_md(skill_md_content)

        files = [SkillPackageFile.from_content("SKILL.md", skill_md_content)]
        file_tree = self.build_file_tree(files)

        package_type = self.determine_package_type(metadata)

        now = datetime.now(UTC)

        return SkillPackage(
            id=str(uuid.uuid4()),
            name=metadata.name,
            description=metadata.description,
            version=metadata.version,
            icon=metadata.icon,
            category=metadata.category,
            author=metadata.author,
            package_type=package_type,
            files=files,
            file_tree=file_tree,
            metadata=metadata,
            created_at=now,
            updated_at=now,
        )

    def validate_package(self, package: SkillPackage) -> list[str]:
        """Validate a skill package for completeness and correctness.

        Args:
            package: The package to validate

        Returns:
            List of validation error messages (empty if valid)
        """
        errors: list[str] = []

        # Check SKILL.md exists
        if not package.get_skill_md():
            errors.append("Package must contain SKILL.md")

        # Check name and description
        if not package.name or len(package.name.strip()) < 2:
            errors.append("Package name must be at least 2 characters")
        if not package.description or len(package.description.strip()) < 10:
            errors.append("Package description must be at least 10 characters")

        # Validate file paths
        for f in package.files:
            if ".." in f.path:
                errors.append(f"Invalid file path: {f.path}")
            if f.path.startswith("/"):
                errors.append(f"File paths must be relative: {f.path}")

        # Check for duplicate files
        paths = [f.path for f in package.files]
        if len(paths) != len(set(paths)):
            errors.append("Package contains duplicate file paths")

        # Validate metadata if present
        if package.metadata:
            # Check required tools reference valid tools
            from app.domain.services.skill_validator import CustomSkillValidator

            all_tools = set(package.metadata.required_tools + package.metadata.optional_tools)
            invalid_tools = all_tools - CustomSkillValidator.ALLOWED_TOOLS
            if invalid_tools:
                errors.append(f"Invalid tools: {', '.join(sorted(invalid_tools))}")

        return errors


# Singleton instance
_packager: SkillPackager | None = None


def get_skill_packager() -> SkillPackager:
    """Get the singleton skill packager instance."""
    global _packager
    if _packager is None:
        _packager = SkillPackager()
    return _packager
