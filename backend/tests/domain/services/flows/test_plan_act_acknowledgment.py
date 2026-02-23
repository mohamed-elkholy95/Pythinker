from app.domain.services.flows.acknowledgment import AcknowledgmentGenerator


def _make_generator() -> AcknowledgmentGenerator:
    return AcknowledgmentGenerator()


def test_research_acknowledgment_is_specific_not_generic() -> None:
    gen = _make_generator()

    message = (
        "Conduct a comprehensive research report analyzing the best AI-powered code review and debugging tools. "
        "The report should include: 1. Define evaluation criteria. 2. Compare GitHub Copilot, DeepCode, and "
        "Amazon CodeGuru. 3. Evaluate performance, features, and adoption."
    )
    acknowledgment = gen.generate(message)

    assert acknowledgment.lower().startswith("got it! i will create a comprehensive research report on")
    assert "code review and debugging tools" in acknowledgment.lower()
    assert "1." not in acknowledgment
    assert len(acknowledgment) < 260


def test_create_acknowledgment_includes_focus() -> None:
    gen = _make_generator()

    message = "Create a dashboard for quarterly sales trends"
    acknowledgment = gen.generate(message)

    assert acknowledgment.lower().startswith("got it!")
    assert "dashboard for quarterly sales trends" in acknowledgment.lower()


def test_research_acknowledgment_for_short_prompt_mentions_topic() -> None:
    gen = _make_generator()

    message = "Research the latest Claude Code model updates"
    acknowledgment = gen.generate(message)

    assert acknowledgment.lower().startswith("got it! i will research")
    assert "claude code model updates" in acknowledgment.lower()


def test_research_acknowledgment_normalizes_messy_prompt_text() -> None:
    gen = _make_generator()

    message = "Create a comprehensive research report on: compare sonnet 4.5 and opus4.6 with loweffort settings"
    acknowledgment = gen.generate(message)

    assert "working" not in acknowledgment.lower()
    assert "i've received your request" not in acknowledgment.lower()
    assert "compoore" not in acknowledgment.lower()
    assert "sonet" not in acknowledgment.lower()
    assert acknowledgment.lower().startswith("got it! i will create a comprehensive research report on")


def test_research_acknowledgment_matches_expected_long_prompt_style() -> None:
    gen = _make_generator()

    message = (
        "Generate a comprehensive research report analyzing the most effective AI integrated development "
        "environments (IDEs), AI agents, and code review tools capable of identifying and addressing the most "
        "recent and prevalent bugs and issues in software development. Ensure reliance solely on the latest data "
        "and sources from 2026."
    )
    acknowledgment = gen.generate(message)

    assert acknowledgment.startswith("Got it! I will create a comprehensive research report on")
    assert "AI IDEs, agents, and code review tools" in acknowledgment
    assert "bug detection and resolution in 2026" in acknowledgment


def test_extract_request_focus_trims_boilerplate() -> None:
    gen = _make_generator()

    focus = gen._extract_request_focus("Please can you create an API health check endpoint")

    assert focus == "an API health check endpoint"


def test_research_acknowledgment_removes_numbered_list_suffix_from_topic() -> None:
    gen = _make_generator()

    message = (
        "Create a comprehensive research report that covers the following topics: "
        "1. Large Language Model (LLM) architecture. "
        "2. Tokenizers used in LLMs."
    )
    acknowledgment = gen.generate(message)

    assert acknowledgment.startswith("Got it! I will create a comprehensive research report on")
    assert "on report that covers" not in acknowledgment.lower()
    assert "following topics: 1" not in acknowledgment.lower()
    assert "the following topics" in acknowledgment.lower()
