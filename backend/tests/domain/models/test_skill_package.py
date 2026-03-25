"""Tests for skill package domain models."""

import pytest

from app.domain.models.skill_package import (
    SkillExample,
    SkillFeatureCategory,
    SkillFeatureMapping,
    SkillPackageType,
    SkillWorkflowStep,
)


@pytest.mark.unit
class TestSkillPackageTypeEnum:
    def test_all_values(self) -> None:
        expected = {"simple", "standard", "advanced"}
        assert {t.value for t in SkillPackageType} == expected


@pytest.mark.unit
class TestSkillFeatureMapping:
    def test_construction(self) -> None:
        mapping = SkillFeatureMapping(
            feature="Bar Chart",
            user_value="Compare values at a glance",
            when_to_use="Comparing across categories",
        )
        assert mapping.feature == "Bar Chart"
        assert mapping.user_value == "Compare values at a glance"


@pytest.mark.unit
class TestSkillFeatureCategory:
    def test_construction(self) -> None:
        cat = SkillFeatureCategory(category="Data Visualization")
        assert cat.category == "Data Visualization"
        assert cat.mappings == []

    def test_with_mappings(self) -> None:
        mapping = SkillFeatureMapping(
            feature="Line Chart",
            user_value="See trends",
            when_to_use="Time series",
        )
        cat = SkillFeatureCategory(category="Charts", mappings=[mapping])
        assert len(cat.mappings) == 1


@pytest.mark.unit
class TestSkillWorkflowStep:
    def test_construction(self) -> None:
        step = SkillWorkflowStep(step_number=1, description="Analyze input")
        assert step.step_number == 1
        assert step.substeps == []

    def test_with_substeps(self) -> None:
        step = SkillWorkflowStep(
            step_number=2,
            description="Process",
            substeps=["Parse data", "Validate", "Transform"],
        )
        assert len(step.substeps) == 3


@pytest.mark.unit
class TestSkillExample:
    def test_minimal(self) -> None:
        example = SkillExample(title="Basic", description="A simple example")
        assert example.title == "Basic"
        assert example.input_example is None
        assert example.output_example is None
        assert example.code_snippet is None

    def test_full(self) -> None:
        example = SkillExample(
            title="Full Example",
            description="Complete demo",
            input_example="input data",
            output_example="output data",
            code_snippet="print('hello')",
        )
        assert example.code_snippet == "print('hello')"
