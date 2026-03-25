"""Tests for Project domain model."""

import pytest

from app.domain.models.project import Project, ProjectStatus


class TestProjectStatus:
    def test_values(self) -> None:
        assert ProjectStatus.ACTIVE == "active"
        assert ProjectStatus.ARCHIVED == "archived"


class TestProject:
    def test_defaults(self) -> None:
        p = Project(user_id="u-1", name="My Project")
        assert p.status == ProjectStatus.ACTIVE
        assert p.session_count == 0
        assert p.instructions == ""
        assert p.connector_ids == []

    def test_empty_name_rejected(self) -> None:
        with pytest.raises(ValueError, match="empty"):
            Project(user_id="u-1", name="")

    def test_whitespace_name_rejected(self) -> None:
        with pytest.raises(ValueError, match="empty"):
            Project(user_id="u-1", name="   ")

    def test_long_name_rejected(self) -> None:
        with pytest.raises(ValueError, match="100"):
            Project(user_id="u-1", name="x" * 101)

    def test_long_instructions_rejected(self) -> None:
        with pytest.raises(ValueError, match="10,000"):
            Project(user_id="u-1", name="Test", instructions="x" * 10_001)

    def test_name_stripped(self) -> None:
        p = Project(user_id="u-1", name="  My Project  ")
        assert p.name == "My Project"

    def test_unique_ids(self) -> None:
        p1 = Project(user_id="u-1", name="A")
        p2 = Project(user_id="u-1", name="B")
        assert p1.id != p2.id
