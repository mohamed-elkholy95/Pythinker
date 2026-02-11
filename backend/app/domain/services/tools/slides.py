"""Presentation/Slides Generator Tool.

This tool generates professional presentations from Markdown content.
Inspired by Manus's two-mode slide generation:
1. HTML mode - reveal.js based, editable, charts via Chart.js
2. Image mode - AI-generated visual slides

Features:
- Markdown to presentation conversion
- Multiple theme support
- Chart and table integration
- Speaker notes
- Export to PDF/PPTX
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, ClassVar

from app.domain.services.tools.base import BaseTool, ToolResult, ToolSchema


class SlideMode(str, Enum):
    """Slide generation mode."""

    HTML = "html"  # reveal.js based
    IMAGE = "image"  # AI-generated images


class SlideTheme(str, Enum):
    """Available presentation themes."""

    # Professional themes
    CORPORATE = "corporate"  # Blue professional
    MINIMAL = "minimal"  # Clean white
    DARK = "dark"  # Dark mode
    ELEGANT = "elegant"  # Black and gold

    # Creative themes
    VIBRANT = "vibrant"  # Colorful
    GRADIENT = "gradient"  # Gradient backgrounds
    MODERN = "modern"  # Contemporary design

    # Specialized themes
    TECH = "tech"  # Technology focused
    ACADEMIC = "academic"  # Academic/research
    STARTUP = "startup"  # Pitch deck style


@dataclass
class Slide:
    """A single slide in the presentation."""

    index: int
    title: str
    content: str
    layout: str = "title-content"  # title, title-content, two-column, image, chart, table
    speaker_notes: str = ""
    background: str | None = None
    chart_data: dict | None = None
    table_data: list[list[str]] | None = None
    image_url: str | None = None


@dataclass
class Presentation:
    """A complete presentation."""

    title: str
    subtitle: str = ""
    author: str = ""
    date: str = ""
    theme: SlideTheme = SlideTheme.CORPORATE
    slides: list[Slide] = field(default_factory=list)
    mode: SlideMode = SlideMode.HTML

    @property
    def slide_count(self) -> int:
        """Get number of slides."""
        return len(self.slides)


THEME_CONFIGS = {
    SlideTheme.CORPORATE: {
        "background": "#ffffff",
        "text_color": "#333333",
        "accent_color": "#1F4E79",
        "heading_font": "Source Serif Pro",
        "body_font": "Source Sans Pro",
        "highlight_color": "#D6E3F0",
    },
    SlideTheme.MINIMAL: {
        "background": "#ffffff",
        "text_color": "#2D2D2D",
        "accent_color": "#2D2D2D",
        "heading_font": "Inter",
        "body_font": "Inter",
        "highlight_color": "#F5F5F5",
    },
    SlideTheme.DARK: {
        "background": "#1a1a2e",
        "text_color": "#eaeaea",
        "accent_color": "#00ADB5",
        "heading_font": "Poppins",
        "body_font": "Poppins",
        "highlight_color": "#16213e",
    },
    SlideTheme.ELEGANT: {
        "background": "#ffffff",
        "text_color": "#2D2D2D",
        "accent_color": "#B8860B",
        "heading_font": "Playfair Display",
        "body_font": "Lato",
        "highlight_color": "#FFF8DC",
    },
    SlideTheme.VIBRANT: {
        "background": "#ffffff",
        "text_color": "#333333",
        "accent_color": "#FF6B6B",
        "heading_font": "Montserrat",
        "body_font": "Open Sans",
        "highlight_color": "#FFE5E5",
    },
    SlideTheme.GRADIENT: {
        "background": "linear-gradient(135deg, #667eea 0%, #764ba2 100%)",
        "text_color": "#ffffff",
        "accent_color": "#FFD93D",
        "heading_font": "Raleway",
        "body_font": "Roboto",
        "highlight_color": "rgba(255,255,255,0.2)",
    },
    SlideTheme.MODERN: {
        "background": "#fafafa",
        "text_color": "#1a1a1a",
        "accent_color": "#6366F1",
        "heading_font": "DM Sans",
        "body_font": "DM Sans",
        "highlight_color": "#EEF2FF",
    },
    SlideTheme.TECH: {
        "background": "#0f0f23",
        "text_color": "#00ff00",
        "accent_color": "#00ff00",
        "heading_font": "JetBrains Mono",
        "body_font": "JetBrains Mono",
        "highlight_color": "#1a1a3e",
    },
    SlideTheme.ACADEMIC: {
        "background": "#ffffff",
        "text_color": "#333333",
        "accent_color": "#800020",
        "heading_font": "Merriweather",
        "body_font": "Source Sans Pro",
        "highlight_color": "#FFF5F5",
    },
    SlideTheme.STARTUP: {
        "background": "#ffffff",
        "text_color": "#1a1a1a",
        "accent_color": "#FF5722",
        "heading_font": "Outfit",
        "body_font": "Inter",
        "highlight_color": "#FFF3E0",
    },
}


class SlidesTool(BaseTool):
    """Tool for generating professional presentations.

    Supports HTML mode (reveal.js) and Image mode for visual slides.
    """

    name = "slides"
    description = "Generate professional presentations from content"

    tools: ClassVar[list[ToolSchema]] = [
        ToolSchema(
            name="slides_create",
            description=(
                "Generate a presentation from markdown content or outline. "
                "Creates professional slides with charts, tables, and speaker notes. "
                "Use HTML mode for editable presentations, Image mode for visual slides."
            ),
            parameters={
                "content": {
                    "type": "string",
                    "description": (
                        "Markdown content for the presentation. Use ## for slide titles, "
                        "### for sections, and standard markdown for content."
                    ),
                },
                "title": {
                    "type": "string",
                    "description": "Presentation title",
                },
                "slide_count": {
                    "type": "integer",
                    "description": "Target number of slides (will adjust content accordingly)",
                    "default": 10,
                },
                "mode": {
                    "type": "string",
                    "enum": ["html", "image"],
                    "description": "Generation mode: 'html' for reveal.js, 'image' for visual slides",
                    "default": "html",
                },
                "theme": {
                    "type": "string",
                    "enum": [t.value for t in SlideTheme],
                    "description": "Visual theme for the presentation",
                    "default": "corporate",
                },
                "subtitle": {
                    "type": "string",
                    "description": "Presentation subtitle",
                },
                "author": {
                    "type": "string",
                    "description": "Author name",
                },
                "include_speaker_notes": {
                    "type": "boolean",
                    "description": "Whether to generate speaker notes",
                    "default": True,
                },
            },
            required=["content", "title"],
        ),
        ToolSchema(
            name="slides_add_chart",
            description=("Add a chart to an existing presentation. Supports bar, line, pie, and doughnut charts."),
            parameters={
                "presentation_id": {
                    "type": "string",
                    "description": "ID of the presentation to add chart to",
                },
                "slide_index": {
                    "type": "integer",
                    "description": "Index of slide to add chart to (0-based)",
                },
                "chart_type": {
                    "type": "string",
                    "enum": ["bar", "line", "pie", "doughnut"],
                    "description": "Type of chart to create",
                },
                "data": {
                    "type": "object",
                    "description": "Chart data with 'labels' and 'values' arrays",
                },
                "chart_title": {
                    "type": "string",
                    "description": "Title for the chart",
                },
            },
            required=["presentation_id", "slide_index", "chart_type", "data"],
        ),
        ToolSchema(
            name="slides_export",
            description="Export a presentation to a file format.",
            parameters={
                "presentation_id": {
                    "type": "string",
                    "description": "ID of the presentation to export",
                },
                "format": {
                    "type": "string",
                    "enum": ["html", "pdf"],
                    "description": "Export format",
                    "default": "html",
                },
                "output_path": {
                    "type": "string",
                    "description": "Path to save the exported file",
                },
            },
            required=["presentation_id", "output_path"],
        ),
    ]

    def __init__(self) -> None:
        """Initialize the slides tool."""
        super().__init__()
        self._presentations: dict[str, Presentation] = {}

    async def execute(self, tool_name: str, tool_input: dict[str, Any]) -> ToolResult:
        """Execute a slides tool."""
        if tool_name == "slides_create":
            return await self._create_presentation(
                content=tool_input["content"],
                title=tool_input["title"],
                slide_count=tool_input.get("slide_count", 10),
                mode=tool_input.get("mode", "html"),
                theme=tool_input.get("theme", "corporate"),
                subtitle=tool_input.get("subtitle", ""),
                author=tool_input.get("author", ""),
                include_speaker_notes=tool_input.get("include_speaker_notes", True),
            )
        if tool_name == "slides_add_chart":
            return await self._add_chart(
                presentation_id=tool_input["presentation_id"],
                slide_index=tool_input["slide_index"],
                chart_type=tool_input["chart_type"],
                data=tool_input["data"],
                chart_title=tool_input.get("chart_title", ""),
            )
        if tool_name == "slides_export":
            return await self._export_presentation(
                presentation_id=tool_input["presentation_id"],
                export_format=tool_input.get("format", "html"),
                output_path=tool_input["output_path"],
            )
        return ToolResult(
            success=False,
            result=f"Unknown tool: {tool_name}",
        )

    async def _create_presentation(
        self,
        content: str,
        title: str,
        slide_count: int,
        mode: str,
        theme: str,
        subtitle: str,
        author: str,
        include_speaker_notes: bool,
    ) -> ToolResult:
        """Create a presentation from markdown content."""
        try:
            # Parse mode and theme
            slide_mode = SlideMode(mode)
            slide_theme = SlideTheme(theme)

            # Parse markdown into slides
            slides = self._parse_markdown_to_slides(content, slide_count, include_speaker_notes)

            # Create presentation
            import uuid

            presentation_id = str(uuid.uuid4())

            presentation = Presentation(
                title=title,
                subtitle=subtitle,
                author=author,
                theme=slide_theme,
                slides=slides,
                mode=slide_mode,
            )

            # Store presentation
            self._presentations[presentation_id] = presentation

            # Generate output based on mode
            if slide_mode == SlideMode.HTML:
                html_content = self._generate_revealjs_html(presentation)
                return ToolResult(
                    success=True,
                    result=self._format_creation_result(presentation_id, presentation),
                    data={
                        "presentation_id": presentation_id,
                        "slide_count": presentation.slide_count,
                        "mode": mode,
                        "theme": theme,
                        "html_content": html_content,
                    },
                )
            # Image mode - generate slide descriptions for AI image generation
            slide_descriptions = self._generate_slide_descriptions(presentation)
            return ToolResult(
                success=True,
                result=self._format_creation_result(presentation_id, presentation),
                data={
                    "presentation_id": presentation_id,
                    "slide_count": presentation.slide_count,
                    "mode": mode,
                    "theme": theme,
                    "slide_descriptions": slide_descriptions,
                },
            )

        except Exception as e:
            return ToolResult(
                success=False,
                result=f"Failed to create presentation: {e!s}",
            )

    def _parse_markdown_to_slides(self, content: str, target_count: int, include_notes: bool) -> list[Slide]:
        """Parse markdown content into slides."""
        slides: list[Slide] = []

        # Split by slide markers (## headers or ---)
        sections = re.split(r"\n(?=##\s)|(?:\n---\n)", content)

        for i, section in enumerate(sections):
            section = section.strip()
            if not section:
                continue

            # Extract title
            title_match = re.match(r"^##\s+(.+?)(?:\n|$)", section)
            if title_match:
                title = title_match.group(1).strip()
                body = section[title_match.end() :].strip()
            else:
                title = f"Slide {i + 1}"
                body = section

            # Detect layout based on content
            layout = self._detect_layout(body)

            # Extract tables
            table_data = self._extract_table(body)

            # Generate speaker notes if requested
            speaker_notes = ""
            if include_notes:
                speaker_notes = self._generate_speaker_notes(title, body)

            slides.append(
                Slide(
                    index=i,
                    title=title,
                    content=body,
                    layout=layout,
                    speaker_notes=speaker_notes,
                    table_data=table_data,
                )
            )

        # Adjust to target count if needed
        if len(slides) > target_count:
            # Merge some slides
            slides = slides[:target_count]
        elif len(slides) < target_count and len(slides) > 0:
            # We'll leave as is - don't artificially create slides
            pass

        return slides

    def _detect_layout(self, content: str) -> str:
        """Detect the appropriate layout for slide content."""
        # Check for chart markers
        if re.search(r"\[chart:|\[graph:", content, re.IGNORECASE):
            return "chart"

        # Check for table
        if "|" in content and re.search(r"^\|.*\|$", content, re.MULTILINE):
            return "table"

        # Check for image
        if re.search(r"!\[.*\]\(.*\)", content):
            return "image"

        # Check for two-column layout marker
        if "|||" in content or "[two-column]" in content.lower():
            return "two-column"

        # Check if it's just a title
        if len(content) < 50:
            return "title"

        # Default to title-content
        return "title-content"

    def _extract_table(self, content: str) -> list[list[str]] | None:
        """Extract table data from markdown."""
        lines = content.split("\n")
        table_lines = []
        in_table = False

        for line in lines:
            if "|" in line:
                in_table = True
                # Skip separator lines
                if not re.match(r"^\|[\s\-:]+\|$", line):
                    cells = [c.strip() for c in line.split("|")[1:-1]]
                    if cells:
                        table_lines.append(cells)
            elif in_table:
                break

        return table_lines if table_lines else None

    def _generate_speaker_notes(self, title: str, content: str) -> str:
        """Generate speaker notes for a slide."""
        # Simple note generation - in production, this would use LLM
        bullet_points = re.findall(r"[-*]\s+(.+?)(?:\n|$)", content)
        if bullet_points:
            notes = f"Key points to cover for '{title}':\n"
            for point in bullet_points[:3]:
                notes += f"- {point}\n"
            return notes
        return f"Discuss: {title}"

    def _generate_revealjs_html(self, presentation: Presentation) -> str:
        """Generate reveal.js HTML for the presentation."""
        theme_config = THEME_CONFIGS.get(presentation.theme, THEME_CONFIGS[SlideTheme.CORPORATE])

        slides_html = []

        # Title slide
        title_slide = f"""
        <section>
            <h1>{presentation.title}</h1>
            {"<h3>" + presentation.subtitle + "</h3>" if presentation.subtitle else ""}
            {"<p><small>" + presentation.author + "</small></p>" if presentation.author else ""}
        </section>
        """
        slides_html.append(title_slide)

        # Content slides
        for slide in presentation.slides:
            slide_html = self._generate_slide_html(slide, theme_config)
            slides_html.append(slide_html)

        # Full HTML template
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{presentation.title}</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/reveal.js@4.5.0/dist/reveal.css">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/reveal.js@4.5.0/dist/theme/white.css">
    <style>
        :root {{
            --background-color: {theme_config["background"]};
            --text-color: {theme_config["text_color"]};
            --accent-color: {theme_config["accent_color"]};
            --heading-font: {theme_config["heading_font"]}, sans-serif;
            --body-font: {theme_config["body_font"]}, sans-serif;
        }}
        .reveal {{
            font-family: var(--body-font);
            color: var(--text-color);
        }}
        .reveal h1, .reveal h2, .reveal h3 {{
            font-family: var(--heading-font);
            color: var(--accent-color);
        }}
        .reveal .slides section {{
            background-color: var(--background-color);
        }}
        .reveal ul {{
            text-align: left;
        }}
        .reveal table {{
            margin: 0 auto;
            border-collapse: collapse;
        }}
        .reveal table th, .reveal table td {{
            border: 1px solid var(--accent-color);
            padding: 8px 16px;
        }}
        .reveal table th {{
            background-color: var(--accent-color);
            color: white;
        }}
        .chart-container {{
            width: 80%;
            margin: 0 auto;
        }}
    </style>
</head>
<body>
    <div class="reveal">
        <div class="slides">
            {"".join(slides_html)}
        </div>
    </div>
    <script src="https://cdn.jsdelivr.net/npm/reveal.js@4.5.0/dist/reveal.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script>
        Reveal.initialize({{
            hash: true,
            slideNumber: true,
            showNotes: true,
        }});
    </script>
</body>
</html>"""

    def _generate_slide_html(self, slide: Slide, theme_config: dict) -> str:
        """Generate HTML for a single slide."""
        notes_html = f'<aside class="notes">{slide.speaker_notes}</aside>' if slide.speaker_notes else ""

        if slide.layout == "title":
            return f"""
            <section>
                <h2>{slide.title}</h2>
                {notes_html}
            </section>
            """

        if slide.layout == "table" and slide.table_data:
            table_html = "<table><thead><tr>"
            table_html += "".join(f"<th>{h}</th>" for h in slide.table_data[0])
            table_html += "</tr></thead><tbody>"
            for row in slide.table_data[1:]:
                table_html += "<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>"
            table_html += "</tbody></table>"

            return f"""
            <section>
                <h2>{slide.title}</h2>
                {table_html}
                {notes_html}
            </section>
            """

        if slide.layout == "chart" and slide.chart_data:
            return f"""
            <section>
                <h2>{slide.title}</h2>
                <div class="chart-container">
                    <canvas id="chart-{slide.index}"></canvas>
                </div>
                {notes_html}
            </section>
            """

        # Default title-content layout
        content_html = self._markdown_to_html(slide.content)
        return f"""
            <section>
                <h2>{slide.title}</h2>
                {content_html}
                {notes_html}
            </section>
            """

    def _markdown_to_html(self, content: str) -> str:
        """Convert markdown to HTML."""
        # Basic markdown conversion
        html = content

        # Headers
        html = re.sub(r"^### (.+)$", r"<h4>\1</h4>", html, flags=re.MULTILINE)

        # Bold
        html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)

        # Italic
        html = re.sub(r"\*(.+?)\*", r"<em>\1</em>", html)

        # Lists
        lines = html.split("\n")
        in_list = False
        result_lines = []
        for line in lines:
            if re.match(r"^[-*]\s+", line):
                if not in_list:
                    result_lines.append("<ul>")
                    in_list = True
                item = re.sub(r"^[-*]\s+", "", line)
                result_lines.append(f"<li>{item}</li>")
            else:
                if in_list:
                    result_lines.append("</ul>")
                    in_list = False
                if line.strip():
                    result_lines.append(f"<p>{line}</p>")
        if in_list:
            result_lines.append("</ul>")

        return "\n".join(result_lines)

    def _generate_slide_descriptions(self, presentation: Presentation) -> list[dict]:
        """Generate descriptions for image-mode slides."""
        descriptions = []
        theme_config = THEME_CONFIGS.get(presentation.theme, THEME_CONFIGS[SlideTheme.CORPORATE])

        # Title slide
        descriptions.append(
            {
                "slide_index": 0,
                "type": "title",
                "title": presentation.title,
                "subtitle": presentation.subtitle,
                "description": (
                    f"Create a professional title slide for '{presentation.title}'. "
                    f"Use {presentation.theme.value} theme with {theme_config['accent_color']} accent. "
                    f"Modern, clean design with centered text."
                ),
            }
        )

        # Content slides
        descriptions.extend(
            {
                "slide_index": slide.index + 1,
                "type": slide.layout,
                "title": slide.title,
                "content_summary": slide.content[:200] if len(slide.content) > 200 else slide.content,
                "description": (
                    f"Create a {slide.layout} slide titled '{slide.title}'. "
                    f"Theme: {presentation.theme.value}. "
                    f"Key content: {slide.content[:100]}..."
                ),
            }
            for slide in presentation.slides
        )

        return descriptions

    async def _add_chart(
        self,
        presentation_id: str,
        slide_index: int,
        chart_type: str,
        data: dict,
        chart_title: str,
    ) -> ToolResult:
        """Add a chart to an existing slide."""
        if presentation_id not in self._presentations:
            return ToolResult(
                success=False,
                result=f"Presentation not found: {presentation_id}",
            )

        presentation = self._presentations[presentation_id]
        if slide_index < 0 or slide_index >= len(presentation.slides):
            return ToolResult(
                success=False,
                result=f"Invalid slide index: {slide_index}",
            )

        # Update slide with chart data
        slide = presentation.slides[slide_index]
        slide.layout = "chart"
        slide.chart_data = {
            "type": chart_type,
            "title": chart_title,
            "labels": data.get("labels", []),
            "values": data.get("values", []),
        }

        return ToolResult(
            success=True,
            result=f"Added {chart_type} chart to slide {slide_index} in presentation {presentation_id}",
            data={
                "presentation_id": presentation_id,
                "slide_index": slide_index,
                "chart_type": chart_type,
            },
        )

    async def _export_presentation(
        self,
        presentation_id: str,
        export_format: str,
        output_path: str,
    ) -> ToolResult:
        """Export a presentation to a file."""
        if presentation_id not in self._presentations:
            return ToolResult(
                success=False,
                result=f"Presentation not found: {presentation_id}",
            )

        presentation = self._presentations[presentation_id]

        try:
            if export_format == "html":
                html_content = self._generate_revealjs_html(presentation)
                with open(output_path, "w", encoding="utf-8") as f:  # noqa: ASYNC230
                    f.write(html_content)
            else:
                return ToolResult(
                    success=False,
                    result=f"Export format '{export_format}' not yet supported",
                )

            return ToolResult(
                success=True,
                result=f"Exported presentation to {output_path}",
                data={
                    "presentation_id": presentation_id,
                    "format": export_format,
                    "output_path": output_path,
                },
            )

        except Exception as e:
            return ToolResult(
                success=False,
                result=f"Failed to export presentation: {e!s}",
            )

    def _format_creation_result(self, presentation_id: str, presentation: Presentation) -> str:
        """Format the creation result for display."""
        parts = [
            f"# Presentation Created: {presentation.title}\n",
            f"**ID:** {presentation_id}",
            f"**Slides:** {presentation.slide_count}",
            f"**Mode:** {presentation.mode.value}",
            f"**Theme:** {presentation.theme.value}",
            "\n## Slide Overview\n",
        ]

        for i, slide in enumerate(presentation.slides):
            parts.append(f"{i + 1}. **{slide.title}** ({slide.layout})")

        parts.append("\n\nUse `slides_export` to save the presentation to a file.")

        return "\n".join(parts)
