"""Tests for deal result quality refinements.

Covers:
- Tighter title relevance filtering (60% threshold + key product word check)
- EDITORIAL_REVIEW_DOMAINS constant completeness
"""

from app.infrastructure.external.deal_finder.adapter import (
    EDITORIAL_REVIEW_DOMAINS,
    _title_matches_query,
)


class TestTitleRelevance:
    # ── Exact matches — always pass ──────────────────────────────────────────

    def test_exact_match_passes(self):
        assert _title_matches_query("Netflix Premium Plan 2026", "Netflix Premium")

    def test_exact_phrase_in_longer_title(self):
        assert _title_matches_query("Buy Netflix Premium Annual Subscription Today", "Netflix Premium")

    # ── Key product word enforcement ─────────────────────────────────────────

    def test_unrelated_product_rejected_by_key_word_check(self):
        """A cutting set should NOT match a Netflix query — 'netflix' absent."""
        assert not _title_matches_query("3-Piece Cutting Set", "Netflix Premium annual subscription")

    def test_generic_words_only_overlap_rejected(self):
        """'annual' and 'subscription' match but 'netflix'/'premium' do not."""
        assert not _title_matches_query("Annual Subscription Box", "Netflix Premium annual subscription")

    def test_key_word_present_but_low_overlap_rejected(self):
        """'Netflix' is present so key check passes, but only 1/4 significant
        words match ('premium', 'annual', 'subscription' are absent) → 25% < 60% → reject.
        'Netflix Standard' is not the same product as 'Netflix Premium'."""
        assert not _title_matches_query("Netflix Standard with Ads Plan", "Netflix Premium annual subscription")

    def test_key_product_words_for_hardware(self):
        """'Sony' and 'WF-1000XM5' are key identifiers — both absent → reject."""
        assert not _title_matches_query("Wireless Earbuds Sale 2026", "Sony WF-1000XM5 earbuds")

    def test_first_key_word_sufficient(self):
        """Only 'Sony' (first key word) needs to match."""
        assert _title_matches_query("Sony True Wireless Earbuds WF-1000XM5", "Sony WF-1000XM5 earbuds")

    # ── Word overlap threshold (60%) ──────────────────────────────────────────

    def test_relevant_product_passes_60pct_threshold(self):
        """All significant words present — well above 60%."""
        assert _title_matches_query("iPad Air M2 11-inch 256GB WiFi", "iPad Air M2 11-inch 256GB")

    def test_partial_model_number_passes(self):
        """'Sony' + 'WF-1000XM5' = 2/3 significant words = 67% ≥ 60%."""
        assert _title_matches_query("Sony WF-1000XM5 True Wireless", "Sony WF-1000XM5 earbuds")

    def test_below_60pct_rejected(self):
        """Only 1/3 significant query words appear in the title — 33% < 60%."""
        assert not _title_matches_query("Green Lipped Mussel Supplement", "GLM 5 AI")

    def test_60pct_threshold_passes_when_key_word_and_overlap_met(self):
        """'pro' is a stop word so query_words=['iphone','15','max'].
        Title has 'iphone'+'15' but NOT 'max' → 2/3 = 67% ≥ 60% → passes.
        Demonstrates that 'pro' being filtered as a stop word means
        'iPhone 15 Case Cover' matches 'iPhone 15 Pro Max' at 67%."""
        assert _title_matches_query("iPhone 15 Case Cover", "iPhone 15 Pro Max")

    def test_model_specific_words_required(self):
        """Only 1/3 significant words match → 33% < 60% → reject."""
        # query_words: ['samsung', 'galaxy', 's24'] ('ultra' is not a stop word)
        # Title 'samsung' matches 1/4 = 25% → reject
        assert not _title_matches_query("Samsung Case Accessory Bundle", "Samsung Galaxy S24 Ultra")

    # ── Existing behaviours preserved ────────────────────────────────────────

    def test_numeric_mismatch_still_rejected(self):
        """Numeric enforcement: title has '400' not '5'."""
        assert not _title_matches_query("Bosch GLM 400C Laser Measure", "GLM 5 AI")

    def test_single_word_query_still_passes(self):
        assert _title_matches_query("PlayStation 5 Console", "PlayStation")

    def test_empty_title_returns_false(self):
        assert not _title_matches_query("", "Netflix Premium")

    def test_empty_query_returns_false(self):
        assert not _title_matches_query("Netflix Premium Plan", "")

    def test_all_stop_words_query_returns_false(self):
        assert not _title_matches_query("The Best Deal Ever", "the best")


class TestEditorialDomains:
    # ── Presence of expected editorial domains ────────────────────────────────

    def test_major_tech_publications_defined(self):
        assert "cnet.com" in EDITORIAL_REVIEW_DOMAINS
        assert "theverge.com" in EDITORIAL_REVIEW_DOMAINS
        assert "techradar.com" in EDITORIAL_REVIEW_DOMAINS
        assert "pcmag.com" in EDITORIAL_REVIEW_DOMAINS
        assert "engadget.com" in EDITORIAL_REVIEW_DOMAINS
        assert "tomsguide.com" in EDITORIAL_REVIEW_DOMAINS

    def test_video_and_news_domains_defined(self):
        assert "youtube.com" in EDITORIAL_REVIEW_DOMAINS
        assert "cnn.com" in EDITORIAL_REVIEW_DOMAINS
        assert "businessinsider.com" in EDITORIAL_REVIEW_DOMAINS
        assert "gizmodo.com" in EDITORIAL_REVIEW_DOMAINS

    def test_apple_and_niche_tech_blogs_defined(self):
        assert "9to5mac.com" in EDITORIAL_REVIEW_DOMAINS
        assert "9to5toys.com" in EDITORIAL_REVIEW_DOMAINS
        assert "howtogeek.com" in EDITORIAL_REVIEW_DOMAINS
        assert "zdnet.com" in EDITORIAL_REVIEW_DOMAINS
        assert "mashable.com" in EDITORIAL_REVIEW_DOMAINS

    def test_audio_and_display_review_sites_defined(self):
        assert "rtings.com" in EDITORIAL_REVIEW_DOMAINS
        assert "soundguys.com" in EDITORIAL_REVIEW_DOMAINS
        assert "notebookcheck.net" in EDITORIAL_REVIEW_DOMAINS

    def test_streaming_guide_and_misc_defined(self):
        assert "cabletv.com" in EDITORIAL_REVIEW_DOMAINS
        assert "agoodmovietowatch.com" in EDITORIAL_REVIEW_DOMAINS
        assert "dealnews.com" in EDITORIAL_REVIEW_DOMAINS

    # ── Retail domains must NOT be in editorial set ───────────────────────────

    def test_amazon_not_in_editorial(self):
        assert "amazon.com" not in EDITORIAL_REVIEW_DOMAINS

    def test_bestbuy_not_in_editorial(self):
        assert "bestbuy.com" not in EDITORIAL_REVIEW_DOMAINS

    def test_walmart_not_in_editorial(self):
        assert "walmart.com" not in EDITORIAL_REVIEW_DOMAINS

    def test_newegg_not_in_editorial(self):
        assert "newegg.com" not in EDITORIAL_REVIEW_DOMAINS

    def test_ebay_not_in_editorial(self):
        assert "ebay.com" not in EDITORIAL_REVIEW_DOMAINS

    def test_target_not_in_editorial(self):
        assert "target.com" not in EDITORIAL_REVIEW_DOMAINS

    # ── Type safety ───────────────────────────────────────────────────────────

    def test_is_frozenset(self):
        assert isinstance(EDITORIAL_REVIEW_DOMAINS, frozenset)

    def test_all_entries_are_strings(self):
        assert all(isinstance(d, str) for d in EDITORIAL_REVIEW_DOMAINS)

    def test_no_www_prefix_in_entries(self):
        """Domain entries must not start with 'www.' (normalised without prefix)."""
        assert not any(d.startswith("www.") for d in EDITORIAL_REVIEW_DOMAINS)
