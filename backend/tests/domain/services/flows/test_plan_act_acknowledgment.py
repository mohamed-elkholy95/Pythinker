from app.domain.services.flows.plan_act import PlanActFlow


def _make_flow() -> PlanActFlow:
    # Avoid heavy constructor dependencies; these tests only exercise pure string helpers.
    return PlanActFlow.__new__(PlanActFlow)


def test_research_acknowledgment_is_specific_not_generic() -> None:
    flow = _make_flow()

    message = (
        "Conduct a comprehensive research report analyzing the best AI-powered code review and debugging tools. "
        "The report should include: 1. Define evaluation criteria. 2. Compare GitHub Copilot, DeepCode, and "
        "Amazon CodeGuru. 3. Evaluate performance, features, and adoption."
    )
    acknowledgment = flow._generate_acknowledgment(message)

    assert acknowledgment.startswith("I've received your request")
    assert "latest tools and data" in acknowledgment
    assert "1." not in acknowledgment
    assert len(acknowledgment) < 220


def test_create_acknowledgment_includes_focus() -> None:
    flow = _make_flow()

    message = "Create a dashboard for quarterly sales trends"
    acknowledgment = flow._generate_acknowledgment(message)

    assert "dashboard for quarterly sales trends" in acknowledgment.lower()
    assert "create a plan" in acknowledgment.lower()


def test_research_acknowledgment_for_short_prompt_mentions_topic() -> None:
    flow = _make_flow()

    message = "Research the latest Claude Code model updates"
    acknowledgment = flow._generate_acknowledgment(message)

    assert acknowledgment.startswith("I've received your request")
    assert "claude code model updates" in acknowledgment.lower()


def test_extract_request_focus_trims_boilerplate() -> None:
    flow = _make_flow()

    focus = flow._extract_request_focus("Please can you create an API health check endpoint")

    assert focus == "an API health check endpoint"
