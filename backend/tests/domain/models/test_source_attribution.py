"""Tests for source attribution models.

Covers SourceType, AccessStatus enums, SourceAttribution methods,
ContentAccessResult, and AttributionSummary aggregation logic.
"""

import pytest
from pydantic import ValidationError

from app.domain.models.source_attribution import (
    AccessStatus,
    AttributionSummary,
    ContentAccessResult,
    SourceAttribution,
    SourceType,
)


class TestSourceType:
    def test_direct_content(self):
        assert SourceType.DIRECT_CONTENT == "direct"

    def test_inferred(self):
        assert SourceType.INFERRED == "inferred"

    def test_unavailable(self):
        assert SourceType.UNAVAILABLE == "unavailable"

    def test_member_count(self):
        assert len(SourceType) == 3


class TestAccessStatus:
    def test_full(self):
        assert AccessStatus.FULL == "full"

    def test_partial(self):
        assert AccessStatus.PARTIAL == "partial"

    def test_paywall(self):
        assert AccessStatus.PAYWALL == "paywall"

    def test_login_required(self):
        assert AccessStatus.LOGIN_REQUIRED == "login_required"

    def test_error(self):
        assert AccessStatus.ERROR == "error"

    def test_member_count(self):
        assert len(AccessStatus) == 5


class TestSourceAttribution:
    def _make_attr(self, **kwargs):
        defaults = {
            "claim": "test claim",
            "source_type": SourceType.DIRECT_CONTENT,
        }
        defaults.update(kwargs)
        return SourceAttribution(**defaults)

    def test_defaults(self):
        a = self._make_attr()
        assert a.source_url is None
        assert a.access_status == AccessStatus.FULL
        assert a.confidence == 1.0
        assert a.raw_excerpt is None

    def test_is_verified_true(self):
        a = self._make_attr(
            source_type=SourceType.DIRECT_CONTENT,
            access_status=AccessStatus.FULL,
            confidence=0.9,
        )
        assert a.is_verified() is True

    def test_is_verified_false_inferred(self):
        a = self._make_attr(source_type=SourceType.INFERRED)
        assert a.is_verified() is False

    def test_is_verified_false_low_confidence(self):
        a = self._make_attr(confidence=0.5)
        assert a.is_verified() is False

    def test_is_verified_false_partial_access(self):
        a = self._make_attr(access_status=AccessStatus.PARTIAL)
        assert a.is_verified() is False

    def test_requires_caveat_inferred(self):
        a = self._make_attr(source_type=SourceType.INFERRED)
        assert a.requires_caveat() is True

    def test_requires_caveat_partial(self):
        a = self._make_attr(access_status=AccessStatus.PARTIAL)
        assert a.requires_caveat() is True

    def test_requires_caveat_paywall(self):
        a = self._make_attr(access_status=AccessStatus.PAYWALL)
        assert a.requires_caveat() is True

    def test_requires_caveat_low_confidence(self):
        a = self._make_attr(confidence=0.5)
        assert a.requires_caveat() is True

    def test_requires_caveat_false(self):
        a = self._make_attr(
            source_type=SourceType.DIRECT_CONTENT,
            access_status=AccessStatus.FULL,
            confidence=0.9,
        )
        assert a.requires_caveat() is False

    def test_get_attribution_prefix_inferred(self):
        a = self._make_attr(source_type=SourceType.INFERRED)
        assert a.get_attribution_prefix() == "[Inferred] "

    def test_get_attribution_prefix_partial(self):
        a = self._make_attr(
            source_type=SourceType.DIRECT_CONTENT,
            access_status=AccessStatus.PARTIAL,
        )
        assert a.get_attribution_prefix() == "[Partial access] "

    def test_get_attribution_prefix_paywall(self):
        a = self._make_attr(
            source_type=SourceType.DIRECT_CONTENT,
            access_status=AccessStatus.PAYWALL,
        )
        assert a.get_attribution_prefix() == "[Behind paywall] "

    def test_get_attribution_prefix_unavailable(self):
        a = self._make_attr(source_type=SourceType.UNAVAILABLE)
        assert a.get_attribution_prefix() == "[Not accessible] "

    def test_get_attribution_prefix_with_url(self):
        a = self._make_attr(source_url="https://example.com")
        assert "According to https://example.com" in a.get_attribution_prefix()

    def test_get_attribution_prefix_empty(self):
        a = self._make_attr()
        assert a.get_attribution_prefix() == ""

    def test_confidence_bounds(self):
        with pytest.raises(ValidationError):
            self._make_attr(confidence=1.5)


class TestContentAccessResult:
    def test_construction(self):
        r = ContentAccessResult(
            url="https://example.com",
            content="Hello world",
            access_status=AccessStatus.FULL,
        )
        assert r.url == "https://example.com"
        assert r.truncated is False
        assert r.paywall_confidence == 0.0

    def test_get_access_message_full(self):
        r = ContentAccessResult(url="u", content="c", access_status=AccessStatus.FULL)
        assert "Full content" in r.get_access_message()

    def test_get_access_message_partial(self):
        r = ContentAccessResult(url="u", content="c", access_status=AccessStatus.PARTIAL)
        assert "partial" in r.get_access_message().lower()

    def test_get_access_message_paywall(self):
        r = ContentAccessResult(
            url="u",
            content="c",
            access_status=AccessStatus.PAYWALL,
            paywall_indicators=["subscribe now"],
        )
        msg = r.get_access_message()
        assert "paywall" in msg.lower()
        assert "subscribe now" in msg

    def test_get_access_message_login(self):
        r = ContentAccessResult(url="u", content="c", access_status=AccessStatus.LOGIN_REQUIRED)
        assert "Login" in r.get_access_message()

    def test_get_access_message_error(self):
        r = ContentAccessResult(url="u", content="c", access_status=AccessStatus.ERROR)
        assert "Error" in r.get_access_message()


class TestAttributionSummary:
    def test_defaults(self):
        s = AttributionSummary()
        assert s.total_claims == 0
        assert s.verified_claims == 0
        assert s.average_confidence == 1.0

    def test_add_verified_attribution(self):
        s = AttributionSummary()
        a = SourceAttribution(claim="fact", source_type=SourceType.DIRECT_CONTENT, confidence=0.9)
        s.add_attribution(a)
        assert s.total_claims == 1
        assert s.verified_claims == 1
        assert s.average_confidence == 0.9

    def test_add_inferred_attribution(self):
        s = AttributionSummary()
        a = SourceAttribution(claim="guess", source_type=SourceType.INFERRED, confidence=0.6)
        s.add_attribution(a)
        assert s.inferred_claims == 1

    def test_add_unavailable_attribution(self):
        s = AttributionSummary()
        a = SourceAttribution(claim="?", source_type=SourceType.UNAVAILABLE, confidence=0.3)
        s.add_attribution(a)
        assert s.unavailable_claims == 1

    def test_paywall_flag(self):
        s = AttributionSummary()
        a = SourceAttribution(
            claim="x",
            source_type=SourceType.DIRECT_CONTENT,
            access_status=AccessStatus.PAYWALL,
        )
        s.add_attribution(a)
        assert s.has_paywall_sources is True

    def test_average_confidence_multiple(self):
        s = AttributionSummary()
        s.add_attribution(SourceAttribution(claim="a", source_type=SourceType.DIRECT_CONTENT, confidence=0.8))
        s.add_attribution(SourceAttribution(claim="b", source_type=SourceType.DIRECT_CONTENT, confidence=0.6))
        assert s.average_confidence == pytest.approx(0.7)

    def test_get_reliability_score_empty(self):
        s = AttributionSummary()
        assert s.get_reliability_score() == 1.0

    def test_get_reliability_score_all_verified(self):
        s = AttributionSummary()
        s.add_attribution(SourceAttribution(claim="a", source_type=SourceType.DIRECT_CONTENT, confidence=1.0))
        assert s.get_reliability_score() == 1.0

    def test_get_reliability_score_mixed(self):
        s = AttributionSummary()
        s.add_attribution(SourceAttribution(claim="a", source_type=SourceType.DIRECT_CONTENT, confidence=1.0))
        s.add_attribution(SourceAttribution(claim="b", source_type=SourceType.INFERRED, confidence=1.0))
        score = s.get_reliability_score()
        assert 0.0 < score < 1.0

    def test_needs_caveats_inferred_majority(self):
        s = AttributionSummary()
        s.add_attribution(SourceAttribution(claim="a", source_type=SourceType.INFERRED, confidence=0.8))
        s.add_attribution(SourceAttribution(claim="b", source_type=SourceType.INFERRED, confidence=0.8))
        assert s.needs_caveats() is True

    def test_needs_caveats_paywall(self):
        s = AttributionSummary()
        s.add_attribution(
            SourceAttribution(
                claim="a",
                source_type=SourceType.DIRECT_CONTENT,
                access_status=AccessStatus.PAYWALL,
            )
        )
        assert s.needs_caveats() is True

    def test_needs_caveats_low_confidence(self):
        s = AttributionSummary()
        s.add_attribution(SourceAttribution(claim="a", source_type=SourceType.DIRECT_CONTENT, confidence=0.5))
        assert s.needs_caveats() is True

    def test_needs_caveats_unavailable(self):
        s = AttributionSummary()
        s.add_attribution(SourceAttribution(claim="a", source_type=SourceType.UNAVAILABLE, confidence=0.3))
        assert s.needs_caveats() is True

    def test_no_caveats_all_verified_high_confidence(self):
        s = AttributionSummary()
        s.add_attribution(SourceAttribution(claim="a", source_type=SourceType.DIRECT_CONTENT, confidence=0.9))
        assert s.needs_caveats() is False
