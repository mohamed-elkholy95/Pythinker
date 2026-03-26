"""Tests for slides.py - enums, dataclasses, constants, and pure methods.

Covers:
- SlideMode enum
- SlideTheme enum
- Slide dataclass
- Presentation dataclass (including slide_count property)
- THEME_CONFIGS constant
- SlidesTool._detect_layout()
- SlidesTool._extract_table()
- SlidesTool._generate_speaker_notes()
- SlidesTool._markdown_to_html()
- SlidesTool._parse_markdown_to_slides()
- SlidesTool._format_creation_result()
- SlidesTool._generate_slide_descriptions()
"""

from __future__ import annotations

from typing import ClassVar

import pytest

from app.domain.services.tools.slides import (
    THEME_CONFIGS,
    Presentation,
    Slide,
    SlideMode,
    SlidesTool,
    SlideTheme,
)

# --------------------------------------------------------------------------
# SlideMode
# --------------------------------------------------------------------------


class TestSlideMode:
    def test_html_value(self) -> None:
        assert SlideMode.HTML == "html"

    def test_image_value(self) -> None:
        assert SlideMode.IMAGE == "image"

    def test_is_str_subclass(self) -> None:
        assert isinstance(SlideMode.HTML, str)
        assert isinstance(SlideMode.IMAGE, str)

    def test_members_count(self) -> None:
        assert len(SlideMode) == 2

    def test_from_string_html(self) -> None:
        assert SlideMode("html") is SlideMode.HTML

    def test_from_string_image(self) -> None:
        assert SlideMode("image") is SlideMode.IMAGE

    def test_invalid_value_raises(self) -> None:
        with pytest.raises(ValueError):
            SlideMode("pptx")


# --------------------------------------------------------------------------
# SlideTheme
# --------------------------------------------------------------------------


class TestSlideTheme:
    EXPECTED_VALUES: ClassVar[set[str]] = {
        "corporate",
        "minimal",
        "dark",
        "elegant",
        "vibrant",
        "gradient",
        "modern",
        "tech",
        "academic",
        "startup",
    }

    def test_all_values_present(self) -> None:
        actual = {t.value for t in SlideTheme}
        assert actual == self.EXPECTED_VALUES

    def test_member_count(self) -> None:
        assert len(SlideTheme) == 10

    def test_is_str_subclass(self) -> None:
        for theme in SlideTheme:
            assert isinstance(theme, str)

    def test_corporate_value(self) -> None:
        assert SlideTheme.CORPORATE == "corporate"

    def test_dark_value(self) -> None:
        assert SlideTheme.DARK == "dark"

    def test_tech_value(self) -> None:
        assert SlideTheme.TECH == "tech"

    def test_from_string_roundtrip(self) -> None:
        for theme in SlideTheme:
            assert SlideTheme(theme.value) is theme

    def test_invalid_value_raises(self) -> None:
        with pytest.raises(ValueError):
            SlideTheme("neon")

    def test_professional_group_present(self) -> None:
        professional = {"corporate", "minimal", "dark", "elegant"}
        assert professional.issubset({t.value for t in SlideTheme})

    def test_creative_group_present(self) -> None:
        creative = {"vibrant", "gradient", "modern"}
        assert creative.issubset({t.value for t in SlideTheme})

    def test_specialized_group_present(self) -> None:
        specialized = {"tech", "academic", "startup"}
        assert specialized.issubset({t.value for t in SlideTheme})


# --------------------------------------------------------------------------
# Slide dataclass
# --------------------------------------------------------------------------


class TestSlideDataclass:
    def test_required_fields(self) -> None:
        slide = Slide(index=0, title="Intro", content="Hello world")
        assert slide.index == 0
        assert slide.title == "Intro"
        assert slide.content == "Hello world"

    def test_default_layout(self) -> None:
        slide = Slide(index=0, title="T", content="C")
        assert slide.layout == "title-content"

    def test_default_speaker_notes_empty(self) -> None:
        slide = Slide(index=0, title="T", content="C")
        assert slide.speaker_notes == ""

    def test_default_background_none(self) -> None:
        slide = Slide(index=0, title="T", content="C")
        assert slide.background is None

    def test_default_chart_data_none(self) -> None:
        slide = Slide(index=0, title="T", content="C")
        assert slide.chart_data is None

    def test_default_table_data_none(self) -> None:
        slide = Slide(index=0, title="T", content="C")
        assert slide.table_data is None

    def test_default_image_url_none(self) -> None:
        slide = Slide(index=0, title="T", content="C")
        assert slide.image_url is None

    def test_explicit_layout(self) -> None:
        slide = Slide(index=1, title="T", content="C", layout="table")
        assert slide.layout == "table"

    def test_speaker_notes_assigned(self) -> None:
        slide = Slide(index=0, title="T", content="C", speaker_notes="Remember to pause")
        assert slide.speaker_notes == "Remember to pause"

    def test_chart_data_assigned(self) -> None:
        data = {"type": "bar", "labels": ["A"], "values": [1]}
        slide = Slide(index=0, title="T", content="C", chart_data=data)
        assert slide.chart_data == data

    def test_table_data_assigned(self) -> None:
        rows = [["Name", "Value"], ["Alpha", "1"]]
        slide = Slide(index=0, title="T", content="C", table_data=rows)
        assert slide.table_data == rows

    def test_image_url_assigned(self) -> None:
        slide = Slide(index=0, title="T", content="C", image_url="https://example.com/img.png")
        assert slide.image_url == "https://example.com/img.png"

    def test_background_assigned(self) -> None:
        slide = Slide(index=0, title="T", content="C", background="#ff0000")
        assert slide.background == "#ff0000"

    def test_index_zero_allowed(self) -> None:
        slide = Slide(index=0, title="First", content="content")
        assert slide.index == 0

    def test_index_large_value(self) -> None:
        slide = Slide(index=99, title="Last", content="content")
        assert slide.index == 99


# --------------------------------------------------------------------------
# Presentation dataclass
# --------------------------------------------------------------------------


class TestPresentationDataclass:
    def test_required_title(self) -> None:
        p = Presentation(title="My Deck")
        assert p.title == "My Deck"

    def test_defaults(self) -> None:
        p = Presentation(title="T")
        assert p.subtitle == ""
        assert p.author == ""
        assert p.date == ""
        assert p.theme is SlideTheme.CORPORATE
        assert p.slides == []
        assert p.mode is SlideMode.HTML

    def test_slide_count_empty(self) -> None:
        p = Presentation(title="T")
        assert p.slide_count == 0

    def test_slide_count_with_slides(self) -> None:
        slides = [
            Slide(index=0, title="A", content="a"),
            Slide(index=1, title="B", content="b"),
            Slide(index=2, title="C", content="c"),
        ]
        p = Presentation(title="T", slides=slides)
        assert p.slide_count == 3

    def test_slide_count_updates_dynamically(self) -> None:
        p = Presentation(title="T")
        assert p.slide_count == 0
        p.slides.append(Slide(index=0, title="New", content="content"))
        assert p.slide_count == 1

    def test_theme_assigned(self) -> None:
        p = Presentation(title="T", theme=SlideTheme.DARK)
        assert p.theme is SlideTheme.DARK

    def test_mode_image(self) -> None:
        p = Presentation(title="T", mode=SlideMode.IMAGE)
        assert p.mode is SlideMode.IMAGE

    def test_author_and_date(self) -> None:
        p = Presentation(title="T", author="Alice", date="2026-01-01")
        assert p.author == "Alice"
        assert p.date == "2026-01-01"

    def test_subtitle_assigned(self) -> None:
        p = Presentation(title="T", subtitle="Quarterly Review")
        assert p.subtitle == "Quarterly Review"

    def test_slides_list_independent(self) -> None:
        p1 = Presentation(title="T1")
        p2 = Presentation(title="T2")
        p1.slides.append(Slide(index=0, title="S", content="c"))
        assert p2.slide_count == 0


# --------------------------------------------------------------------------
# THEME_CONFIGS constant
# --------------------------------------------------------------------------


class TestThemeConfigs:
    REQUIRED_KEYS: ClassVar[set[str]] = {
        "background",
        "text_color",
        "accent_color",
        "heading_font",
        "body_font",
        "highlight_color",
    }

    def test_all_themes_covered(self) -> None:
        assert set(THEME_CONFIGS.keys()) == set(SlideTheme)

    def test_each_theme_has_required_keys(self) -> None:
        for theme, config in THEME_CONFIGS.items():
            missing = self.REQUIRED_KEYS - config.keys()
            assert missing == set(), f"Theme {theme.value} missing keys: {missing}"

    def test_corporate_accent_color(self) -> None:
        assert THEME_CONFIGS[SlideTheme.CORPORATE]["accent_color"] == "#1F4E79"

    def test_dark_background(self) -> None:
        assert THEME_CONFIGS[SlideTheme.DARK]["background"] == "#1a1a2e"

    def test_dark_text_color(self) -> None:
        assert THEME_CONFIGS[SlideTheme.DARK]["text_color"] == "#eaeaea"

    def test_tech_text_color_green(self) -> None:
        assert THEME_CONFIGS[SlideTheme.TECH]["text_color"] == "#00ff00"

    def test_gradient_background_contains_linear(self) -> None:
        bg = THEME_CONFIGS[SlideTheme.GRADIENT]["background"]
        assert "linear-gradient" in bg

    def test_elegant_heading_font(self) -> None:
        assert THEME_CONFIGS[SlideTheme.ELEGANT]["heading_font"] == "Playfair Display"

    def test_minimal_fonts_are_inter(self) -> None:
        config = THEME_CONFIGS[SlideTheme.MINIMAL]
        assert config["heading_font"] == "Inter"
        assert config["body_font"] == "Inter"

    def test_academic_accent_is_crimson(self) -> None:
        # Crimson/burgundy code for academic
        assert THEME_CONFIGS[SlideTheme.ACADEMIC]["accent_color"] == "#800020"

    def test_startup_accent_color(self) -> None:
        assert THEME_CONFIGS[SlideTheme.STARTUP]["accent_color"] == "#FF5722"

    def test_all_values_are_strings(self) -> None:
        for theme, config in THEME_CONFIGS.items():
            for key, value in config.items():
                assert isinstance(value, str), f"Theme {theme.value}[{key}] is not a string"

    def test_no_empty_values(self) -> None:
        for theme, config in THEME_CONFIGS.items():
            for key, value in config.items():
                assert value.strip(), f"Theme {theme.value}[{key}] is empty"


# --------------------------------------------------------------------------
# --- SlidesTool._detect_layout() ---
# --------------------------------------------------------------------------


class TestDetectLayout:
    @pytest.fixture()
    def tool(self) -> SlidesTool:
        return SlidesTool()

    def test_chart_marker_square_bracket(self, tool: SlidesTool) -> None:
        assert tool._detect_layout("[chart: bar]") == "chart"

    def test_graph_marker(self, tool: SlidesTool) -> None:
        assert tool._detect_layout("[graph: line]") == "chart"

    def test_chart_marker_case_insensitive(self, tool: SlidesTool) -> None:
        assert tool._detect_layout("[CHART: pie]") == "chart"

    def test_table_with_pipe_rows(self, tool: SlidesTool) -> None:
        content = "| Name | Value |\n| --- | --- |\n| A | 1 |"
        assert tool._detect_layout(content) == "table"

    def test_image_markdown_syntax(self, tool: SlidesTool) -> None:
        content = "![logo](https://example.com/logo.png)"
        assert tool._detect_layout(content) == "image"

    def test_two_column_triple_pipe(self, tool: SlidesTool) -> None:
        assert tool._detect_layout("Left content ||| Right content") == "two-column"

    def test_two_column_explicit_marker(self, tool: SlidesTool) -> None:
        assert tool._detect_layout("[two-column] split here") == "two-column"

    def test_two_column_marker_case_insensitive(self, tool: SlidesTool) -> None:
        assert tool._detect_layout("[TWO-COLUMN] split here") == "two-column"

    def test_short_content_returns_title(self, tool: SlidesTool) -> None:
        # Less than 50 characters with no special markers
        assert tool._detect_layout("Short text") == "title"

    def test_exactly_50_chars_boundary(self, tool: SlidesTool) -> None:
        # 49 chars — should be "title"
        content = "x" * 49
        assert tool._detect_layout(content) == "title"

    def test_50_chars_returns_title_content(self, tool: SlidesTool) -> None:
        # Exactly 50 chars triggers title-content (len < 50 is False)
        content = "x" * 50
        assert tool._detect_layout(content) == "title-content"

    def test_long_text_returns_title_content(self, tool: SlidesTool) -> None:
        content = "This is a much longer paragraph of content " * 3
        assert tool._detect_layout(content) == "title-content"

    def test_empty_string_returns_title(self, tool: SlidesTool) -> None:
        assert tool._detect_layout("") == "title"

    def test_chart_takes_priority_over_length(self, tool: SlidesTool) -> None:
        # Even short content with chart marker → chart
        assert tool._detect_layout("[chart: x]") == "chart"


# --------------------------------------------------------------------------
# --- SlidesTool._extract_table() ---
# --------------------------------------------------------------------------


class TestExtractTable:
    @pytest.fixture()
    def tool(self) -> SlidesTool:
        return SlidesTool()

    def test_no_table_returns_none(self, tool: SlidesTool) -> None:
        result = tool._extract_table("Just some plain text\nwithout any table markers")
        assert result is None

    def test_empty_content_returns_none(self, tool: SlidesTool) -> None:
        result = tool._extract_table("")
        assert result is None

    def test_single_row_table(self, tool: SlidesTool) -> None:
        content = "| Col1 | Col2 |"
        result = tool._extract_table(content)
        assert result is not None
        assert result[0] == ["Col1", "Col2"]

    def test_cells_are_stripped(self, tool: SlidesTool) -> None:
        content = "|  Name  |  Value  |\n|---|---|\n|  Alice  |  100  |"
        result = tool._extract_table(content)
        assert result is not None
        assert result[0] == ["Name", "Value"]

    def test_table_stops_at_non_pipe_line(self, tool: SlidesTool) -> None:
        content = "| A | B |\n| 1 | 2 |\nThis is not a table row\n| 3 | 4 |"
        result = tool._extract_table(content)
        assert result is not None
        # Should stop before the non-pipe line; "3 | 4" line is after break
        rows_as_flat = [cell for row in result for cell in row]
        assert "3" not in rows_as_flat

    def test_three_column_table_is_parseable(self, tool: SlidesTool) -> None:
        content = "| A | B | C |\n|---|---|---|\n| 1 | 2 | 3 |"
        result = tool._extract_table(content)
        assert result is not None


# --------------------------------------------------------------------------
# --- SlidesTool._generate_speaker_notes() ---
# --------------------------------------------------------------------------


class TestGenerateSpeakerNotes:
    @pytest.fixture()
    def tool(self) -> SlidesTool:
        return SlidesTool()

    def test_with_bullet_points_returns_key_points_header(self, tool: SlidesTool) -> None:
        content = "- First point\n- Second point\n- Third point"
        notes = tool._generate_speaker_notes("My Slide", content)
        assert "Key points to cover" in notes
        assert "My Slide" in notes

    def test_bullet_points_included(self, tool: SlidesTool) -> None:
        content = "- Alpha\n- Beta\n- Gamma"
        notes = tool._generate_speaker_notes("T", content)
        assert "Alpha" in notes
        assert "Beta" in notes
        assert "Gamma" in notes

    def test_max_three_bullet_points(self, tool: SlidesTool) -> None:
        content = "- One\n- Two\n- Three\n- Four\n- Five"
        notes = tool._generate_speaker_notes("T", content)
        # Only first 3 extracted
        assert "Four" not in notes
        assert "Five" not in notes

    def test_no_bullets_returns_discuss_prefix(self, tool: SlidesTool) -> None:
        notes = tool._generate_speaker_notes("Market Analysis", "No bullets here")
        assert notes == "Discuss: Market Analysis"

    def test_empty_content_returns_discuss_prefix(self, tool: SlidesTool) -> None:
        notes = tool._generate_speaker_notes("Title", "")
        assert notes == "Discuss: Title"

    def test_asterisk_bullets_also_detected(self, tool: SlidesTool) -> None:
        content = "* First\n* Second"
        notes = tool._generate_speaker_notes("T", content)
        assert "Key points to cover" in notes
        assert "First" in notes

    def test_single_bullet_included(self, tool: SlidesTool) -> None:
        content = "- Only one point"
        notes = tool._generate_speaker_notes("Single", content)
        assert "Only one point" in notes

    def test_title_in_notes_when_bullets_present(self, tool: SlidesTool) -> None:
        content = "- Point A"
        notes = tool._generate_speaker_notes("Revenue Growth", content)
        assert "Revenue Growth" in notes


# --------------------------------------------------------------------------
# --- SlidesTool._markdown_to_html() ---
# --------------------------------------------------------------------------


class TestMarkdownToHtml:
    @pytest.fixture()
    def tool(self) -> SlidesTool:
        return SlidesTool()

    def test_h3_header_conversion(self, tool: SlidesTool) -> None:
        html = tool._markdown_to_html("### My Section")
        assert "<h4>My Section</h4>" in html

    def test_bold_conversion(self, tool: SlidesTool) -> None:
        html = tool._markdown_to_html("This is **bold** text")
        assert "<strong>bold</strong>" in html

    def test_italic_conversion(self, tool: SlidesTool) -> None:
        html = tool._markdown_to_html("This is *italic* text")
        assert "<em>italic</em>" in html

    def test_unordered_list_dash(self, tool: SlidesTool) -> None:
        html = tool._markdown_to_html("- Item one\n- Item two")
        assert "<ul>" in html
        assert "<li>Item one</li>" in html
        assert "<li>Item two</li>" in html
        assert "</ul>" in html

    def test_unordered_list_asterisk(self, tool: SlidesTool) -> None:
        html = tool._markdown_to_html("* First\n* Second")
        assert "<ul>" in html
        assert "<li>First</li>" in html

    def test_list_closes_properly(self, tool: SlidesTool) -> None:
        html = tool._markdown_to_html("- Item\nParagraph after")
        assert "</ul>" in html
        assert "<p>Paragraph after</p>" in html

    def test_plain_paragraph_wrapped(self, tool: SlidesTool) -> None:
        html = tool._markdown_to_html("Just a paragraph")
        assert "<p>Just a paragraph</p>" in html

    def test_empty_lines_not_wrapped(self, tool: SlidesTool) -> None:
        html = tool._markdown_to_html("Line one\n\nLine two")
        assert "<p>Line one</p>" in html
        assert "<p>Line two</p>" in html
        # Empty line should not produce a <p></p>
        assert "<p></p>" not in html

    def test_bold_and_italic_combined(self, tool: SlidesTool) -> None:
        html = tool._markdown_to_html("**bold** and *italic*")
        assert "<strong>bold</strong>" in html
        assert "<em>italic</em>" in html

    def test_multiple_h3_headers(self, tool: SlidesTool) -> None:
        html = tool._markdown_to_html("### First\n### Second")
        assert "<h4>First</h4>" in html
        assert "<h4>Second</h4>" in html

    def test_list_at_end_of_content(self, tool: SlidesTool) -> None:
        html = tool._markdown_to_html("Intro\n- A\n- B")
        assert "</ul>" in html

    def test_empty_string_returns_empty(self, tool: SlidesTool) -> None:
        html = tool._markdown_to_html("")
        assert html.strip() == ""


# --------------------------------------------------------------------------
# --- SlidesTool._parse_markdown_to_slides() ---
# --------------------------------------------------------------------------


class TestParseMarkdownToSlides:
    @pytest.fixture()
    def tool(self) -> SlidesTool:
        return SlidesTool()

    def test_simple_two_slides(self, tool: SlidesTool) -> None:
        content = "## Introduction\nHello world\n## Conclusion\nThat is all"
        slides = tool._parse_markdown_to_slides(content, target_count=10, include_notes=False)
        assert len(slides) == 2
        assert slides[0].title == "Introduction"
        assert slides[1].title == "Conclusion"

    def test_section_separator_splits(self, tool: SlidesTool) -> None:
        content = "First slide content\n---\nSecond slide content"
        slides = tool._parse_markdown_to_slides(content, target_count=10, include_notes=False)
        assert len(slides) == 2

    def test_no_h2_uses_numbered_title(self, tool: SlidesTool) -> None:
        content = "Just some content without a header"
        slides = tool._parse_markdown_to_slides(content, target_count=10, include_notes=False)
        assert len(slides) == 1
        assert "Slide" in slides[0].title

    def test_slides_truncated_to_target(self, tool: SlidesTool) -> None:
        sections = "\n".join(f"## Slide {i}\nContent {i}" for i in range(10))
        slides = tool._parse_markdown_to_slides(sections, target_count=5, include_notes=False)
        assert len(slides) == 5

    def test_fewer_slides_than_target_ok(self, tool: SlidesTool) -> None:
        content = "## Only One\nContent"
        slides = tool._parse_markdown_to_slides(content, target_count=10, include_notes=False)
        assert len(slides) == 1

    def test_index_assigned_sequentially(self, tool: SlidesTool) -> None:
        content = "## A\ncontent\n## B\ncontent\n## C\ncontent"
        slides = tool._parse_markdown_to_slides(content, target_count=10, include_notes=False)
        for idx, slide in enumerate(slides):
            assert slide.index == idx

    def test_include_notes_true_generates_notes(self, tool: SlidesTool) -> None:
        content = "## Tips\n- First tip\n- Second tip"
        slides = tool._parse_markdown_to_slides(content, target_count=10, include_notes=True)
        assert slides[0].speaker_notes != ""

    def test_include_notes_false_empty_notes(self, tool: SlidesTool) -> None:
        content = "## Tips\n- First tip\n- Second tip"
        slides = tool._parse_markdown_to_slides(content, target_count=10, include_notes=False)
        assert slides[0].speaker_notes == ""

    def test_table_content_extracted(self, tool: SlidesTool) -> None:
        content = "## Data\n| A | B |\n|---|---|\n| 1 | 2 |"
        slides = tool._parse_markdown_to_slides(content, target_count=10, include_notes=False)
        assert slides[0].table_data is not None

    def test_layout_detected_for_table_slide(self, tool: SlidesTool) -> None:
        content = "## Data\n| A | B |\n|---|---|\n| 1 | 2 |"
        slides = tool._parse_markdown_to_slides(content, target_count=10, include_notes=False)
        assert slides[0].layout == "table"

    def test_body_content_assigned(self, tool: SlidesTool) -> None:
        content = "## Slide Title\nThis is the body text"
        slides = tool._parse_markdown_to_slides(content, target_count=10, include_notes=False)
        assert "This is the body text" in slides[0].content

    def test_empty_content_returns_no_slides(self, tool: SlidesTool) -> None:
        slides = tool._parse_markdown_to_slides("", target_count=10, include_notes=False)
        assert slides == []

    def test_title_stripped(self, tool: SlidesTool) -> None:
        content = "##   Padded Title   \nContent"
        slides = tool._parse_markdown_to_slides(content, target_count=10, include_notes=False)
        assert slides[0].title == "Padded Title"


# --------------------------------------------------------------------------
# --- SlidesTool._format_creation_result() ---
# --------------------------------------------------------------------------


class TestFormatCreationResult:
    @pytest.fixture()
    def tool(self) -> SlidesTool:
        return SlidesTool()

    def _make_presentation(self, titles: list[str]) -> Presentation:
        slides = [Slide(index=i, title=t, content="body") for i, t in enumerate(titles)]
        return Presentation(
            title="Test Deck",
            theme=SlideTheme.CORPORATE,
            mode=SlideMode.HTML,
            slides=slides,
        )

    def test_contains_presentation_title(self, tool: SlidesTool) -> None:
        p = self._make_presentation(["Intro"])
        result = tool._format_creation_result("abc-123", p)
        assert "Test Deck" in result

    def test_contains_presentation_id(self, tool: SlidesTool) -> None:
        p = self._make_presentation(["Intro"])
        result = tool._format_creation_result("abc-123", p)
        assert "abc-123" in result

    def test_contains_slide_count(self, tool: SlidesTool) -> None:
        p = self._make_presentation(["A", "B", "C"])
        result = tool._format_creation_result("id-001", p)
        assert "3" in result

    def test_contains_mode(self, tool: SlidesTool) -> None:
        p = self._make_presentation(["Intro"])
        result = tool._format_creation_result("id-001", p)
        assert "html" in result

    def test_contains_theme(self, tool: SlidesTool) -> None:
        p = self._make_presentation(["Intro"])
        result = tool._format_creation_result("id-001", p)
        assert "corporate" in result

    def test_slide_titles_in_overview(self, tool: SlidesTool) -> None:
        p = self._make_presentation(["Introduction", "Conclusion"])
        result = tool._format_creation_result("id-001", p)
        assert "Introduction" in result
        assert "Conclusion" in result

    def test_export_hint_present(self, tool: SlidesTool) -> None:
        p = self._make_presentation(["Intro"])
        result = tool._format_creation_result("id-001", p)
        assert "slides_export" in result

    def test_slide_overview_section_header(self, tool: SlidesTool) -> None:
        p = self._make_presentation(["Intro"])
        result = tool._format_creation_result("id-001", p)
        assert "Slide Overview" in result

    def test_slide_layout_included(self, tool: SlidesTool) -> None:
        slides = [Slide(index=0, title="Data", content="c", layout="table")]
        p = Presentation(title="T", slides=slides)
        result = tool._format_creation_result("id-001", p)
        assert "table" in result

    def test_empty_slides_result_still_valid(self, tool: SlidesTool) -> None:
        p = Presentation(title="Empty Deck")
        result = tool._format_creation_result("id-001", p)
        assert "Empty Deck" in result
        assert "0" in result


# --------------------------------------------------------------------------
# --- SlidesTool._generate_slide_descriptions() ---
# --------------------------------------------------------------------------


class TestGenerateSlideDescriptions:
    @pytest.fixture()
    def tool(self) -> SlidesTool:
        return SlidesTool()

    def _make_presentation(self) -> Presentation:
        slides = [
            Slide(index=0, title="Intro", content="Intro content here for AI", layout="title-content"),
            Slide(index=1, title="Details", content="Detail content", layout="title-content"),
        ]
        return Presentation(
            title="Annual Report",
            subtitle="2026",
            theme=SlideTheme.CORPORATE,
            slides=slides,
        )

    def test_includes_title_slide_first(self, tool: SlidesTool) -> None:
        p = self._make_presentation()
        descs = tool._generate_slide_descriptions(p)
        assert descs[0]["type"] == "title"

    def test_total_count_title_plus_slides(self, tool: SlidesTool) -> None:
        p = self._make_presentation()
        descs = tool._generate_slide_descriptions(p)
        # 1 title slide + 2 content slides
        assert len(descs) == 3

    def test_title_slide_has_presentation_title(self, tool: SlidesTool) -> None:
        p = self._make_presentation()
        descs = tool._generate_slide_descriptions(p)
        assert descs[0]["title"] == "Annual Report"

    def test_title_slide_has_subtitle(self, tool: SlidesTool) -> None:
        p = self._make_presentation()
        descs = tool._generate_slide_descriptions(p)
        assert descs[0]["subtitle"] == "2026"

    def test_title_slide_index_is_zero(self, tool: SlidesTool) -> None:
        p = self._make_presentation()
        descs = tool._generate_slide_descriptions(p)
        assert descs[0]["slide_index"] == 0

    def test_content_slide_index_offset(self, tool: SlidesTool) -> None:
        p = self._make_presentation()
        descs = tool._generate_slide_descriptions(p)
        # First content slide: slide.index=0 → slide_index=1
        assert descs[1]["slide_index"] == 1
        assert descs[2]["slide_index"] == 2

    def test_content_slide_has_title(self, tool: SlidesTool) -> None:
        p = self._make_presentation()
        descs = tool._generate_slide_descriptions(p)
        assert descs[1]["title"] == "Intro"

    def test_description_contains_theme(self, tool: SlidesTool) -> None:
        p = self._make_presentation()
        descs = tool._generate_slide_descriptions(p)
        assert "corporate" in descs[0]["description"]

    def test_description_contains_accent_color(self, tool: SlidesTool) -> None:
        p = self._make_presentation()
        descs = tool._generate_slide_descriptions(p)
        corporate_accent = THEME_CONFIGS[SlideTheme.CORPORATE]["accent_color"]
        assert corporate_accent in descs[0]["description"]

    def test_content_summary_truncated_at_200(self, tool: SlidesTool) -> None:
        long_content = "x" * 300
        slides = [Slide(index=0, title="Big Slide", content=long_content, layout="title-content")]
        p = Presentation(title="T", theme=SlideTheme.MINIMAL, slides=slides)
        descs = tool._generate_slide_descriptions(p)
        # descs[0] is title slide, descs[1] is content
        assert len(descs[1]["content_summary"]) == 200

    def test_short_content_not_truncated(self, tool: SlidesTool) -> None:
        short_content = "Short"
        slides = [Slide(index=0, title="S", content=short_content, layout="title-content")]
        p = Presentation(title="T", theme=SlideTheme.MINIMAL, slides=slides)
        descs = tool._generate_slide_descriptions(p)
        assert descs[1]["content_summary"] == "Short"

    def test_empty_slides_only_title_description(self, tool: SlidesTool) -> None:
        p = Presentation(title="Empty", theme=SlideTheme.CORPORATE)
        descs = tool._generate_slide_descriptions(p)
        assert len(descs) == 1
        assert descs[0]["type"] == "title"

    def test_content_slide_type_matches_layout(self, tool: SlidesTool) -> None:
        slides = [Slide(index=0, title="T", content="c", layout="table")]
        p = Presentation(title="T", theme=SlideTheme.CORPORATE, slides=slides)
        descs = tool._generate_slide_descriptions(p)
        assert descs[1]["type"] == "table"
