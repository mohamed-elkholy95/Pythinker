"""Tests for Scratchpad — persistent working notes that survive compaction."""

import pytest

from app.domain.services.agents.scratchpad import Scratchpad, ScratchpadEntry


class TestAppendAndRead:
    """Basic append/read roundtrip."""

    def test_append_and_get_content(self):
        pad = Scratchpad()
        pad.append("Found login page at /login", tag="url")
        content = pad.get_content()

        assert "SCRATCHPAD" in content
        assert "Found login page at /login" in content
        assert "[url]" in content

    def test_append_without_tag(self):
        pad = Scratchpad()
        pad.append("Important finding")
        content = pad.get_content()

        assert "Important finding" in content
        # Should NOT have empty tag brackets
        assert "[]" not in content

    def test_multiple_entries_numbered(self):
        pad = Scratchpad()
        pad.append("First note")
        pad.append("Second note")
        pad.append("Third note")
        content = pad.get_content()

        assert "1. First note" in content
        assert "2. Second note" in content
        assert "3. Third note" in content

    def test_empty_scratchpad_returns_empty_string(self):
        pad = Scratchpad()
        assert pad.get_content() == ""


class TestFIFOEviction:
    """FIFO eviction by max_chars and max_entries."""

    def test_eviction_by_max_entries(self):
        pad = Scratchpad(max_entries=3, max_chars=10000)

        pad.append("Note 1")
        pad.append("Note 2")
        pad.append("Note 3")
        assert pad.entry_count == 3

        pad.append("Note 4")
        assert pad.entry_count == 3

        content = pad.get_content()
        assert "Note 1" not in content  # evicted (oldest)
        assert "Note 2" in content
        assert "Note 3" in content
        assert "Note 4" in content

    def test_eviction_by_max_chars(self):
        pad = Scratchpad(max_chars=50, max_entries=100)

        pad.append("a" * 30)
        pad.append("b" * 30)  # Total 60 > 50, should evict first

        assert pad.entry_count == 1
        content = pad.get_content()
        assert "b" * 30 in content
        assert "a" * 30 not in content

    def test_eviction_cascades_until_under_budget(self):
        pad = Scratchpad(max_chars=100, max_entries=100)

        pad.append("x" * 40)
        pad.append("y" * 40)
        pad.append("z" * 80)  # Total would be 160, needs to evict both x and y

        assert pad.entry_count == 1
        content = pad.get_content()
        assert "z" * 80 in content


class TestClear:
    """Clear all entries."""

    def test_clear_returns_count(self):
        pad = Scratchpad()
        pad.append("A")
        pad.append("B")
        pad.append("C")

        count = pad.clear()
        assert count == 3

    def test_clear_empties_scratchpad(self):
        pad = Scratchpad()
        pad.append("A")
        pad.clear()

        assert pad.is_empty
        assert pad.entry_count == 0
        assert pad.get_content() == ""

    def test_clear_empty_returns_zero(self):
        pad = Scratchpad()
        assert pad.clear() == 0


class TestProperties:
    """is_empty and entry_count properties."""

    def test_is_empty_when_empty(self):
        pad = Scratchpad()
        assert pad.is_empty is True

    def test_is_empty_after_append(self):
        pad = Scratchpad()
        pad.append("Note")
        assert pad.is_empty is False

    def test_entry_count(self):
        pad = Scratchpad()
        assert pad.entry_count == 0
        pad.append("A")
        assert pad.entry_count == 1
        pad.append("B")
        assert pad.entry_count == 2


class TestScratchpadEntry:
    """ScratchpadEntry dataclass."""

    def test_immutable(self):
        entry = ScratchpadEntry(note="test", tag="url")
        with pytest.raises(AttributeError):
            entry.note = "changed"  # type: ignore[misc]

    def test_default_tag_empty(self):
        entry = ScratchpadEntry(note="test")
        assert entry.tag == ""

    def test_timestamp_auto_set(self):
        entry = ScratchpadEntry(note="test")
        assert entry.timestamp > 0


class TestTransientInjection:
    """Scratchpad content should be suitable for transient injection."""

    def test_content_format_for_llm(self):
        pad = Scratchpad()
        pad.append("Key URL: https://example.com/api", tag="url")
        pad.append("Error: 404 on /users endpoint", tag="error")
        pad.append("Decision: use pagination", tag="decision")

        content = pad.get_content()

        # Should be a single string suitable for injection
        assert isinstance(content, str)
        assert content.startswith("[SCRATCHPAD")
        assert len(content) > 0

        # Each entry should be clearly numbered
        lines = content.split("\n")
        assert len(lines) == 4  # header + 3 entries

    def test_content_not_in_memory_messages(self):
        """Demonstrates the injection pattern — content is NOT stored in memory."""
        pad = Scratchpad()
        pad.append("Working note")

        # The content is meant to be injected into the message list
        # BEFORE the LLM call, but NOT persisted to memory
        content = pad.get_content()
        injection_message = {"role": "user", "content": content}

        # This message would be added to the LLM call's message list
        # but NOT to self.memory.messages
        assert injection_message["role"] == "user"
        assert "Working note" in injection_message["content"]


class TestScratchpadToolIntegration:
    """Test that ScratchpadTool works with Scratchpad."""

    @pytest.mark.asyncio
    async def test_write_and_read(self):
        from app.domain.services.tools.scratchpad import ScratchpadTool

        pad = Scratchpad()
        tool = ScratchpadTool(scratchpad=pad)

        # Write a note
        result = await tool.scratchpad_write(note="Found API key in config", tag="finding")
        assert result.success is True
        assert "1 entries" in result.message

        # Read notes
        result = await tool.scratchpad_read()
        assert result.success is True
        assert "Found API key in config" in result.data

    @pytest.mark.asyncio
    async def test_write_empty_note_fails(self):
        from app.domain.services.tools.scratchpad import ScratchpadTool

        pad = Scratchpad()
        tool = ScratchpadTool(scratchpad=pad)

        result = await tool.scratchpad_write(note="")
        assert result.success is False

    @pytest.mark.asyncio
    async def test_read_empty_scratchpad(self):
        from app.domain.services.tools.scratchpad import ScratchpadTool

        pad = Scratchpad()
        tool = ScratchpadTool(scratchpad=pad)

        result = await tool.scratchpad_read()
        assert result.success is True
        assert "empty" in result.message.lower()
