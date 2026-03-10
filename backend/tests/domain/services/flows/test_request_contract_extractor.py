"""Tests for RequestContract entity extraction (2026-02-13 plan Phase 1)."""

from app.domain.services.flows.request_contract_extractor import extract


def test_extract_model_names() -> None:
    """Model names like Claude Sonnet 4.5 should be extracted."""
    r = extract("What is Claude Sonnet 4.5?")
    assert "Claude Sonnet 4.5" in r.locked_entities or "claude sonnet 4.5" in [e.lower() for e in r.locked_entities]
    assert r.exact_query == "What is Claude Sonnet 4.5?"


def test_extract_compare_models() -> None:
    """Multiple models in one query."""
    r = extract("Compare GPT-4 and Claude Opus 4.6")
    entities_lower = [e.lower() for e in r.locked_entities]
    assert any("gpt" in e and "4" in e for e in entities_lower)
    assert any("claude" in e and "opus" in e for e in entities_lower)


def test_extract_python_version() -> None:
    """Python 3.12 should be extracted."""
    r = extract("Python 3.12 new features")
    assert any("python" in e.lower() and "3.12" in e for e in r.locked_entities)
    assert "3.12" in r.locked_versions


def test_extract_version_numbers() -> None:
    """Standalone version numbers."""
    r = extract("FastAPI 0.115 migration guide")
    assert "0.115" in r.locked_versions or any("0.115" in e for e in r.locked_entities)


def test_extract_numeric_constraints() -> None:
    """Top N, under $X patterns."""
    r = extract("Top 5 JavaScript frameworks")
    assert any("top" in c.lower() and "5" in c for c in r.numeric_constraints)


def test_extract_quoted_strings() -> None:
    """Quoted exact phrases as fallback."""
    r = extract('Find the "exact phrase" in the document')
    assert "exact phrase" in r.locked_entities


def test_extract_empty_query() -> None:
    """Empty query returns empty contract."""
    r = extract("")
    assert r.locked_entities == []
    assert r.locked_versions == []
    assert r.extraction_confidence == 0.0


def test_extract_no_entities() -> None:
    """Query with no extractable entities."""
    r = extract("What is the weather today?")
    assert r.exact_query == "What is the weather today?"
    # May have quoted or capitalized fallbacks, or empty
    assert isinstance(r.locked_entities, list)
    assert isinstance(r.locked_versions, list)


# --- Requested filename extraction tests ---


def test_extract_requested_output_filename() -> None:
    """Explicit .md filename in the query should be captured."""
    contract = extract(
        "Produce a cited markdown report named agent_observability_report.md in the workspace.",
        intent="research",
        action_type="research",
    )
    assert "agent_observability_report.md" in contract.requested_filenames


def test_extract_no_filename_when_absent() -> None:
    """No filename when the query has no file extension pattern."""
    contract = extract(
        "Tell me about Python frameworks",
        intent="research",
        action_type="research",
    )
    assert contract.requested_filenames == []


def test_extract_multiple_filenames() -> None:
    """Multiple filenames in the same query are all captured."""
    contract = extract(
        "Save results to output.csv and summary_report.md",
        intent="research",
        action_type="research",
    )
    assert "output.csv" in contract.requested_filenames
    assert "summary_report.md" in contract.requested_filenames


def test_extract_filename_with_various_extensions() -> None:
    """Filenames with .txt, .json, .html, .pdf extensions are captured."""
    contract = extract("Write the data to results.json")
    assert "results.json" in contract.requested_filenames

    contract2 = extract("Export the page to analysis.html")
    assert "analysis.html" in contract2.requested_filenames

    contract3 = extract("Create notes.txt with the findings")
    assert "notes.txt" in contract3.requested_filenames


def test_extract_filename_ignores_urls() -> None:
    """URLs should not be captured as filenames."""
    contract = extract("Go to example.com and download the file")
    # example.com should not appear as a requested filename
    # (no file extension like .md/.txt/.csv/.json/.html/.pdf/.png)
    assert all(not f.endswith(".com") for f in contract.requested_filenames)


def test_extract_empty_query_has_no_filenames() -> None:
    """Empty query should have no filenames."""
    contract = extract("")
    assert contract.requested_filenames == []
