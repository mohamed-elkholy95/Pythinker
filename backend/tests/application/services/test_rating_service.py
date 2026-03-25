"""Tests for RatingService.submit_rating()."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.application.services.rating_service import RatingService, get_rating_service

PATCH_TARGET = "app.application.services.rating_service.RatingDocument"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_doc() -> MagicMock:
    """Return a MagicMock that behaves as a RatingDocument instance."""
    doc = MagicMock()
    doc.insert = AsyncMock()
    return doc


# ---------------------------------------------------------------------------
# submit_rating tests
# ---------------------------------------------------------------------------


class TestSubmitRating:
    @pytest.mark.asyncio
    async def test_creates_rating_document_with_correct_fields(self):
        mock_doc = _make_mock_doc()
        with patch(PATCH_TARGET, return_value=mock_doc) as mock_rating_cls:
            service = RatingService()
            await service.submit_rating(
                session_id="session-1",
                report_id="report-1",
                user_id="user-1",
                user_email="user@example.com",
                user_name="Alice",
                rating=5,
                feedback="Great report",
            )
            mock_rating_cls.assert_called_once_with(
                session_id="session-1",
                report_id="report-1",
                user_id="user-1",
                user_email="user@example.com",
                user_name="Alice",
                rating=5,
                feedback="Great report",
            )

    @pytest.mark.asyncio
    async def test_calls_insert_on_document(self):
        mock_doc = _make_mock_doc()
        with patch(PATCH_TARGET, return_value=mock_doc):
            service = RatingService()
            await service.submit_rating(
                session_id="session-1",
                report_id="report-1",
                user_id="user-1",
                user_email="user@example.com",
                user_name="Alice",
                rating=4,
            )
            mock_doc.insert.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_none(self):
        mock_doc = _make_mock_doc()
        with patch(PATCH_TARGET, return_value=mock_doc):
            service = RatingService()
            result = await service.submit_rating(
                session_id="s",
                report_id="r",
                user_id="u",
                user_email="e@e.com",
                user_name="Bob",
                rating=3,
            )
            assert result is None

    @pytest.mark.asyncio
    async def test_feedback_defaults_to_none_when_omitted(self):
        mock_doc = _make_mock_doc()
        with patch(PATCH_TARGET, return_value=mock_doc) as mock_rating_cls:
            service = RatingService()
            await service.submit_rating(
                session_id="s",
                report_id="r",
                user_id="u",
                user_email="e@e.com",
                user_name="Carol",
                rating=2,
            )
            _, kwargs = mock_rating_cls.call_args
            assert kwargs.get("feedback") is None

    @pytest.mark.asyncio
    async def test_feedback_passed_when_provided(self):
        mock_doc = _make_mock_doc()
        with patch(PATCH_TARGET, return_value=mock_doc) as mock_rating_cls:
            service = RatingService()
            await service.submit_rating(
                session_id="s",
                report_id="r",
                user_id="u",
                user_email="e@e.com",
                user_name="Dave",
                rating=1,
                feedback="Needs improvement",
            )
            _, kwargs = mock_rating_cls.call_args
            assert kwargs["feedback"] == "Needs improvement"

    @pytest.mark.asyncio
    async def test_insert_exception_propagates(self):
        mock_doc = _make_mock_doc()
        mock_doc.insert.side_effect = RuntimeError("DB unavailable")
        with patch(PATCH_TARGET, return_value=mock_doc):
            service = RatingService()
            with pytest.raises(RuntimeError, match="DB unavailable"):
                await service.submit_rating(
                    session_id="s",
                    report_id="r",
                    user_id="u",
                    user_email="e@e.com",
                    user_name="Eve",
                    rating=5,
                )

    @pytest.mark.asyncio
    async def test_rating_value_forwarded_exactly(self):
        mock_doc = _make_mock_doc()
        with patch(PATCH_TARGET, return_value=mock_doc) as mock_rating_cls:
            service = RatingService()
            await service.submit_rating(
                session_id="s",
                report_id="r",
                user_id="u",
                user_email="e@e.com",
                user_name="Frank",
                rating=1,
            )
            _, kwargs = mock_rating_cls.call_args
            assert kwargs["rating"] == 1

    @pytest.mark.asyncio
    async def test_multiple_submissions_each_create_separate_document(self):
        docs = [_make_mock_doc(), _make_mock_doc()]
        call_count = 0

        def factory(**kwargs):
            nonlocal call_count
            doc = docs[call_count]
            call_count += 1
            return doc

        with patch(PATCH_TARGET, side_effect=factory):
            service = RatingService()
            await service.submit_rating("s1", "r1", "u1", "a@a.com", "Alice", 5)
            await service.submit_rating("s2", "r2", "u2", "b@b.com", "Bob", 3)

        docs[0].insert.assert_awaited_once()
        docs[1].insert.assert_awaited_once()


# ---------------------------------------------------------------------------
# get_rating_service factory
# ---------------------------------------------------------------------------


class TestGetRatingService:
    def test_returns_rating_service_instance(self):
        # Call without cache interference by using a fresh import path test
        service = get_rating_service()
        assert isinstance(service, RatingService)

    def test_returns_same_instance_on_repeated_calls(self):
        a = get_rating_service()
        b = get_rating_service()
        assert a is b
