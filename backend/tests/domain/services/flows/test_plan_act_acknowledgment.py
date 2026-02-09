from app.domain.services.flows.plan_act import PlanActFlow


def _make_flow() -> PlanActFlow:
    # Avoid heavy constructor dependencies; these tests only exercise pure string helpers.
    return PlanActFlow.__new__(PlanActFlow)


def test_research_acknowledgment_is_specific_not_generic() -> None:
    flow = _make_flow()

    message = "create html blog post about claude code latest relaesed model"
    acknowledgment = flow._generate_acknowledgment(message)

    assert "quickly analyze" in acknowledgment.lower()
    assert "claude code latest relaesed model" in acknowledgment.lower()
    assert acknowledgment != "I'll conduct comprehensive research on this topic and provide you with a detailed report."


def test_create_acknowledgment_includes_focus() -> None:
    flow = _make_flow()

    message = "Create a dashboard for quarterly sales trends"
    acknowledgment = flow._generate_acknowledgment(message)

    assert "dashboard for quarterly sales trends" in acknowledgment.lower()
    assert "create a plan" in acknowledgment.lower()


def test_extract_request_focus_trims_boilerplate() -> None:
    flow = _make_flow()

    focus = flow._extract_request_focus("Please can you create an API health check endpoint")

    assert focus == "an API health check endpoint"
