"""Tests for Histogram bounded storage in prometheus_metrics.

Regression tests ensuring:
- Correct bucket/sum/count values
- No raw observation list is retained (bounded memory)
- Multiple independent label sets
- Edge cases (zero, negative, above all buckets)
"""

import math

import pytest

from app.core.prometheus_metrics import Histogram, reset_all_metrics


@pytest.fixture(autouse=True)
def _reset_metrics() -> None:
    reset_all_metrics()
    yield
    reset_all_metrics()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_histogram(buckets: list[float] | None = None) -> Histogram:
    """Create a fresh Histogram not registered in _metrics_registry."""
    if buckets is None:
        buckets = [0.1, 0.5, 1.0, 2.5, 5.0, 10.0]
    return Histogram(
        name="test_histogram",
        help_text="Test histogram",
        labels=["env"],
        buckets=buckets,
    )


def _collect_for_labels(h: Histogram, labels: dict[str, str]) -> dict:
    """Return the single collect() entry matching the given labels."""
    entries = h.collect()
    for entry in entries:
        if entry["labels"] == labels:
            return entry
    raise KeyError(f"No collect() entry for labels {labels!r}")


# ---------------------------------------------------------------------------
# Correctness: bucket counts, sum, count
# ---------------------------------------------------------------------------


def test_observe_basic_bucket_counts() -> None:
    """Values are placed in the correct buckets."""
    h = _make_histogram(buckets=[1.0, 5.0, 10.0])
    h.observe({"env": "test"}, 0.5)  # <= 1, <= 5, <= 10, +Inf
    h.observe({"env": "test"}, 3.0)  # > 1,  <= 5, <= 10, +Inf
    h.observe({"env": "test"}, 7.0)  # > 1,  > 5,  <= 10, +Inf
    h.observe({"env": "test"}, 15.0)  # > 1,  > 5,  > 10,  +Inf

    entry = _collect_for_labels(h, {"env": "test"})
    assert entry["buckets"][1.0] == 1
    assert entry["buckets"][5.0] == 2
    assert entry["buckets"][10.0] == 3
    assert entry["buckets"][float("inf")] == 4
    assert entry["count"] == 4
    assert entry["sum"] == pytest.approx(0.5 + 3.0 + 7.0 + 15.0)


def test_observe_sum_and_count_accumulate() -> None:
    """sum and count correctly accumulate across many calls."""
    h = _make_histogram()
    values = [0.05, 0.2, 0.8, 2.0, 6.0]
    for v in values:
        h.observe({"env": "prod"}, v)

    entry = _collect_for_labels(h, {"env": "prod"})
    assert entry["count"] == len(values)
    assert entry["sum"] == pytest.approx(sum(values))


def test_observe_10000_times_correct_values() -> None:
    """After 10 000 observations the aggregated values remain correct."""
    h = _make_histogram(buckets=[0.5, 1.0, 5.0])
    n = 10_000
    # Alternate between two values so we have deterministic expectations
    for i in range(n):
        h.observe({"env": "load"}, 0.3 if i % 2 == 0 else 3.0)

    entry = _collect_for_labels(h, {"env": "load"})
    assert entry["count"] == n
    expected_sum = (n / 2) * 0.3 + (n / 2) * 3.0
    assert entry["sum"] == pytest.approx(expected_sum)
    # 0.3 <= 0.5: half of n
    assert entry["buckets"][0.5] == n // 2
    # 0.3 and 3.0 are both <= 5.0 → all n
    assert entry["buckets"][5.0] == n
    assert entry["buckets"][float("inf")] == n


# ---------------------------------------------------------------------------
# Bounded storage: no raw observation list retained
# ---------------------------------------------------------------------------


def test_no_raw_observation_list_stored() -> None:
    """Internal state must NOT grow with the number of observations.

    After 10 000 observe() calls the histogram must not contain a list
    of raw float values.  The total in-memory footprint of the per-label
    state must be bounded by O(buckets), not O(observations).
    """
    h = _make_histogram(buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0])

    for _ in range(10_000):
        h.observe({"env": "mem_test"}, 1.5)

    # The histogram must not have _observations attribute at all, or if it
    # does, the list for this label set must not hold 10 000 raw floats.
    if hasattr(h, "_observations"):
        label_tuple = ("mem_test",)
        obs = h._observations.get(label_tuple, [])
        # A list longer than the number of buckets (6) is unacceptable —
        # it means raw samples are still being stored.
        assert len(obs) <= len(h.buckets) + 2, (
            f"Raw observation list has {len(obs)} entries; expected bounded storage (max ~buckets count)"
        )

    # Positive check: the internal state for this label must be compact.
    # After the refactor, _states[label_tuple] should hold only a small
    # fixed-size structure.
    if hasattr(h, "_states"):
        label_tuple = ("mem_test",)
        assert label_tuple in h._states, "Expected _states to contain the label key"
        state = h._states[label_tuple]
        # The state's bucket_counts dict must have at most len(buckets)+1 entries
        assert len(state.bucket_counts) <= len(h.buckets) + 1


def test_internal_state_size_does_not_grow() -> None:
    """Memory footprint stays constant regardless of observation count.

    We measure the size of the internal per-label state object before and
    after a burst of observations.  It must not change.
    """
    import sys

    h = _make_histogram(buckets=[1.0, 5.0, 10.0])
    h.observe({"env": "size_test"}, 2.0)  # prime the state

    # Measure size after first observation
    if hasattr(h, "_states"):
        label_tuple = ("size_test",)
        size_before = sys.getsizeof(h._states[label_tuple].bucket_counts)
        for _ in range(5_000):
            h.observe({"env": "size_test"}, 2.0)
        size_after = sys.getsizeof(h._states[label_tuple].bucket_counts)
        assert size_before == size_after, (
            f"bucket_counts grew from {size_before} to {size_after} bytes; expected fixed-size storage"
        )
    elif hasattr(h, "_observations"):
        pytest.fail("Histogram still uses _observations list storage — bounded storage refactor has not been applied")


# ---------------------------------------------------------------------------
# Multiple independent label sets
# ---------------------------------------------------------------------------


def test_multiple_label_sets_are_independent() -> None:
    """Each label combination maintains its own independent counters."""
    h = _make_histogram(buckets=[1.0, 10.0])
    h.observe({"env": "dev"}, 0.5)
    h.observe({"env": "dev"}, 0.5)
    h.observe({"env": "prod"}, 8.0)

    dev = _collect_for_labels(h, {"env": "dev"})
    prod = _collect_for_labels(h, {"env": "prod"})

    assert dev["count"] == 2
    assert dev["sum"] == pytest.approx(1.0)
    assert dev["buckets"][1.0] == 2
    assert dev["buckets"][float("inf")] == 2

    assert prod["count"] == 1
    assert prod["sum"] == pytest.approx(8.0)
    assert prod["buckets"][1.0] == 0
    assert prod["buckets"][10.0] == 1
    assert prod["buckets"][float("inf")] == 1


def test_multiple_label_sets_no_cross_contamination_large() -> None:
    """10 000 observations on label A don't affect label B counts."""
    h = _make_histogram(buckets=[1.0, 5.0])
    for _ in range(10_000):
        h.observe({"env": "heavy"}, 0.5)
    h.observe({"env": "light"}, 3.0)

    heavy = _collect_for_labels(h, {"env": "heavy"})
    light = _collect_for_labels(h, {"env": "light"})

    assert heavy["count"] == 10_000
    assert light["count"] == 1
    assert light["buckets"][1.0] == 0
    assert light["buckets"][5.0] == 1


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_observe_zero() -> None:
    """Zero value falls into all finite buckets (0 <= any positive bucket)."""
    h = _make_histogram(buckets=[0.0, 1.0, 5.0])
    h.observe({"env": "edge"}, 0.0)

    entry = _collect_for_labels(h, {"env": "edge"})
    assert entry["count"] == 1
    assert entry["sum"] == pytest.approx(0.0)
    # 0.0 <= 0.0 → bucket count 1
    assert entry["buckets"][0.0] == 1
    assert entry["buckets"][1.0] == 1
    assert entry["buckets"][5.0] == 1
    assert entry["buckets"][float("inf")] == 1


def test_observe_negative() -> None:
    """Negative values fall below all positive buckets except +Inf."""
    h = _make_histogram(buckets=[0.0, 1.0, 5.0])
    h.observe({"env": "neg"}, -1.0)

    entry = _collect_for_labels(h, {"env": "neg"})
    assert entry["count"] == 1
    assert entry["sum"] == pytest.approx(-1.0)
    # -1.0 <= 0.0 → yes
    assert entry["buckets"][0.0] == 1
    # -1.0 <= 1.0 → yes
    assert entry["buckets"][1.0] == 1
    # +Inf always catches everything
    assert entry["buckets"][float("inf")] == 1


def test_observe_above_all_buckets() -> None:
    """Values above all finite buckets only appear in +Inf bucket."""
    h = _make_histogram(buckets=[0.1, 0.5, 1.0])
    h.observe({"env": "high"}, 999.0)

    entry = _collect_for_labels(h, {"env": "high"})
    assert entry["count"] == 1
    assert entry["sum"] == pytest.approx(999.0)
    assert entry["buckets"][0.1] == 0
    assert entry["buckets"][0.5] == 0
    assert entry["buckets"][1.0] == 0
    assert entry["buckets"][float("inf")] == 1


def test_observe_exact_bucket_boundary() -> None:
    """Values exactly equal to a bucket boundary are included in that bucket."""
    h = _make_histogram(buckets=[1.0, 5.0])
    h.observe({"env": "boundary"}, 1.0)
    h.observe({"env": "boundary"}, 5.0)

    entry = _collect_for_labels(h, {"env": "boundary"})
    assert entry["buckets"][1.0] == 1  # 1.0 <= 1.0
    assert entry["buckets"][5.0] == 2  # both <= 5.0
    assert entry["buckets"][float("inf")] == 2


def test_observe_inf_value() -> None:
    """A value of +Inf is counted in the +Inf bucket and sum."""
    h = _make_histogram(buckets=[1.0, 5.0])
    h.observe({"env": "inf_val"}, float("inf"))

    entry = _collect_for_labels(h, {"env": "inf_val"})
    assert entry["count"] == 1
    assert math.isinf(entry["sum"])
    assert entry["buckets"][1.0] == 0
    assert entry["buckets"][5.0] == 0
    assert entry["buckets"][float("inf")] == 1


# ---------------------------------------------------------------------------
# collect() output format
# ---------------------------------------------------------------------------


def test_collect_output_structure() -> None:
    """collect() returns a list of dicts with expected keys."""
    h = _make_histogram(buckets=[1.0, 5.0])
    h.observe({"env": "fmt"}, 2.0)

    entries = h.collect()
    assert len(entries) == 1
    entry = entries[0]
    assert entry["name"] == "test_histogram"
    assert entry["type"] == "histogram"
    assert "labels" in entry
    assert "buckets" in entry
    assert "sum" in entry
    assert "count" in entry
    # +Inf bucket must always be present
    assert float("inf") in entry["buckets"]


def test_collect_empty_when_no_observations() -> None:
    """collect() returns empty list when no observations have been made."""
    h = _make_histogram()
    assert h.collect() == []
