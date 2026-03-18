"""Tests for the multi-method price consensus engine (price_voter.py).

Validates:
- Unanimous consensus when all methods agree
- Majority consensus when 2/3 methods agree
- Single-vote fallback when only one method succeeds
- Best-confidence fallback when methods disagree
- Agreement threshold logic (5%)
- LLM vote integration via add_llm_vote()
- Metadata collection from richest vote
"""

from __future__ import annotations

from app.infrastructure.external.deal_finder.price_voter import (
    PriceVote,
    VotingResult,
    _find_consensus_group,
    _prices_agree,
    add_llm_vote,
    vote_on_price,
)

# ──────────────────────────────────────────────────────────────
# _prices_agree tests
# ──────────────────────────────────────────────────────────────


class TestPricesAgree:
    def test_identical_prices(self) -> None:
        assert _prices_agree(49.99, 49.99) is True

    def test_within_threshold(self) -> None:
        # 50.00 vs 51.00 → 2% diff → within 5%
        assert _prices_agree(50.00, 51.00) is True

    def test_at_threshold_boundary(self) -> None:
        # 100.00 vs 105.00 → exactly 5%
        assert _prices_agree(100.00, 105.00) is True

    def test_beyond_threshold(self) -> None:
        # 100.00 vs 106.00 → 6% → outside 5%
        assert _prices_agree(100.00, 106.00) is False

    def test_large_price_difference(self) -> None:
        assert _prices_agree(49.99, 399.99) is False

    def test_zero_prices_equal(self) -> None:
        assert _prices_agree(0.0, 0.0) is True

    def test_zero_and_nonzero(self) -> None:
        assert _prices_agree(0.0, 50.0) is False


# ──────────────────────────────────────────────────────────────
# _find_consensus_group tests
# ──────────────────────────────────────────────────────────────


class TestFindConsensusGroup:
    def test_empty_votes(self) -> None:
        group, method = _find_consensus_group([])
        assert group == []
        assert method == "none"

    def test_no_valid_votes(self) -> None:
        votes = [
            PriceVote(price=None, method="json_ld", confidence=0.95),
            PriceVote(price=0.0, method="css", confidence=0.80),
        ]
        group, method = _find_consensus_group(votes)
        assert group == []
        assert method == "none"

    def test_single_vote(self) -> None:
        votes = [
            PriceVote(price=49.99, method="json_ld", confidence=0.95),
            PriceVote(price=None, method="css", confidence=0.80),
        ]
        group, method = _find_consensus_group(votes)
        assert len(group) == 1
        assert method == "single"
        assert group[0].price == 49.99

    def test_unanimous_agreement(self) -> None:
        votes = [
            PriceVote(price=49.99, method="json_ld", confidence=0.95),
            PriceVote(price=50.00, method="css", confidence=0.80),  # Within 5%
            PriceVote(price=49.50, method="generic", confidence=0.30),  # Within 5%
        ]
        group, method = _find_consensus_group(votes)
        assert method == "unanimous"
        assert len(group) == 3

    def test_majority_agreement(self) -> None:
        votes = [
            PriceVote(price=49.99, method="json_ld", confidence=0.95),
            PriceVote(price=50.50, method="css", confidence=0.80),  # Within 5%
            PriceVote(price=399.99, method="generic", confidence=0.30),  # Disagrees
        ]
        group, method = _find_consensus_group(votes)
        assert method == "majority"
        assert len(group) == 2

    def test_best_confidence_no_agreement(self) -> None:
        votes = [
            PriceVote(price=49.99, method="json_ld", confidence=0.95),
            PriceVote(price=399.99, method="css", confidence=0.80),
        ]
        group, method = _find_consensus_group(votes)
        assert method == "best_confidence"
        assert len(group) == 1
        assert group[0].confidence == 0.95  # Highest confidence wins


# ──────────────────────────────────────────────────────────────
# vote_on_price integration tests
# ──────────────────────────────────────────────────────────────


class TestVoteOnPrice:
    """Tests that run actual extraction on synthetic HTML."""

    def test_jsonld_only(self) -> None:
        """JSON-LD present, no CSS or regex matches."""
        html = """
        <html>
        <head>
        <script type="application/ld+json">
        {"@type": "Product", "name": "Test Widget",
         "offers": {"price": 29.99, "availability": "InStock"}}
        </script>
        </head>
        <body><h1>Test Widget</h1></body>
        </html>
        """
        result = vote_on_price(html, "https://example.com/product")
        assert result.price == 29.99
        assert result.consensus_method in ("single", "unanimous", "majority")
        assert result.confidence > 0
        assert result.product_name == "Test Widget"

    def test_all_methods_agree(self) -> None:
        """HTML with JSON-LD + CSS-matchable price + regex price."""
        html = """
        <html>
        <head>
        <script type="application/ld+json">
        {"@type": "Product", "name": "Headphones",
         "offers": {"price": 199.99, "availability": "InStock"}}
        </script>
        </head>
        <body>
        <h1>Headphones</h1>
        <span class="a-price .a-offscreen">$199.99</span>
        <div>Price: $199.99</div>
        </body>
        </html>
        """
        result = vote_on_price(html, "https://amazon.com/product")
        assert result.price == 199.99
        # Confidence depends on which methods matched; CSS may not match synthetic HTML
        assert result.confidence > 0

    def test_no_price_found(self) -> None:
        """HTML with no price information."""
        html = "<html><body><h1>About Us</h1><p>Welcome!</p></body></html>"
        result = vote_on_price(html, "https://example.com/about")
        assert result.price is None
        assert result.consensus_method == "none"
        assert result.total_votes == 0

    def test_original_price_propagation(self) -> None:
        """Ensure original price from JSON-LD is propagated."""
        html = """
        <script type="application/ld+json">
        {"@type": "Product", "name": "Gadget",
         "offers": {"price": 79.99, "highPrice": 99.99}}
        </script>
        """
        result = vote_on_price(html, "https://example.com/gadget")
        assert result.price == 79.99
        assert result.original_price == 99.99

    def test_out_of_stock_detection(self) -> None:
        """Detect out-of-stock from JSON-LD availability."""
        html = """
        <script type="application/ld+json">
        {"@type": "Product", "name": "Rare Item",
         "offers": {"price": 59.99, "availability": "OutOfStock"}}
        </script>
        """
        result = vote_on_price(html, "https://example.com/rare")
        assert result.price == 59.99
        assert result.in_stock is False


# ──────────────────────────────────────────────────────────────
# add_llm_vote tests
# ──────────────────────────────────────────────────────────────


class TestAddLLMVote:
    def test_llm_creates_consensus(self) -> None:
        """LLM vote agrees with existing best_confidence → upgrades to majority."""
        initial = VotingResult(
            price=49.99,
            consensus_method="best_confidence",
            winning_strategy="json_ld",
            confidence=0.76,  # 0.95 * 0.8 penalty
            agreement_count=1,
            total_votes=2,
            votes=[
                PriceVote(price=49.99, method="json_ld", confidence=0.95),
                PriceVote(price=399.99, method="css", confidence=0.80),
            ],
        )

        llm_vote = PriceVote(price=50.00, method="llm", confidence=0.85)
        result = add_llm_vote(initial, llm_vote)

        assert result.consensus_method == "majority"
        assert result.agreement_count == 2
        assert result.price == 49.99  # json_ld has higher confidence

    def test_llm_disagrees(self) -> None:
        """LLM vote disagrees with all → still best_confidence."""
        initial = VotingResult(
            price=49.99,
            consensus_method="best_confidence",
            winning_strategy="json_ld",
            confidence=0.76,
            agreement_count=1,
            total_votes=1,
            votes=[
                PriceVote(price=49.99, method="json_ld", confidence=0.95),
            ],
        )

        llm_vote = PriceVote(price=199.99, method="llm", confidence=0.85)
        result = add_llm_vote(initial, llm_vote)

        assert result.consensus_method == "best_confidence"
        assert result.price == 49.99  # json_ld still wins

    def test_llm_fills_missing_metadata(self) -> None:
        """LLM provides product_name when others don't."""
        initial = VotingResult(
            price=29.99,
            product_name=None,
            votes=[PriceVote(price=29.99, method="generic", confidence=0.30)],
        )

        llm_vote = PriceVote(price=29.99, method="llm", confidence=0.85, product_name="Smart Widget Pro")
        result = add_llm_vote(initial, llm_vote)
        assert result.product_name == "Smart Widget Pro"
