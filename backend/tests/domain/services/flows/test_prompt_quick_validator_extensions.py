from app.domain.services.flows.prompt_quick_validator import EnhancedPromptQuickValidator
from app.infrastructure.observability.typo_correction_analytics import TypoCorrectionAnalytics


class FakeRapidFuzzMatcher:
    def extract_one(self, query: str, choices, *, score_cutoff: float):
        if query == "cmopare" and score_cutoff <= 96.0:
            return "compare", 96.0
        return None


class FakeSymSpellProvider:
    def correct_word(self, word: str):
        if word == "sanboxx":
            return "sandbox", 0.95
        return None


def test_feedback_override_is_applied_before_dictionary(tmp_path) -> None:
    analytics = TypoCorrectionAnalytics(storage_path=tmp_path / "feedback.json", min_feedback_occurrences=2)
    analytics.record_feedback(original="copding", corrected="coding", user_override="copying")
    analytics.record_feedback(original="copding", corrected="coding", user_override="copying")

    validator = EnhancedPromptQuickValidator(feedback_lookup=analytics.get_feedback_override)
    cleaned = validator.validate("copding")

    assert cleaned == "copying"


def test_correction_event_sink_receives_events() -> None:
    events = []

    validator = EnhancedPromptQuickValidator(correction_event_sink=events.append)
    validator.validate("copding")

    assert events
    assert events[0].original.lower() == "copding"
    assert events[0].corrected.lower() == "coding"


def test_rapidfuzz_matcher_path_is_used() -> None:
    validator = EnhancedPromptQuickValidator(
        rapidfuzz_matcher=FakeRapidFuzzMatcher(),
        confidence_threshold=0.90,
        rapidfuzz_score_cutoff=90.0,
    )

    cleaned = validator.validate("cmopare")
    assert cleaned == "compare"


def test_symspell_provider_path_is_used() -> None:
    validator = EnhancedPromptQuickValidator(
        symspell_provider=FakeSymSpellProvider(),
        confidence_threshold=0.90,
    )

    cleaned = validator.validate("sanboxx")
    assert cleaned == "sandbox"


def test_feedback_store_persists_overrides(tmp_path) -> None:
    store_path = tmp_path / "feedback.json"
    analytics = TypoCorrectionAnalytics(storage_path=store_path, min_feedback_occurrences=1)
    analytics.record_feedback(original="copding", corrected="coding", user_override="copying")

    reloaded = TypoCorrectionAnalytics(storage_path=store_path, min_feedback_occurrences=1)
    assert reloaded.get_feedback_override("copding") == "copying"
