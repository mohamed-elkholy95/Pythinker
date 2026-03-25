"""Tests for repository map domain models."""

import pytest

from app.domain.models.repo_map import EntryType, RepoMap, RepoMapEntry


@pytest.mark.unit
class TestEntryTypeEnum:
    def test_all_values(self) -> None:
        expected = {
            "file", "directory", "class", "function", "method",
            "interface", "module", "constant", "type",
        }
        assert {e.value for e in EntryType} == expected


@pytest.mark.unit
class TestRepoMapEntry:
    def _make_entry(self, **kwargs) -> RepoMapEntry:
        defaults = {
            "path": "app/main.py",
            "entry_type": EntryType.FUNCTION,
            "name": "main",
        }
        defaults.update(kwargs)
        return RepoMapEntry(**defaults)

    def test_basic_construction(self) -> None:
        entry = self._make_entry()
        assert entry.path == "app/main.py"
        assert entry.entry_type == EntryType.FUNCTION
        assert entry.name == "main"
        assert entry.importance == 1.0

    def test_to_dict(self) -> None:
        entry = self._make_entry(signature="main() -> None", line_number=10)
        d = entry.to_dict()
        assert d["path"] == "app/main.py"
        assert d["entry_type"] == "function"
        assert d["name"] == "main"
        assert d["signature"] == "main() -> None"
        assert d["line_number"] == 10

    def test_from_dict(self) -> None:
        data = {
            "path": "app/utils.py",
            "entry_type": "class",
            "name": "Helper",
            "signature": "class Helper",
            "line_number": 5,
        }
        entry = RepoMapEntry.from_dict(data)
        assert entry.path == "app/utils.py"
        assert entry.entry_type == EntryType.CLASS
        assert entry.name == "Helper"

    def test_roundtrip_dict(self) -> None:
        original = self._make_entry(
            signature="main() -> None",
            docstring="Entry point",
            line_number=1,
            parent="module",
            references=["util.py"],
            importance=0.8,
        )
        restored = RepoMapEntry.from_dict(original.to_dict())
        assert restored.path == original.path
        assert restored.name == original.name
        assert restored.signature == original.signature
        assert restored.importance == original.importance

    def test_to_context_line_function(self) -> None:
        entry = self._make_entry(
            signature="main(args: list) -> int",
            line_number=10,
        )
        line = entry.to_context_line()
        assert "app/main.py:10" in line
        assert "def" in line
        assert "main(args: list) -> int" in line

    def test_to_context_line_file(self) -> None:
        entry = self._make_entry(entry_type=EntryType.FILE)
        line = entry.to_context_line()
        assert "main" in line

    def test_to_context_line_with_docstring(self) -> None:
        entry = self._make_entry(docstring="This is the main function")
        line = entry.to_context_line()
        assert "This is the main function" in line


@pytest.mark.unit
class TestRepoMap:
    def _make_map(self, **kwargs) -> RepoMap:
        return RepoMap(root_path="/repo", **kwargs)

    def test_basic_construction(self) -> None:
        repo = self._make_map()
        assert repo.root_path == "/repo"
        assert repo.entries == []
        assert repo.file_count == 0

    def test_add_entry(self) -> None:
        repo = self._make_map()
        entry = RepoMapEntry(path="file.py", entry_type=EntryType.FILE, name="file.py")
        repo.add_entry(entry)
        assert len(repo.entries) == 1

    def test_get_by_type(self) -> None:
        repo = self._make_map()
        repo.add_entry(RepoMapEntry(path="a.py", entry_type=EntryType.FILE, name="a.py"))
        repo.add_entry(RepoMapEntry(path="a.py", entry_type=EntryType.CLASS, name="Foo"))
        repo.add_entry(RepoMapEntry(path="b.py", entry_type=EntryType.FILE, name="b.py"))
        files = repo.get_by_type(EntryType.FILE)
        assert len(files) == 2
        classes = repo.get_by_type(EntryType.CLASS)
        assert len(classes) == 1

    def test_get_by_path(self) -> None:
        repo = self._make_map()
        repo.add_entry(RepoMapEntry(path="a.py", entry_type=EntryType.CLASS, name="Foo"))
        repo.add_entry(RepoMapEntry(path="b.py", entry_type=EntryType.CLASS, name="Bar"))
        entries = repo.get_by_path("a.py")
        assert len(entries) == 1
        assert entries[0].name == "Foo"

    def test_languages(self) -> None:
        repo = self._make_map(languages={"python": 10, "typescript": 5})
        assert repo.languages["python"] == 10
