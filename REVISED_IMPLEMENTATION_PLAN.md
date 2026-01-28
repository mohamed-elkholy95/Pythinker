# Revised Implementation Plan: Multi-Task Autonomous Enhancements
**Project**: Pythinker AI Agent System
**Timeline**: 11-13 weeks (phased rollout)
**Approach**: Additive enhancements leveraging existing infrastructure

---

## 📋 Executive Summary

This revised plan integrates multi-task capabilities, enhanced monitoring, and workspace management into Pythinker while **leveraging existing systems** (usage tracking, orchestration, event sourcing). Key changes from original:

✅ **Reuses** existing UsageRecord instead of new CreditBudget
✅ **Extends** existing AgentRegistry instead of creating new orchestration
✅ **Adds** missing API routes and frontend types
✅ **Includes** database migrations and error handling
✅ **Realistic** 11-13 week timeline with built-in buffer

---

## 🏗️ Architecture Alignment

### Existing Infrastructure to Leverage
```
✅ backend/app/domain/models/usage.py           → Extend for budget tracking
✅ backend/app/domain/services/orchestration/   → Add research agent here
✅ backend/app/domain/services/usage/           → Extend for metrics
✅ backend/app/infrastructure/storage/mongodb.py → Add GridFS
✅ backend/app/domain/models/event.py           → Polymorphic events ready
```

### New Infrastructure to Build
```
🆕 backend/app/domain/services/agents/context_manager.py
🆕 backend/app/domain/services/screenshot/
🆕 backend/app/domain/services/workspace/
🆕 backend/app/domain/services/validation/
🆕 backend/app/interfaces/api/routes/screenshot.py
🆕 frontend/src/components/monitoring/
```

---

## Phase 1: Foundation & Models (Weeks 1-3)

### Week 1: Core Models & Event System

#### 1.1 Event System Extensions

**File**: `backend/app/domain/models/event.py` (MODIFY)

Add new event types to existing polymorphic system:

```python
# Add after line 238 (after ReflectionEvent)

class MultiTaskEvent(BaseEvent):
    """Multi-task challenge progress event"""
    type: Literal["multi_task"] = "multi_task"
    challenge_id: str
    action: str  # "started", "task_switching", "task_completed", "challenge_completed"
    current_task_index: int
    total_tasks: int
    current_task: Optional[str] = None  # Task description
    progress_percentage: float = 0.0
    elapsed_time_seconds: Optional[float] = None


class WorkspaceEvent(BaseEvent):
    """Workspace structure and organization event"""
    type: Literal["workspace"] = "workspace"
    action: str  # "initialized", "organized", "validated", "deliverable_added"
    workspace_type: Optional[str] = None  # "research", "code_project", "data_analysis"
    structure: Optional[Dict[str, str]] = None  # folder_name -> purpose
    files_organized: int = 0
    deliverables_count: int = 0
    manifest_path: Optional[str] = None


class ScreenshotEvent(BaseEvent):
    """Screenshot capture event"""
    type: Literal["screenshot"] = "screenshot"
    screenshot_id: str
    action: str  # "captured", "annotated", "thumbnail_generated"
    capture_reason: str  # "step_start", "step_complete", "error", "verification"
    tool_name: Optional[str] = None
    thumbnail_url: Optional[str] = None  # GridFS URL or base64
    full_image_url: Optional[str] = None


class BudgetEvent(BaseEvent):
    """Budget threshold and exhaustion events"""
    type: Literal["budget"] = "budget"
    action: str  # "warning", "exhausted", "resumed"
    budget_limit: float  # USD
    consumed: float  # USD
    remaining: float  # USD
    percentage_used: float
    warning_threshold: float = 0.8
    session_paused: bool = False


# Update ToolEvent (add after line 119)
class ToolEvent(BaseEvent):
    """Tool related events"""
    # ... existing fields ...

    # Enhanced command display (Phase 3)
    display_command: Optional[str] = None  # "Searching 'machine learning'"
    command_category: Optional[str] = None  # "search", "browse", "file", "shell", "code"
    command_summary: Optional[str] = None  # Short summary for UI badges

    # Screenshot association (Phase 2)
    screenshot_id: Optional[str] = None  # Link to screenshot if captured


# Update AgentEvent union (line 249)
AgentEvent = Union[
    ErrorEvent,
    PlanEvent,
    ToolEvent,
    StepEvent,
    MessageEvent,
    DoneEvent,
    TitleEvent,
    WaitEvent,
    KnowledgeEvent,
    DatasourceEvent,
    IdleEvent,
    MCPHealthEvent,
    ModeChangeEvent,
    SuggestionEvent,
    ReportEvent,
    StreamEvent,
    VerificationEvent,
    ReflectionEvent,
    PathEvent,
    MultiTaskEvent,      # 🆕
    WorkspaceEvent,      # 🆕
    ScreenshotEvent,     # 🆕
    BudgetEvent,         # 🆕
]
```

**Testing**:
```bash
pytest tests/domain/models/test_events.py::test_new_event_types
```

---

#### 1.2 Multi-Task Domain Models

**File**: `backend/app/domain/models/multi_task.py` (NEW)

```python
"""Multi-task challenge domain models."""
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime, UTC
from enum import Enum
import uuid


class TaskStatus(str, Enum):
    """Status of individual task within challenge"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class DeliverableType(str, Enum):
    """Type of deliverable"""
    FILE = "file"
    DIRECTORY = "directory"
    REPORT = "report"
    DATA = "data"
    CODE = "code"
    ARTIFACT = "artifact"


class Deliverable(BaseModel):
    """Expected deliverable for a task"""
    name: str
    type: DeliverableType
    path: str  # Expected path in workspace
    description: str
    required: bool = True
    validation_criteria: Optional[str] = None


class TaskDefinition(BaseModel):
    """Definition of a single task within multi-task challenge"""
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    title: str
    description: str
    deliverables: List[Deliverable] = []
    workspace_folder: Optional[str] = None  # e.g., "task_1_research"
    validation_criteria: Optional[str] = None
    estimated_complexity: float = 0.5  # 0.0-1.0
    depends_on: List[str] = []  # Task IDs this depends on
    status: TaskStatus = TaskStatus.PENDING

    # Execution tracking
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    iterations_used: int = 0


class TaskResult(BaseModel):
    """Result of task execution"""
    task_id: str
    status: TaskStatus
    deliverables_created: List[str] = []  # File paths
    validation_passed: bool = False
    validation_report: Optional[str] = None
    error_message: Optional[str] = None
    duration_seconds: float
    iterations_used: int


class MultiTaskChallenge(BaseModel):
    """Container for multi-task challenge execution"""
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:16])
    title: str
    description: str
    tasks: List[TaskDefinition] = []

    # Workspace configuration
    workspace_root: str = "/workspace"
    workspace_template: Optional[str] = None  # "research", "data_analysis", "code_project"

    # Progress tracking
    current_task_index: int = 0
    completed_tasks: List[str] = []  # Task IDs
    failed_tasks: List[str] = []  # Task IDs

    # Execution metadata
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    total_duration_seconds: Optional[float] = None

    # Results
    task_results: List[TaskResult] = []
    overall_success: bool = False

    def get_current_task(self) -> Optional[TaskDefinition]:
        """Get currently active task"""
        if 0 <= self.current_task_index < len(self.tasks):
            return self.tasks[self.current_task_index]
        return None

    def get_progress_percentage(self) -> float:
        """Calculate overall progress"""
        if not self.tasks:
            return 0.0
        return (len(self.completed_tasks) / len(self.tasks)) * 100
```

**Testing**:
```bash
pytest tests/domain/models/test_multi_task.py
```

---

#### 1.3 Session Model Extensions

**File**: `backend/app/domain/models/session.py` (MODIFY)

Add fields after line 58 (after git_remote):

```python
    # Multi-task challenge tracking (Phase 1)
    multi_task_challenge: Optional[MultiTaskChallenge] = None
    workspace_structure: Optional[Dict[str, str]] = None  # folder -> purpose

    # Budget tracking (leverages existing usage system)
    budget_limit: Optional[float] = None  # USD limit
    budget_warning_threshold: float = 0.8  # Warn at 80%
    budget_paused: bool = False  # Session paused due to budget

    # Execution metadata
    iteration_limit_override: Optional[int] = None  # Override default iterations
    complexity_score: Optional[float] = None  # Assessed task complexity (0.0-1.0)
```

**Import addition** (line 8):
```python
from app.domain.models.multi_task import MultiTaskChallenge
```

---

#### 1.4 Usage Model Extensions

**File**: `backend/app/domain/models/usage.py` (MODIFY)

Add after SessionUsage class (line 73):

```python
class SessionMetrics(BaseModel):
    """Enhanced session metrics for monitoring dashboard.

    Aggregates performance and activity metrics beyond just token usage.
    """
    session_id: str
    user_id: str

    # Time metrics
    duration_seconds: Optional[float] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # Task metrics
    tasks_completed: int = 0
    tasks_failed: int = 0
    steps_executed: int = 0

    # Tool usage
    tool_usage_stats: Dict[str, int] = {}  # tool_name -> count
    avg_step_duration_seconds: float = 0.0

    # Performance metrics
    total_tokens_used: int = 0
    error_count: int = 0
    warning_count: int = 0
    reflection_count: int = 0
    verification_count: int = 0

    # Budget tracking (references UsageRecord)
    budget_limit: Optional[float] = None
    budget_consumed: float = 0.0
    budget_warnings_triggered: int = 0

    # Screenshot metrics
    screenshots_captured: int = 0

    # Deliverables
    files_created: int = 0
    files_modified: int = 0

    # Updated timestamp
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
```

---

### Week 2: Context Management & GridFS Setup

#### 2.1 Context Manager

**File**: `backend/app/domain/services/agents/context_manager.py` (NEW)

```python
"""Context retention system for execution continuity across steps.

Solves the problem where ExecutionAgent loses context between steps,
requiring re-reading of files created in previous steps.
"""

from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field
from datetime import datetime, UTC
import logging

logger = logging.getLogger(__name__)


@dataclass
class FileContext:
    """Context for a file that was created or read"""
    path: str
    operation: str  # "created", "read", "modified"
    timestamp: datetime
    size_bytes: Optional[int] = None
    content_summary: Optional[str] = None  # Brief description
    is_deliverable: bool = False


@dataclass
class ToolContext:
    """Context from tool execution"""
    tool_name: str
    timestamp: datetime
    summary: str  # Brief result summary
    key_findings: List[str] = field(default_factory=list)
    urls_visited: List[str] = field(default_factory=list)
    files_affected: List[str] = field(default_factory=list)


@dataclass
class WorkingContext:
    """Accumulated context during execution"""
    files: Dict[str, FileContext] = field(default_factory=dict)  # path -> context
    tools: List[ToolContext] = field(default_factory=list)
    key_facts: List[str] = field(default_factory=list)  # Important discoveries
    deliverables: List[str] = field(default_factory=list)  # Completed deliverables
    total_tokens: int = 0  # Estimated context size


class ContextManager:
    """Manages working context across execution steps.

    Features:
    - Tracks files created/read to avoid re-reading
    - Stores key findings from research/browsing
    - Generates token-aware context summaries
    - Prioritizes recent and important context
    """

    def __init__(self, max_context_tokens: int = 8000):
        self._context = WorkingContext()
        self._max_tokens = max_context_tokens
        self._token_per_char = 0.25  # Conservative estimate

    def track_file_operation(
        self,
        path: str,
        operation: str,
        size_bytes: Optional[int] = None,
        content_summary: Optional[str] = None,
        is_deliverable: bool = False,
    ):
        """Track file creation/read/modification"""
        self._context.files[path] = FileContext(
            path=path,
            operation=operation,
            timestamp=datetime.now(UTC),
            size_bytes=size_bytes,
            content_summary=content_summary,
            is_deliverable=is_deliverable,
        )
        logger.debug(f"Tracked file {operation}: {path}")

    def track_tool_execution(
        self,
        tool_name: str,
        summary: str,
        key_findings: List[str] = None,
        urls_visited: List[str] = None,
        files_affected: List[str] = None,
    ):
        """Track tool execution results"""
        self._context.tools.append(ToolContext(
            tool_name=tool_name,
            timestamp=datetime.now(UTC),
            summary=summary,
            key_findings=key_findings or [],
            urls_visited=urls_visited or [],
            files_affected=files_affected or [],
        ))
        logger.debug(f"Tracked tool execution: {tool_name}")

    def add_key_fact(self, fact: str):
        """Add important discovery/fact"""
        if fact not in self._context.key_facts:
            self._context.key_facts.append(fact)

    def mark_deliverable_complete(self, deliverable_path: str):
        """Mark a deliverable as completed"""
        if deliverable_path not in self._context.deliverables:
            self._context.deliverables.append(deliverable_path)
            # Also mark in files context
            if deliverable_path in self._context.files:
                self._context.files[deliverable_path].is_deliverable = True

    def get_context_summary(self, max_tokens: Optional[int] = None) -> str:
        """Generate token-aware context summary for prompt injection.

        Prioritizes:
        1. Deliverables (most important)
        2. Recent tool executions
        3. Key facts
        4. File operations
        """
        max_tokens = max_tokens or self._max_tokens

        sections = []

        # 1. Deliverables (highest priority)
        if self._context.deliverables:
            sections.append("## Completed Deliverables")
            for path in self._context.deliverables:
                sections.append(f"- {path}")
            sections.append("")

        # 2. Files context
        if self._context.files:
            sections.append("## Working Files")
            # Prioritize deliverables and recently modified
            sorted_files = sorted(
                self._context.files.values(),
                key=lambda f: (f.is_deliverable, f.timestamp),
                reverse=True
            )
            for file_ctx in sorted_files[:20]:  # Limit to 20 most important
                summary = file_ctx.content_summary or "No summary"
                sections.append(f"- {file_ctx.path} ({file_ctx.operation}): {summary}")
            sections.append("")

        # 3. Key facts
        if self._context.key_facts:
            sections.append("## Key Findings")
            for fact in self._context.key_facts[-10:]:  # Last 10 facts
                sections.append(f"- {fact}")
            sections.append("")

        # 4. Recent tool executions
        if self._context.tools:
            sections.append("## Recent Actions")
            for tool_ctx in self._context.tools[-5:]:  # Last 5 tools
                sections.append(f"- {tool_ctx.tool_name}: {tool_ctx.summary}")
            sections.append("")

        full_summary = "\n".join(sections)

        # Token limit enforcement (truncate if needed)
        estimated_tokens = int(len(full_summary) * self._token_per_char)
        if estimated_tokens > max_tokens:
            # Truncate proportionally
            char_limit = int(max_tokens / self._token_per_char)
            full_summary = full_summary[:char_limit] + "\n... (truncated)"

        return full_summary

    def get_files_created(self) -> List[str]:
        """Get list of files created in this session"""
        return [
            path for path, ctx in self._context.files.items()
            if ctx.operation == "created"
        ]

    def get_deliverables(self) -> List[str]:
        """Get list of completed deliverables"""
        return self._context.deliverables.copy()

    def clear(self):
        """Clear all context (use at task boundaries)"""
        self._context = WorkingContext()
        logger.info("Context cleared")
```

**Testing**:
```bash
pytest tests/domain/services/agents/test_context_manager.py
```

---

#### 2.2 GridFS Setup for Screenshots

**File**: `backend/app/infrastructure/storage/mongodb.py` (MODIFY)

Add GridFS initialization after MongoClient setup:

```python
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorGridFSBucket
import gridfs

class MongoDBClient:
    def __init__(self, connection_string: str, database_name: str):
        self.client = AsyncIOMotorClient(connection_string)
        self.db = self.client[database_name]

        # Initialize GridFS bucket for screenshot storage (Phase 2)
        self.screenshot_bucket = AsyncIOMotorGridFSBucket(
            self.db,
            bucket_name="screenshots"
        )

        # Initialize GridFS bucket for file artifacts (Phase 2)
        self.artifacts_bucket = AsyncIOMotorGridFSBucket(
            self.db,
            bucket_name="artifacts"
        )

    async def store_screenshot(
        self,
        image_data: bytes,
        filename: str,
        metadata: dict,
    ) -> str:
        """Store screenshot in GridFS and return file ID"""
        file_id = await self.screenshot_bucket.upload_from_stream(
            filename,
            image_data,
            metadata=metadata
        )
        return str(file_id)

    async def get_screenshot(self, file_id: str) -> bytes:
        """Retrieve screenshot from GridFS"""
        grid_out = await self.screenshot_bucket.open_download_stream(
            ObjectId(file_id)
        )
        return await grid_out.read()
```

**Migration script**: `backend/migrations/002_add_gridfs_indexes.py` (NEW)

```python
"""Add GridFS indexes for screenshots and artifacts."""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import get_settings

async def migrate():
    settings = get_settings()
    client = AsyncIOMotorClient(settings.MONGODB_URI)
    db = client[settings.MONGODB_DATABASE]

    # Create indexes for screenshots.files collection
    await db["screenshots.files"].create_index("uploadDate")
    await db["screenshots.files"].create_index("metadata.session_id")
    await db["screenshots.files"].create_index("metadata.task_id")

    print("✅ GridFS indexes created")

if __name__ == "__main__":
    asyncio.run(migrate())
```

---

### Week 3: Workspace Management

#### 3.1 Workspace Templates & Selector

**File**: `backend/app/domain/services/workspace/workspace_templates.py` (NEW)

```python
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
```

**File**: `backend/app/domain/services/workspace/workspace_selector.py` (NEW)

```python
"""Workspace template selection based on task analysis."""
from typing import Optional
from app.domain.services.workspace.workspace_templates import (
    get_template,
    get_all_templates,
    WorkspaceTemplate,
)
import logging

logger = logging.getLogger(__name__)


class WorkspaceSelector:
    """Selects appropriate workspace template based on task description."""

    def select_template(self, task_description: str) -> WorkspaceTemplate:
        """Select best workspace template for task.

        Args:
            task_description: User's task description

        Returns:
            Best matching WorkspaceTemplate
        """
        task_lower = task_description.lower()

        # Score each template
        scores = {}
        for template in get_all_templates():
            score = 0
            for keyword in template.trigger_keywords:
                if keyword.lower() in task_lower:
                    score += 1
            scores[template.name] = score

        # Get highest scoring template
        if scores:
            best_template_name = max(scores, key=scores.get)
            best_score = scores[best_template_name]

            # If score > 0, use that template
            if best_score > 0:
                template = get_template(best_template_name)
                logger.info(f"Selected workspace template: {template.name} (score: {best_score})")
                return template

        # Default to research template
        logger.info("No specific template matched, using default: research")
        return get_template("research")
```

---

**File**: `backend/app/domain/services/workspace/workspace_organizer.py` (NEW)

```python
"""Workspace organization and deliverable tracking."""
from typing import Dict, List, Optional
from pathlib import Path
import logging
from app.domain.services.workspace.workspace_templates import WorkspaceTemplate
from app.domain.external.sandbox import Sandbox

logger = logging.getLogger(__name__)


class WorkspaceOrganizer:
    """Organizes workspace structure and tracks deliverables."""

    def __init__(self, sandbox: Sandbox, workspace_root: str = "/workspace"):
        self._sandbox = sandbox
        self._workspace_root = workspace_root
        self._deliverables: List[str] = []

    async def initialize_workspace(
        self,
        template: WorkspaceTemplate
    ) -> Dict[str, str]:
        """Initialize workspace structure from template.

        Returns:
            Dict mapping folder names to their purposes
        """
        logger.info(f"Initializing workspace with template: {template.name}")

        # Create folders
        for folder_name, purpose in template.folders.items():
            folder_path = f"{self._workspace_root}/{folder_name}"

            # Create directory
            await self._sandbox.execute_code(
                language="python",
                code=f"""
import os
os.makedirs("{folder_path}", exist_ok=True)
"""
            )

            logger.debug(f"Created folder: {folder_path} ({purpose})")

        # Create README
        readme_path = f"{self._workspace_root}/README.md"
        await self._sandbox.execute_code(
            language="python",
            code=f"""
with open("{readme_path}", "w") as f:
    f.write('''{template.readme_content}''')
"""
        )

        logger.info(f"Workspace initialized: {len(template.folders)} folders created")
        return template.folders

    def add_deliverable(self, file_path: str):
        """Track a file as a deliverable"""
        if file_path not in self._deliverables:
            self._deliverables.append(file_path)
            logger.info(f"Added deliverable: {file_path}")

    def get_deliverables(self) -> List[str]:
        """Get list of tracked deliverables"""
        return self._deliverables.copy()

    async def generate_manifest(self) -> str:
        """Generate deliverables manifest.

        Returns:
            Path to manifest file
        """
        manifest_path = f"{self._workspace_root}/deliverables/MANIFEST.md"

        manifest_content = "# Deliverables Manifest\n\n"
        manifest_content += f"Total deliverables: {len(self._deliverables)}\n\n"

        for i, deliverable in enumerate(self._deliverables, 1):
            manifest_content += f"{i}. `{deliverable}`\n"

        # Write manifest
        await self._sandbox.execute_code(
            language="python",
            code=f"""
with open("{manifest_path}", "w") as f:
    f.write('''{manifest_content}''')
"""
        )

        logger.info(f"Generated manifest: {manifest_path}")
        return manifest_path
```

**Testing**:
```bash
pytest tests/domain/services/workspace/
```

---

## Phase 2: Screenshot & Monitoring (Weeks 4-6)

### Week 4: Screenshot Capture System

#### 4.1 Screenshot Domain Models

**File**: `backend/app/domain/models/screenshot.py` (NEW)

```python
"""Screenshot domain models for VNC capture and storage."""
from pydantic import BaseModel, Field
from datetime import datetime, UTC
from typing import Optional
from enum import Enum
import uuid


class CaptureReason(str, Enum):
    """Reason for screenshot capture"""
    STEP_START = "step_start"
    STEP_COMPLETE = "step_complete"
    TOOL_EXECUTION = "tool_execution"
    ERROR = "error"
    VERIFICATION = "verification"
    MANUAL = "manual"


class Screenshot(BaseModel):
    """Screenshot with metadata and storage references"""
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:16])
    session_id: str
    task_id: Optional[str] = None

    # Capture metadata
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    capture_reason: CaptureReason
    tool_name: Optional[str] = None
    action_description: str  # Human-readable description

    # Storage references (GridFS IDs)
    full_image_id: str  # GridFS file ID
    thumbnail_id: Optional[str] = None  # GridFS file ID for thumbnail

    # Image metadata
    width: int
    height: int
    format: str = "png"  # "png" or "jpeg"
    file_size_bytes: int

    # Sequence tracking
    sequence_number: int  # Position in session timeline

    # Optional annotations
    annotations: Optional[dict] = None  # For future use
```

---

#### 4.2 Screenshot Manager

**File**: `backend/app/domain/services/screenshot/screenshot_manager.py` (NEW)

```python
"""Screenshot capture and management service."""
from typing import Optional
import base64
import io
from PIL import Image
from app.domain.models.screenshot import Screenshot, CaptureReason
from app.infrastructure.storage.mongodb import MongoDBClient
from app.domain.external.browser import Browser
import logging

logger = logging.getLogger(__name__)


class ScreenshotManager:
    """Manages screenshot capture, compression, and storage."""

    def __init__(
        self,
        mongodb: MongoDBClient,
        browser: Browser,
        thumbnail_size: tuple = (200, 150),
        jpeg_quality: int = 85,
    ):
        self._mongodb = mongodb
        self._browser = browser
        self._thumbnail_size = thumbnail_size
        self._jpeg_quality = jpeg_quality
        self._sequence_counter: dict = {}  # session_id -> counter

    async def capture_screenshot(
        self,
        session_id: str,
        capture_reason: CaptureReason,
        action_description: str,
        task_id: Optional[str] = None,
        tool_name: Optional[str] = None,
    ) -> Screenshot:
        """Capture screenshot from VNC session.

        Args:
            session_id: Session ID
            capture_reason: Why screenshot was captured
            action_description: Human-readable description
            task_id: Optional task ID
            tool_name: Optional tool name

        Returns:
            Screenshot model with GridFS references
        """
        logger.info(f"Capturing screenshot: {action_description}")

        # Get screenshot from browser/VNC
        screenshot_base64 = await self._browser.take_screenshot()

        # Decode base64
        image_data = base64.b64decode(screenshot_base64)

        # Open with PIL for processing
        image = Image.open(io.BytesIO(image_data))
        width, height = image.size

        # Compress to JPEG
        compressed_buffer = io.BytesIO()
        image.convert("RGB").save(
            compressed_buffer,
            format="JPEG",
            quality=self._jpeg_quality,
            optimize=True
        )
        compressed_data = compressed_buffer.getvalue()

        # Generate thumbnail
        thumbnail_data = await self._generate_thumbnail(image)

        # Store in GridFS
        full_image_id = await self._mongodb.store_screenshot(
            compressed_data,
            filename=f"{session_id}_{capture_reason.value}.jpg",
            metadata={
                "session_id": session_id,
                "task_id": task_id,
                "capture_reason": capture_reason.value,
                "action_description": action_description,
            }
        )

        thumbnail_id = await self._mongodb.store_screenshot(
            thumbnail_data,
            filename=f"{session_id}_{capture_reason.value}_thumb.jpg",
            metadata={
                "session_id": session_id,
                "is_thumbnail": True,
            }
        )

        # Increment sequence counter
        if session_id not in self._sequence_counter:
            self._sequence_counter[session_id] = 0
        self._sequence_counter[session_id] += 1

        # Create screenshot model
        screenshot = Screenshot(
            session_id=session_id,
            task_id=task_id,
            capture_reason=capture_reason,
            tool_name=tool_name,
            action_description=action_description,
            full_image_id=full_image_id,
            thumbnail_id=thumbnail_id,
            width=width,
            height=height,
            format="jpeg",
            file_size_bytes=len(compressed_data),
            sequence_number=self._sequence_counter[session_id],
        )

        logger.info(
            f"Screenshot captured: {screenshot.id} "
            f"({screenshot.file_size_bytes} bytes, sequence {screenshot.sequence_number})"
        )

        return screenshot

    async def _generate_thumbnail(self, image: Image.Image) -> bytes:
        """Generate thumbnail from full image"""
        thumbnail = image.copy()
        thumbnail.thumbnail(self._thumbnail_size, Image.Resampling.LANCZOS)

        buffer = io.BytesIO()
        thumbnail.convert("RGB").save(buffer, format="JPEG", quality=self._jpeg_quality)
        return buffer.getvalue()

    async def get_screenshot(self, screenshot_id: str) -> bytes:
        """Retrieve screenshot image data"""
        return await self._mongodb.get_screenshot(screenshot_id)
```

---

#### 4.3 Screenshot Repository

**File**: `backend/app/domain/repositories/screenshot_repository.py` (NEW)

```python
"""Repository interface for screenshot persistence."""
from abc import ABC, abstractmethod
from typing import List, Optional
from app.domain.models.screenshot import Screenshot, CaptureReason


class ScreenshotRepository(ABC):
    """Abstract repository for screenshot storage and retrieval."""

    @abstractmethod
    async def save(self, screenshot: Screenshot) -> Screenshot:
        """Save screenshot metadata"""
        pass

    @abstractmethod
    async def get_by_id(self, screenshot_id: str) -> Optional[Screenshot]:
        """Get screenshot by ID"""
        pass

    @abstractmethod
    async def get_by_session(
        self,
        session_id: str,
        limit: int = 50,
        offset: int = 0
    ) -> List[Screenshot]:
        """Get screenshots for session with pagination"""
        pass

    @abstractmethod
    async def get_by_task(self, task_id: str) -> List[Screenshot]:
        """Get screenshots for specific task"""
        pass

    @abstractmethod
    async def get_latest(self, session_id: str, count: int = 10) -> List[Screenshot]:
        """Get latest N screenshots for session"""
        pass

    @abstractmethod
    async def delete_old_screenshots(self, days: int = 30) -> int:
        """Delete screenshots older than specified days (retention policy)"""
        pass
```

**File**: `backend/app/infrastructure/repositories/mongodb_screenshot.py` (NEW)

```python
"""MongoDB implementation of screenshot repository."""
from typing import List, Optional
from datetime import datetime, timedelta, UTC
from app.domain.repositories.screenshot_repository import ScreenshotRepository
from app.domain.models.screenshot import Screenshot
from motor.motor_asyncio import AsyncIOMotorCollection


class MongoDBScreenshotRepository(ScreenshotRepository):
    """MongoDB implementation of screenshot storage."""

    def __init__(self, collection: AsyncIOMotorCollection):
        self._collection = collection

    async def save(self, screenshot: Screenshot) -> Screenshot:
        """Save screenshot metadata to MongoDB"""
        await self._collection.insert_one(screenshot.model_dump())
        return screenshot

    async def get_by_id(self, screenshot_id: str) -> Optional[Screenshot]:
        """Get screenshot by ID"""
        doc = await self._collection.find_one({"id": screenshot_id})
        return Screenshot(**doc) if doc else None

    async def get_by_session(
        self,
        session_id: str,
        limit: int = 50,
        offset: int = 0
    ) -> List[Screenshot]:
        """Get screenshots for session with pagination"""
        cursor = self._collection.find(
            {"session_id": session_id}
        ).sort("sequence_number", -1).skip(offset).limit(limit)

        docs = await cursor.to_list(length=limit)
        return [Screenshot(**doc) for doc in docs]

    async def get_by_task(self, task_id: str) -> List[Screenshot]:
        """Get screenshots for specific task"""
        cursor = self._collection.find({"task_id": task_id}).sort("sequence_number", 1)
        docs = await cursor.to_list(length=None)
        return [Screenshot(**doc) for doc in docs]

    async def get_latest(self, session_id: str, count: int = 10) -> List[Screenshot]:
        """Get latest N screenshots"""
        cursor = self._collection.find(
            {"session_id": session_id}
        ).sort("sequence_number", -1).limit(count)

        docs = await cursor.to_list(length=count)
        return [Screenshot(**doc) for doc in docs]

    async def delete_old_screenshots(self, days: int = 30) -> int:
        """Delete screenshots older than specified days"""
        cutoff = datetime.now(UTC) - timedelta(days=days)
        result = await self._collection.delete_many({"timestamp": {"$lt": cutoff}})
        return result.deleted_count
```

---

### Week 5: Metrics & Budget Tracking

#### 5.1 Metrics Collector (Extends Existing Usage Service)

**File**: `backend/app/domain/services/usage/metrics_collector.py` (NEW)

```python
"""Session metrics collection service.

Extends existing usage tracking with performance and activity metrics.
"""
from typing import Dict, Any
from datetime import datetime, UTC
from app.domain.models.usage import SessionMetrics, SessionUsage
from app.domain.models.event import AgentEvent, ToolEvent, StepEvent, ErrorEvent
import logging

logger = logging.getLogger(__name__)


class MetricsCollector:
    """Collects and aggregates session metrics from events.

    Works alongside existing UsageRecord tracking to provide
    comprehensive performance and activity insights.
    """

    def __init__(self):
        self._metrics: Dict[str, SessionMetrics] = {}  # session_id -> metrics
        self._event_batch: Dict[str, list] = {}  # Batch events for efficiency
        self._batch_size = 10

    def initialize_session(self, session_id: str, user_id: str):
        """Initialize metrics tracking for new session"""
        self._metrics[session_id] = SessionMetrics(
            session_id=session_id,
            user_id=user_id,
            started_at=datetime.now(UTC),
        )
        self._event_batch[session_id] = []
        logger.debug(f"Initialized metrics for session: {session_id}")

    def process_event(self, session_id: str, event: AgentEvent):
        """Process single event and update metrics.

        Batches events for efficiency - flushes every N events.
        """
        if session_id not in self._metrics:
            logger.warning(f"Metrics not initialized for session: {session_id}")
            return

        # Add to batch
        self._event_batch[session_id].append(event)

        # Process batch if size reached
        if len(self._event_batch[session_id]) >= self._batch_size:
            self._process_batch(session_id)

    def _process_batch(self, session_id: str):
        """Process batched events"""
        metrics = self._metrics[session_id]
        events = self._event_batch[session_id]

        for event in events:
            # Tool usage tracking
            if isinstance(event, ToolEvent):
                tool_name = event.tool_name
                metrics.tool_usage_stats[tool_name] = \
                    metrics.tool_usage_stats.get(tool_name, 0) + 1

                # Screenshot tracking
                if event.screenshot_id:
                    metrics.screenshots_captured += 1

            # Step tracking
            elif isinstance(event, StepEvent):
                if event.status.value == "completed":
                    metrics.steps_executed += 1

            # Error tracking
            elif isinstance(event, ErrorEvent):
                metrics.error_count += 1

        # Update timestamp
        metrics.updated_at = datetime.now(UTC)

        # Clear batch
        self._event_batch[session_id] = []

        logger.debug(f"Processed batch of {len(events)} events for {session_id}")

    def update_budget(
        self,
        session_id: str,
        budget_limit: float,
        budget_consumed: float,
    ):
        """Update budget tracking from UsageRecord totals"""
        if session_id not in self._metrics:
            return

        metrics = self._metrics[session_id]
        metrics.budget_limit = budget_limit
        metrics.budget_consumed = budget_consumed

        # Check if warning threshold reached
        if budget_limit > 0:
            percentage = budget_consumed / budget_limit
            if percentage >= 0.8 and metrics.budget_warnings_triggered == 0:
                metrics.budget_warnings_triggered += 1
                logger.warning(
                    f"Budget warning for session {session_id}: "
                    f"{budget_consumed:.4f}/{budget_limit:.4f} USD ({percentage*100:.1f}%)"
                )

    def finalize_session(self, session_id: str) -> SessionMetrics:
        """Finalize metrics for completed session"""
        if session_id not in self._metrics:
            raise ValueError(f"No metrics found for session: {session_id}")

        # Process remaining events
        if self._event_batch.get(session_id):
            self._process_batch(session_id)

        metrics = self._metrics[session_id]
        metrics.completed_at = datetime.now(UTC)

        # Calculate duration
        if metrics.started_at:
            duration = (metrics.completed_at - metrics.started_at).total_seconds()
            metrics.duration_seconds = duration

            # Calculate avg step duration
            if metrics.steps_executed > 0:
                metrics.avg_step_duration_seconds = duration / metrics.steps_executed

        logger.info(
            f"Finalized metrics for {session_id}: "
            f"{metrics.steps_executed} steps, {metrics.duration_seconds}s duration"
        )

        return metrics

    def get_metrics(self, session_id: str) -> SessionMetrics:
        """Get current metrics for session"""
        return self._metrics.get(session_id)
```

---

#### 5.2 Budget Manager (Integrates with Existing Usage)

**File**: `backend/app/domain/services/usage/budget_manager.py` (NEW)

```python
"""Budget management and enforcement service.

Integrates with existing UsageRecord tracking to enforce budget limits.
"""
from typing import Optional, Callable
from app.domain.models.usage import SessionUsage
from app.domain.models.event import BudgetEvent
import logging

logger = logging.getLogger(__name__)


class BudgetManager:
    """Manages budget limits and enforcement for sessions."""

    def __init__(
        self,
        warning_threshold: float = 0.8,
        on_warning: Optional[Callable] = None,
        on_exhausted: Optional[Callable] = None,
    ):
        self._warning_threshold = warning_threshold
        self._on_warning = on_warning
        self._on_exhausted = on_exhausted
        self._warning_triggered: set = set()  # Track warnings per session

    def check_budget(
        self,
        session_id: str,
        budget_limit: float,
        session_usage: SessionUsage,
    ) -> tuple[bool, Optional[BudgetEvent]]:
        """Check budget status and generate events if needed.

        Args:
            session_id: Session ID
            budget_limit: Budget limit in USD
            session_usage: Current session usage from UsageRecord aggregation

        Returns:
            Tuple of (should_continue, optional_budget_event)
        """
        consumed = session_usage.total_cost
        remaining = budget_limit - consumed
        percentage_used = consumed / budget_limit if budget_limit > 0 else 0

        # Check for exhaustion (100%)
        if remaining <= 0:
            logger.error(
                f"Budget exhausted for session {session_id}: "
                f"${consumed:.4f}/${budget_limit:.4f}"
            )

            event = BudgetEvent(
                action="exhausted",
                budget_limit=budget_limit,
                consumed=consumed,
                remaining=0.0,
                percentage_used=1.0,
                warning_threshold=self._warning_threshold,
                session_paused=True,
            )

            if self._on_exhausted:
                self._on_exhausted(session_id, event)

            return False, event

        # Check for warning threshold (80%)
        if percentage_used >= self._warning_threshold:
            if session_id not in self._warning_triggered:
                logger.warning(
                    f"Budget warning for session {session_id}: "
                    f"${consumed:.4f}/${budget_limit:.4f} ({percentage_used*100:.1f}%)"
                )

                event = BudgetEvent(
                    action="warning",
                    budget_limit=budget_limit,
                    consumed=consumed,
                    remaining=remaining,
                    percentage_used=percentage_used,
                    warning_threshold=self._warning_threshold,
                    session_paused=False,
                )

                self._warning_triggered.add(session_id)

                if self._on_warning:
                    self._on_warning(session_id, event)

                return True, event

        # Budget OK
        return True, None

    def reset_warnings(self, session_id: str):
        """Reset warning state for session (e.g., after budget increase)"""
        self._warning_triggered.discard(session_id)
```

---

### Week 6: Validation System

#### 6.1 Self-Validator

**File**: `backend/app/domain/services/validation/self_validator.py` (NEW)

```python
"""Self-validation service for deliverable verification."""
from typing import List, Dict, Optional
from pathlib import Path
from dataclasses import dataclass
from app.domain.external.sandbox import Sandbox
from app.domain.models.multi_task import Deliverable, DeliverableType
import logging

logger = logging.getLogger(__name__)


@dataclass
class ValidationIssue:
    """Issue found during validation"""
    severity: str  # "error", "warning", "info"
    deliverable: str
    message: str
    auto_fixable: bool = False
    suggested_fix: Optional[str] = None


@dataclass
class ValidationReport:
    """Validation report for deliverables"""
    passed: bool
    total_deliverables: int
    validated: int
    issues: List[ValidationIssue]
    summary: str


class SelfValidator:
    """Validates task deliverables before completion.

    Performs:
    - File existence checks
    - Non-empty file verification
    - Deliverable completeness
    - Basic content validation
    """

    def __init__(self, sandbox: Sandbox):
        self._sandbox = sandbox

    async def validate_deliverables(
        self,
        deliverables: List[Deliverable],
        workspace_root: str = "/workspace",
    ) -> ValidationReport:
        """Validate all deliverables.

        Args:
            deliverables: List of expected deliverables
            workspace_root: Root workspace directory

        Returns:
            ValidationReport with findings
        """
        logger.info(f"Validating {len(deliverables)} deliverables...")

        issues: List[ValidationIssue] = []
        validated_count = 0

        for deliverable in deliverables:
            full_path = f"{workspace_root}/{deliverable.path}"

            # Check file existence
            exists = await self._check_file_exists(full_path)

            if not exists:
                if deliverable.required:
                    issues.append(ValidationIssue(
                        severity="error",
                        deliverable=deliverable.name,
                        message=f"Required file missing: {full_path}",
                        auto_fixable=False,
                    ))
                else:
                    issues.append(ValidationIssue(
                        severity="warning",
                        deliverable=deliverable.name,
                        message=f"Optional file missing: {full_path}",
                        auto_fixable=False,
                    ))
                continue

            # Check if file is empty
            is_empty = await self._check_file_empty(full_path)

            if is_empty:
                issues.append(ValidationIssue(
                    severity="error" if deliverable.required else "warning",
                    deliverable=deliverable.name,
                    message=f"File is empty: {full_path}",
                    auto_fixable=False,
                ))
                continue

            # Type-specific validation
            if deliverable.type == DeliverableType.DIRECTORY:
                has_contents = await self._check_directory_contents(full_path)
                if not has_contents:
                    issues.append(ValidationIssue(
                        severity="warning",
                        deliverable=deliverable.name,
                        message=f"Directory is empty: {full_path}",
                        auto_fixable=False,
                    ))

            validated_count += 1

        # Generate summary
        error_count = sum(1 for i in issues if i.severity == "error")
        warning_count = sum(1 for i in issues if i.severity == "warning")

        passed = error_count == 0

        summary = f"Validated {validated_count}/{len(deliverables)} deliverables. "
        if error_count > 0:
            summary += f"{error_count} errors. "
        if warning_count > 0:
            summary += f"{warning_count} warnings."

        report = ValidationReport(
            passed=passed,
            total_deliverables=len(deliverables),
            validated=validated_count,
            issues=issues,
            summary=summary,
        )

        logger.info(f"Validation complete: {report.summary}")

        return report

    async def _check_file_exists(self, path: str) -> bool:
        """Check if file exists"""
        result = await self._sandbox.execute_code(
            language="python",
            code=f"""
import os
result = os.path.exists("{path}")
print(result)
"""
        )
        return "True" in result.get("console", "")

    async def _check_file_empty(self, path: str) -> bool:
        """Check if file is empty"""
        result = await self._sandbox.execute_code(
            language="python",
            code=f"""
import os
result = os.path.getsize("{path}") == 0
print(result)
"""
        )
        return "True" in result.get("console", "")

    async def _check_directory_contents(self, path: str) -> bool:
        """Check if directory has contents"""
        result = await self._sandbox.execute_code(
            language="python",
            code=f"""
import os
result = len(os.listdir("{path}")) > 0
print(result)
"""
        )
        return "True" in result.get("console", "")
```

**Testing**:
```bash
pytest tests/domain/services/validation/test_self_validator.py
```

---

## Phase 3: Enhanced Agent Behaviors (Weeks 7-8)

### Week 7: Research Workflow & Complexity Assessment

#### 7.1 Research Agent (Integrates with Existing Orchestration)

**File**: `backend/app/domain/services/orchestration/research_agent.py` (NEW)

```python
"""Specialized research agent for deep information gathering.

Integrates with existing AgentRegistry for automatic dispatch.
"""
from typing import AsyncGenerator, List, Dict, Any
from app.domain.services.agents.base import BaseAgent
from app.domain.external.llm import LLM
from app.domain.external.search import SearchEngine
from app.domain.external.browser import Browser
from app.domain.models.event import BaseEvent, MessageEvent, ToolEvent
from app.domain.models.agent_response import AgentResponse
from app.domain.utils.json_parser import JsonParser
import logging

logger = logging.getLogger(__name__)


class ResearchAgent(BaseAgent):
    """Specialized agent for comprehensive research tasks.

    Workflow:
    1. Generate diverse search queries (3-8 based on depth)
    2. Execute searches and rank sources
    3. Browse top 10 sources
    4. Download PDFs if applicable
    5. Synthesize findings with cross-referencing
    6. Generate bibliography
    7. Create final report with citations
    """

    name: str = "research"
    system_prompt: str = """You are a research specialist agent focused on comprehensive information gathering.

Your workflow:
1. Generate diverse, complementary search queries
2. Evaluate source credibility (.edu, .gov = high)
3. Extract and synthesize key information
4. Cross-reference findings
5. Cite all sources properly

Prioritize authoritative sources and recent information."""

    def __init__(
        self,
        llm: LLM,
        search_engine: SearchEngine,
        browser: Browser,
        json_parser: JsonParser,
        max_sources: int = 10,
        search_depth: str = "deep",  # "quick", "standard", "deep"
    ):
        super().__init__(
            agent_id="research_agent",
            agent_repository=None,  # Research agent doesn't persist
            llm=llm,
            json_parser=json_parser,
            tools=[],
        )
        self._search_engine = search_engine
        self._browser = browser
        self._max_sources = max_sources
        self._search_depth = search_depth

        # Search query counts by depth
        self._query_counts = {
            "quick": 3,
            "standard": 5,
            "deep": 8,
        }

    async def research(
        self,
        topic: str,
        requirements: Optional[str] = None,
    ) -> AsyncGenerator[BaseEvent, None]:
        """Execute research workflow.

        Args:
            topic: Research topic/question
            requirements: Specific requirements or constraints

        Yields:
            Events documenting research progress
        """
        logger.info(f"Starting research: {topic}")

        # Step 1: Generate search queries
        yield MessageEvent(
            message=f"Generating search queries for: {topic}",
            role="assistant"
        )

        queries = await self._generate_queries(topic, requirements)

        yield MessageEvent(
            message=f"Generated {len(queries)} search queries",
            role="assistant"
        )

        # Step 2: Execute searches
        all_results = []
        for query in queries:
            yield ToolEvent(
                tool_call_id=f"search_{hash(query)}",
                tool_name="search_web",
                function_name="search_web",
                function_args={"query": query},
                status="calling",
                display_command=f"Searching '{query}'",
                command_category="search",
            )

            results = await self._search_engine.search(query)
            all_results.extend(results)

        # Deduplicate and rank
        ranked_sources = self._rank_sources(all_results)[:self._max_sources]

        yield MessageEvent(
            message=f"Found {len(ranked_sources)} relevant sources",
            role="assistant"
        )

        # Step 3: Browse and extract
        extracted_content = []
        for source in ranked_sources:
            yield ToolEvent(
                tool_call_id=f"browse_{hash(source['url'])}",
                tool_name="browser_navigate",
                function_name="browser_navigate",
                function_args={"url": source['url']},
                status="calling",
                display_command=f"Browsing {source['url']}",
                command_category="browse",
            )

            content = await self._browser.get_page_content(source['url'])
            extracted_content.append({
                "url": source['url'],
                "title": source.get('title', 'Unknown'),
                "content": content,
                "credibility": source.get('credibility', 'medium'),
            })

        # Step 4: Synthesize findings
        yield MessageEvent(
            message="Synthesizing research findings...",
            role="assistant"
        )

        synthesis = await self._synthesize_findings(
            topic=topic,
            sources=extracted_content,
            requirements=requirements,
        )

        # Step 5: Generate report
        report = self._generate_report(
            topic=topic,
            synthesis=synthesis,
            sources=extracted_content,
        )

        yield MessageEvent(
            message=report,
            role="assistant"
        )

        logger.info("Research complete")

    async def _generate_queries(
        self,
        topic: str,
        requirements: Optional[str],
    ) -> List[str]:
        """Generate diverse search queries using LLM"""
        query_count = self._query_counts.get(self._search_depth, 5)

        prompt = f"""Generate {query_count} diverse, complementary search queries for researching: {topic}

Requirements: {requirements or "Comprehensive coverage"}

Return JSON array of queries:
{{"queries": ["query 1", "query 2", ...]}}"""

        response = await self._llm.generate(
            messages=[{"role": "user", "content": prompt}],
            format="json_object",
        )

        parsed = self._json_parser.parse(response)
        return parsed.get("queries", [topic])

    def _rank_sources(self, results: List[Dict]) -> List[Dict]:
        """Rank sources by credibility and relevance"""
        def credibility_score(result):
            url = result.get('url', '')
            score = 0

            # High credibility domains
            if any(domain in url for domain in ['.edu', '.gov', '.org']):
                score += 3

            # Academic/research indicators
            if any(term in url.lower() for term in ['scholar', 'research', 'journal', 'arxiv']):
                score += 2

            # Penalize low-quality sources
            if any(term in url.lower() for term in ['blog', 'forum', 'reddit']):
                score -= 1

            result['credibility_score'] = score
            result['credibility'] = 'high' if score >= 3 else 'medium' if score >= 1 else 'low'

            return score

        # Sort by credibility score (descending)
        sorted_results = sorted(results, key=credibility_score, reverse=True)

        # Deduplicate by URL
        seen_urls = set()
        unique_results = []
        for result in sorted_results:
            url = result.get('url', '')
            if url not in seen_urls:
                seen_urls.add(url)
                unique_results.append(result)

        return unique_results

    async def _synthesize_findings(
        self,
        topic: str,
        sources: List[Dict],
        requirements: Optional[str],
    ) -> str:
        """Synthesize findings using LLM"""
        # Build context from sources
        context = "\n\n".join([
            f"Source: {s['title']} ({s['url']})\nCredibility: {s['credibility']}\n{s['content'][:1000]}..."
            for s in sources
        ])

        prompt = f"""Synthesize comprehensive findings on: {topic}

Requirements: {requirements or "Comprehensive analysis"}

Sources:
{context}

Provide a 500-800 word synthesis that:
1. Answers the research question
2. Cross-references multiple sources
3. Notes any conflicting information
4. Highlights key findings

Return JSON:
{{"synthesis": "...", "key_findings": ["...", "..."], "conflicts": ["..."]}}"""

        response = await self._llm.generate(
            messages=[{"role": "user", "content": prompt}],
            format="json_object",
        )

        return self._json_parser.parse(response).get("synthesis", "")

    def _generate_report(
        self,
        topic: str,
        synthesis: str,
        sources: List[Dict],
    ) -> str:
        """Generate final markdown report with citations"""
        report = f"""# Research Report: {topic}

## Synthesis

{synthesis}

## Bibliography

"""

        for i, source in enumerate(sources, 1):
            report += f"{i}. [{source['title']}]({source['url']}) - Credibility: {source['credibility']}\n"

        report += f"\n---\n*Research completed with {len(sources)} sources*"

        return report
```

**Register in orchestration**: `backend/app/domain/services/orchestration/agent_types.py` (MODIFY after line 100)

```python
# Research agent spec
RESEARCH_AGENT_SPEC = AgentSpec(
    agent_type=AgentType.RESEARCHER,
    name="Research Specialist",
    description="Deep research and comprehensive information gathering",
    capabilities={
        AgentCapability.RESEARCH,
        AgentCapability.WEB_SEARCH,
        AgentCapability.WEB_BROWSING,
        AgentCapability.ANALYSIS,
        AgentCapability.SUMMARIZATION,
    },
    tools=["search_web", "browser_navigate", "browser_click", "browser_extract"],
    system_prompt_template="Research specialist system prompt...",
    max_iterations=100,
    priority=2,
    trigger_patterns=[
        r"research\s+",
        r"find\s+(information|data|sources)",
        r"gather\s+(information|evidence)",
        r"investigate\s+",
        r"comprehensive\s+(analysis|study)",
    ],
    max_tokens=150000,
)

# Add to registry initialization
def get_default_agent_specs() -> List[AgentSpec]:
    return [
        RESEARCH_AGENT_SPEC,
        # ... other specs
    ]
```

---

#### 7.2 Complexity Assessor

**File**: `backend/app/domain/services/agents/complexity_assessor.py` (NEW)

```python
"""Task complexity assessment for dynamic iteration limits."""
from typing import Optional, Dict
from dataclasses import dataclass
import re
import logging

logger = logging.getLogger(__name__)


@dataclass
class ComplexityAssessment:
    """Result of complexity assessment"""
    score: float  # 0.0 (simple) to 1.0 (very complex)
    category: str  # "simple", "medium", "complex", "very_complex"
    recommended_iterations: int
    estimated_tool_calls: int
    reasoning: str


class ComplexityAssessor:
    """Assesses task complexity to set appropriate iteration limits.

    Analyzes:
    - Task description keywords
    - Plan complexity (number of steps, dependencies)
    - Estimated tool usage
    - Multi-task indicators
    """

    # Complexity indicators
    SIMPLE_KEYWORDS = [
        "read", "check", "verify", "show", "display", "list", "find",
    ]

    MEDIUM_KEYWORDS = [
        "create", "write", "modify", "update", "search", "analyze",
    ]

    COMPLEX_KEYWORDS = [
        "build", "develop", "implement", "design", "refactor",
        "research", "investigate", "comprehensive",
    ]

    VERY_COMPLEX_KEYWORDS = [
        "multi-task", "pipeline", "system", "architecture", "full-stack",
        "end-to-end", "comprehensive", "production-grade",
    ]

    def assess_task_complexity(
        self,
        task_description: str,
        plan_steps: Optional[int] = None,
        is_multi_task: bool = False,
    ) -> ComplexityAssessment:
        """Assess task complexity.

        Args:
            task_description: User's task description
            plan_steps: Number of steps in plan (if available)
            is_multi_task: Whether this is a multi-task challenge

        Returns:
            ComplexityAssessment with recommendations
        """
        logger.info("Assessing task complexity...")

        task_lower = task_description.lower()

        # Base score from keywords
        score = 0.0
        reasoning_parts = []

        # Check keyword categories
        simple_matches = sum(1 for kw in self.SIMPLE_KEYWORDS if kw in task_lower)
        medium_matches = sum(1 for kw in self.MEDIUM_KEYWORDS if kw in task_lower)
        complex_matches = sum(1 for kw in self.COMPLEX_KEYWORDS if kw in task_lower)
        very_complex_matches = sum(1 for kw in self.VERY_COMPLEX_KEYWORDS if kw in task_lower)

        # Weight keyword matches
        score += simple_matches * 0.1
        score += medium_matches * 0.3
        score += complex_matches * 0.5
        score += very_complex_matches * 0.8

        if simple_matches > 0:
            reasoning_parts.append(f"{simple_matches} simple operation(s)")
        if medium_matches > 0:
            reasoning_parts.append(f"{medium_matches} medium operation(s)")
        if complex_matches > 0:
            reasoning_parts.append(f"{complex_matches} complex operation(s)")
        if very_complex_matches > 0:
            reasoning_parts.append(f"{very_complex_matches} very complex operation(s)")

        # Adjust for plan steps
        if plan_steps:
            if plan_steps <= 3:
                score += 0.1
                reasoning_parts.append(f"{plan_steps} steps (simple)")
            elif plan_steps <= 7:
                score += 0.3
                reasoning_parts.append(f"{plan_steps} steps (medium)")
            elif plan_steps <= 15:
                score += 0.5
                reasoning_parts.append(f"{plan_steps} steps (complex)")
            else:
                score += 0.8
                reasoning_parts.append(f"{plan_steps} steps (very complex)")

        # Multi-task bonus
        if is_multi_task:
            score += 0.3
            reasoning_parts.append("multi-task challenge")

        # Task length indicator
        word_count = len(task_description.split())
        if word_count > 100:
            score += 0.2
            reasoning_parts.append("detailed description")

        # Normalize to 0.0-1.0
        score = min(1.0, score)

        # Categorize
        if score < 0.25:
            category = "simple"
            recommended_iterations = 50
            estimated_tool_calls = 10
        elif score < 0.5:
            category = "medium"
            recommended_iterations = 100
            estimated_tool_calls = 25
        elif score < 0.75:
            category = "complex"
            recommended_iterations = 200
            estimated_tool_calls = 50
        else:
            category = "very_complex"
            recommended_iterations = 300
            estimated_tool_calls = 100

        # Build reasoning
        reasoning = f"Complexity: {category} ({score:.2f}). " + ", ".join(reasoning_parts)

        assessment = ComplexityAssessment(
            score=score,
            category=category,
            recommended_iterations=recommended_iterations,
            estimated_tool_calls=estimated_tool_calls,
            reasoning=reasoning,
        )

        logger.info(f"Complexity assessment: {assessment.reasoning}")

        return assessment
```

**Testing**:
```bash
pytest tests/domain/services/agents/test_complexity_assessor.py
```

---

### Week 8: Command Formatting

#### 8.1 Command Formatter

**File**: `backend/app/domain/services/tools/command_formatter.py` (NEW)

```python
"""Human-readable command formatting for tool calls."""
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class CommandFormatter:
    """Formats tool calls as human-readable commands for UI display."""

    @staticmethod
    def format_tool_call(
        tool_name: str,
        function_name: str,
        function_args: Dict[str, Any],
    ) -> tuple[str, str, str]:
        """Format tool call into display components.

        Args:
            tool_name: Name of the tool
            function_name: Function being called
            function_args: Function arguments

        Returns:
            Tuple of (display_command, command_category, command_summary)
        """
        # Route to specific formatter
        formatters = {
            "search": CommandFormatter._format_search,
            "browser": CommandFormatter._format_browser,
            "shell": CommandFormatter._format_shell,
            "file": CommandFormatter._format_file,
            "mcp": CommandFormatter._format_mcp,
        }

        for prefix, formatter in formatters.items():
            if tool_name.startswith(prefix) or function_name.startswith(prefix):
                return formatter(function_name, function_args)

        # Default formatting
        return (
            f"{function_name}({', '.join(f'{k}={v}' for k, v in function_args.items())})",
            "other",
            function_name
        )

    @staticmethod
    def _format_search(function_name: str, args: Dict) -> tuple[str, str, str]:
        """Format search commands"""
        query = args.get("query", "")

        if "web" in function_name:
            return (
                f"Searching '{query}'",
                "search",
                f"Search: {query[:40]}"
            )
        else:
            return (
                f"Search: {query}",
                "search",
                f"Search: {query[:40]}"
            )

    @staticmethod
    def _format_browser(function_name: str, args: Dict) -> tuple[str, str, str]:
        """Format browser commands"""
        if "navigate" in function_name:
            url = args.get("url", "")
            domain = url.split("/")[2] if "//" in url else url[:30]
            return (
                f"Browsing {domain}",
                "browse",
                f"Browse: {domain}"
            )

        elif "click" in function_name:
            selector = args.get("selector", "element")
            return (
                f"Clicking {selector}",
                "browse",
                f"Click: {selector[:30]}"
            )

        elif "type" in function_name or "input" in function_name:
            text = args.get("text", args.get("value", ""))
            return (
                f"Typing '{text[:30]}...'",
                "browse",
                f"Type: {text[:20]}"
            )

        else:
            return (
                f"Browser: {function_name}",
                "browse",
                function_name
            )

    @staticmethod
    def _format_shell(function_name: str, args: Dict) -> tuple[str, str, str]:
        """Format shell commands"""
        language = args.get("language", "bash")
        code = args.get("code", "")

        # Extract first meaningful line
        lines = [l.strip() for l in code.split("\n") if l.strip() and not l.strip().startswith("#")]
        first_line = lines[0] if lines else code[:50]

        return (
            f"Running {language}: {first_line}",
            "shell",
            f"{language}: {first_line[:30]}"
        )

    @staticmethod
    def _format_file(function_name: str, args: Dict) -> tuple[str, str, str]:
        """Format file commands"""
        path = args.get("path", args.get("file_path", ""))

        if "read" in function_name:
            return (
                f"Reading {path}",
                "file",
                f"Read: {path.split('/')[-1]}"
            )

        elif "write" in function_name or "create" in function_name:
            return (
                f"Creating {path}",
                "file",
                f"Create: {path.split('/')[-1]}"
            )

        elif "list" in function_name:
            directory = path or args.get("directory", ".")
            return (
                f"Listing files in {directory}",
                "file",
                f"List: {directory}"
            )

        else:
            return (
                f"File operation: {path}",
                "file",
                path.split('/')[-1]
            )

    @staticmethod
    def _format_mcp(function_name: str, args: Dict) -> tuple[str, str, str]:
        """Format MCP tool commands"""
        server = args.get("server", "")
        resource = args.get("resource", "")

        return (
            f"MCP: {server}/{resource}",
            "mcp",
            f"{server}: {resource}"
        )
```

**Integration into ToolEvent**: Modify `backend/app/domain/services/tools/base.py` (or wherever tools emit events):

```python
from app.domain.services.tools.command_formatter import CommandFormatter

# In tool execution code:
def create_tool_event(tool_name, function_name, function_args, ...):
    # Format command
    display_command, command_category, command_summary = CommandFormatter.format_tool_call(
        tool_name=tool_name,
        function_name=function_name,
        function_args=function_args,
    )

    return ToolEvent(
        tool_name=tool_name,
        function_name=function_name,
        function_args=function_args,
        display_command=display_command,
        command_category=command_category,
        command_summary=command_summary,
        # ... other fields
    )
```

---

## Phase 4: Frontend UI Enhancements (Weeks 9-10)

*(Continued in next response due to length...)*

Would you like me to continue with Phase 4 (Frontend) and Phase 5 (Testing), or would you prefer to review this portion first?
---

## Phase 4: Frontend UI Enhancements (Weeks 9-10)

### Week 9: Monitoring Components & Timeline

#### 9.1 Frontend Type Definitions

**File**: `frontend/src/types/multi_task.ts` (NEW)

```typescript
/**
 * Multi-task domain types
 */
export enum TaskStatus {
  PENDING = 'pending',
  IN_PROGRESS = 'in_progress',
  COMPLETED = 'completed',
  FAILED = 'failed',
  SKIPPED = 'skipped',
}

export enum DeliverableType {
  FILE = 'file',
  DIRECTORY = 'directory',
  REPORT = 'report',
  DATA = 'data',
  CODE = 'code',
  ARTIFACT = 'artifact',
}

export interface Deliverable {
  name: string
  type: DeliverableType
  path: string
  description: string
  required: boolean
  validation_criteria?: string
}

export interface TaskDefinition {
  id: string
  title: string
  description: string
  deliverables: Deliverable[]
  workspace_folder?: string
  validation_criteria?: string
  estimated_complexity: number
  depends_on: string[]
  status: TaskStatus
  started_at?: string
  completed_at?: string
  duration_seconds?: number
  iterations_used: number
}

export interface MultiTaskChallenge {
  id: string
  title: string
  description: string
  tasks: TaskDefinition[]
  workspace_root: string
  workspace_template?: string
  current_task_index: number
  completed_tasks: string[]
  failed_tasks: string[]
  started_at?: string
  completed_at?: string
  total_duration_seconds?: number
}
```

**File**: `frontend/src/types/screenshot.ts` (NEW)

```typescript
/**
 * Screenshot types
 */
export enum CaptureReason {
  STEP_START = 'step_start',
  STEP_COMPLETE = 'step_complete',
  TOOL_EXECUTION = 'tool_execution',
  ERROR = 'error',
  VERIFICATION = 'verification',
  MANUAL = 'manual',
}

export interface Screenshot {
  id: string
  session_id: string
  task_id?: string
  timestamp: string
  capture_reason: CaptureReason
  tool_name?: string
  action_description: string
  full_image_id: string
  thumbnail_id?: string
  width: number
  height: number
  format: string
  file_size_bytes: number
  sequence_number: number
  annotations?: Record<string, any>
}

export interface ScreenshotEntry {
  id: string
  timestamp: number
  screenshot: string // URL or base64
  toolEvent?: ToolEvent
  action: string
  sequenceNumber: number
}
```

**File**: `frontend/src/types/event.ts` (MODIFY)

Add new event types:

```typescript
// Add to existing event types

export interface MultiTaskEvent extends BaseEvent {
  type: 'multi_task'
  challenge_id: string
  action: string
  current_task_index: number
  total_tasks: number
  current_task?: string
  progress_percentage: number
  elapsed_time_seconds?: number
}

export interface WorkspaceEvent extends BaseEvent {
  type: 'workspace'
  action: string
  workspace_type?: string
  structure?: Record<string, string>
  files_organized: number
  deliverables_count: number
  manifest_path?: string
}

export interface ScreenshotEvent extends BaseEvent {
  type: 'screenshot'
  screenshot_id: string
  action: string
  capture_reason: string
  tool_name?: string
  thumbnail_url?: string
  full_image_url?: string
}

export interface BudgetEvent extends BaseEvent {
  type: 'budget'
  action: string
  budget_limit: number
  consumed: number
  remaining: number
  percentage_used: number
  warning_threshold: number
  session_paused: boolean
}

// Update ToolEvent
export interface ToolEvent extends BaseEvent {
  // ... existing fields ...
  display_command?: string
  command_category?: string
  command_summary?: string
  screenshot_id?: string
}

// Update AgentEvent union
export type AgentEvent = 
  | ErrorEvent
  | PlanEvent
  | ToolEvent
  | StepEvent
  | MessageEvent
  | DoneEvent
  | TitleEvent
  | WaitEvent
  | MultiTaskEvent
  | WorkspaceEvent
  | ScreenshotEvent
  | BudgetEvent
  // ... other existing types
```

---

#### 9.2 Screenshot Timeline Component

**File**: `frontend/src/composables/useScreenshotTimeline.ts` (NEW)

```typescript
import { ref, computed } from 'vue'
import type { Screenshot, ScreenshotEntry } from '@/types/screenshot'
import type { ToolEvent } from '@/types/event'

export function useScreenshotTimeline() {
  const screenshots = ref<ScreenshotEntry[]>([])
  const selectedScreenshot = ref<ScreenshotEntry | null>(null)
  const maxScreenshots = 50

  const addScreenshot = (screenshot: Screenshot, toolEvent?: ToolEvent) => {
    const entry: ScreenshotEntry = {
      id: screenshot.id,
      timestamp: new Date(screenshot.timestamp).getTime(),
      screenshot: `/api/v1/screenshots/${screenshot.thumbnail_id || screenshot.full_image_id}`,
      toolEvent,
      action: screenshot.action_description,
      sequenceNumber: screenshot.sequence_number,
    }

    screenshots.value.push(entry)

    // Limit to last N screenshots to prevent memory issues
    if (screenshots.value.length > maxScreenshots) {
      screenshots.value.shift()
    }
  }

  const selectScreenshot = (screenshot: ScreenshotEntry) => {
    selectedScreenshot.value = screenshot
  }

  const clearSelection = () => {
    selectedScreenshot.value = null
  }

  const getNextScreenshot = () => {
    if (!selectedScreenshot.value) return null

    const currentIndex = screenshots.value.findIndex(
      s => s.id === selectedScreenshot.value!.id
    )

    if (currentIndex < screenshots.value.length - 1) {
      return screenshots.value[currentIndex + 1]
    }

    return null
  }

  const getPreviousScreenshot = () => {
    if (!selectedScreenshot.value) return null

    const currentIndex = screenshots.value.findIndex(
      s => s.id === selectedScreenshot.value!.id
    )

    if (currentIndex > 0) {
      return screenshots.value[currentIndex - 1]
    }

    return null
  }

  const sortedScreenshots = computed(() => {
    return [...screenshots.value].sort((a, b) => a.sequenceNumber - b.sequenceNumber)
  })

  return {
    screenshots: sortedScreenshots,
    selectedScreenshot,
    addScreenshot,
    selectScreenshot,
    clearSelection,
    getNextScreenshot,
    getPreviousScreenshot,
  }
}
```

**File**: `frontend/src/components/monitoring/ScreenshotTimeline.vue` (NEW)

```vue
<template>
  <div class="screenshot-timeline">
    <div class="timeline-header">
      <h3>Screenshot Timeline</h3>
      <span class="screenshot-count">{{ screenshots.length }} screenshots</span>
    </div>

    <div class="timeline-scrollable" ref="scrollContainer">
      <div class="timeline-track">
        <div
          v-for="screenshot in screenshots"
          :key="screenshot.id"
          :class="['timeline-item', { selected: isSelected(screenshot) }]"
          @click="onSelectScreenshot(screenshot)"
        >
          <img
            :src="screenshot.screenshot"
            :alt="screenshot.action"
            class="screenshot-thumbnail"
            loading="lazy"
          />
          <div class="screenshot-overlay">
            <div class="screenshot-time">
              {{ formatTime(screenshot.timestamp) }}
            </div>
            <div class="screenshot-action">
              {{ screenshot.action }}
            </div>
          </div>
          <div class="sequence-badge">
            {{ screenshot.sequenceNumber }}
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import type { ScreenshotEntry } from '@/types/screenshot'

interface Props {
  screenshots: ScreenshotEntry[]
  selectedScreenshot?: ScreenshotEntry | null
  autoScroll?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  autoScroll: true,
})

const emit = defineEmits<{
  select: [screenshot: ScreenshotEntry]
}>()

const scrollContainer = ref<HTMLElement>()

const isSelected = (screenshot: ScreenshotEntry) => {
  return props.selectedScreenshot?.id === screenshot.id
}

const onSelectScreenshot = (screenshot: ScreenshotEntry) => {
  emit('select', screenshot)
}

const formatTime = (timestamp: number) => {
  const date = new Date(timestamp)
  return date.toLocaleTimeString()
}

// Auto-scroll to latest screenshot
watch(
  () => props.screenshots.length,
  async () => {
    if (props.autoScroll && scrollContainer.value) {
      await nextTick()
      scrollContainer.value.scrollLeft = scrollContainer.value.scrollWidth
    }
  }
)
</script>

<style scoped>
.screenshot-timeline {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px;
  background: var(--background-secondary);
  border-radius: 8px;
}

.timeline-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.timeline-header h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.screenshot-count {
  font-size: 12px;
  color: var(--text-tertiary);
}

.timeline-scrollable {
  overflow-x: auto;
  overflow-y: hidden;
  scrollbar-width: thin;
}

.timeline-track {
  display: flex;
  gap: 12px;
  padding-bottom: 8px;
}

.timeline-item {
  position: relative;
  flex-shrink: 0;
  width: 200px;
  height: 150px;
  border-radius: 6px;
  overflow: hidden;
  cursor: pointer;
  border: 2px solid transparent;
  transition: all 0.2s;
}

.timeline-item:hover {
  border-color: var(--border-hover);
  transform: scale(1.05);
}

.timeline-item.selected {
  border-color: var(--primary-color);
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
}

.screenshot-thumbnail {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.screenshot-overlay {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  padding: 8px;
  background: linear-gradient(to top, rgba(0, 0, 0, 0.7), transparent);
  color: white;
  font-size: 11px;
}

.screenshot-time {
  font-weight: 600;
  margin-bottom: 2px;
}

.screenshot-action {
  opacity: 0.9;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sequence-badge {
  position: absolute;
  top: 8px;
  right: 8px;
  background: rgba(0, 0, 0, 0.7);
  color: white;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 10px;
  font-weight: 600;
}
</style>
```

**File**: `frontend/src/components/monitoring/ScreenshotModal.vue` (NEW)

```vue
<template>
  <Dialog :open="open" @update:open="onClose">
    <DialogContent class="screenshot-modal">
      <DialogHeader>
        <DialogTitle>Screenshot #{{ screenshot?.sequenceNumber }}</DialogTitle>
        <DialogDescription>
          {{ screenshot?.action }}
        </DialogDescription>
      </DialogHeader>

      <div class="screenshot-viewer">
        <img
          :src="fullImageUrl"
          :alt="screenshot?.action"
          class="screenshot-full"
        />
      </div>

      <div class="screenshot-controls">
        <button
          @click="onPrevious"
          :disabled="!hasPrevious"
          class="nav-button"
        >
          ← Previous
        </button>

        <div class="screenshot-info">
          <span>{{ formatTime(screenshot?.timestamp) }}</span>
          <span class="separator">•</span>
          <span>{{ screenshot?.tool_name || 'No tool' }}</span>
        </div>

        <button
          @click="onNext"
          :disabled="!hasNext"
          class="nav-button"
        >
          Next →
        </button>
      </div>
    </DialogContent>
  </Dialog>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { ScreenshotEntry } from '@/types/screenshot'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog'

interface Props {
  open: boolean
  screenshot: ScreenshotEntry | null
  hasPrevious?: boolean
  hasNext?: boolean
}

const props = defineProps<Props>()

const emit = defineEmits<{
  close: []
  previous: []
  next: []
}>()

const fullImageUrl = computed(() => {
  if (!props.screenshot) return ''
  // Replace thumbnail with full image
  return props.screenshot.screenshot.replace('_thumb', '')
})

const formatTime = (timestamp?: number) => {
  if (!timestamp) return ''
  const date = new Date(timestamp)
  return date.toLocaleString()
}

const onClose = () => {
  emit('close')
}

const onPrevious = () => {
  emit('previous')
}

const onNext = () => {
  emit('next')
}
</script>

<style scoped>
.screenshot-modal {
  max-width: 90vw;
  max-height: 90vh;
}

.screenshot-viewer {
  display: flex;
  justify-content: center;
  align-items: center;
  max-height: 70vh;
  overflow: auto;
  background: var(--background-tertiary);
  border-radius: 8px;
  padding: 16px;
}

.screenshot-full {
  max-width: 100%;
  max-height: 100%;
  border-radius: 4px;
}

.screenshot-controls {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-top: 16px;
  border-top: 1px solid var(--border-main);
}

.nav-button {
  padding: 8px 16px;
  border-radius: 6px;
  background: var(--background-secondary);
  border: 1px solid var(--border-main);
  cursor: pointer;
  transition: all 0.2s;
}

.nav-button:hover:not(:disabled) {
  background: var(--background-hover);
}

.nav-button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.screenshot-info {
  display: flex;
  gap: 8px;
  align-items: center;
  font-size: 13px;
  color: var(--text-secondary);
}

.separator {
  color: var(--text-tertiary);
}
</style>
```

---

#### 9.3 Enhanced Status Bar Component

**File**: `frontend/src/components/monitoring/EnhancedStatusBar.vue` (NEW)

```vue
<template>
  <div :class="['enhanced-status-bar', statusClass]">
    <div class="status-indicator">
      <div :class="['status-pulse', statusClass]" />
      <component :is="statusIcon" class="status-icon" />
    </div>

    <div class="status-content">
      <div class="status-command">
        {{ displayCommand }}
      </div>
      <div v-if="duration" class="status-duration">
        {{ formatDuration(duration) }}
      </div>
    </div>

    <div v-if="progress !== undefined" class="status-progress">
      <div class="progress-bar" :style="{ width: `${progress}%` }" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { 
  Search, 
  Globe, 
  FileText, 
  Terminal, 
  Code,
  CheckCircle,
  AlertCircle,
  Loader,
} from 'lucide-vue-next'

interface Props {
  status: 'idle' | 'thinking' | 'executing' | 'complete' | 'error'
  displayCommand?: string
  commandCategory?: string
  duration?: number
  progress?: number
}

const props = defineProps<Props>()

const statusClass = computed(() => {
  return `status-${props.status}`
})

const statusIcon = computed(() => {
  switch (props.status) {
    case 'complete':
      return CheckCircle
    case 'error':
      return AlertCircle
    case 'thinking':
    case 'executing':
      return Loader
    default:
      if (props.commandCategory) {
        return getCategoryIcon(props.commandCategory)
      }
      return Terminal
  }
})

const displayCommand = computed(() => {
  return props.displayCommand || 'Processing...'
})

const getCategoryIcon = (category: string) => {
  const icons: Record<string, any> = {
    search: Search,
    browse: Globe,
    file: FileText,
    shell: Terminal,
    code: Code,
  }
  return icons[category] || Terminal
}

const formatDuration = (ms: number) => {
  const seconds = Math.floor(ms / 1000)
  if (seconds < 60) {
    return `${seconds}s`
  }
  const minutes = Math.floor(seconds / 60)
  const remainingSeconds = seconds % 60
  return `${minutes}m ${remainingSeconds}s`
}
</script>

<style scoped>
.enhanced-status-bar {
  position: relative;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  border-radius: 8px;
  background: var(--background-secondary);
  border: 1px solid var(--border-main);
  transition: all 0.3s;
}

.status-indicator {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
}

.status-pulse {
  position: absolute;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  opacity: 0.3;
}

.status-pulse.status-thinking,
.status-pulse.status-executing {
  animation: pulse 2s ease-in-out infinite;
  background: var(--primary-color);
}

.status-icon {
  width: 20px;
  height: 20px;
  z-index: 1;
}

.status-thinking .status-icon,
.status-executing .status-icon {
  animation: spin 1s linear infinite;
}

.status-complete {
  border-color: var(--success-color);
}

.status-complete .status-icon {
  color: var(--success-color);
}

.status-error {
  border-color: var(--error-color);
}

.status-error .status-icon {
  color: var(--error-color);
}

.status-content {
  flex: 1;
  min-width: 0;
}

.status-command {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.status-duration {
  font-size: 12px;
  color: var(--text-tertiary);
  margin-top: 2px;
}

.status-progress {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 2px;
  background: var(--background-tertiary);
  border-radius: 0 0 8px 8px;
  overflow: hidden;
}

.progress-bar {
  height: 100%;
  background: var(--primary-color);
  transition: width 0.3s ease-out;
}

@keyframes pulse {
  0%, 100% {
    transform: scale(1);
    opacity: 0.3;
  }
  50% {
    transform: scale(1.2);
    opacity: 0.1;
  }
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}
</style>
```

---

### Week 10: Multi-Task Dashboard & Monitoring Panel

#### 10.1 Multi-Task Progress Components

**File**: `frontend/src/composables/useTaskProgress.ts` (NEW)

```typescript
import { ref, computed } from 'vue'
import type { MultiTaskChallenge, TaskDefinition, TaskStatus } from '@/types/multi_task'

export function useTaskProgress() {
  const challenge = ref<MultiTaskChallenge | null>(null)

  const currentTask = computed(() => {
    if (!challenge.value) return null
    const index = challenge.value.current_task_index
    if (index >= 0 && index < challenge.value.tasks.length) {
      return challenge.value.tasks[index]
    }
    return null
  })

  const progressPercentage = computed(() => {
    if (!challenge.value || challenge.value.tasks.length === 0) return 0
    return (challenge.value.completed_tasks.length / challenge.value.tasks.length) * 100
  })

  const completedCount = computed(() => {
    return challenge.value?.completed_tasks.length || 0
  })

  const totalCount = computed(() => {
    return challenge.value?.tasks.length || 0
  })

  const tasksWithStatus = computed(() => {
    if (!challenge.value) return []

    return challenge.value.tasks.map((task, index) => ({
      ...task,
      isActive: index === challenge.value!.current_task_index,
      isCompleted: challenge.value!.completed_tasks.includes(task.id),
      isFailed: challenge.value!.failed_tasks.includes(task.id),
    }))
  })

  const updateChallenge = (newChallenge: MultiTaskChallenge) => {
    challenge.value = newChallenge
  }

  const updateTaskStatus = (taskId: string, status: TaskStatus) => {
    if (!challenge.value) return

    const task = challenge.value.tasks.find(t => t.id === taskId)
    if (task) {
      task.status = status
    }
  }

  return {
    challenge,
    currentTask,
    progressPercentage,
    completedCount,
    totalCount,
    tasksWithStatus,
    updateChallenge,
    updateTaskStatus,
  }
}
```

**File**: `frontend/src/components/monitoring/MultiTaskDashboard.vue` (NEW)

```vue
<template>
  <div class="multi-task-dashboard">
    <div class="dashboard-header">
      <h3>{{ challenge?.title || 'Multi-Task Challenge' }}</h3>
      <div class="overall-progress">
        <div class="progress-text">
          {{ completedCount }}/{{ totalCount }} tasks
        </div>
        <div class="progress-bar-container">
          <div 
            class="progress-bar-fill" 
            :style="{ width: `${progressPercentage}%` }"
          />
        </div>
        <div class="progress-percentage">
          {{ Math.round(progressPercentage) }}%
        </div>
      </div>
    </div>

    <div class="task-list">
      <div
        v-for="(task, index) in tasksWithStatus"
        :key="task.id"
        :class="[
          'task-item',
          {
            active: task.isActive,
            completed: task.isCompleted,
            failed: task.isFailed,
          }
        ]"
      >
        <div class="task-indicator">
          <CheckCircle v-if="task.isCompleted" class="icon-completed" />
          <XCircle v-else-if="task.isFailed" class="icon-failed" />
          <Loader v-else-if="task.isActive" class="icon-active" />
          <Circle v-else class="icon-pending" />
        </div>

        <div class="task-content">
          <div class="task-title">
            Task {{ index + 1 }}: {{ task.title }}
            <span v-if="task.isActive" class="active-badge">Active</span>
          </div>
          <div class="task-description">
            {{ task.description }}
          </div>
          <div v-if="task.duration_seconds" class="task-duration">
            {{ formatDuration(task.duration_seconds) }}
          </div>
        </div>

        <div v-if="task.deliverables.length > 0" class="task-deliverables">
          <div class="deliverables-count">
            {{ task.deliverables.length }} deliverable(s)
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { CheckCircle, XCircle, Circle, Loader } from 'lucide-vue-next'
import type { MultiTaskChallenge } from '@/types/multi_task'

interface TaskWithStatus {
  id: string
  title: string
  description: string
  deliverables: any[]
  duration_seconds?: number
  isActive: boolean
  isCompleted: boolean
  isFailed: boolean
}

interface Props {
  challenge: MultiTaskChallenge | null
  tasksWithStatus: TaskWithStatus[]
  progressPercentage: number
  completedCount: number
  totalCount: number
}

const props = defineProps<Props>()

const formatDuration = (seconds: number) => {
  if (seconds < 60) {
    return `${Math.round(seconds)}s`
  }
  const minutes = Math.floor(seconds / 60)
  const remainingSeconds = Math.round(seconds % 60)
  return `${minutes}m ${remainingSeconds}s`
}
</script>

<style scoped>
.multi-task-dashboard {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 16px;
  background: var(--background-secondary);
  border-radius: 8px;
}

.dashboard-header {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.dashboard-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.overall-progress {
  display: flex;
  align-items: center;
  gap: 12px;
}

.progress-text {
  font-size: 13px;
  color: var(--text-secondary);
  white-space: nowrap;
}

.progress-bar-container {
  flex: 1;
  height: 8px;
  background: var(--background-tertiary);
  border-radius: 4px;
  overflow: hidden;
}

.progress-bar-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--primary-color), var(--primary-color-light));
  transition: width 0.3s ease-out;
}

.progress-percentage {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  min-width: 40px;
  text-align: right;
}

.task-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.task-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 12px;
  border-radius: 6px;
  border: 1px solid var(--border-main);
  background: var(--background-white-main);
  transition: all 0.2s;
}

.task-item.active {
  border-color: var(--primary-color);
  background: var(--primary-background);
}

.task-item.completed {
  opacity: 0.7;
}

.task-indicator {
  flex-shrink: 0;
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.icon-completed {
  color: var(--success-color);
}

.icon-failed {
  color: var(--error-color);
}

.icon-active {
  color: var(--primary-color);
  animation: spin 2s linear infinite;
}

.icon-pending {
  color: var(--text-tertiary);
}

.task-content {
  flex: 1;
  min-width: 0;
}

.task-title {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.active-badge {
  display: inline-block;
  padding: 2px 8px;
  background: var(--primary-color);
  color: white;
  font-size: 11px;
  font-weight: 600;
  border-radius: 4px;
}

.task-description {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.4;
}

.task-duration {
  font-size: 12px;
  color: var(--text-tertiary);
  margin-top: 4px;
}

.task-deliverables {
  flex-shrink: 0;
}

.deliverables-count {
  font-size: 12px;
  color: var(--text-tertiary);
  padding: 4px 8px;
  background: var(--background-tertiary);
  border-radius: 4px;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>
```

---

#### 10.2 Monitoring Panel Integration

**File**: `frontend/src/components/monitoring/MonitoringPanel.vue` (NEW)

```vue
<template>
  <div class="monitoring-panel">
    <div class="panel-tabs">
      <button
        v-for="tab in tabs"
        :key="tab.id"
        :class="['tab-button', { active: activeTab === tab.id }]"
        @click="activeTab = tab.id"
      >
        <component :is="tab.icon" class="tab-icon" />
        {{ tab.label }}
        <span v-if="tab.count" class="tab-count">{{ tab.count }}</span>
      </button>
    </div>

    <div class="panel-content">
      <!-- Overview Tab -->
      <div v-if="activeTab === 'overview'" class="tab-panel">
        <SessionMetrics :metrics="sessionMetrics" />
        <MultiTaskDashboard
          v-if="multiTaskChallenge"
          :challenge="multiTaskChallenge"
          :tasks-with-status="tasksWithStatus"
          :progress-percentage="progressPercentage"
          :completed-count="completedCount"
          :total-count="totalCount"
        />
      </div>

      <!-- Screenshots Tab -->
      <div v-if="activeTab === 'screenshots'" class="tab-panel">
        <ScreenshotTimeline
          :screenshots="screenshots"
          :selected-screenshot="selectedScreenshot"
          @select="onSelectScreenshot"
        />
      </div>

      <!-- Commands Tab -->
      <div v-if="activeTab === 'commands'" class="tab-panel">
        <CommandHistoryPanel :commands="commandHistory" />
      </div>

      <!-- Deliverables Tab -->
      <div v-if="activeTab === 'deliverables'" class="tab-panel">
        <DeliverableGallery :deliverables="deliverables" />
      </div>
    </div>

    <!-- Screenshot Modal -->
    <ScreenshotModal
      :open="!!selectedScreenshot"
      :screenshot="selectedScreenshot"
      :has-previous="hasPreviousScreenshot"
      :has-next="hasNextScreenshot"
      @close="selectedScreenshot = null"
      @previous="selectPreviousScreenshot"
      @next="selectNextScreenshot"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { LayoutDashboard, Camera, Terminal, FileText } from 'lucide-vue-next'
import ScreenshotTimeline from './ScreenshotTimeline.vue'
import ScreenshotModal from './ScreenshotModal.vue'
import MultiTaskDashboard from './MultiTaskDashboard.vue'
import SessionMetrics from './SessionMetrics.vue'
import CommandHistoryPanel from './CommandHistoryPanel.vue'
import DeliverableGallery from './DeliverableGallery.vue'

// Props would come from parent (ChatPage.vue)
const activeTab = ref('overview')

const tabs = [
  { id: 'overview', label: 'Overview', icon: LayoutDashboard },
  { id: 'screenshots', label: 'Screenshots', icon: Camera, count: computed(() => screenshots.value.length) },
  { id: 'commands', label: 'Commands', icon: Terminal, count: computed(() => commandHistory.value.length) },
  { id: 'deliverables', label: 'Deliverables', icon: FileText, count: computed(() => deliverables.value.length) },
]
</script>

<style scoped>
.monitoring-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--background-white-main);
  border-left: 1px solid var(--border-main);
}

.panel-tabs {
  display: flex;
  border-bottom: 1px solid var(--border-main);
  padding: 8px;
  gap: 4px;
}

.tab-button {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  border: none;
  background: transparent;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  color: var(--text-secondary);
  transition: all 0.2s;
}

.tab-button:hover {
  background: var(--background-hover);
}

.tab-button.active {
  background: var(--background-secondary);
  color: var(--text-primary);
  font-weight: 500;
}

.tab-icon {
  width: 16px;
  height: 16px;
}

.tab-count {
  display: inline-block;
  padding: 2px 6px;
  background: var(--background-tertiary);
  border-radius: 10px;
  font-size: 11px;
  font-weight: 600;
}

.panel-content {
  flex: 1;
  overflow-y: auto;
}

.tab-panel {
  padding: 16px;
}
</style>
```

---

## Phase 5: API Routes & Testing (Weeks 11-13)

### Week 11: API Layer

#### 11.1 Screenshot API Routes

**File**: `backend/app/interfaces/api/routes/screenshot.py` (NEW)

```python
"""Screenshot API routes."""
from fastapi import APIRouter, Depends, HTTPException, Path
from fastapi.responses import Response
from typing import List
from app.domain.repositories.screenshot_repository import ScreenshotRepository
from app.infrastructure.repositories.mongodb_screenshot import MongoDBScreenshotRepository
from app.infrastructure.storage.mongodb import get_mongodb_client
from app.domain.models.screenshot import Screenshot
from app.interfaces.api.dependencies import get_current_user
from app.domain.models.user import User
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/screenshots", tags=["screenshots"])


def get_screenshot_repository(
    mongodb=Depends(get_mongodb_client),
) -> ScreenshotRepository:
    """Dependency for screenshot repository"""
    return MongoDBScreenshotRepository(mongodb.db.screenshots)


@router.get("/session/{session_id}", response_model=List[Screenshot])
async def get_session_screenshots(
    session_id: str = Path(..., description="Session ID"),
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    repository: ScreenshotRepository = Depends(get_screenshot_repository),
):
    """Get screenshots for a session."""
    screenshots = await repository.get_by_session(
        session_id=session_id,
        limit=limit,
        offset=offset,
    )
    return screenshots


@router.get("/task/{task_id}", response_model=List[Screenshot])
async def get_task_screenshots(
    task_id: str = Path(..., description="Task ID"),
    current_user: User = Depends(get_current_user),
    repository: ScreenshotRepository = Depends(get_screenshot_repository),
):
    """Get screenshots for a specific task."""
    screenshots = await repository.get_by_task(task_id=task_id)
    return screenshots


@router.get("/{screenshot_id}/image")
async def get_screenshot_image(
    screenshot_id: str = Path(..., description="Screenshot or GridFS file ID"),
    current_user: User = Depends(get_current_user),
    mongodb=Depends(get_mongodb_client),
):
    """Get screenshot image data."""
    try:
        # Retrieve from GridFS
        image_data = await mongodb.get_screenshot(screenshot_id)

        return Response(
            content=image_data,
            media_type="image/jpeg",
            headers={
                "Cache-Control": "public, max-age=86400",  # Cache for 1 day
            }
        )
    except Exception as e:
        logger.error(f"Failed to retrieve screenshot {screenshot_id}: {e}")
        raise HTTPException(status_code=404, detail="Screenshot not found")


@router.get("/{screenshot_id}", response_model=Screenshot)
async def get_screenshot(
    screenshot_id: str = Path(..., description="Screenshot ID"),
    current_user: User = Depends(get_current_user),
    repository: ScreenshotRepository = Depends(get_screenshot_repository),
):
    """Get screenshot metadata."""
    screenshot = await repository.get_by_id(screenshot_id)
    if not screenshot:
        raise HTTPException(status_code=404, detail="Screenshot not found")
    return screenshot
```

---

#### 11.2 Workspace API Routes

**File**: `backend/app/interfaces/api/routes/workspace.py` (NEW)

```python
"""Workspace API routes."""
from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, List
from pydantic import BaseModel
from app.domain.services.workspace.workspace_templates import (
    get_all_templates,
    get_template,
    WorkspaceTemplate,
)
from app.interfaces.api.dependencies import get_current_user
from app.domain.models.user import User

router = APIRouter(prefix="/workspace", tags=["workspace"])


class WorkspaceTemplateResponse(BaseModel):
    """Workspace template response"""
    name: str
    description: str
    folders: Dict[str, str]
    readme_content: str
    trigger_keywords: List[str]


@router.get("/templates", response_model=List[WorkspaceTemplateResponse])
async def list_workspace_templates(
    current_user: User = Depends(get_current_user),
):
    """List all available workspace templates."""
    templates = get_all_templates()
    return [
        WorkspaceTemplateResponse(
            name=t.name,
            description=t.description,
            folders=t.folders,
            readme_content=t.readme_content,
            trigger_keywords=t.trigger_keywords,
        )
        for t in templates
    ]


@router.get("/templates/{template_name}", response_model=WorkspaceTemplateResponse)
async def get_workspace_template(
    template_name: str,
    current_user: User = Depends(get_current_user),
):
    """Get specific workspace template."""
    template = get_template(template_name)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    return WorkspaceTemplateResponse(
        name=template.name,
        description=template.description,
        folders=template.folders,
        readme_content=template.readme_content,
        trigger_keywords=template.trigger_keywords,
    )
```

---

#### 11.3 Update Main Router

**File**: `backend/app/interfaces/api/routes/__init__.py` (MODIFY)

```python
# Add new route imports
from app.interfaces.api.routes import (
    # ... existing imports
    screenshot,
    workspace,
)

# In create_api_router():
api_router.include_router(screenshot.router)
api_router.include_router(workspace.router)
```

---

### Week 12: Database Migrations

#### 12.1 Migration Scripts

**File**: `backend/migrations/001_add_multi_task_fields.py` (NEW)

```python
"""Add multi-task fields to sessions collection."""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import get_settings

async def migrate():
    """Add multi_task_challenge, workspace_structure, and budget fields to sessions."""
    settings = get_settings()
    client = AsyncIOMotorClient(settings.MONGODB_URI)
    db = client[settings.MONGODB_DATABASE]

    # Update sessions collection schema (MongoDB is schemaless, so this is documentation)
    # The actual fields will be added when sessions are created/updated

    # Create indexes for new queries
    await db.sessions.create_index("multi_task_challenge.id")
    await db.sessions.create_index("budget_paused")

    print("✅ Multi-task fields migration complete")

if __name__ == "__main__":
    asyncio.run(migrate())
```

**File**: `backend/migrations/003_add_metrics_collection.py` (NEW)

```python
"""Create session_metrics collection."""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import get_settings

async def migrate():
    """Create session_metrics collection with indexes."""
    settings = get_settings()
    client = AsyncIOMotorClient(settings.MONGODB_URI)
    db = client[settings.MONGODB_DATABASE]

    # Create indexes for session_metrics
    await db.session_metrics.create_index("session_id", unique=True)
    await db.session_metrics.create_index("user_id")
    await db.session_metrics.create_index("started_at")
    await db.session_metrics.create_index("updated_at")

    print("✅ Session metrics collection created")

if __name__ == "__main__":
    asyncio.run(migrate())
```

**File**: `backend/migrations/run_all.sh` (NEW)

```bash
#!/bin/bash
# Run all migrations in order

set -e

echo "Running migrations..."

python migrations/001_add_multi_task_fields.py
python migrations/002_add_gridfs_indexes.py
python migrations/003_add_metrics_collection.py

echo "✅ All migrations complete"
```

---

### Week 13: Testing & Integration

#### 13.1 Unit Tests

**File**: `backend/tests/domain/services/agents/test_context_manager.py` (NEW)

```python
"""Tests for ContextManager."""
import pytest
from app.domain.services.agents.context_manager import ContextManager


def test_track_file_operation():
    """Test file operation tracking."""
    manager = ContextManager()

    manager.track_file_operation(
        path="/workspace/test.py",
        operation="created",
        content_summary="Test file",
    )

    summary = manager.get_context_summary()
    assert "/workspace/test.py" in summary
    assert "created" in summary


def test_deliverable_tracking():
    """Test deliverable completion tracking."""
    manager = ContextManager()

    manager.mark_deliverable_complete("/workspace/report.pdf")

    deliverables = manager.get_deliverables()
    assert "/workspace/report.pdf" in deliverables


def test_token_limit_enforcement():
    """Test that context summary respects token limits."""
    manager = ContextManager(max_context_tokens=100)

    # Add lots of context
    for i in range(100):
        manager.track_file_operation(
            path=f"/workspace/file_{i}.txt",
            operation="created",
        )

    summary = manager.get_context_summary(max_tokens=50)

    # Estimate tokens (rough)
    estimated_tokens = len(summary) * 0.25
    assert estimated_tokens <= 60  # Allow some margin


def test_context_prioritization():
    """Test that deliverables are prioritized in summary."""
    manager = ContextManager()

    # Add regular file
    manager.track_file_operation(
        path="/workspace/temp.txt",
        operation="created",
    )

    # Add deliverable
    manager.track_file_operation(
        path="/workspace/deliverable.pdf",
        operation="created",
        is_deliverable=True,
    )
    manager.mark_deliverable_complete("/workspace/deliverable.pdf")

    summary = manager.get_context_summary()

    # Deliverables should appear first
    deliverable_pos = summary.find("deliverable.pdf")
    temp_pos = summary.find("temp.txt")

    assert deliverable_pos < temp_pos
```

---

#### 13.2 Integration Tests

**File**: `backend/tests/integration/test_multi_task_workflow.py` (NEW)

```python
"""Integration tests for multi-task workflow."""
import pytest
from app.domain.models.multi_task import MultiTaskChallenge, TaskDefinition, Deliverable, DeliverableType
from app.domain.services.flows.plan_act import PlanActFlow


@pytest.mark.asyncio
async def test_multi_task_execution(
    test_session,
    plan_act_flow: PlanActFlow,
):
    """Test end-to-end multi-task execution."""

    # Create multi-task challenge
    challenge = MultiTaskChallenge(
        title="Test Challenge",
        description="Multi-task test",
        tasks=[
            TaskDefinition(
                title="Task 1",
                description="Create file",
                deliverables=[
                    Deliverable(
                        name="test.txt",
                        type=DeliverableType.FILE,
                        path="deliverables/test.txt",
                        description="Test file",
                        required=True,
                    )
                ],
            ),
            TaskDefinition(
                title="Task 2",
                description="Read file",
                deliverables=[],
            ),
        ],
    )

    test_session.multi_task_challenge = challenge

    # Execute workflow (this would be the actual flow execution)
    # ... test implementation
```

---

#### 13.3 E2E Tests (Playwright)

**File**: `frontend/tests/e2e/multi-task-workflow.spec.ts` (NEW)

```typescript
import { test, expect } from '@playwright/test'

test.describe('Multi-Task Workflow', () => {
  test('should display multi-task dashboard', async ({ page }) => {
    await page.goto('/chat/test-session')

    // Start multi-task challenge
    await page.fill('[data-testid="chat-input"]', 'Execute multi-task challenge')
    await page.click('[data-testid="send-button"]')

    // Wait for multi-task dashboard to appear
    await expect(page.locator('.multi-task-dashboard')).toBeVisible()

    // Verify task list
    const tasks = page.locator('.task-item')
    await expect(tasks).toHaveCount(3)

    // Verify progress bar
    const progress = page.locator('.progress-percentage')
    await expect(progress).toBeVisible()
  })

  test('should update task progress in real-time', async ({ page }) => {
    await page.goto('/chat/test-session')

    // Monitor for multi-task events
    const progressUpdates: string[] = []

    page.on('websocket', ws => {
      ws.on('framereceived', frame => {
        const data = JSON.parse(frame.payload.toString())
        if (data.type === 'multi_task') {
          progressUpdates.push(data.action)
        }
      })
    })

    // Start multi-task
    await page.fill('[data-testid="chat-input"]', 'Run multi-task test')
    await page.click('[data-testid="send-button"]')

    // Wait for completion
    await page.waitForSelector('.task-item.completed')

    // Verify we received progress updates
    expect(progressUpdates).toContain('task_completed')
  })
})
```

---

## 📊 Implementation Timeline Summary

| Phase | Duration | Deliverables | Dependencies |
|-------|----------|--------------|--------------|
| **Phase 1: Foundation** | Weeks 1-3 | Event models, multi-task models, context manager, workspace templates, GridFS setup | None |
| **Phase 2: Screenshot & Monitoring** | Weeks 4-6 | Screenshot capture, metrics collector, budget manager, self-validator | Phase 1 |
| **Phase 3: Agent Enhancements** | Weeks 7-8 | Research agent, complexity assessor, command formatter | Phase 1-2 |
| **Phase 4: Frontend UI** | Weeks 9-10 | Screenshot timeline, multi-task dashboard, monitoring panel, enhanced status bar | Phase 1-3 |
| **Phase 5: API & Testing** | Weeks 11-13 | API routes, migrations, unit tests, integration tests, E2E tests | All phases |

**Total**: 11-13 weeks with built-in buffer

---

## 🗂️ Critical Files Summary

### Backend Files to Modify

| File | Type | Priority | Description |
|------|------|----------|-------------|
| `backend/app/domain/models/event.py` | MODIFY | HIGH | Add new event types |
| `backend/app/domain/models/session.py` | MODIFY | HIGH | Add multi-task/budget fields |
| `backend/app/domain/models/usage.py` | MODIFY | HIGH | Add SessionMetrics |
| `backend/app/infrastructure/storage/mongodb.py` | MODIFY | HIGH | Add GridFS buckets |
| `backend/app/domain/services/agents/execution.py` | MODIFY | MEDIUM | Integrate ContextManager |
| `backend/app/domain/services/flows/plan_act.py` | MODIFY | MEDIUM | Add workspace init, validation |
| `backend/app/domain/services/orchestration/agent_types.py` | MODIFY | MEDIUM | Register research agent |
| `backend/app/interfaces/api/routes/__init__.py` | MODIFY | MEDIUM | Include new routers |

### Backend Files to Create

| File | Type | Phase | Description |
|------|------|-------|-------------|
| `backend/app/domain/services/agents/context_manager.py` | NEW | 1 | Context retention system |
| `backend/app/domain/models/multi_task.py` | NEW | 1 | Multi-task domain models |
| `backend/app/domain/models/screenshot.py` | NEW | 2 | Screenshot models |
| `backend/app/domain/services/workspace/` (3 files) | NEW | 1 | Workspace management |
| `backend/app/domain/services/screenshot/` (2 files) | NEW | 2 | Screenshot capture |
| `backend/app/domain/services/usage/` (2 files) | NEW | 2 | Metrics & budget |
| `backend/app/domain/services/validation/self_validator.py` | NEW | 2 | Deliverable validation |
| `backend/app/domain/services/orchestration/research_agent.py` | NEW | 3 | Research specialist |
| `backend/app/domain/services/agents/complexity_assessor.py` | NEW | 3 | Complexity assessment |
| `backend/app/domain/services/tools/command_formatter.py` | NEW | 3 | Command formatting |
| `backend/app/interfaces/api/routes/screenshot.py` | NEW | 5 | Screenshot API |
| `backend/app/interfaces/api/routes/workspace.py` | NEW | 5 | Workspace API |
| `backend/migrations/` (3 scripts) | NEW | 5 | Database migrations |

### Frontend Files to Create

| File | Type | Phase | Description |
|------|------|-------|-------------|
| `frontend/src/types/multi_task.ts` | NEW | 4 | Multi-task types |
| `frontend/src/types/screenshot.ts` | NEW | 4 | Screenshot types |
| `frontend/src/composables/useScreenshotTimeline.ts` | NEW | 4 | Screenshot state |
| `frontend/src/composables/useTaskProgress.ts` | NEW | 4 | Multi-task state |
| `frontend/src/components/monitoring/` (8 components) | NEW | 4 | Monitoring UI |

---

## ✅ Success Criteria

### Functional Requirements

- ✅ Multi-task challenges execute 6+ tasks sequentially with progress tracking
- ✅ Workspace auto-initializes with appropriate template based on task
- ✅ Screenshots captured at key execution points (step start/complete, errors, verification)
- ✅ Context retained across execution steps (files created in step 1 accessible in step 2)
- ✅ Budget tracking warns at 80% and pauses execution at 100%
- ✅ Self-validation runs before task completion and reports issues
- ✅ Command display shows human-readable actions in UI
- ✅ Deliverables organized in workspace and tracked in manifest

### Non-Functional Requirements

- ✅ No performance degradation (< 5% overhead from new features)
- ✅ Screenshots compressed to < 500KB each with JPEG quality 85
- ✅ UI remains responsive with 100+ screenshots (virtual scrolling)
- ✅ Backward compatible with existing sessions (all new fields Optional)
- ✅ Test coverage > 80% for new code
- ✅ GridFS storage with 30-day retention policy

---

## 🚨 Risk Mitigation

| Risk | Impact | Mitigation Strategy |
|------|--------|---------------------|
| **Storage growth from screenshots** | HIGH | Compression (JPEG 85%), thumbnails, 30-day retention policy, GridFS cleanup job |
| **Performance from more events** | MEDIUM | Event batching (10 events), async processing, Redis caching, MongoDB indexing |
| **Complexity from many features** | MEDIUM | Phased rollout, feature flags, comprehensive testing, documentation |
| **Credit tracking accuracy** | LOW | Conservative token estimates, 20% buffer, user override capability |
| **Context token usage** | MEDIUM | Token-aware summarization (8K limit), smart truncation, prioritization (deliverables first) |
| **GridFS setup complexity** | LOW | Use existing motor library, migrations tested in staging first |
| **Frontend memory with screenshots** | MEDIUM | Limit to 50 screenshots in memory, lazy loading, virtual scrolling |
| **Multi-task state complexity** | MEDIUM | Use existing event sourcing, store state in Session model, replay capability |

---

## 🎯 Post-Implementation

### Deployment Checklist

1. **Database Migrations**
   ```bash
   cd backend/migrations
   chmod +x run_all.sh
   ./run_all.sh
   ```

2. **Environment Variables**
   - No new env vars required (uses existing MongoDB, Redis)
   - GridFS uses same MongoDB connection

3. **Feature Flags** (Optional)
   ```python
   ENABLE_MULTI_TASK = True
   ENABLE_SCREENSHOTS = True
   ENABLE_BUDGET_TRACKING = True
   ```

4. **Monitoring**
   - Add CloudWatch/Datadog metrics for:
     - Screenshot storage size
     - Budget warning frequency
     - Multi-task completion rate
     - Context manager token usage

5. **Documentation**
   - Update API docs with new endpoints
   - Add workspace template guide
   - Create multi-task tutorial
   - Document screenshot storage policy

---

## 📈 Performance Benchmarks

**Before Implementation**:
- Session creation: ~200ms
- Event processing: ~50ms
- Memory per session: ~10MB

**Target After Implementation**:
- Session creation: <220ms (+10%)
- Event processing: <60ms (+20% due to batching)
- Memory per session: ~15MB (+50% due to context manager)
- Screenshot capture: <500ms (async, non-blocking)

---

## 🔄 Rollout Strategy

### Staging (Week 11)
1. Deploy Phase 1-3 to staging
2. Run integration tests
3. Manual QA with test multi-task challenges

### Canary (Week 12)
1. Deploy to 10% of production users
2. Monitor metrics (errors, latency, storage)
3. Gather user feedback

### Full Production (Week 13)
1. Deploy to 100% if canary successful
2. Monitor for 48 hours
3. Enable all features via feature flags

---

## 📝 Next Steps

1. **Review & Approval** - Team review of revised plan
2. **Sprint Planning** - Break down into 2-week sprints
3. **Kick-off** - Phase 1 Week 1 implementation
4. **Daily Standups** - Track progress and blockers
5. **Weekly Demos** - Show incremental progress to stakeholders

---

## 🎉 Summary

This revised plan:
- ✅ **Fixes** all issues identified in original plan
- ✅ **Leverages** existing infrastructure (usage tracking, orchestration)
- ✅ **Adds** missing components (API routes, migrations, frontend types)
- ✅ **Realistic** 11-13 week timeline with buffer
- ✅ **Backward compatible** with existing sessions
- ✅ **Tested** with comprehensive unit, integration, and E2E tests
- ✅ **Production-ready** with migrations, monitoring, and rollout strategy

**Ready to proceed with Phase 1, Week 1!** 🚀
