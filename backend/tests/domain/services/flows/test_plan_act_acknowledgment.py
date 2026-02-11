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

    assert acknowledgment.split(" ", 1)[0] in {"Understood.", "Got", "Sounds", "All"}
    assert "research plan" in acknowledgment.lower()
    assert "1." not in acknowledgment
    assert len(acknowledgment) < 220


def test_create_acknowledgment_includes_focus() -> None:
    gen = _make_generator()

    message = "Create a dashboard for quarterly sales trends"
    acknowledgment = gen.generate(message)

    assert "dashboard for quarterly sales trends" in acknowledgment.lower()
    assert "create a plan" in acknowledgment.lower()


def test_research_acknowledgment_for_short_prompt_mentions_topic() -> None:
    gen = _make_generator()

    message = "Research the latest Claude Code model updates"
    acknowledgment = gen.generate(message)

    assert "research request" in acknowledgment.lower()
    assert "research plan" in acknowledgment.lower()


def test_research_acknowledgment_normalizes_messy_prompt_text() -> None:
    gen = _make_generator()

    message = "Create a comprehensive research report on: compare sonnet 4.5 and opus4.6 with loweffort settings"
    acknowledgment = gen.generate(message)

    assert "working" not in acknowledgment.lower()
    assert "i've received your request" not in acknowledgment.lower()
    assert "compoore" not in acknowledgment.lower()
    assert "sonet" not in acknowledgment.lower()
    assert "research plan" in acknowledgment.lower()


def test_research_acknowledgment_uses_search_prompt_label_when_present() -> None:
    gen = _make_generator()

    message = "Run research using this search text prompt for model comparison"
    acknowledgment = gen.generate(message)

    assert "search prompt" in acknowledgment.lower()
    assert "research plan" in acknowledgment.lower()


def test_extract_request_focus_trims_boilerplate() -> None:
    gen = _make_generator()

    focus = gen._extract_request_focus("Please can you create an API health check endpoint")

    assert focus == "an API health check endpoint"
