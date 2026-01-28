#!/usr/bin/env python3
"""Test that all new modules can be imported successfully."""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

def test_imports():
    """Test all new module imports."""
    print("Testing imports for multi-task system...")
    print()

    tests_passed = 0
    tests_failed = 0

    # Test 1: Domain models
    print("1. Testing domain models...")
    try:
        from app.domain.models.multi_task import (
            TaskStatus,
            DeliverableType,
            Deliverable,
            TaskDefinition,
            TaskResult,
            MultiTaskChallenge,
        )
        print("   ✅ multi_task models")
        tests_passed += 1
    except Exception as e:
        print(f"   ❌ multi_task models: {e}")
        tests_failed += 1

    try:
        from app.domain.models.event import (
            MultiTaskEvent,
            WorkspaceEvent,
            ScreenshotEvent,
            BudgetEvent,
        )
        print("   ✅ new event types")
        tests_passed += 1
    except Exception as e:
        print(f"   ❌ new event types: {e}")
        tests_failed += 1

    try:
        from app.domain.models.usage import SessionMetrics
        print("   ✅ SessionMetrics")
        tests_passed += 1
    except Exception as e:
        print(f"   ❌ SessionMetrics: {e}")
        tests_failed += 1

    try:
        from app.domain.models.session import Session
        print("   ✅ updated Session model")
        tests_passed += 1
    except Exception as e:
        print(f"   ❌ updated Session model: {e}")
        tests_failed += 1

    # Test 2: Services
    print("\n2. Testing services...")
    try:
        from app.domain.services.agents.context_manager import (
            ContextManager,
            FileContext,
            ToolContext,
        )
        print("   ✅ ContextManager")
        tests_passed += 1
    except Exception as e:
        print(f"   ❌ ContextManager: {e}")
        tests_failed += 1

    try:
        from app.domain.services.agents.complexity_assessor import (
            ComplexityAssessor,
            ComplexityAssessment,
        )
        print("   ✅ ComplexityAssessor")
        tests_passed += 1
    except Exception as e:
        print(f"   ❌ ComplexityAssessor: {e}")
        tests_failed += 1

    try:
        from app.domain.services.tools.command_formatter import CommandFormatter
        print("   ✅ CommandFormatter")
        tests_passed += 1
    except Exception as e:
        print(f"   ❌ CommandFormatter: {e}")
        tests_failed += 1

    try:
        from app.domain.services.workspace import (
            WorkspaceTemplate,
            WorkspaceSelector,
            WorkspaceOrganizer,
            get_template,
            get_all_templates,
        )
        print("   ✅ Workspace services")
        tests_passed += 1
    except Exception as e:
        print(f"   ❌ Workspace services: {e}")
        tests_failed += 1

    try:
        from app.domain.services.orchestration.research_agent import ResearchAgent
        print("   ✅ ResearchAgent")
        tests_passed += 1
    except Exception as e:
        print(f"   ❌ ResearchAgent: {e}")
        tests_failed += 1

    # Test 3: Infrastructure
    print("\n3. Testing infrastructure...")
    try:
        from app.infrastructure.storage.mongodb import MongoDB, get_mongodb
        print("   ✅ MongoDB with GridFS")
        tests_passed += 1
    except Exception as e:
        print(f"   ❌ MongoDB with GridFS: {e}")
        tests_failed += 1

    # Summary
    print("\n" + "="*50)
    print(f"Tests passed: {tests_passed}")
    print(f"Tests failed: {tests_failed}")
    print("="*50)

    if tests_failed == 0:
        print("\n✅ All imports successful!")
        return 0
    else:
        print(f"\n❌ {tests_failed} import(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(test_imports())
