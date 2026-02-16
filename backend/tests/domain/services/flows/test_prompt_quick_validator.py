from app.domain.services.flows.prompt_quick_validator import PromptQuickValidator


def test_quick_validator_fixes_common_typos_and_model_spacing() -> None:
    validator = PromptQuickValidator()

    raw = "Create a comprehensive research report on: compoore sonet 4.5 and opus4.6 with loweffort settings"
    cleaned = validator.validate(raw)

    assert "compoore" not in cleaned.lower()
    assert "sonet" not in cleaned.lower()
    assert "opus4.6" not in cleaned.lower()
    assert "Sonnet 4.5" in cleaned
    assert "Opus 4.6" in cleaned
    assert "low-effort settings" in cleaned.lower()


def test_quick_validator_handles_spacing_noise() -> None:
    validator = PromptQuickValidator()

    raw = "  compare   sonnet4.5   vs   opus4.6   "
    cleaned = validator.validate(raw)

    assert cleaned == "compare Sonnet 4.5 vs Opus 4.6"


def test_quick_validator_fixes_additional_common_misspellings() -> None:
    validator = PromptQuickValidator()

    raw = "use code.html as a refrence and resesearch onlime with standerdized styles for pythiner"
    cleaned = validator.validate(raw)

    assert "reference" in cleaned.lower()
    assert "research online" in cleaned.lower()
    assert "standardized" in cleaned.lower()
    assert "pythinker" in cleaned.lower()


def test_quick_validator_does_not_overcorrect_technical_terms() -> None:
    validator = PromptQuickValidator()

    raw = "research qdrant kubectl pytest fastapi and prometheus integration patterns"
    cleaned = validator.validate(raw)

    assert "qdrant" in cleaned.lower()
    assert "kubectl" in cleaned.lower()
    assert "pytest" in cleaned.lower()
    assert "fastapi" in cleaned.lower()
    assert "prometheus" in cleaned.lower()


def test_quick_validator_fixes_glm_and_coding_typo_for_research_prompts() -> None:
    validator = PromptQuickValidator()

    raw = "Create a comprehensive research report on: glm-5 copding agent"
    cleaned = validator.validate(raw)

    assert "copding" not in cleaned.lower()
    assert "coding agent" in cleaned.lower()
    assert "GLM-5" in cleaned
