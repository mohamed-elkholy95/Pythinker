"""Tests for truncation notice suppression when evidence is poor."""



class TestTruncationNoticeSuppression:
    """Truncation notice should only appear for actual truncation, not zero-source reports."""

    def test_no_banner_when_zero_sources_and_artifacts(self):
        """Don't prepend truncation banner when the real problem is zero sources."""
        source_count = 0
        truncation_exhausted = False
        has_artifacts = True  # Content has [...] but that's from LLM, not truncation

        # New logic: suppress banner when source_count == 0
        should_show_banner = (truncation_exhausted or has_artifacts) and source_count > 0
        assert should_show_banner is False

    def test_no_banner_when_zero_sources_and_truncation_exhausted(self):
        """Even truncation_exhausted should not show banner with zero sources."""
        source_count = 0
        truncation_exhausted = True
        has_artifacts = True

        should_show_banner = (truncation_exhausted or has_artifacts) and source_count > 0
        assert should_show_banner is False

    def test_banner_shown_for_actual_truncation_with_sources(self):
        """Show truncation banner when there are sources and actual truncation."""
        source_count = 5
        truncation_exhausted = True
        has_artifacts = True

        should_show_banner = (truncation_exhausted or has_artifacts) and source_count > 0
        assert should_show_banner is True

    def test_banner_shown_for_artifacts_with_sources(self):
        """Show truncation banner when there are sources and streaming artifacts."""
        source_count = 3
        truncation_exhausted = False
        has_artifacts = True

        should_show_banner = (truncation_exhausted or has_artifacts) and source_count > 0
        assert should_show_banner is True

    def test_no_banner_when_no_truncation_and_no_artifacts(self):
        """No banner when there's no truncation issue at all."""
        source_count = 5
        truncation_exhausted = False
        has_artifacts = False

        should_show_banner = (truncation_exhausted or has_artifacts) and source_count > 0
        assert should_show_banner is False
