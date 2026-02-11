from app.domain.services.agents.output_coverage_validator import OutputCoverageValidator
from app.domain.services.agents.response_compressor import ResponseCompressor
from app.domain.services.agents.response_policy import VerbosityMode


def test_output_coverage_validator_rejects_missing_next_step() -> None:
    validator = OutputCoverageValidator()
    output = """
    Final result: Updated the parser and added tests.
    Artifact references: `backend/app/parser.py`, `backend/tests/test_parser.py`
    """
    result = validator.validate(
        output=output,
        user_request="Update parser and include next action",
        required_sections=["final result", "artifact references", "next step"],
    )

    assert result.is_valid is False
    assert "next step" in result.missing_requirements


def test_output_coverage_validator_accepts_complete_response() -> None:
    validator = OutputCoverageValidator()
    output = """
    Final result: Updated the parser and added tests.
    Artifact references: `backend/app/parser.py`, `backend/tests/test_parser.py`
    Caveat: This has not been load-tested yet.
    Next step: Run the parser benchmark in CI.
    """
    result = validator.validate(
        output=output,
        user_request="Update parser and include caveats",
        required_sections=["final result", "artifact references", "key caveat", "next step"],
    )

    assert result.is_valid is True
    assert result.quality_score > 0.9


def test_response_compressor_preserves_key_sections() -> None:
    compressor = ResponseCompressor()
    validator = OutputCoverageValidator()
    content = """
    # Report

    Final result: Implemented adaptive verbosity and clarification flow with coverage checks.

    Details: This update introduces policy selection, clarification gating, and quality-aware compression.
    It also updates settings schemas and frontend defaults.

    Artifact references: `backend/app/domain/services/agents/response_policy.py`,
    `backend/app/domain/services/agents/response_compressor.py`,
    `backend/app/domain/services/flows/plan_act.py`.

    Caveat: Compression is rejected when required sections are missing.

    Next step: Run backend and frontend lint/type/test checks.
    """ + ("\n\nExtra background context." * 120)

    compressed = compressor.compress(content, mode=VerbosityMode.CONCISE, max_chars=900)
    result = validator.validate(
        output=compressed,
        user_request="Implement adaptive verbosity with safe compression",
        required_sections=["final result", "artifact references", "key caveat", "next step"],
    )

    assert len(compressed) <= 903
    assert result.is_valid is True


def test_output_coverage_validator_accepts_explicit_no_artifacts_statement() -> None:
    validator = OutputCoverageValidator()
    output = """
    Final result: Investigated the runtime behavior and completed the requested analysis.
    Artifact references: no file artifacts were created for this request.
    Next step: Review the findings and decide whether implementation changes are needed.
    """
    result = validator.validate(
        output=output,
        user_request="Investigate behavior and summarize findings",
        required_sections=["final result", "artifact references", "next step"],
    )

    assert result.is_valid is True
    assert "artifact references" not in result.missing_requirements
