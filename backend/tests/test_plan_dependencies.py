"""Tests for plan dependency inference and validation."""

from app.domain.models.plan import ExecutionStatus, Plan, Step


class TestPlanDependencyInference:
    """Tests for dependency inference methods."""

    def test_sequential_dependency_inference(self):
        """Test that sequential dependencies are inferred correctly."""
        plan = Plan(
            goal="Test task",
            steps=[
                Step(id="1", description="First step"),
                Step(id="2", description="Second step"),
                Step(id="3", description="Third step"),
            ],
        )
        plan.infer_sequential_dependencies()

        assert plan.steps[0].dependencies == []
        assert plan.steps[1].dependencies == ["1"]
        assert plan.steps[2].dependencies == ["2"]

    def test_smart_dependency_with_previous_patterns(self):
        """Test keyword-based dependency detection for previous step."""
        plan = Plan(
            goal="Research task",
            steps=[
                Step(id="1", description="Search for information about the topic"),
                Step(id="2", description="Using the search results, analyze the data"),
                Step(id="3", description="Based on the analysis, create a summary"),
            ],
        )
        plan.infer_smart_dependencies(use_sequential_fallback=False)

        # First step has no dependencies
        assert plan.steps[0].dependencies == []
        # "Using the" pattern detected
        assert plan.steps[1].dependencies == ["1"]
        # "Based on" pattern detected
        assert plan.steps[2].dependencies == ["2"]

    def test_smart_dependency_with_aggregation_patterns(self):
        """Test that aggregation patterns depend on all previous steps."""
        plan = Plan(
            goal="Multi-source research",
            steps=[
                Step(id="1", description="Search source A for data"),
                Step(id="2", description="Search source B for data"),
                Step(id="3", description="Search source C for data"),
                Step(id="4", description="Combine all findings into a report"),
            ],
        )
        plan.infer_smart_dependencies(use_sequential_fallback=False)

        # First three steps have no explicit patterns (no sequential fallback)
        assert plan.steps[0].dependencies == []
        assert plan.steps[1].dependencies == []
        assert plan.steps[2].dependencies == []
        # "Combine" triggers all-previous dependency
        assert set(plan.steps[3].dependencies) == {"1", "2", "3"}

    def test_smart_dependency_summarize_pattern(self):
        """Test that summarize pattern triggers all-previous dependency."""
        plan = Plan(
            goal="Research and summarize",
            steps=[
                Step(id="1", description="Research topic A"),
                Step(id="2", description="Research topic B"),
                Step(id="3", description="Summarize all results"),
            ],
        )
        plan.infer_smart_dependencies(use_sequential_fallback=False)

        assert set(plan.steps[2].dependencies) == {"1", "2"}

    def test_smart_dependency_independent_patterns(self):
        """Test that independent patterns result in no dependencies."""
        plan = Plan(
            goal="Task with independent start",
            steps=[
                Step(id="1", description="First, gather requirements"),
                Step(id="2", description="Then analyze the requirements"),
            ],
        )
        plan.infer_smart_dependencies(use_sequential_fallback=False)

        # "First," indicates independent step
        assert plan.steps[0].dependencies == []
        # "Then" indicates dependency on previous
        assert plan.steps[1].dependencies == ["1"]

    def test_smart_dependency_with_sequential_fallback(self):
        """Test that sequential fallback works when enabled."""
        plan = Plan(
            goal="Generic task",
            steps=[
                Step(id="1", description="Do something"),
                Step(id="2", description="Do another thing"),
                Step(id="3", description="Do final thing"),
            ],
        )
        plan.infer_smart_dependencies(use_sequential_fallback=True)

        # No patterns detected, but fallback enabled
        assert plan.steps[0].dependencies == []
        assert plan.steps[1].dependencies == ["1"]
        assert plan.steps[2].dependencies == ["2"]

    def test_smart_dependency_without_sequential_fallback(self):
        """Test that steps remain independent when fallback is disabled."""
        plan = Plan(
            goal="Parallel task",
            steps=[
                Step(id="1", description="Do task A"),
                Step(id="2", description="Do task B"),
                Step(id="3", description="Do task C"),
            ],
        )
        plan.infer_smart_dependencies(use_sequential_fallback=False)

        # No patterns detected, no fallback - all independent
        assert plan.steps[0].dependencies == []
        assert plan.steps[1].dependencies == []
        assert plan.steps[2].dependencies == []

    def test_existing_dependencies_not_overwritten(self):
        """Test that explicit dependencies are preserved."""
        plan = Plan(
            goal="Pre-defined dependencies",
            steps=[
                Step(id="1", description="Step 1"),
                Step(id="2", description="Step 2", dependencies=["1"]),
                Step(id="3", description="Step 3"),
            ],
        )
        plan.infer_smart_dependencies(use_sequential_fallback=True)

        # Explicit dependency preserved
        assert plan.steps[1].dependencies == ["1"]
        # New dependency inferred
        assert plan.steps[2].dependencies == ["2"]


class TestPlanDependencyValidation:
    """Tests for dependency validation."""

    def test_valid_plan_passes_validation(self):
        """Test that a valid plan passes validation."""
        plan = Plan(
            goal="Valid task",
            steps=[
                Step(id="1", description="Step 1"),
                Step(id="2", description="Step 2", dependencies=["1"]),
            ],
        )
        result = plan.validate_plan()

        assert result.passed is True
        assert len(result.errors) == 0

    def test_circular_dependency_detected(self):
        """Test that circular dependencies are detected."""
        plan = Plan(
            goal="Circular task",
            steps=[
                Step(id="1", description="Step 1", dependencies=["2"]),
                Step(id="2", description="Step 2", dependencies=["1"]),
            ],
        )
        result = plan.validate_plan()

        assert result.passed is False
        assert any("Circular dependency" in err for err in result.errors)

    def test_self_dependency_detected(self):
        """Test that self-dependencies are detected."""
        plan = Plan(
            goal="Self-referencing task",
            steps=[
                Step(id="1", description="Step 1", dependencies=["1"]),
            ],
        )
        result = plan.validate_plan()

        assert result.passed is False
        assert any("depends on itself" in err for err in result.errors)

    def test_orphan_dependency_detected(self):
        """Test that dependencies on non-existent steps are detected."""
        plan = Plan(
            goal="Orphan dependency task",
            steps=[
                Step(id="1", description="Step 1"),
                Step(id="2", description="Step 2", dependencies=["99"]),
            ],
        )
        result = plan.validate_plan()

        assert result.passed is False
        assert any("non-existent step" in err for err in result.errors)

    def test_empty_plan_fails_validation(self):
        """Test that empty plans fail validation."""
        plan = Plan(goal="Empty task", steps=[])
        result = plan.validate_plan()

        assert result.passed is False
        assert any("no steps" in err for err in result.errors)

    def test_empty_description_fails_validation(self):
        """Test that steps with empty descriptions fail validation."""
        plan = Plan(
            goal="Empty description task",
            steps=[
                Step(id="1", description=""),
            ],
        )
        result = plan.validate_plan()

        assert result.passed is False
        assert any("empty description" in err for err in result.errors)

    def test_complex_plan_warning(self):
        """Test that plans with many steps get warnings."""
        plan = Plan(
            goal="Complex task",
            steps=[Step(id=str(i), description=f"Step {i}") for i in range(15)],
        )
        result = plan.validate_plan()

        assert result.passed is True  # Warnings don't fail validation
        assert any("consider simplifying" in warn for warn in result.warnings)

    def test_many_dependencies_warning(self):
        """Test that steps with many dependencies get warnings."""
        plan = Plan(
            goal="Overly dependent task",
            steps=[
                Step(id="1", description="Step 1"),
                Step(id="2", description="Step 2"),
                Step(id="3", description="Step 3"),
                Step(id="4", description="Step 4"),
                Step(id="5", description="Step 5"),
                Step(id="6", description="Step 6"),
                Step(
                    id="7",
                    description="Final step",
                    dependencies=["1", "2", "3", "4", "5", "6"],
                ),
            ],
        )
        result = plan.validate_plan()

        assert result.passed is True
        assert any("dependencies" in warn and "complex" in warn for warn in result.warnings)


class TestBlockedCascade:
    """Tests for blocked step cascade."""

    def test_blocked_cascade_simple(self):
        """Test that blocking propagates through dependencies."""
        plan = Plan(
            goal="Cascade task",
            steps=[
                Step(id="1", description="Step 1"),
                Step(id="2", description="Step 2", dependencies=["1"]),
                Step(id="3", description="Step 3", dependencies=["2"]),
            ],
        )

        # Mark step 1 as failed
        plan.steps[0].status = ExecutionStatus.FAILED
        blocked_ids = plan.mark_blocked_cascade("1", "Step 1 failed")

        assert "2" in blocked_ids
        assert "3" in blocked_ids
        assert plan.steps[1].status == ExecutionStatus.BLOCKED
        assert plan.steps[2].status == ExecutionStatus.BLOCKED

    def test_blocked_cascade_partial(self):
        """Test that only dependent steps are blocked."""
        plan = Plan(
            goal="Partial cascade",
            steps=[
                Step(id="1", description="Step 1"),
                Step(id="2", description="Independent step"),  # No dependencies
                Step(id="3", description="Step 3", dependencies=["1"]),
            ],
        )

        plan.steps[0].status = ExecutionStatus.FAILED
        blocked_ids = plan.mark_blocked_cascade("1", "Step 1 failed")

        assert "3" in blocked_ids
        assert "2" not in blocked_ids
        assert plan.steps[1].status == ExecutionStatus.PENDING

    def test_blocked_cascade_with_aggregation_deps(self):
        """Test cascade with aggregation dependencies."""
        plan = Plan(
            goal="Aggregation cascade",
            steps=[
                Step(id="1", description="Research A"),
                Step(id="2", description="Research B"),
                Step(id="3", description="Combine all findings", dependencies=["1", "2"]),
            ],
        )

        # Block just step 1
        plan.steps[0].status = ExecutionStatus.FAILED
        blocked_ids = plan.mark_blocked_cascade("1", "Step 1 failed")

        # Step 3 should be blocked since it depends on step 1
        assert "3" in blocked_ids
        # Step 2 is independent
        assert "2" not in blocked_ids

    def test_blocked_cascade_already_done_steps(self):
        """Test that already-done steps are not blocked."""
        plan = Plan(
            goal="Partial completion",
            steps=[
                Step(id="1", description="Step 1"),
                Step(id="2", description="Step 2", dependencies=["1"], status=ExecutionStatus.COMPLETED),
                Step(id="3", description="Step 3", dependencies=["1"]),
            ],
        )

        plan.steps[0].status = ExecutionStatus.FAILED
        blocked_ids = plan.mark_blocked_cascade("1", "Step 1 failed")

        # Step 2 already completed - not blocked
        assert "2" not in blocked_ids
        # Step 3 pending and dependent - blocked
        assert "3" in blocked_ids


class TestStepStatus:
    """Tests for step status methods."""

    def test_step_is_actionable(self):
        """Test is_actionable for different statuses."""
        pending_step = Step(id="1", description="Pending", status=ExecutionStatus.PENDING)
        running_step = Step(id="2", description="Running", status=ExecutionStatus.RUNNING)
        completed_step = Step(id="3", description="Completed", status=ExecutionStatus.COMPLETED)

        assert pending_step.is_actionable() is True
        assert running_step.is_actionable() is False
        assert completed_step.is_actionable() is False

    def test_step_is_done(self):
        """Test is_done for different statuses."""
        pending_step = Step(id="1", description="Pending", status=ExecutionStatus.PENDING)
        completed_step = Step(id="2", description="Completed", status=ExecutionStatus.COMPLETED)
        failed_step = Step(id="3", description="Failed", status=ExecutionStatus.FAILED)
        blocked_step = Step(id="4", description="Blocked", status=ExecutionStatus.BLOCKED)

        assert pending_step.is_done() is False
        assert completed_step.is_done() is True
        assert failed_step.is_done() is True
        assert blocked_step.is_done() is True
