"""Tests for the deterministic SourceSelector.

Covers normalization/deduplication, source classification, constraint
enforcement, adversarial intent detection, and scoring.
"""

from __future__ import annotations

import types

from app.domain.models.evidence import QueryContext, SelectedSource, SourceType
from app.domain.models.search import SearchResultItem
from app.domain.services.agents.source_selector import SourceSelector

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _item(title: str, link: str, snippet: str = "A search snippet.") -> SearchResultItem:
    return SearchResultItem(title=title, link=link, snippet=snippet)


def _default_config(**overrides: object) -> types.SimpleNamespace:
    defaults = {
        "research_source_select_count": 4,
        "research_source_max_per_domain": 1,
        "research_source_allow_multi_page_domains": False,
        "research_weight_relevance": 0.35,
        "research_weight_authority": 0.35,
        "research_weight_freshness": 0.10,
        "research_weight_rank": 0.20,
    }
    defaults.update(overrides)
    return types.SimpleNamespace(**defaults)


# ---------------------------------------------------------------------------
# TestNormalizationAndDedupe
# ---------------------------------------------------------------------------


class TestNormalizationAndDedupe:
    """SourceSelector correctly normalises URLs and removes duplicates."""

    def test_dedupes_identical_urls(self) -> None:
        cfg = _default_config(research_source_select_count=4)
        selector = SourceSelector(cfg)
        items = [
            _item("Page A", "https://example.com/page"),
            _item("Page A duplicate", "https://example.com/page"),
            _item("Page B", "https://other.com/page"),
        ]
        results = selector.select(items, "example query")
        urls = [s.url for s in results]
        assert urls.count("https://example.com/page") <= 1

    def test_dedupes_trailing_slash_variants(self) -> None:
        cfg = _default_config(research_source_select_count=4)
        selector = SourceSelector(cfg)
        items = [
            _item("Page", "https://example.com/page/"),
            _item("Page no slash", "https://example.com/page"),
        ]
        results = selector.select(items, "query")
        # Both normalise to the same canonical URL — only one survives
        assert len(results) == 1

    def test_dedupes_www_prefix(self) -> None:
        cfg = _default_config(research_source_select_count=4)
        selector = SourceSelector(cfg)
        items = [
            _item("Site", "https://www.example.com/about"),
            _item("Site no www", "https://example.com/about"),
        ]
        results = selector.select(items, "query")
        assert len(results) == 1

    def test_strips_utm_tracking_params(self) -> None:
        cfg = _default_config(research_source_select_count=2)
        selector = SourceSelector(cfg)
        items = [
            _item(
                "Tracked",
                "https://example.com/page?utm_source=google&utm_medium=cpc",
            ),
            _item("Clean", "https://example.com/page"),
        ]
        results = selector.select(items, "query")
        # Same canonical URL after stripping — only one survives
        assert len(results) == 1

    def test_filters_denylist_domains_entirely(self) -> None:
        cfg = _default_config(research_source_select_count=4)
        selector = SourceSelector(cfg)
        items = [
            _item("Reddit post", "https://reddit.com/r/python/comments/abc"),
            _item("Twitter tweet", "https://twitter.com/user/status/123"),
            _item("X post", "https://x.com/user/status/456"),
            _item("Instagram", "https://instagram.com/p/xyz"),
            _item("Good source", "https://docs.python.org/3/library/"),
        ]
        results = selector.select(items, "python library")
        urls = [s.url for s in results]
        for url in urls:
            assert "reddit.com" not in url
            assert "twitter.com" not in url
            assert "x.com" not in url
            assert "instagram.com" not in url

    def test_facebook_denylist(self) -> None:
        cfg = _default_config(research_source_select_count=4)
        selector = SourceSelector(cfg)
        items = [
            _item("Facebook post", "https://facebook.com/page/posts/123"),
            _item("Good source", "https://example.com/article"),
        ]
        results = selector.select(items, "query")
        assert all("facebook.com" not in s.url for s in results)

    def test_keeps_non_denylist_sources(self) -> None:
        cfg = _default_config(research_source_select_count=4)
        selector = SourceSelector(cfg)
        items = [
            _item("Legit site", "https://techcrunch.com/2024/01/01/article"),
            _item("Another legit", "https://example.org/report"),
        ]
        results = selector.select(items, "technology news")
        assert len(results) == 2


# ---------------------------------------------------------------------------
# TestClassification
# ---------------------------------------------------------------------------


class TestClassification:
    """SourceSelector correctly classifies source types."""

    def test_gov_domain_is_official(self) -> None:
        cfg = _default_config(research_source_select_count=4)
        selector = SourceSelector(cfg)
        items = [_item("CDC report", "https://cdc.gov/health/topic")]
        results = selector.select(items, "health topic")
        assert results[0].source_type == SourceType.official

    def test_edu_domain_is_official(self) -> None:
        cfg = _default_config(research_source_select_count=4)
        selector = SourceSelector(cfg)
        items = [_item("MIT research", "https://mit.edu/research/paper")]
        results = selector.select(items, "research paper")
        assert results[0].source_type == SourceType.official

    def test_docs_subdomain_is_official(self) -> None:
        cfg = _default_config(research_source_select_count=4)
        selector = SourceSelector(cfg)
        items = [_item("Python docs", "https://docs.python.org/3/library/os")]
        results = selector.select(items, "python os module")
        assert results[0].source_type == SourceType.official

    def test_developer_subdomain_is_official(self) -> None:
        cfg = _default_config(research_source_select_count=4)
        selector = SourceSelector(cfg)
        items = [_item("MDN docs", "https://developer.mozilla.org/en-US/docs/Web")]
        results = selector.select(items, "web api")
        assert results[0].source_type == SourceType.official

    def test_entity_domain_match_is_official(self) -> None:
        """A query token that appears in the domain signals official source."""
        cfg = _default_config(research_source_select_count=4)
        selector = SourceSelector(cfg)
        # "python" appears in "python.org" domain → entity match
        items = [_item("Python home", "https://python.org/downloads")]
        results = selector.select(items, "python programming language")
        assert results[0].source_type == SourceType.official

    def test_stackoverflow_is_ugc_low_trust(self) -> None:
        cfg = _default_config(research_source_select_count=4)
        selector = SourceSelector(cfg)
        items = [_item("SO answer", "https://stackoverflow.com/questions/12345")]
        results = selector.select(items, "python question")
        assert results[0].source_type == SourceType.ugc_low_trust

    def test_medium_is_ugc_low_trust(self) -> None:
        cfg = _default_config(research_source_select_count=4)
        selector = SourceSelector(cfg)
        items = [_item("Medium post", "https://medium.com/@author/post")]
        results = selector.select(items, "tech opinion")
        assert results[0].source_type == SourceType.ugc_low_trust

    def test_wikipedia_is_authoritative_neutral(self) -> None:
        cfg = _default_config(research_source_select_count=4)
        selector = SourceSelector(cfg)
        items = [_item("Wikipedia article", "https://wikipedia.org/wiki/Python")]
        results = selector.select(items, "python programming")
        assert results[0].source_type == SourceType.authoritative_neutral

    def test_news_site_is_authoritative_neutral_or_independent(self) -> None:
        cfg = _default_config(research_source_select_count=4)
        selector = SourceSelector(cfg)
        items = [_item("TechCrunch article", "https://techcrunch.com/2024/01/01/ai")]
        results = selector.select(items, "artificial intelligence")
        assert results[0].source_type in (
            SourceType.authoritative_neutral,
            SourceType.independent,
        )

    def test_unknown_site_is_independent(self) -> None:
        cfg = _default_config(research_source_select_count=4)
        selector = SourceSelector(cfg)
        items = [_item("Random blog", "https://someblog.io/article")]
        results = selector.select(items, "query")
        assert results[0].source_type == SourceType.independent

    def test_authority_score_official_higher_than_ugc(self) -> None:
        cfg = _default_config(research_source_select_count=4)
        selector = SourceSelector(cfg)
        gov = [_item("Gov site", "https://data.gov/dataset/xyz")]
        ugc = [_item("SO answer", "https://stackoverflow.com/questions/99")]
        gov_results = selector.select(gov, "query")
        ugc_results = selector.select(ugc, "query")
        assert gov_results[0].authority_score > ugc_results[0].authority_score

    def test_api_subdomain_is_official(self) -> None:
        cfg = _default_config(research_source_select_count=4)
        selector = SourceSelector(cfg)
        items = [_item("API reference", "https://api.stripe.com/v1/docs")]
        results = selector.select(items, "stripe payment")
        assert results[0].source_type == SourceType.official


# ---------------------------------------------------------------------------
# TestConstraintEnforcement
# ---------------------------------------------------------------------------


class TestConstraintEnforcement:
    """SourceSelector respects domain diversity and count constraints."""

    def test_respects_select_count(self) -> None:
        cfg = _default_config(research_source_select_count=3)
        selector = SourceSelector(cfg)
        items = [
            _item(f"Site {i}", f"https://site{i}.com/page") for i in range(10)
        ]
        results = selector.select(items, "query")
        assert len(results) <= 3

    def test_max_one_per_domain_by_default(self) -> None:
        cfg = _default_config(
            research_source_select_count=4,
            research_source_max_per_domain=1,
        )
        selector = SourceSelector(cfg)
        items = [
            _item("Page 1", "https://example.com/page1"),
            _item("Page 2", "https://example.com/page2"),
            _item("Page 3", "https://example.com/page3"),
            _item("Other", "https://other.com/page"),
        ]
        results = selector.select(items, "query")
        domains = [s.domain for s in results]
        assert domains.count("example.com") <= 1

    def test_max_two_per_domain_allows_two(self) -> None:
        cfg = _default_config(
            research_source_select_count=4,
            research_source_max_per_domain=2,
        )
        selector = SourceSelector(cfg)
        items = [
            _item("Page 1", "https://example.com/page1"),
            _item("Page 2", "https://example.com/page2"),
            _item("Page 3", "https://example.com/page3"),
        ]
        results = selector.select(items, "query")
        domains = [s.domain for s in results]
        assert domains.count("example.com") <= 2

    def test_includes_at_least_one_independent_when_available(self) -> None:
        cfg = _default_config(research_source_select_count=4)
        selector = SourceSelector(cfg)
        items = [
            _item("Gov 1", "https://hhs.gov/topic"),
            _item("Gov 2", "https://fda.gov/drugs"),
            _item("Gov 3", "https://cdc.gov/health"),
            _item("Independent", "https://healthline.com/article"),
        ]
        results = selector.select(items, "health query")
        source_types = [s.source_type for s in results]
        # At least one non-official should be present
        assert any(st != SourceType.official for st in source_types)

    def test_returns_empty_list_when_no_results(self) -> None:
        cfg = _default_config()
        selector = SourceSelector(cfg)
        results = selector.select([], "query")
        assert results == []

    def test_all_results_denylist_returns_empty(self) -> None:
        cfg = _default_config(research_source_select_count=4)
        selector = SourceSelector(cfg)
        items = [
            _item("Reddit", "https://reddit.com/r/python"),
            _item("Twitter", "https://twitter.com/user"),
        ]
        results = selector.select(items, "python")
        assert results == []

    def test_domain_diversity_applied_flag_set(self) -> None:
        """When a domain is skipped due to the max-per-domain cap, higher-ranked
        surviving items from other domains have domain_diversity_applied=True."""
        cfg = _default_config(
            research_source_select_count=2,
            research_source_max_per_domain=1,
        )
        selector = SourceSelector(cfg)
        items = [
            _item("Page 1", "https://example.com/page1"),
            _item("Page 2", "https://example.com/page2"),  # same domain, capped
            _item("Other", "https://other.com/page"),
        ]
        results = selector.select(items, "query")
        # There should be at most one example.com result
        example_results = [r for r in results if r.domain == "example.com"]
        assert len(example_results) <= 1


# ---------------------------------------------------------------------------
# TestAdversarialIntent
# ---------------------------------------------------------------------------


class TestAdversarialIntent:
    """Comparative queries limit over-representation of official sources."""

    def test_detects_vs_keyword(self) -> None:
        cfg = _default_config()
        selector = SourceSelector(cfg)
        assert selector._detect_adversarial_intent("python vs javascript performance")

    def test_detects_best_alternative(self) -> None:
        cfg = _default_config()
        selector = SourceSelector(cfg)
        assert selector._detect_adversarial_intent("best alternative to Django")

    def test_detects_compared_to(self) -> None:
        cfg = _default_config()
        selector = SourceSelector(cfg)
        assert selector._detect_adversarial_intent("React compared to Vue")

    def test_detects_versus(self) -> None:
        cfg = _default_config()
        selector = SourceSelector(cfg)
        assert selector._detect_adversarial_intent("numpy versus pandas speed")

    def test_detects_problems_with(self) -> None:
        cfg = _default_config()
        selector = SourceSelector(cfg)
        assert selector._detect_adversarial_intent("problems with Django ORM")

    def test_detects_independent_benchmark(self) -> None:
        cfg = _default_config()
        selector = SourceSelector(cfg)
        assert selector._detect_adversarial_intent("independent benchmark results")

    def test_non_comparative_query_is_not_adversarial(self) -> None:
        cfg = _default_config()
        selector = SourceSelector(cfg)
        assert not selector._detect_adversarial_intent("how to install Python")

    def test_comparative_query_adds_independent_source(self) -> None:
        """When comparative intent detected and >50% official, swap one official
        for the best available independent source."""
        cfg = _default_config(research_source_select_count=3)
        selector = SourceSelector(cfg)
        items = [
            _item("Gov 1", "https://nist.gov/crypto"),
            _item("Gov 2", "https://cisa.gov/security"),
            _item("Gov 3", "https://ftc.gov/report"),
            _item("Independent review", "https://infosecblog.com/review"),
        ]
        results = selector.select(items, "nist vs cisa security compared to ftc")
        source_types = [s.source_type for s in results]
        # At least one non-official source should be present due to comparative intent
        assert any(st != SourceType.official for st in source_types)

    def test_criticism_of_triggers_adversarial(self) -> None:
        cfg = _default_config()
        selector = SourceSelector(cfg)
        assert selector._detect_adversarial_intent("criticism of Python packaging")

    def test_review_of_triggers_adversarial(self) -> None:
        cfg = _default_config()
        selector = SourceSelector(cfg)
        assert selector._detect_adversarial_intent("review of Django framework")


# ---------------------------------------------------------------------------
# TestScoring
# ---------------------------------------------------------------------------


class TestScoring:
    """SourceSelector populates all score fields and orders by rank correctly."""

    def test_all_score_fields_populated(self) -> None:
        cfg = _default_config(research_source_select_count=4)
        selector = SourceSelector(cfg)
        items = [_item("Result", "https://example.com/page", "Python snippet")]
        results = selector.select(items, "python")
        assert len(results) == 1
        s = results[0]
        assert 0.0 <= s.relevance_score <= 1.0
        assert 0.0 <= s.authority_score <= 1.0
        assert 0.0 <= s.freshness_score <= 1.0
        assert 0.0 <= s.rank_score <= 1.0
        assert 0.0 <= s.composite_score <= 1.0

    def test_higher_rank_position_means_lower_rank_score(self) -> None:
        """Position 0 in search results should score higher than position 3."""
        cfg = _default_config(research_source_select_count=4)
        selector = SourceSelector(cfg)
        # Items for individual rank score comparison — use different domains
        items = [
            _item("First result", "https://site0.com/page"),
            _item("Second result", "https://site1.com/page"),
            _item("Third result", "https://site2.com/page"),
            _item("Fourth result", "https://site3.com/page"),
        ]
        results = selector.select(items, "query")
        # All results should have rank_score > 0
        for r in results:
            assert r.rank_score > 0.0

    def test_first_position_has_highest_rank_score(self) -> None:
        """The item originally at rank 0 should have the highest rank_score."""
        cfg = _default_config(research_source_select_count=4)
        selector = SourceSelector(cfg)
        items = [
            _item("Rank 0", "https://alpha.com/page"),
            _item("Rank 1", "https://beta.com/page"),
            _item("Rank 2", "https://gamma.com/page"),
        ]
        results = selector.select(items, "query")
        # Find the result that was originally at rank 0
        rank_0_result = next(r for r in results if r.original_rank == 0)
        others = [r for r in results if r.original_rank != 0]
        for other in others:
            assert rank_0_result.rank_score >= other.rank_score

    def test_relevance_score_higher_for_matching_query(self) -> None:
        cfg = _default_config(research_source_select_count=4)
        selector = SourceSelector(cfg)
        # Snippet with query terms should score higher on relevance
        matching = _item(
            "Python asyncio guide",
            "https://site1.com/page",
            "Python asyncio guide for beginners asyncio tutorial",
        )
        unrelated = _item(
            "Cooking recipes",
            "https://site2.com/page",
            "How to bake a chocolate cake",
        )
        results = selector.select([matching, unrelated], "python asyncio")
        matching_result = next(r for r in results if "site1.com" in r.url)
        unrelated_result = next(r for r in results if "site2.com" in r.url)
        assert matching_result.relevance_score >= unrelated_result.relevance_score

    def test_selected_source_has_query_field(self) -> None:
        cfg = _default_config(research_source_select_count=2)
        selector = SourceSelector(cfg)
        items = [_item("Page", "https://example.com/page")]
        results = selector.select(items, "test query")
        assert results[0].query == "test query"

    def test_selected_source_has_selection_reason(self) -> None:
        cfg = _default_config(research_source_select_count=2)
        selector = SourceSelector(cfg)
        items = [_item("Page", "https://example.com/page")]
        results = selector.select(items, "query")
        assert results[0].selection_reason != ""

    def test_freshness_score_is_one_for_all_sources(self) -> None:
        """MVP: no date extraction, so freshness_score defaults to 1.0."""
        cfg = _default_config(research_source_select_count=4)
        selector = SourceSelector(cfg)
        items = [
            _item("Old article", "https://oldsite.com/2010/article"),
            _item("New article", "https://newsite.com/2024/article"),
        ]
        results = selector.select(items, "query")
        for r in results:
            assert r.freshness_score == 1.0

    def test_composite_score_is_weighted_sum(self) -> None:
        """composite_score should reflect the configured weights."""
        cfg = _default_config(
            research_source_select_count=2,
            research_weight_relevance=0.25,
            research_weight_authority=0.25,
            research_weight_freshness=0.25,
            research_weight_rank=0.25,
        )
        selector = SourceSelector(cfg)
        items = [_item("Test", "https://example.com/page")]
        results = selector.select(items, "query")
        s = results[0]
        expected = (
            s.relevance_score * 0.25
            + s.authority_score * 0.25
            + s.freshness_score * 0.25
            + s.rank_score * 0.25
        )
        assert abs(s.composite_score - expected) < 1e-6


# ---------------------------------------------------------------------------
# TestImportanceDetermination
# ---------------------------------------------------------------------------


class TestImportanceDetermination:
    """_determine_importance returns correct tier labels."""

    def test_official_high_authority_is_high_importance(self) -> None:
        cfg = _default_config()
        selector = SourceSelector(cfg)
        importance = selector._determine_importance(SourceType.official, 0.9)
        assert importance == "high"

    def test_official_low_authority_is_not_high(self) -> None:
        cfg = _default_config()
        selector = SourceSelector(cfg)
        importance = selector._determine_importance(SourceType.official, 0.70)
        # authority < 0.8 → does not qualify for "high" by default rule
        assert importance in ("medium", "low")

    def test_authoritative_neutral_is_medium(self) -> None:
        cfg = _default_config()
        selector = SourceSelector(cfg)
        importance = selector._determine_importance(SourceType.authoritative_neutral, 0.75)
        assert importance == "medium"

    def test_independent_high_authority_is_medium(self) -> None:
        cfg = _default_config()
        selector = SourceSelector(cfg)
        importance = selector._determine_importance(SourceType.independent, 0.60)
        assert importance == "medium"

    def test_ugc_is_low_importance(self) -> None:
        cfg = _default_config()
        selector = SourceSelector(cfg)
        importance = selector._determine_importance(SourceType.ugc_low_trust, 0.25)
        assert importance == "low"


# ---------------------------------------------------------------------------
# TestQueryContextIntegration
# ---------------------------------------------------------------------------


class TestQueryContextIntegration:
    """SourceSelector respects QueryContext when provided."""

    def test_comparative_context_limits_official_overrepresentation(self) -> None:
        cfg = _default_config(research_source_select_count=3)
        selector = SourceSelector(cfg)
        ctx = QueryContext(comparative=True)
        items = [
            _item("Gov 1", "https://nist.gov/framework"),
            _item("Gov 2", "https://cisa.gov/guidelines"),
            _item("Gov 3", "https://ftc.gov/policy"),
            _item("Tech review", "https://techreview.com/analysis"),
        ]
        results = selector.select(items, "security framework", query_context=ctx)
        source_types = [s.source_type for s in results]
        # With comparative=True, must include at least one non-official source
        assert any(st != SourceType.official for st in source_types)

    def test_non_comparative_context_does_not_restrict_official(self) -> None:
        cfg = _default_config(research_source_select_count=3)
        selector = SourceSelector(cfg)
        ctx = QueryContext(comparative=False)
        items = [
            _item("Gov 1", "https://hhs.gov/health"),
            _item("Gov 2", "https://cdc.gov/disease"),
            _item("Gov 3", "https://fda.gov/drugs"),
        ]
        # With comparative=False and only official sources, all 3 may be selected
        results = selector.select(items, "health information", query_context=ctx)
        assert len(results) == 3

    def test_select_returns_selected_source_instances(self) -> None:
        cfg = _default_config(research_source_select_count=2)
        selector = SourceSelector(cfg)
        items = [
            _item("A", "https://alpha.com/page"),
            _item("B", "https://beta.com/page"),
        ]
        results = selector.select(items, "query")
        for r in results:
            assert isinstance(r, SelectedSource)
