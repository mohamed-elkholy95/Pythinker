"""Repository Protocol for SkillPackage persistence."""

from typing import Any, Protocol


class SkillPackageRepository(Protocol):
    """Minimal write-only repository for persisting skill packages."""

    async def save_package(self, package_doc: dict[str, Any]) -> None:
        """Insert a skill package document into persistent storage."""
        ...
