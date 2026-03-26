"""Tests for SkillPackager service.

Covers all public methods and classes:
- parse_skill_md: YAML frontmatter parsing, section extraction, feature categories,
  workflow steps, implementation layers, examples
- create_skill_md: SKILL.md generation with frontmatter and all section types
- build_file_tree: Hierarchical tree construction from flat file lists
- create_zip: ZIP archive creation and round-trip integrity
- create_requirements_txt: requirements.txt generation
- determine_package_type: Package type classification logic
- create_package: Full package assembly with all optional directories
- create_simple_package: Convenience factory
- load_from_zip: ZIP archive loading and SKILL.md validation
- load_from_skill_md: Minimal package creation from raw content
- validate_package: Completeness and correctness validation
- get_skill_packager: Singleton factory
"""

import io
import uuid
import zipfile

import pytest

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
from app.domain.services.skill_packager import SkillPackager, get_skill_packager

_MINIMAL_SKILL_MD = """\
---
name: My Skill
description: A useful skill for testing
---

## Goal

Do great things.
"""

_FULL_SKILL_MD = """\
---
name: Data Analyst
description: Helps users understand and visualize data
version: 2.0.0
author: Alice
category: analytics
icon: chart-bar
required_tools:
  - info_search_web
  - browser_navigate
optional_tools:
  - browser_view
tags:
  - data
  - analytics
python_dependencies:
  - pandas
  - matplotlib
system_dependencies:
  - gnuplot
---

# Data Analyst

## Goal

Turn raw data into actionable insights.

## Core Principle

Always show, never just tell.

## Overview

An overview section.

## Help Users\u300cUnderstand Data\u300d

| Feature | User Value | When to Use |
|---------|-----------|-------------|
| Bar Chart | See comparisons | Comparing values |
| Line Chart | Track trends | Time series |

## Workflow

1. Collect data
   - Identify sources
   - Validate schema
2. Analyse
   - Run statistics
3. Visualise

## Layer: Structure

**Goal**: Provide solid foundations.

```python
def setup():
    pass
```

## Layer: Information

**Goal**: Surface key insights.

## Examples

### Basic Usage

A simple walkthrough.

```python
print("hello")
```

### Advanced Usage

A complex walkthrough.
"""


def _make_metadata(**overrides) -> SkillPackageMetadata:
    defaults = {
        "name": "Test Skill",
        "description": "A test skill description",
    }
    defaults.update(overrides)
    return SkillPackageMetadata(**defaults)


def _make_file(path: str, content: str = "content") -> SkillPackageFile:
    return SkillPackageFile.from_content(path, content)


class TestParseSkillMdFrontmatter:
    """Frontmatter extraction from SKILL.md."""

    def setup_method(self):
        self.packager = SkillPackager()

    def test_minimal_frontmatter_name_and_description(self):
        metadata = self.packager.parse_skill_md(_MINIMAL_SKILL_MD)
        assert metadata.name == "My Skill"
        assert metadata.description == "A useful skill for testing"

    def test_full_frontmatter_all_fields(self):
        metadata = self.packager.parse_skill_md(_FULL_SKILL_MD)
        assert metadata.name == "Data Analyst"
        assert metadata.version == "2.0.0"
        assert metadata.author == "Alice"
        assert metadata.category == "analytics"
        assert metadata.icon == "chart-bar"
        assert metadata.required_tools == ["info_search_web", "browser_navigate"]
        assert metadata.optional_tools == ["browser_view"]
        assert metadata.tags == ["data", "analytics"]
        assert metadata.python_dependencies == ["pandas", "matplotlib"]
        assert metadata.system_dependencies == ["gnuplot"]

    def test_missing_frontmatter_raises_business_rule_violation(self):
        with pytest.raises(BusinessRuleViolation, match="YAML frontmatter"):
            self.packager.parse_skill_md("# No frontmatter here\n\nJust prose.")

    def test_empty_frontmatter_uses_defaults(self):
        content = "---\nname: Minimal\ndescription: desc\n---\n"
        metadata = self.packager.parse_skill_md(content)
        assert metadata.version == "1.0.0"
        assert metadata.category == "custom"
        assert metadata.icon == "puzzle"
        assert metadata.required_tools == []
        assert metadata.optional_tools == []
        assert metadata.tags == []
        assert metadata.python_dependencies == []
        assert metadata.system_dependencies == []

    def test_author_is_none_when_absent(self):
        metadata = self.packager.parse_skill_md(_MINIMAL_SKILL_MD)
        assert metadata.author is None

    def test_name_falls_back_to_untitled_when_missing(self):
        content = "---\ndescription: desc\n---\n"
        metadata = self.packager.parse_skill_md(content)
        assert metadata.name == "Untitled Skill"


class TestParseSkillMdSections:
    """Body section parsing: Goal, Core Principle, Workflow, Layers, Examples."""

    def setup_method(self):
        self.packager = SkillPackager()

    def test_goal_section_extracted(self):
        metadata = self.packager.parse_skill_md(_FULL_SKILL_MD)
        assert metadata.goal == "Turn raw data into actionable insights."

    def test_core_principle_extracted(self):
        metadata = self.packager.parse_skill_md(_FULL_SKILL_MD)
        assert metadata.core_principle == "Always show, never just tell."

    def test_goal_present_in_minimal(self):
        metadata = self.packager.parse_skill_md(_MINIMAL_SKILL_MD)
        assert metadata.goal == "Do great things."

    def test_core_principle_is_none_when_missing(self):
        metadata = self.packager.parse_skill_md(_MINIMAL_SKILL_MD)
        assert metadata.core_principle is None

    def test_no_sections_yields_empty_lists(self):
        content = "---\nname: X\ndescription: Y\n---\n"
        metadata = self.packager.parse_skill_md(content)
        assert metadata.workflow_steps == []
        assert metadata.feature_categories == []
        assert metadata.implementation_layers == []
        assert metadata.examples == []


class TestParseWorkflowSteps:
    """Numbered workflow step parsing."""

    def setup_method(self):
        self.packager = SkillPackager()

    def test_workflow_steps_count(self):
        metadata = self.packager.parse_skill_md(_FULL_SKILL_MD)
        assert len(metadata.workflow_steps) == 3

    def test_first_step_number_and_description(self):
        metadata = self.packager.parse_skill_md(_FULL_SKILL_MD)
        step = metadata.workflow_steps[0]
        assert step.step_number == 1
        assert step.description == "Collect data"

    def test_substeps_parsed_correctly(self):
        metadata = self.packager.parse_skill_md(_FULL_SKILL_MD)
        step = metadata.workflow_steps[0]
        assert "Identify sources" in step.substeps
        assert "Validate schema" in step.substeps

    def test_step_without_substeps_has_empty_list(self):
        metadata = self.packager.parse_skill_md(_FULL_SKILL_MD)
        step = metadata.workflow_steps[2]
        assert step.substeps == []

    def test_single_step_parsed(self):
        content = "---\nname: X\ndescription: Y\n---\n\n## Workflow\n\n1. Do the thing\n"
        metadata = self.packager.parse_skill_md(content)
        assert len(metadata.workflow_steps) == 1
        assert metadata.workflow_steps[0].step_number == 1
        assert metadata.workflow_steps[0].description == "Do the thing"

    def test_empty_workflow_section_yields_no_steps(self):
        content = "---\nname: X\ndescription: Y\n---\n\n## Workflow\n\nSome prose only.\n"
        metadata = self.packager.parse_skill_md(content)
        assert metadata.workflow_steps == []


class TestParseFeatureCategories:
    """Pythinker-style 'Help Users' table parsing."""

    def setup_method(self):
        self.packager = SkillPackager()

    def test_feature_categories_count(self):
        metadata = self.packager.parse_skill_md(_FULL_SKILL_MD)
        assert len(metadata.feature_categories) == 1

    def test_category_name_preserved(self):
        metadata = self.packager.parse_skill_md(_FULL_SKILL_MD)
        assert metadata.feature_categories[0].category == "Help Users\u300cUnderstand Data\u300d"

    def test_feature_mappings_count(self):
        metadata = self.packager.parse_skill_md(_FULL_SKILL_MD)
        mappings = metadata.feature_categories[0].mappings
        assert len(mappings) == 2

    def test_first_mapping_fields(self):
        metadata = self.packager.parse_skill_md(_FULL_SKILL_MD)
        mapping = metadata.feature_categories[0].mappings[0]
        assert mapping.feature == "Bar Chart"
        assert mapping.user_value == "See comparisons"
        assert mapping.when_to_use == "Comparing values"

    def test_no_feature_categories_when_absent(self):
        metadata = self.packager.parse_skill_md(_MINIMAL_SKILL_MD)
        assert metadata.feature_categories == []

    def test_table_with_fewer_than_three_cells_skipped(self):
        content = (
            "---\nname: X\ndescription: Y\n---\n\n"
            "## Help Users\u300cDo Stuff\u300d\n\n"
            "| Feature | Value |\n"
            "|---------|-------|\n"
            "| A | B |\n"
        )
        metadata = self.packager.parse_skill_md(content)
        assert metadata.feature_categories == []

    def test_multiple_categories_parsed(self):
        content = (
            "---\nname: X\ndescription: Y\n---\n\n"
            "## Help Users\u300cCat A\u300d\n\n"
            "| Feature | Value | When |\n"
            "|---------|-------|------|\n"
            "| F1 | V1 | W1 |\n\n"
            "## Help Users\u300cCat B\u300d\n\n"
            "| Feature | Value | When |\n"
            "|---------|-------|------|\n"
            "| F2 | V2 | W2 |\n"
        )
        metadata = self.packager.parse_skill_md(content)
        assert len(metadata.feature_categories) == 2
        assert metadata.feature_categories[0].category == "Help Users\u300cCat A\u300d"
        assert metadata.feature_categories[1].category == "Help Users\u300cCat B\u300d"


class TestParseImplementationLayers:
    """Four-layer implementation section parsing."""

    def setup_method(self):
        self.packager = SkillPackager()

    def test_layers_detected_by_standard_names(self):
        metadata = self.packager.parse_skill_md(_FULL_SKILL_MD)
        layer_names = [layer.name for layer in metadata.implementation_layers]
        assert "Structure" in layer_names
        assert "Information" in layer_names

    def test_layer_goal_extracted(self):
        metadata = self.packager.parse_skill_md(_FULL_SKILL_MD)
        structure = next(layer for layer in metadata.implementation_layers if layer.name == "Structure")
        assert structure.goal == "Provide solid foundations."

    def test_code_examples_extracted(self):
        metadata = self.packager.parse_skill_md(_FULL_SKILL_MD)
        structure = next(layer for layer in metadata.implementation_layers if layer.name == "Structure")
        assert len(structure.code_examples) == 1
        assert "def setup():" in structure.code_examples[0]

    def test_layer_without_code_has_empty_list(self):
        metadata = self.packager.parse_skill_md(_FULL_SKILL_MD)
        info = next(layer for layer in metadata.implementation_layers if layer.name == "Information")
        assert info.code_examples == []

    def test_no_layers_when_absent(self):
        metadata = self.packager.parse_skill_md(_MINIMAL_SKILL_MD)
        assert metadata.implementation_layers == []


class TestParseExamples:
    """Examples section parsing."""

    def setup_method(self):
        self.packager = SkillPackager()

    def test_examples_count(self):
        metadata = self.packager.parse_skill_md(_FULL_SKILL_MD)
        assert len(metadata.examples) == 2

    def test_first_example_title(self):
        metadata = self.packager.parse_skill_md(_FULL_SKILL_MD)
        assert metadata.examples[0].title == "Basic Usage"

    def test_example_code_snippet_extracted(self):
        metadata = self.packager.parse_skill_md(_FULL_SKILL_MD)
        ex = metadata.examples[0]
        assert ex.code_snippet is not None
        assert 'print("hello")' in ex.code_snippet

    def test_example_description_truncated_at_500(self):
        long_desc = "x" * 600
        content = f"---\nname: X\ndescription: Y\n---\n\n## Examples\n\n### My Example\n\n{long_desc}\n"
        metadata = self.packager.parse_skill_md(content)
        if metadata.examples:
            assert len(metadata.examples[0].description) <= 500

    def test_no_examples_when_absent(self):
        metadata = self.packager.parse_skill_md(_MINIMAL_SKILL_MD)
        assert metadata.examples == []


class TestParseSections:
    """Internal _parse_sections behaviour."""

    def setup_method(self):
        self.packager = SkillPackager()

    def test_multiple_sections_all_captured(self):
        body = "## Alpha\n\nFirst content.\n\n## Beta\n\nSecond content."
        sections = self.packager._parse_sections(body)
        assert "Alpha" in sections
        assert "Beta" in sections

    def test_section_content_trimmed(self):
        body = "## Section\n\n   trimmed   \n"
        sections = self.packager._parse_sections(body)
        assert sections["Section"] == "trimmed"

    def test_empty_body_returns_empty_dict(self):
        assert self.packager._parse_sections("") == {}

    def test_body_with_no_sections_returns_empty_dict(self):
        assert self.packager._parse_sections("Just prose, no headers.") == {}

    def test_section_with_no_content_stores_empty_string(self):
        body = "## EmptySection\n\n## NextSection\n\ncontent"
        sections = self.packager._parse_sections(body)
        assert sections["EmptySection"] == ""

    def test_last_section_captured_without_trailing_header(self):
        body = "## Only\n\nlast section content"
        sections = self.packager._parse_sections(body)
        assert sections["Only"] == "last section content"


class TestCreateSkillMd:
    """SKILL.md generation."""

    def setup_method(self):
        self.packager = SkillPackager()

    def test_output_starts_with_frontmatter_delimiter(self):
        md = self.packager.create_skill_md(_make_metadata())
        assert md.startswith("---")

    def test_frontmatter_contains_name_and_description(self):
        meta = _make_metadata(name="My Tool", description="Does things")
        md = self.packager.create_skill_md(meta)
        assert "My Tool" in md
        assert "Does things" in md

    def test_default_version_not_included_in_frontmatter(self):
        meta = _make_metadata()
        md = self.packager.create_skill_md(meta)
        assert "version:" not in md

    def test_non_default_version_included(self):
        meta = _make_metadata(version="3.1.0")
        md = self.packager.create_skill_md(meta)
        assert "version: 3.1.0" in md

    def test_author_included_when_set(self):
        meta = _make_metadata(author="Bob")
        md = self.packager.create_skill_md(meta)
        assert "author: Bob" in md

    def test_author_omitted_when_none(self):
        meta = _make_metadata()
        md = self.packager.create_skill_md(meta)
        assert "author:" not in md

    def test_default_category_omitted(self):
        meta = _make_metadata(category="custom")
        md = self.packager.create_skill_md(meta)
        assert "category:" not in md

    def test_non_default_category_included(self):
        meta = _make_metadata(category="analytics")
        md = self.packager.create_skill_md(meta)
        assert "category: analytics" in md

    def test_default_icon_omitted(self):
        meta = _make_metadata(icon="puzzle")
        md = self.packager.create_skill_md(meta)
        assert "icon:" not in md

    def test_non_default_icon_included(self):
        meta = _make_metadata(icon="chart-bar")
        md = self.packager.create_skill_md(meta)
        assert "icon: chart-bar" in md

    def test_required_tools_included_when_set(self):
        meta = _make_metadata(required_tools=["info_search_web"])
        md = self.packager.create_skill_md(meta)
        assert "required_tools:" in md
        assert "info_search_web" in md

    def test_tags_included_when_set(self):
        meta = _make_metadata(tags=["seo", "analytics"])
        md = self.packager.create_skill_md(meta)
        assert "tags:" in md

    def test_python_dependencies_included_when_set(self):
        meta = _make_metadata(python_dependencies=["requests", "pandas"])
        md = self.packager.create_skill_md(meta)
        assert "python_dependencies:" in md

    def test_goal_section_present_when_set(self):
        meta = _make_metadata(goal="Achieve great things.")
        md = self.packager.create_skill_md(meta)
        assert "## Goal" in md
        assert "Achieve great things." in md

    def test_goal_section_absent_when_not_set(self):
        meta = _make_metadata()
        md = self.packager.create_skill_md(meta)
        assert "## Goal" not in md

    def test_core_principle_section_present_when_set(self):
        meta = _make_metadata(core_principle="Keep it simple.")
        md = self.packager.create_skill_md(meta)
        assert "## Core Principle" in md
        assert "Keep it simple." in md

    def test_overview_section_always_present(self):
        meta = _make_metadata(description="Some description")
        md = self.packager.create_skill_md(meta)
        assert "## Overview" in md

    def test_workflow_steps_rendered(self):
        meta = _make_metadata(
            workflow_steps=[
                SkillWorkflowStep(step_number=1, description="Step one"),
                SkillWorkflowStep(step_number=2, description="Step two"),
            ]
        )
        md = self.packager.create_skill_md(meta)
        assert "## Workflow" in md
        assert "1. Step one" in md
        assert "2. Step two" in md

    def test_workflow_substeps_rendered(self):
        meta = _make_metadata(
            workflow_steps=[
                SkillWorkflowStep(
                    step_number=1,
                    description="Collect",
                    substeps=["Identify sources"],
                )
            ]
        )
        md = self.packager.create_skill_md(meta)
        assert "   - Identify sources" in md

    def test_workflow_content_fallback_used_when_no_steps(self):
        meta = _make_metadata()
        md = self.packager.create_skill_md(meta, workflow_content="Manual workflow text")
        assert "Manual workflow text" in md

    def test_feature_categories_table_rendered(self):
        meta = _make_metadata(
            feature_categories=[
                SkillFeatureCategory(
                    category="Help Users\u300cDo Stuff\u300d",
                    mappings=[
                        SkillFeatureMapping(
                            feature="Feat",
                            user_value="Value",
                            when_to_use="Always",
                        )
                    ],
                )
            ]
        )
        md = self.packager.create_skill_md(meta)
        assert "## Features" in md
        assert "Help Users\u300cDo Stuff\u300d" in md
        assert "| Feat | Value | Always |" in md

    def test_implementation_layers_rendered(self):
        meta = _make_metadata(
            implementation_layers=[
                SkillImplementationLayer(
                    name="Structure",
                    goal="Build solid base.",
                    code_examples=["def hello(): pass"],
                )
            ]
        )
        md = self.packager.create_skill_md(meta)
        assert "## Implementation" in md
        assert "### Layer: Structure" in md
        assert "**Goal**: Build solid base." in md
        assert "def hello(): pass" in md

    def test_examples_rendered(self):
        meta = _make_metadata(
            examples=[
                SkillExample(
                    title="My Example",
                    description="An example description",
                    code_snippet="print('hi')",
                )
            ]
        )
        md = self.packager.create_skill_md(meta)
        assert "## Examples" in md
        assert "### 1. My Example" in md
        assert "An example description" in md
        assert "print('hi')" in md

    def test_resources_section_always_present(self):
        meta = _make_metadata()
        md = self.packager.create_skill_md(meta)
        assert "## Resources" in md
        assert "### scripts/" in md
        assert "### references/" in md
        assert "### templates/" in md

    def test_roundtrip_name_survives_parse(self):
        meta = _make_metadata(name="Round Trip", description="A roundtrip description")
        md = self.packager.create_skill_md(meta)
        parsed = self.packager.parse_skill_md(md)
        assert parsed.name == "Round Trip"


class TestBuildFileTree:
    """Hierarchical tree construction."""

    def setup_method(self):
        self.packager = SkillPackager()

    def test_root_file_appears_at_top_level(self):
        files = [_make_file("SKILL.md")]
        tree = self.packager.build_file_tree(files)
        assert "SKILL.md" in tree

    def test_nested_file_creates_folder_structure(self):
        files = [_make_file("scripts/helper.py")]
        tree = self.packager.build_file_tree(files)
        assert "scripts" in tree
        assert "helper.py" in tree["scripts"]

    def test_leaf_node_contains_type_path_and_size(self):
        files = [_make_file("SKILL.md", "hello")]
        tree = self.packager.build_file_tree(files)
        node = tree["SKILL.md"]
        assert node["type"] == "file"
        assert node["path"] == "SKILL.md"
        assert isinstance(node["size"], int)

    def test_multiple_files_in_same_directory(self):
        files = [
            _make_file("scripts/a.py"),
            _make_file("scripts/b.py"),
        ]
        tree = self.packager.build_file_tree(files)
        assert "a.py" in tree["scripts"]
        assert "b.py" in tree["scripts"]

    def test_deeply_nested_file(self):
        files = [_make_file("a/b/c/deep.txt")]
        tree = self.packager.build_file_tree(files)
        assert "deep.txt" in tree["a"]["b"]["c"]

    def test_empty_file_list_returns_empty_tree(self):
        assert self.packager.build_file_tree([]) == {}

    def test_multiple_directories_coexist(self):
        files = [
            _make_file("scripts/s.py"),
            _make_file("templates/t.md"),
        ]
        tree = self.packager.build_file_tree(files)
        assert "scripts" in tree
        assert "templates" in tree


class TestCreateZip:
    """ZIP archive creation and integrity."""

    def setup_method(self):
        self.packager = SkillPackager()

    def _minimal_package(self) -> SkillPackage:
        meta = _make_metadata()
        return self.packager.create_package(meta)

    def test_returns_bytes_io(self):
        pkg = self._minimal_package()
        buf = self.packager.create_zip(pkg)
        assert isinstance(buf, io.BytesIO)

    def test_zip_buffer_is_valid_zip(self):
        pkg = self._minimal_package()
        buf = self.packager.create_zip(pkg)
        assert zipfile.is_zipfile(buf)

    def test_zip_contains_skill_md(self):
        pkg = self._minimal_package()
        buf = self.packager.create_zip(pkg)
        with zipfile.ZipFile(buf, "r") as zf:
            assert "SKILL.md" in zf.namelist()

    def test_buffer_seeked_to_start(self):
        pkg = self._minimal_package()
        buf = self.packager.create_zip(pkg)
        assert buf.tell() == 0

    def test_zip_contains_all_package_files(self):
        meta = _make_metadata(python_dependencies=["requests"])
        pkg = self.packager.create_package(meta)
        buf = self.packager.create_zip(pkg)
        with zipfile.ZipFile(buf, "r") as zf:
            names = zf.namelist()
        for pkg_file in pkg.files:
            assert pkg_file.path in names

    def test_zip_content_is_utf8_encoded(self):
        pkg = self._minimal_package()
        buf = self.packager.create_zip(pkg)
        with zipfile.ZipFile(buf, "r") as zf:
            raw = zf.read("SKILL.md")
        decoded = raw.decode("utf-8")
        assert "Test Skill" in decoded


class TestLoadFromZip:
    """Loading a ZIP archive into a SkillPackage."""

    def setup_method(self):
        self.packager = SkillPackager()

    def _zip_with(self, files: dict[str, str]) -> io.BytesIO:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            for path, content in files.items():
                zf.writestr(path, content.encode("utf-8"))
        buf.seek(0)
        return buf

    def test_loads_name_and_description(self):
        buf = self._zip_with({"SKILL.md": _MINIMAL_SKILL_MD})
        pkg = self.packager.load_from_zip(buf)
        assert pkg.name == "My Skill"
        assert pkg.description == "A useful skill for testing"

    def test_package_has_skill_md_file(self):
        buf = self._zip_with({"SKILL.md": _MINIMAL_SKILL_MD})
        pkg = self.packager.load_from_zip(buf)
        assert pkg.get_skill_md() is not None

    def test_raises_when_skill_md_missing(self):
        buf = self._zip_with({"readme.txt": "nothing useful"})
        with pytest.raises(BusinessRuleViolation, match=r"SKILL\.md"):
            self.packager.load_from_zip(buf)

    def test_directory_entries_skipped(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.mkdir("scripts")
            zf.writestr("SKILL.md", _MINIMAL_SKILL_MD.encode())
        buf.seek(0)
        pkg = self.packager.load_from_zip(buf)
        paths = [pkg_file.path for pkg_file in pkg.files]
        assert all(not p.endswith("/") for p in paths)

    def test_extra_files_included_in_package(self):
        buf = self._zip_with(
            {
                "SKILL.md": _MINIMAL_SKILL_MD,
                "scripts/helper.py": "def helper(): pass",
            }
        )
        pkg = self.packager.load_from_zip(buf)
        paths = [pkg_file.path for pkg_file in pkg.files]
        assert "scripts/helper.py" in paths

    def test_has_tools_flag_set_for_tool_files(self):
        buf = self._zip_with(
            {
                "SKILL.md": _MINIMAL_SKILL_MD,
                "tools/my_tool.py": "# custom tool",
            }
        )
        pkg = self.packager.load_from_zip(buf)
        assert pkg.package_type == SkillPackageType.ADVANCED

    def test_package_id_is_uuid_string(self):
        buf = self._zip_with({"SKILL.md": _MINIMAL_SKILL_MD})
        pkg = self.packager.load_from_zip(buf)
        uuid.UUID(pkg.id)

    def test_file_tree_populated(self):
        buf = self._zip_with({"SKILL.md": _MINIMAL_SKILL_MD})
        pkg = self.packager.load_from_zip(buf)
        assert "SKILL.md" in pkg.file_tree


class TestCreateRequirementsTxt:
    """requirements.txt generation."""

    def setup_method(self):
        self.packager = SkillPackager()

    def test_empty_dependencies_returns_empty_string(self):
        assert self.packager.create_requirements_txt([]) == ""

    def test_header_comment_included(self):
        result = self.packager.create_requirements_txt(["requests"])
        assert "# Python dependencies" in result

    def test_dependencies_sorted(self):
        result = self.packager.create_requirements_txt(["zlib", "aiohttp", "requests"])
        lines = [line for line in result.splitlines() if not line.startswith("#") and line]
        assert lines == sorted(["zlib", "aiohttp", "requests"])

    def test_single_dependency_present(self):
        result = self.packager.create_requirements_txt(["pandas"])
        assert "pandas" in result

    def test_version_specifiers_preserved(self):
        result = self.packager.create_requirements_txt(["requests>=2.28.0"])
        assert "requests>=2.28.0" in result

    def test_multiple_dependencies_each_on_own_line(self):
        result = self.packager.create_requirements_txt(["a", "b", "c"])
        lines = [line for line in result.splitlines() if not line.startswith("#") and line]
        assert len(lines) == 3


class TestDeterminePackageType:
    """Package type classification."""

    def setup_method(self):
        self.packager = SkillPackager()

    def test_simple_type_for_basic_metadata(self):
        meta = _make_metadata()
        assert self.packager.determine_package_type(meta) == SkillPackageType.SIMPLE

    def test_standard_type_for_workflow_steps(self):
        meta = _make_metadata(workflow_steps=[SkillWorkflowStep(step_number=1, description="Step")])
        assert self.packager.determine_package_type(meta) == SkillPackageType.STANDARD

    def test_standard_type_for_feature_categories(self):
        meta = _make_metadata(
            feature_categories=[
                SkillFeatureCategory(
                    category="Help Users\u300cX\u300d",
                    mappings=[SkillFeatureMapping(feature="F", user_value="V", when_to_use="W")],
                )
            ]
        )
        assert self.packager.determine_package_type(meta) == SkillPackageType.STANDARD

    def test_advanced_type_for_implementation_layers(self):
        meta = _make_metadata(implementation_layers=[SkillImplementationLayer(name="Structure", goal="Build base.")])
        assert self.packager.determine_package_type(meta) == SkillPackageType.ADVANCED

    def test_advanced_type_for_custom_tools_flag(self):
        meta = _make_metadata()
        assert self.packager.determine_package_type(meta, has_custom_tools=True) == SkillPackageType.ADVANCED

    def test_advanced_takes_precedence_over_standard(self):
        meta = _make_metadata(
            workflow_steps=[SkillWorkflowStep(step_number=1, description="Step")],
            implementation_layers=[SkillImplementationLayer(name="Structure", goal="Base.")],
        )
        assert self.packager.determine_package_type(meta) == SkillPackageType.ADVANCED


class TestCreatePackage:
    """Full package assembly."""

    def setup_method(self):
        self.packager = SkillPackager()

    def test_package_always_contains_skill_md(self):
        pkg = self.packager.create_package(_make_metadata())
        assert pkg.get_skill_md() is not None

    def test_requirements_included_when_python_deps_present(self):
        meta = _make_metadata(python_dependencies=["requests"])
        pkg = self.packager.create_package(meta)
        assert pkg.get_requirements_txt() is not None

    def test_requirements_excluded_when_no_python_deps(self):
        pkg = self.packager.create_package(_make_metadata())
        assert pkg.get_requirements_txt() is None

    def test_requirements_excluded_when_include_requirements_false(self):
        meta = _make_metadata(python_dependencies=["requests"])
        pkg = self.packager.create_package(meta, include_requirements=False)
        assert pkg.get_requirements_txt() is None

    def test_scripts_prefixed_correctly(self):
        script = _make_file("helper.py", "# script")
        pkg = self.packager.create_package(_make_metadata(), scripts=[script])
        paths = [pkg_file.path for pkg_file in pkg.files]
        assert "scripts/helper.py" in paths

    def test_scripts_already_prefixed_not_double_prefixed(self):
        script = _make_file("scripts/helper.py", "# script")
        pkg = self.packager.create_package(_make_metadata(), scripts=[script])
        paths = [pkg_file.path for pkg_file in pkg.files]
        assert "scripts/scripts/helper.py" not in paths
        assert "scripts/helper.py" in paths

    def test_references_prefixed_correctly(self):
        ref = _make_file("guide.md", "# Guide")
        pkg = self.packager.create_package(_make_metadata(), references=[ref])
        paths = [pkg_file.path for pkg_file in pkg.files]
        assert "references/guide.md" in paths

    def test_templates_prefixed_correctly(self):
        tmpl = _make_file("report.md", "# Report")
        pkg = self.packager.create_package(_make_metadata(), templates=[tmpl])
        paths = [pkg_file.path for pkg_file in pkg.files]
        assert "templates/report.md" in paths

    def test_tools_prefixed_correctly(self):
        tool = _make_file("my_tool.py", "# tool")
        pkg = self.packager.create_package(_make_metadata(), tools=[tool])
        paths = [pkg_file.path for pkg_file in pkg.files]
        assert "tools/my_tool.py" in paths

    def test_examples_prefixed_correctly(self):
        ex = _make_file("demo.py", "# demo")
        pkg = self.packager.create_package(_make_metadata(), examples=[ex])
        paths = [pkg_file.path for pkg_file in pkg.files]
        assert "examples/demo.py" in paths

    def test_package_type_advanced_when_tools_provided(self):
        tool = _make_file("my_tool.py")
        pkg = self.packager.create_package(_make_metadata(), tools=[tool])
        assert pkg.package_type == SkillPackageType.ADVANCED

    def test_package_id_is_non_empty_string(self):
        pkg = self.packager.create_package(_make_metadata())
        assert isinstance(pkg.id, str)
        assert len(pkg.id) > 0

    def test_skill_id_propagated(self):
        pkg = self.packager.create_package(_make_metadata(), skill_id="abc-123")
        assert pkg.skill_id == "abc-123"

    def test_skill_id_none_by_default(self):
        pkg = self.packager.create_package(_make_metadata())
        assert pkg.skill_id is None

    def test_metadata_attached_to_package(self):
        meta = _make_metadata()
        pkg = self.packager.create_package(meta)
        assert pkg.metadata is not None
        assert pkg.metadata.name == meta.name

    def test_file_tree_populated_after_create(self):
        pkg = self.packager.create_package(_make_metadata())
        assert "SKILL.md" in pkg.file_tree

    def test_package_name_version_category_icon_propagated(self):
        meta = _make_metadata(
            name="Tool",
            description="Does things",
            version="2.0.0",
            category="analytics",
            icon="chart",
        )
        pkg = self.packager.create_package(meta)
        assert pkg.name == "Tool"
        assert pkg.version == "2.0.0"
        assert pkg.category == "analytics"
        assert pkg.icon == "chart"

    def test_workflow_content_used_when_no_steps(self):
        meta = _make_metadata()
        pkg = self.packager.create_package(meta, workflow_content="Do the thing.")
        skill_md = pkg.get_skill_md()
        assert skill_md is not None
        assert "Do the thing." in skill_md.content


class TestCreateSimplePackage:
    """Convenience factory for simple packages."""

    def setup_method(self):
        self.packager = SkillPackager()

    def test_package_has_correct_name(self):
        pkg = self.packager.create_simple_package(
            name="Simple",
            description="A simple description",
            system_prompt="Be helpful.",
        )
        assert pkg.name == "Simple"

    def test_system_prompt_appears_in_skill_md(self):
        pkg = self.packager.create_simple_package(
            name="X",
            description="A simple test skill description",
            system_prompt="Always be concise.",
        )
        skill_md = pkg.get_skill_md()
        assert skill_md is not None
        assert "Always be concise." in skill_md.content

    def test_required_tools_forwarded(self):
        pkg = self.packager.create_simple_package(
            name="X",
            description="A simple test skill description",
            system_prompt="Help.",
            required_tools=["info_search_web"],
        )
        assert pkg.metadata is not None
        assert "info_search_web" in pkg.metadata.required_tools

    def test_optional_tools_forwarded(self):
        pkg = self.packager.create_simple_package(
            name="X",
            description="A simple test skill description",
            system_prompt="Help.",
            optional_tools=["browser_view"],
        )
        assert pkg.metadata is not None
        assert "browser_view" in pkg.metadata.optional_tools

    def test_none_tools_default_to_empty(self):
        pkg = self.packager.create_simple_package(
            name="X",
            description="A simple test skill description",
            system_prompt="Help.",
        )
        assert pkg.metadata is not None
        assert pkg.metadata.required_tools == []
        assert pkg.metadata.optional_tools == []

    def test_icon_forwarded(self):
        pkg = self.packager.create_simple_package(
            name="X",
            description="A simple test skill description",
            system_prompt="Help.",
            icon="star",
        )
        assert pkg.icon == "star"

    def test_skill_id_forwarded(self):
        pkg = self.packager.create_simple_package(
            name="X",
            description="A simple test skill description",
            system_prompt="Help.",
            skill_id="sid-999",
        )
        assert pkg.skill_id == "sid-999"

    def test_package_type_is_simple(self):
        pkg = self.packager.create_simple_package(
            name="X",
            description="A simple test skill description",
            system_prompt="Help.",
        )
        assert pkg.package_type == SkillPackageType.SIMPLE


class TestLoadFromSkillMd:
    """Minimal package from raw SKILL.md content."""

    def setup_method(self):
        self.packager = SkillPackager()

    def test_package_name_from_frontmatter(self):
        pkg = self.packager.load_from_skill_md(_MINIMAL_SKILL_MD)
        assert pkg.name == "My Skill"

    def test_package_contains_skill_md(self):
        pkg = self.packager.load_from_skill_md(_MINIMAL_SKILL_MD)
        assert pkg.get_skill_md() is not None

    def test_metadata_populated(self):
        pkg = self.packager.load_from_skill_md(_MINIMAL_SKILL_MD)
        assert pkg.metadata is not None

    def test_file_tree_populated(self):
        pkg = self.packager.load_from_skill_md(_MINIMAL_SKILL_MD)
        assert "SKILL.md" in pkg.file_tree

    def test_raises_for_invalid_content(self):
        with pytest.raises(BusinessRuleViolation):
            self.packager.load_from_skill_md("No frontmatter at all.")

    def test_full_skill_md_parses_advanced_type(self):
        pkg = self.packager.load_from_skill_md(_FULL_SKILL_MD)
        assert pkg.package_type == SkillPackageType.ADVANCED

    def test_minimal_skill_md_parses_simple_type(self):
        pkg = self.packager.load_from_skill_md(_MINIMAL_SKILL_MD)
        assert pkg.package_type == SkillPackageType.SIMPLE


class TestValidatePackage:
    """Package completeness and correctness validation."""

    def setup_method(self):
        self.packager = SkillPackager()

    def _valid_package(self, **meta_overrides) -> SkillPackage:
        meta = _make_metadata(
            description="A description long enough to pass validation",
            **meta_overrides,
        )
        return self.packager.create_package(meta)

    def test_valid_package_returns_no_errors(self):
        pkg = self._valid_package()
        errors = self.packager.validate_package(pkg)
        assert errors == []

    def test_missing_skill_md_is_an_error(self):
        pkg = self._valid_package()
        pkg.files = [pkg_file for pkg_file in pkg.files if pkg_file.path != "SKILL.md"]
        errors = self.packager.validate_package(pkg)
        assert any("SKILL.md" in e for e in errors)

    def test_short_name_is_an_error(self):
        pkg = self._valid_package()
        pkg.name = "X"
        errors = self.packager.validate_package(pkg)
        assert any("name" in e.lower() or "2 character" in e for e in errors)

    def test_short_description_is_an_error(self):
        pkg = self._valid_package()
        pkg.description = "Too short"
        errors = self.packager.validate_package(pkg)
        assert any("description" in e.lower() for e in errors)

    def test_path_traversal_is_an_error(self):
        pkg = self._valid_package()
        pkg.files.append(_make_file("../evil.txt"))
        errors = self.packager.validate_package(pkg)
        assert any(".." in e for e in errors)

    def test_absolute_path_is_an_error(self):
        pkg = self._valid_package()
        pkg.files.append(_make_file("/etc/passwd"))
        errors = self.packager.validate_package(pkg)
        assert any("relative" in e.lower() for e in errors)

    def test_duplicate_file_paths_are_an_error(self):
        pkg = self._valid_package()
        skill_md = pkg.get_skill_md()
        assert skill_md is not None
        pkg.files.append(skill_md)
        errors = self.packager.validate_package(pkg)
        assert any("duplicate" in e.lower() for e in errors)

    def test_invalid_tool_in_metadata_is_an_error(self):
        meta = _make_metadata(
            description="A description long enough to pass validation",
            required_tools=["not_a_real_tool_xyz"],
        )
        pkg = self.packager.create_package(meta)
        errors = self.packager.validate_package(pkg)
        assert any("not_a_real_tool_xyz" in e for e in errors)

    def test_valid_allowed_tools_pass(self):
        meta = _make_metadata(
            description="A description long enough to pass validation",
            required_tools=["info_search_web", "browser_navigate"],
        )
        pkg = self.packager.create_package(meta)
        errors = self.packager.validate_package(pkg)
        assert errors == []

    def test_empty_name_is_an_error(self):
        pkg = self._valid_package()
        pkg.name = ""
        errors = self.packager.validate_package(pkg)
        assert any("name" in e.lower() for e in errors)


class TestGetSkillPackager:
    """Singleton factory behaviour."""

    def test_returns_skill_packager_instance(self):
        packager = get_skill_packager()
        assert isinstance(packager, SkillPackager)

    def test_returns_same_instance_on_repeated_calls(self):
        first = get_skill_packager()
        second = get_skill_packager()
        assert first is second

    def test_singleton_is_functional(self):
        packager = get_skill_packager()
        pkg = packager.create_simple_package(
            name="Singleton Test",
            description="Testing the singleton packager instance",
            system_prompt="Help.",
        )
        assert pkg.name == "Singleton Test"
