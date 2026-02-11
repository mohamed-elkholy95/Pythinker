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
