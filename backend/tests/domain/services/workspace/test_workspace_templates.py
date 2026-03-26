"""Tests for workspace templates."""

import pytest

from app.domain.services.workspace.workspace_templates import (
    CODE_PROJECT_TEMPLATE,
    DATA_ANALYSIS_TEMPLATE,
    DOCUMENT_GENERATION_TEMPLATE,
    RESEARCH_TEMPLATE,
    WORKSPACE_TEMPLATES,
    WorkspaceTemplate,
    get_all_templates,
    get_template,
)


class TestWorkspaceTemplate:
    """Tests for WorkspaceTemplate dataclass."""

    def test_create_template(self):
        template = WorkspaceTemplate(
            name="test",
            description="Test template",
            folders={"src": "Source code"},
            readme_content="# Test",
            trigger_keywords=["test"],
        )
        assert template.name == "test"
        assert template.description == "Test template"
        assert template.folders == {"src": "Source code"}
        assert template.readme_content == "# Test"
        assert template.trigger_keywords == ["test"]

    def test_empty_folders(self):
        template = WorkspaceTemplate(
            name="minimal",
            description="Minimal",
            folders={},
            readme_content="",
            trigger_keywords=[],
        )
        assert template.folders == {}
        assert template.trigger_keywords == []

    def test_multiple_folders(self):
        folders = {"a": "Folder A", "b": "Folder B", "c": "Folder C"}
        template = WorkspaceTemplate(
            name="multi",
            description="Multi",
            folders=folders,
            readme_content="# Multi",
            trigger_keywords=["x", "y"],
        )
        assert len(template.folders) == 3
        assert "a" in template.folders


class TestResearchTemplate:
    """Tests for RESEARCH_TEMPLATE."""

    def test_name(self):
        assert RESEARCH_TEMPLATE.name == "research"

    def test_has_required_folders(self):
        expected = {"inputs", "research", "analysis", "deliverables", "logs"}
        assert set(RESEARCH_TEMPLATE.folders.keys()) == expected

    def test_has_trigger_keywords(self):
        assert len(RESEARCH_TEMPLATE.trigger_keywords) > 0
        assert "research" in RESEARCH_TEMPLATE.trigger_keywords

    def test_readme_content_not_empty(self):
        assert len(RESEARCH_TEMPLATE.readme_content) > 0
        assert "Research" in RESEARCH_TEMPLATE.readme_content


class TestDataAnalysisTemplate:
    """Tests for DATA_ANALYSIS_TEMPLATE."""

    def test_name(self):
        assert DATA_ANALYSIS_TEMPLATE.name == "data_analysis"

    def test_has_required_folders(self):
        expected = {"raw_data", "processed_data", "analysis", "visualizations", "deliverables", "logs"}
        assert set(DATA_ANALYSIS_TEMPLATE.folders.keys()) == expected

    def test_has_trigger_keywords(self):
        assert "data analysis" in DATA_ANALYSIS_TEMPLATE.trigger_keywords


class TestCodeProjectTemplate:
    """Tests for CODE_PROJECT_TEMPLATE."""

    def test_name(self):
        assert CODE_PROJECT_TEMPLATE.name == "code_project"

    def test_has_required_folders(self):
        expected = {"src", "tests", "docs", "data", "deliverables", "logs"}
        assert set(CODE_PROJECT_TEMPLATE.folders.keys()) == expected

    def test_has_trigger_keywords(self):
        assert "write code" in CODE_PROJECT_TEMPLATE.trigger_keywords


class TestDocumentGenerationTemplate:
    """Tests for DOCUMENT_GENERATION_TEMPLATE."""

    def test_name(self):
        assert DOCUMENT_GENERATION_TEMPLATE.name == "document_generation"

    def test_has_required_folders(self):
        expected = {"inputs", "drafts", "assets", "deliverables", "logs"}
        assert set(DOCUMENT_GENERATION_TEMPLATE.folders.keys()) == expected

    def test_has_trigger_keywords(self):
        assert "write document" in DOCUMENT_GENERATION_TEMPLATE.trigger_keywords


class TestWorkspaceTemplateRegistry:
    """Tests for WORKSPACE_TEMPLATES registry."""

    def test_all_templates_registered(self):
        expected_names = {"research", "data_analysis", "code_project", "document_generation"}
        assert set(WORKSPACE_TEMPLATES.keys()) == expected_names

    def test_registry_values_are_templates(self):
        for name, template in WORKSPACE_TEMPLATES.items():
            assert isinstance(template, WorkspaceTemplate)
            assert template.name == name


class TestGetTemplate:
    """Tests for get_template function."""

    def test_get_existing_template(self):
        template = get_template("research")
        assert template is RESEARCH_TEMPLATE

    def test_get_all_known_templates(self):
        for name in ["research", "data_analysis", "code_project", "document_generation"]:
            assert get_template(name) is not None

    def test_get_nonexistent_template_returns_none(self):
        result = get_template("nonexistent")
        assert result is None

    def test_get_empty_string_returns_none(self):
        result = get_template("")
        assert result is None


class TestGetAllTemplates:
    """Tests for get_all_templates function."""

    def test_returns_list(self):
        result = get_all_templates()
        assert isinstance(result, list)

    def test_returns_all_templates(self):
        result = get_all_templates()
        assert len(result) == 4

    def test_all_items_are_templates(self):
        for template in get_all_templates():
            assert isinstance(template, WorkspaceTemplate)

    def test_contains_all_known_templates(self):
        templates = get_all_templates()
        names = {t.name for t in templates}
        assert names == {"research", "data_analysis", "code_project", "document_generation"}


class TestTemplateConsistency:
    """Cross-template consistency checks."""

    @pytest.mark.parametrize("template", get_all_templates(), ids=lambda t: t.name)
    def test_all_templates_have_deliverables_folder(self, template):
        assert "deliverables" in template.folders

    @pytest.mark.parametrize("template", get_all_templates(), ids=lambda t: t.name)
    def test_all_templates_have_logs_folder(self, template):
        assert "logs" in template.folders

    @pytest.mark.parametrize("template", get_all_templates(), ids=lambda t: t.name)
    def test_all_templates_have_nonempty_description(self, template):
        assert len(template.description) > 0

    @pytest.mark.parametrize("template", get_all_templates(), ids=lambda t: t.name)
    def test_all_templates_have_readme(self, template):
        assert len(template.readme_content) > 10

    @pytest.mark.parametrize("template", get_all_templates(), ids=lambda t: t.name)
    def test_all_templates_have_at_least_one_keyword(self, template):
        assert len(template.trigger_keywords) >= 1
