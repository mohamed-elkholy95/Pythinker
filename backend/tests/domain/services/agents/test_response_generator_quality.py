from unittest.mock import MagicMock

from app.domain.services.agents.response_generator import ResponseGenerator


def _make_generator() -> ResponseGenerator:
    return ResponseGenerator(
        llm=MagicMock(),
        memory=MagicMock(),
        source_tracker=MagicMock(),
    )


def test_is_meta_commentary_detects_long_content_suffix() -> None:
    generator = _make_generator()
    content = "# Report\n" + ("Detailed finding line.\n" * 120) + "\nI will write the final report content to the file."
    assert len(content) > 800
    assert generator.is_meta_commentary(content) is True
