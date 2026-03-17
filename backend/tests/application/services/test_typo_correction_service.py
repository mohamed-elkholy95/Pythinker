from app.application.services.typo_correction_service import TypoCorrectionService
from app.infrastructure.observability.typo_correction_analytics import TypoCorrectionAnalytics


class StubAnalytics:
    def __init__(self) -> None:
        self.summary = {"total_corrections": 0, "methods": {}}
        self.feedback_calls = []

    def get_summary(self):
        return self.summary

    def record_feedback(self, *, original: str, corrected: str, user_override: str) -> None:
        self.feedback_calls.append((original, corrected, user_override))


def test_typo_correction_service_summary(monkeypatch) -> None:
    stub = StubAnalytics()
    monkeypatch.setattr(
        "app.application.services.typo_correction_service.get_typo_correction_analytics",
        lambda: stub,
    )

    service = TypoCorrectionService()
    assert service.get_summary() == stub.summary


def test_typo_correction_service_feedback(monkeypatch) -> None:
    stub = StubAnalytics()
    monkeypatch.setattr(
        "app.application.services.typo_correction_service.get_typo_correction_analytics",
        lambda: stub,
    )

    service = TypoCorrectionService()
    service.submit_feedback(original="copding", corrected="coding", user_override="copying")

    assert stub.feedback_calls == [("copding", "coding", "copying")]


def test_typo_correction_analytics_summary_shape(tmp_path) -> None:
    analytics = TypoCorrectionAnalytics(storage_path=tmp_path / "feedback.json", min_feedback_occurrences=1)
    analytics.record_feedback(original="copding", corrected="coding", user_override="copying")
    summary = analytics.get_summary()

    assert "total_corrections" in summary
    assert "top_feedback_overrides" in summary
