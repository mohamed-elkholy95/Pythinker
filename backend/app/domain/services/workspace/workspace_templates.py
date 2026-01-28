"""Workspace templates for different task types."""
from typing import Dict, List
from dataclasses import dataclass


@dataclass
class WorkspaceTemplate:
    """Template for workspace structure"""
    name: str
    description: str
    folders: Dict[str, str]  # folder_name -> purpose
    readme_content: str
    trigger_keywords: List[str]


RESEARCH_TEMPLATE = WorkspaceTemplate(
    name="research",
    description="Deep research and information gathering",
    folders={
        "inputs": "Original data, files, and resources",
        "research": "Web research outputs, scraped content, PDFs",
        "analysis": "Analysis notes and intermediate findings",
        "deliverables": "Final reports, summaries, bibliographies",
        "logs": "Execution logs and debug info",
    },
    readme_content="""# Research Workspace

## Structure
- `/inputs` - Source materials and data
- `/research` - Web research outputs
- `/analysis` - Analysis and notes
- `/deliverables` - Final outputs
- `/logs` - Execution logs

## Usage
Place source materials in `/inputs`. Final reports go in `/deliverables`.
""",
    trigger_keywords=["research", "investigate", "find information", "gather data", "analyze"]
)


DATA_ANALYSIS_TEMPLATE = WorkspaceTemplate(
    name="data_analysis",
    description="Data processing and analysis",
    folders={
        "raw_data": "Raw input data files",
        "processed_data": "Cleaned and processed datasets",
        "analysis": "Analysis scripts and notebooks",
        "visualizations": "Charts, graphs, plots",
        "deliverables": "Final reports and summaries",
        "logs": "Execution logs",
    },
    readme_content="""# Data Analysis Workspace

## Structure
- `/raw_data` - Original datasets
- `/processed_data` - Cleaned data
- `/analysis` - Analysis code
- `/visualizations` - Charts and graphs
- `/deliverables` - Final deliverables
- `/logs` - Logs

## Workflow
1. Place raw data in `/raw_data`
2. Process and clean to `/processed_data`
3. Run analysis from `/analysis`
4. Save outputs to `/deliverables`
""",
    trigger_keywords=["analyze data", "process dataset", "data analysis", "statistics", "visualize"]
)


CODE_PROJECT_TEMPLATE = WorkspaceTemplate(
    name="code_project",
    description="Software development project",
    folders={
        "src": "Source code files",
        "tests": "Test files",
        "docs": "Documentation",
        "data": "Data files and assets",
        "deliverables": "Build outputs and releases",
        "logs": "Build and execution logs",
    },
    readme_content="""# Code Project Workspace

## Structure
- `/src` - Source code
- `/tests` - Unit and integration tests
- `/docs` - Documentation
- `/data` - Data files
- `/deliverables` - Builds and releases
- `/logs` - Logs

## Development
Write code in `/src`, tests in `/tests`. Build outputs go to `/deliverables`.
""",
    trigger_keywords=["write code", "develop", "build", "implement", "create application"]
)


DOCUMENT_GENERATION_TEMPLATE = WorkspaceTemplate(
    name="document_generation",
    description="Document writing and generation",
    folders={
        "inputs": "Source materials and references",
        "drafts": "Work-in-progress drafts",
        "assets": "Images, diagrams, supporting files",
        "deliverables": "Final documents",
        "logs": "Execution logs",
    },
    readme_content="""# Document Generation Workspace

## Structure
- `/inputs` - Source materials
- `/drafts` - Work in progress
- `/assets` - Images and diagrams
- `/deliverables` - Final documents
- `/logs` - Logs

## Writing Process
1. Gather sources in `/inputs`
2. Create drafts in `/drafts`
3. Add visuals to `/assets`
4. Finalize in `/deliverables`
""",
    trigger_keywords=["write document", "create report", "generate documentation", "compose"]
)


# Template registry
WORKSPACE_TEMPLATES = {
    "research": RESEARCH_TEMPLATE,
    "data_analysis": DATA_ANALYSIS_TEMPLATE,
    "code_project": CODE_PROJECT_TEMPLATE,
    "document_generation": DOCUMENT_GENERATION_TEMPLATE,
}


def get_template(name: str) -> WorkspaceTemplate:
    """Get workspace template by name"""
    return WORKSPACE_TEMPLATES.get(name)


def get_all_templates() -> List[WorkspaceTemplate]:
    """Get all available templates"""
    return list(WORKSPACE_TEMPLATES.values())
