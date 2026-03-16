"""Tests for the HMAS (Hierarchical Multi-Agent System) Orchestrator.

Tests the HMASOrchestrator which coordinates supervisors and manages
task routing, dependency handling, and parallel execution within
the hierarchical multi-agent system.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.models.supervisor import (
    SubTask,
    Supervisor,
    SupervisorDomain,
)
from app.domain.services.hmas_orchestrator import HMASOrchestrator


class TestHMASOrchestrator:
    """Tests for HMASOrchestrator core functionality."""

    @pytest.fixture
    def mock_agent_factory(self) -> MagicMock:
        """Create a mock agent factory."""
        factory = MagicMock()
        factory.create_agent = MagicMock(return_value=AsyncMock(execute=AsyncMock(return_value="Task completed")))
        return factory

    @pytest.fixture
    def research_supervisor(self) -> Supervisor:
        """Create a research supervisor."""
        return Supervisor(
            name="research-sup",
            domain=SupervisorDomain.RESEARCH,
            description="Research supervisor for information gathering",
        )

    @pytest.fixture
    def code_supervisor(self) -> Supervisor:
        """Create a code supervisor."""
        return Supervisor(
            name="code-sup",
            domain=SupervisorDomain.CODE,
            description="Code supervisor for development tasks",
        )

    def test_register_supervisor(self, mock_agent_factory: MagicMock, research_supervisor: Supervisor) -> None:
        """Test registering a supervisor."""
        orchestrator = HMASOrchestrator(agent_factory=mock_agent_factory)

        orchestrator.register_supervisor(research_supervisor)

        assert orchestrator.get_supervisor(SupervisorDomain.RESEARCH) is not None
        assert orchestrator.get_supervisor(SupervisorDomain.RESEARCH).name == "research-sup"

    def test_register_multiple_supervisors(
        self,
        mock_agent_factory: MagicMock,
        research_supervisor: Supervisor,
        code_supervisor: Supervisor,
    ) -> None:
        """Test registering multiple supervisors for different domains."""
        orchestrator = HMASOrchestrator(agent_factory=mock_agent_factory)

        orchestrator.register_supervisor(research_supervisor)
        orchestrator.register_supervisor(code_supervisor)

        assert orchestrator.get_supervisor(SupervisorDomain.RESEARCH) is not None
        assert orchestrator.get_supervisor(SupervisorDomain.CODE) is not None
        assert orchestrator.get_supervisor(SupervisorDomain.DATA) is None

    @pytest.mark.asyncio
    async def test_orchestrator_routes_to_supervisor(
        self,
        mock_agent_factory: MagicMock,
        research_supervisor: Supervisor,
        code_supervisor: Supervisor,
    ) -> None:
        """Test that tasks are routed to the correct supervisor."""
        orchestrator = HMASOrchestrator(agent_factory=mock_agent_factory)

        # Add supervisors
        orchestrator.register_supervisor(research_supervisor)
        orchestrator.register_supervisor(code_supervisor)

        # Route a research task
        supervisor = orchestrator.route_task("Research the topic", SupervisorDomain.RESEARCH)
        assert supervisor is not None
        assert supervisor.name == "research-sup"

        # Route a code task
        supervisor = orchestrator.route_task("Write a function", SupervisorDomain.CODE)
        assert supervisor is not None
        assert supervisor.name == "code-sup"

    @pytest.mark.asyncio
    async def test_route_task_with_auto_detection(
        self,
        mock_agent_factory: MagicMock,
        research_supervisor: Supervisor,
        code_supervisor: Supervisor,
    ) -> None:
        """Test automatic domain detection from task description."""
        orchestrator = HMASOrchestrator(agent_factory=mock_agent_factory)

        orchestrator.register_supervisor(research_supervisor)
        orchestrator.register_supervisor(code_supervisor)

        # Should detect research domain
        supervisor = orchestrator.route_task("Research AI trends and gather data")
        assert supervisor is not None
        assert supervisor.domain == SupervisorDomain.RESEARCH

        # Should detect code domain
        supervisor = orchestrator.route_task("Implement a Python function to parse JSON")
        assert supervisor is not None
        assert supervisor.domain == SupervisorDomain.CODE

    @pytest.mark.asyncio
    async def test_route_task_returns_none_for_unknown_domain(self, mock_agent_factory: MagicMock) -> None:
        """Test that routing returns None when no supervisor matches."""
        orchestrator = HMASOrchestrator(agent_factory=mock_agent_factory)

        # No supervisors registered
        supervisor = orchestrator.route_task("Random task", SupervisorDomain.RESEARCH)
        assert supervisor is None

    @pytest.mark.asyncio
    async def test_orchestrator_manages_dependencies(
        self, mock_agent_factory: MagicMock, research_supervisor: Supervisor
    ) -> None:
        """Test that the orchestrator properly manages task dependencies."""
        orchestrator = HMASOrchestrator(agent_factory=mock_agent_factory)
        orchestrator.register_supervisor(research_supervisor)

        # Add tasks with dependencies
        task1 = SubTask(id="t1", description="Gather data")
        task2 = SubTask(id="t2", description="Analyze data", dependencies=["t1"])

        research_supervisor.assign_task(task1)
        research_supervisor.assign_task(task2)

        # Only t1 should be ready initially
        ready = research_supervisor.get_ready_tasks()
        assert len(ready) == 1
        assert ready[0].id == "t1"

    @pytest.mark.asyncio
    async def test_dependency_chain_execution(
        self, mock_agent_factory: MagicMock, research_supervisor: Supervisor
    ) -> None:
        """Test that completing a task unblocks dependent tasks."""
        orchestrator = HMASOrchestrator(agent_factory=mock_agent_factory)
        orchestrator.register_supervisor(research_supervisor)

        # Create a dependency chain: t1 -> t2 -> t3
        task1 = SubTask(id="t1", description="First task")
        task2 = SubTask(id="t2", description="Second task", dependencies=["t1"])
        task3 = SubTask(id="t3", description="Third task", dependencies=["t2"])

        research_supervisor.assign_task(task1)
        research_supervisor.assign_task(task2)
        research_supervisor.assign_task(task3)

        # Only t1 should be ready initially
        ready = research_supervisor.get_ready_tasks()
        assert len(ready) == 1
        assert ready[0].id == "t1"

        # Complete t1
        research_supervisor.complete_task("t1", "First result")

        # Now t2 should be ready
        ready = research_supervisor.get_ready_tasks()
        assert len(ready) == 1
        assert ready[0].id == "t2"

        # Complete t2
        research_supervisor.complete_task("t2", "Second result")

        # Now t3 should be ready
        ready = research_supervisor.get_ready_tasks()
        assert len(ready) == 1
        assert ready[0].id == "t3"

    @pytest.mark.asyncio
    async def test_parallel_tasks_ready(self, mock_agent_factory: MagicMock, research_supervisor: Supervisor) -> None:
        """Test that independent tasks can run in parallel."""
        orchestrator = HMASOrchestrator(agent_factory=mock_agent_factory)
        orchestrator.register_supervisor(research_supervisor)

        # Create independent tasks
        task1 = SubTask(id="t1", description="First independent task")
        task2 = SubTask(id="t2", description="Second independent task")
        task3 = SubTask(id="t3", description="Depends on both", dependencies=["t1", "t2"])

        research_supervisor.assign_task(task1)
        research_supervisor.assign_task(task2)
        research_supervisor.assign_task(task3)

        # Both t1 and t2 should be ready
        ready = research_supervisor.get_ready_tasks()
        assert len(ready) == 2
        ready_ids = {task.id for task in ready}
        assert "t1" in ready_ids
        assert "t2" in ready_ids
        assert "t3" not in ready_ids

    @pytest.mark.asyncio
    async def test_execute_with_supervisor_basic(
        self, mock_agent_factory: MagicMock, research_supervisor: Supervisor
    ) -> None:
        """Test basic execution with a supervisor."""
        orchestrator = HMASOrchestrator(agent_factory=mock_agent_factory)
        orchestrator.register_supervisor(research_supervisor)

        # Add a simple task
        task = SubTask(id="t1", description="Simple task", assigned_agent="search-agent")
        research_supervisor.assign_task(task)

        # Execute all tasks under the supervisor
        results = await orchestrator.execute_with_supervisor(research_supervisor)

        assert "t1" in results
        assert results["t1"] == "Task completed"

    @pytest.mark.asyncio
    async def test_execute_with_supervisor_respects_dependencies(
        self, mock_agent_factory: MagicMock, research_supervisor: Supervisor
    ) -> None:
        """Test that execution respects task dependencies."""
        # Track execution order
        execution_order: list[str] = []

        async def mock_execute(task_id: str) -> str:
            execution_order.append(task_id)
            return f"Result for {task_id}"

        mock_agent_factory.create_agent = MagicMock(return_value=AsyncMock(execute=mock_execute))

        orchestrator = HMASOrchestrator(agent_factory=mock_agent_factory)
        orchestrator.register_supervisor(research_supervisor)

        # Create tasks with dependency
        task1 = SubTask(id="t1", description="First", assigned_agent="agent1")
        task2 = SubTask(id="t2", description="Second", dependencies=["t1"], assigned_agent="agent2")

        research_supervisor.assign_task(task1)
        research_supervisor.assign_task(task2)

        await orchestrator.execute_with_supervisor(research_supervisor)

        # t1 must complete before t2
        assert execution_order.index("t1") < execution_order.index("t2")

    @pytest.mark.asyncio
    async def test_execute_with_max_parallel(
        self, mock_agent_factory: MagicMock, research_supervisor: Supervisor
    ) -> None:
        """Test that max_parallel limits concurrent execution."""
        orchestrator = HMASOrchestrator(agent_factory=mock_agent_factory)
        orchestrator.register_supervisor(research_supervisor)

        # Add many independent tasks
        for i in range(10):
            task = SubTask(id=f"t{i}", description=f"Task {i}", assigned_agent=f"agent{i}")
            research_supervisor.assign_task(task)

        # Execute with max_parallel=2
        results = await orchestrator.execute_with_supervisor(research_supervisor, max_parallel=2)

        # All tasks should complete
        assert len(results) == 10


class TestHMASOrchestrationWithoutFactory:
    """Tests for HMASOrchestrator without an agent factory."""

    def test_orchestrator_without_factory(self) -> None:
        """Test that orchestrator can be created without a factory."""
        orchestrator = HMASOrchestrator()

        supervisor = Supervisor(
            name="test-sup",
            domain=SupervisorDomain.GENERAL,
        )
        orchestrator.register_supervisor(supervisor)

        assert orchestrator.get_supervisor(SupervisorDomain.GENERAL) is not None

    def test_route_task_explicit_domain(self) -> None:
        """Test routing with explicit domain specification."""
        orchestrator = HMASOrchestrator()

        supervisor = Supervisor(
            name="general-sup",
            domain=SupervisorDomain.GENERAL,
        )
        orchestrator.register_supervisor(supervisor)

        result = orchestrator.route_task("Any task description", SupervisorDomain.GENERAL)
        assert result is not None
        assert result.name == "general-sup"


class TestDomainDetection:
    """Tests for automatic domain detection from task descriptions."""

    @pytest.fixture
    def fully_equipped_orchestrator(self) -> HMASOrchestrator:
        """Create an orchestrator with all domain supervisors."""
        orchestrator = HMASOrchestrator()

        for domain in SupervisorDomain:
            supervisor = Supervisor(
                name=f"{domain.value}-supervisor",
                domain=domain,
                description=f"Supervisor for {domain.value} domain",
            )
            orchestrator.register_supervisor(supervisor)

        return orchestrator

    def test_detect_research_domain(self, fully_equipped_orchestrator: HMASOrchestrator) -> None:
        """Test detection of research-related tasks."""
        research_tasks = [
            "Research the latest trends in AI",
            "Find information about climate change",
            "Investigate the history of Python programming",
            "Search for academic papers on machine learning",
            "Analyze market trends for tech stocks",
        ]

        for task in research_tasks:
            supervisor = fully_equipped_orchestrator.route_task(task)
            assert supervisor is not None, f"Failed to route: {task}"
            assert supervisor.domain == SupervisorDomain.RESEARCH, f"Expected RESEARCH for: {task}"

    def test_detect_code_domain(self, fully_equipped_orchestrator: HMASOrchestrator) -> None:
        """Test detection of code-related tasks."""
        code_tasks = [
            "Write a Python function to parse JSON",
            "Implement a sorting algorithm",
            "Debug the authentication code",
            "Refactor the database module",
            "Create a class for user management",
            "Fix the bug in the payment processing",
        ]

        for task in code_tasks:
            supervisor = fully_equipped_orchestrator.route_task(task)
            assert supervisor is not None, f"Failed to route: {task}"
            assert supervisor.domain == SupervisorDomain.CODE, f"Expected CODE for: {task}"

    def test_detect_data_domain(self, fully_equipped_orchestrator: HMASOrchestrator) -> None:
        """Test detection of data-related tasks."""
        data_tasks = [
            "Process the CSV dataset",
            "Transform the JSON data",
            "Clean the user data",
            "Aggregate sales statistics",
            "Parse the log files",
        ]

        for task in data_tasks:
            supervisor = fully_equipped_orchestrator.route_task(task)
            assert supervisor is not None, f"Failed to route: {task}"
            assert supervisor.domain == SupervisorDomain.DATA, f"Expected DATA for: {task}"

    def test_detect_browser_domain(self, fully_equipped_orchestrator: HMASOrchestrator) -> None:
        """Test detection of browser-related tasks."""
        browser_tasks = [
            "Navigate to the website and fill the form",
            "Click the login button",
            "Scrape the product prices from the page",
            "Download the file from the website",
            "Browse to the settings page",
        ]

        for task in browser_tasks:
            supervisor = fully_equipped_orchestrator.route_task(task)
            assert supervisor is not None, f"Failed to route: {task}"
            assert supervisor.domain == SupervisorDomain.BROWSER, f"Expected BROWSER for: {task}"

    def test_fallback_to_general_domain(self, fully_equipped_orchestrator: HMASOrchestrator) -> None:
        """Test that ambiguous tasks fall back to GENERAL domain."""
        ambiguous_tasks = [
            "Do something",
            "Help me with this",
            "Complete the task",
        ]

        for task in ambiguous_tasks:
            supervisor = fully_equipped_orchestrator.route_task(task)
            assert supervisor is not None, f"Failed to route: {task}"
            assert supervisor.domain == SupervisorDomain.GENERAL, f"Expected GENERAL for: {task}"


class TestSupervisorReplacement:
    """Tests for supervisor replacement behavior."""

    def test_replace_supervisor_for_domain(self) -> None:
        """Test that registering a new supervisor replaces the old one."""
        orchestrator = HMASOrchestrator()

        first_sup = Supervisor(name="first", domain=SupervisorDomain.RESEARCH)
        second_sup = Supervisor(name="second", domain=SupervisorDomain.RESEARCH)

        orchestrator.register_supervisor(first_sup)
        assert orchestrator.get_supervisor(SupervisorDomain.RESEARCH).name == "first"

        orchestrator.register_supervisor(second_sup)
        assert orchestrator.get_supervisor(SupervisorDomain.RESEARCH).name == "second"


class TestGetAllSupervisors:
    """Tests for retrieving all registered supervisors."""

    def test_get_all_supervisors(self) -> None:
        """Test getting all registered supervisors."""
        orchestrator = HMASOrchestrator()

        research_sup = Supervisor(name="research", domain=SupervisorDomain.RESEARCH)
        code_sup = Supervisor(name="code", domain=SupervisorDomain.CODE)

        orchestrator.register_supervisor(research_sup)
        orchestrator.register_supervisor(code_sup)

        all_supervisors = orchestrator.get_all_supervisors()

        assert len(all_supervisors) == 2
        names = {s.name for s in all_supervisors}
        assert "research" in names
        assert "code" in names

    def test_get_all_supervisors_empty(self) -> None:
        """Test getting supervisors when none are registered."""
        orchestrator = HMASOrchestrator()

        all_supervisors = orchestrator.get_all_supervisors()

        assert len(all_supervisors) == 0
