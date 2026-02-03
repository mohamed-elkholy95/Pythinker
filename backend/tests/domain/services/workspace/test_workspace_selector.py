"""Unit tests for WorkspaceSelector."""

import pytest

from app.domain.services.workspace.workspace_selector import WorkspaceSelector
from app.domain.services.workspace.workspace_templates import (
    RESEARCH_TEMPLATE,
)


class TestWorkspaceSelector:
    """Test WorkspaceSelector template selection logic."""

    @pytest.fixture
    def selector(self):
        """Create a WorkspaceSelector instance."""
        return WorkspaceSelector()

    # Research template tests
    def test_select_research_template_explicit(self, selector):
        """Test research template selection with explicit keyword."""
        task = "Research machine learning algorithms"
        template = selector.select_template(task)
        assert template.name == "research"
        assert template == RESEARCH_TEMPLATE

    def test_select_research_template_investigate(self, selector):
        """Test research template selection with 'investigate' keyword."""
        task = "Investigate cloud computing providers"
        template = selector.select_template(task)
        assert template.name == "research"

    def test_select_research_find_information(self, selector):
        """Test research template with 'find information' phrase."""
        task = "Find information about cloud security best practices"
        template = selector.select_template(task)
        assert template.name == "research"

    def test_select_research_gather_data(self, selector):
        """Test research template with 'gather data' phrase."""
        task = "Gather data about market trends"
        template = selector.select_template(task)
        assert template.name == "research"

    # Data analysis template tests - use specific keywords
    def test_select_data_analysis_data_analysis_phrase(self, selector):
        """Test data analysis template with 'data analysis' phrase."""
        task = "Perform data analysis on the sales CSV file"
        template = selector.select_template(task)
        assert template.name == "data_analysis"

    def test_select_data_analysis_process_dataset(self, selector):
        """Test data analysis template with 'process dataset' phrase."""
        task = "Process dataset containing customer transactions"
        template = selector.select_template(task)
        assert template.name == "data_analysis"

    def test_select_data_analysis_visualize(self, selector):
        """Test data analysis template with visualize keyword."""
        task = "Visualize the customer demographics data"
        template = selector.select_template(task)
        assert template.name == "data_analysis"

    def test_select_data_analysis_statistics(self, selector):
        """Test data analysis template with statistics keyword."""
        task = "Calculate statistics for the experiment results"
        template = selector.select_template(task)
        assert template.name == "data_analysis"

    # Code project template tests - use specific keywords
    def test_select_code_project_write_code(self, selector):
        """Test code project template with 'write code' phrase."""
        task = "Write code for a REST API with authentication"
        template = selector.select_template(task)
        assert template.name == "code_project"

    def test_select_code_project_develop(self, selector):
        """Test code project template with develop keyword."""
        task = "Develop a React application with TypeScript"
        template = selector.select_template(task)
        assert template.name == "code_project"

    def test_select_code_project_implement(self, selector):
        """Test code project template with implement keyword."""
        task = "Implement user authentication system"
        template = selector.select_template(task)
        assert template.name == "code_project"

    def test_select_code_project_build(self, selector):
        """Test code project template with build keyword."""
        task = "Build a microservices architecture"
        template = selector.select_template(task)
        assert template.name == "code_project"

    def test_select_code_project_create_application(self, selector):
        """Test code project template with 'create application' phrase."""
        task = "Create application for managing inventory"
        template = selector.select_template(task)
        assert template.name == "code_project"

    # Document generation template tests - use specific keywords
    def test_select_document_write_document(self, selector):
        """Test document generation template with 'write document' phrase."""
        task = "Write document about API best practices"
        template = selector.select_template(task)
        assert template.name == "document_generation"

    def test_select_document_create_report(self, selector):
        """Test document generation template with 'create report' phrase."""
        task = "Create report on quarterly performance"
        template = selector.select_template(task)
        assert template.name == "document_generation"

    def test_select_document_generate_documentation(self, selector):
        """Test document generation template with 'generate documentation' phrase."""
        task = "Generate documentation for the API endpoints"
        template = selector.select_template(task)
        assert template.name == "document_generation"

    def test_select_document_compose(self, selector):
        """Test document generation template with compose keyword."""
        task = "Compose a technical proposal for the new system"
        template = selector.select_template(task)
        assert template.name == "document_generation"

    # Edge cases and defaults
    def test_select_default_template_simple_task(self, selector):
        """Test default template for simple tasks."""
        task = "What is 2+2?"
        template = selector.select_template(task)
        assert template.name == "research"  # Default fallback

    def test_select_default_template_no_keywords(self, selector):
        """Test default template when no keywords match."""
        task = "Hello, how are you?"
        template = selector.select_template(task)
        assert template.name == "research"  # Default fallback

    def test_select_template_empty_string(self, selector):
        """Test template selection with empty string."""
        task = ""
        template = selector.select_template(task)
        assert template.name == "research"  # Default fallback

    def test_select_template_whitespace(self, selector):
        """Test template selection with only whitespace."""
        task = "   \n\t  "
        template = selector.select_template(task)
        assert template.name == "research"  # Default fallback

    # Case sensitivity tests
    def test_select_template_case_insensitive(self, selector):
        """Test that keyword matching is case-insensitive."""
        tasks = [
            "RESEARCH machine learning",
            "Research Machine Learning",
            "research MACHINE LEARNING",
        ]
        for task in tasks:
            template = selector.select_template(task)
            assert template.name == "research"

    # Multiple keyword tests
    def test_select_template_multiple_keywords_research_wins(self, selector):
        """Test template selection with multiple matching keywords where research wins."""
        # Research has "analyze" keyword so if task has both research and analyze keywords,
        # it scores higher on research
        task = "Research and investigate data patterns"
        template = selector.select_template(task)
        assert template.name == "research"

    def test_select_template_data_analysis_with_more_keywords(self, selector):
        """Test that template with more keyword matches wins."""
        # Task with multiple data analysis keywords
        task = "Analyze data and calculate statistics with visualize features"
        template = selector.select_template(task)
        assert template.name == "data_analysis"

    # Template attribute validation
    def test_selected_template_has_folders(self, selector):
        """Test that selected template has folder structure."""
        task = "Research AI trends"
        template = selector.select_template(task)
        assert hasattr(template, "folders")
        assert len(template.folders) > 0
        assert isinstance(template.folders, dict)

    def test_selected_template_has_description(self, selector):
        """Test that selected template has description."""
        task = "Analyze data from CSV"
        template = selector.select_template(task)
        assert hasattr(template, "description")
        assert len(template.description) > 0

    def test_selected_template_has_trigger_keywords(self, selector):
        """Test that selected template has trigger keywords."""
        task = "Build a web application"
        template = selector.select_template(task)
        assert hasattr(template, "trigger_keywords")
        assert len(template.trigger_keywords) > 0

    def test_selected_template_has_readme_content(self, selector):
        """Test that selected template has readme content."""
        task = "Develop a mobile app"
        template = selector.select_template(task)
        assert hasattr(template, "readme_content")
        assert len(template.readme_content) > 0

    # Real-world task examples
    def test_real_world_research_task(self, selector):
        """Test with realistic research task description."""
        task = (
            "Research the current state of quantum computing and investigate "
            "its potential applications in cryptography. Find information from "
            "recent academic papers and industry reports."
        )
        template = selector.select_template(task)
        assert template.name == "research"

    def test_real_world_data_analysis_task(self, selector):
        """Test with realistic data analysis task description."""
        task = (
            "Analyze data from customer behavior dataset, "
            "calculate statistics showing purchase patterns, and "
            "visualize key metrics."
        )
        template = selector.select_template(task)
        assert template.name == "data_analysis"

    def test_real_world_code_project_task(self, selector):
        """Test with realistic code project task description."""
        task = (
            "Develop a full-stack web application and implement "
            "CRUD operations. Build REST API with proper authentication."
        )
        template = selector.select_template(task)
        assert template.name == "code_project"

    def test_real_world_document_task(self, selector):
        """Test with realistic document generation task description."""
        task = (
            "Write document for the API including endpoint descriptions. "
            "Generate documentation with request/response examples."
        )
        template = selector.select_template(task)
        assert template.name == "document_generation"

    # Performance test
    def test_template_selection_is_fast(self, selector):
        """Test that template selection completes quickly."""
        import time

        task = "Research machine learning algorithms and create a report"
        start = time.time()
        for _ in range(100):
            selector.select_template(task)
        elapsed = time.time() - start
        # 100 selections should complete in under 100ms
        assert elapsed < 0.1, f"Template selection too slow: {elapsed}s for 100 iterations"

    # Unicode and special characters
    def test_template_selection_with_unicode(self, selector):
        """Test template selection with unicode characters."""
        task = "Research résumé parsing techniques and naïve Bayes"
        template = selector.select_template(task)
        assert template.name == "research"

    def test_template_selection_with_special_chars(self, selector):
        """Test template selection with special characters."""
        task = "Analyze data@#$ and visualize results!!!"
        template = selector.select_template(task)
        assert template.name == "data_analysis"
