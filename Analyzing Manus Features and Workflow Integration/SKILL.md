---
name: excel-generator
description: Professional Excel spreadsheet creation with a focus on aesthetics and data analysis. Use when creating spreadsheets for organizing, analyzing, and presenting structured data in a clear and professional format.
---

# Excel Generator Skill

## Goal

Make the user able to use the Excel immediately and gain insights upon opening.

## Core Principle

Enrich visuals as much as possible, while ensuring content clarity and not adding cognitive burden. Every visual element should be meaningful and purposeful—serving the content, not decorating it.

---

## Part 1: User Needs & Feature Matching

Before creating any Excel, think through:
1. **What does the user need?** — Not "an Excel file", but what problem are they solving?
2. **What can I provide?** — Which features will help them?
3. **How to match?** — Select the right combination for this specific scenario.

### Feature ↔ User Value Pairs

#### Help Users「Understand Data」

| Feature | User Value | When to Use |
|---------|-----------|-------------|
| Bar/Column Chart | See comparisons at a glance | Comparing values across categories |
| Line Chart | See trends at a glance | Time series data |
| Pie Chart | See proportions at a glance | Part-to-whole (≤6 categories) |
| Data Bars | Compare magnitude without leaving the cell | Numeric columns needing quick comparison |
| Color Scale | Heatmap effect, patterns pop out | Matrices, ranges, distributions |
| Sparklines | See trend within a single cell | Summary rows with historical context |

#### Help Users「Find What Matters」

| Feature | User Value | When to Use |
|---------|-----------|-------------|
| Pre-sorting | Most important data comes first | Rankings, Top N, priorities |
| Conditional Highlighting | Key data stands out automatically | Outliers, thresholds, Top/Bottom N |
| Icon Sets | Status visible at a glance | KPI status, categorical states (use sparingly) |
| Bold/Color Emphasis | Visual distinction between primary and secondary | Summary rows, key metrics |
| KEY INSIGHTS Section | Conclusions delivered directly | Analytical reports |

#### Help Users「Save Time」

| Feature | User Value | When to Use |
|---------|-----------|-------------|
| Overview Sheet | Summary on first page, no hunting | All multi-sheet files |
| Pre-calculated Summaries | Results ready, no manual calculation | Data requiring statistics |
| Consistent Number Formats | No format adjustments needed | All numeric data |
| Freeze Panes | Headers visible while scrolling | Tables with >10 rows |
| Sheet Index with Links | Quick navigation, no guessing | Files with >3 sheets |

#### Help Users「Use Directly」

| Feature | User Value | When to Use |
|---------|-----------|-------------|
| Filters | Users can explore data themselves | Exploratory analysis needs |
| Hyperlinks | Click to navigate, no manual switching | Cross-sheet references, external sources |
| Print-friendly Layout | Ready to print or export to PDF | Reports for sharing |
| Formulas (not hardcoded) | Change parameters, results update | Models, forecasts, adjustable scenarios |
| Data Validation Dropdowns | Prevent input errors | Templates requiring user input |

#### Help Users「Trust the Data」

| Feature | User Value | When to Use |
|---------|-----------|-------------|
| Data Source Attribution | Know where data comes from | All external data |
| Generation Date | Know data freshness | Time-sensitive reports |
| Data Time Range | Know what period is covered | Time series data |
| Professional Formatting | Looks reliable | All external-facing files |
| Consistent Precision | No doubts about accuracy | All numeric values |

#### Help Users「Gain Insights」

| Feature | User Value | When to Use |
|---------|-----------|-------------|
| Comparison Columns (Δ, %) | No manual calculation for comparisons | YoY, MoM, A vs B |
| Rank Column | Position visible directly | Competitive analysis, performance |
| Grouped Summaries | Aggregated results by dimension | Segmented analysis |
| Trend Indicators (↑↓) | Direction clear at a glance | Change direction matters |
| Insight Text | The "so what" is stated explicitly | Analytical reports |

---

## Part 2: Four-Layer Implementation

### Layer 1: Structure (How It's Organized)

**Goal**: Logical, easy to navigate, user finds what they need immediately.

#### Sheet Organization

| Guideline | Recommendation |
|-----------|----------------|
| Sheet count | 3-5 ideal, max 7 |
| First sheet | Always "Overview" with summary and navigation |
| Sheet order | General → Specific (Overview → Data → Analysis) |
| Naming | Clear, concise (e.g., "Revenue Data", not "Sheet1") |

#### Information Architecture

- **Overview sheet must stand alone**: User should understand the main message without opening other sheets
- **Progressive disclosure**: Summary first, details available for those who want to dig deeper
- **Consistent structure across sheets**: Same layout patterns, same starting positions

#### Layout Rules

| Element | Position |
|---------|----------|
| Left margin | Column A empty (width 3) |
| Top margin | Row 1 empty |
| Content start | Cell B2 |
| Section spacing | 1 empty row between sections |
| Table spacing | 2 empty rows between tables |
| Charts | Below all tables (2 rows gap), or right of related table |

**Chart placement**:
- Default: below all tables, left-aligned with content
- Alternative: right of a single related table
- Charts must never overlap each other or tables

#### Standalone Text Rows

For rows with a single text cell (titles, descriptions, notes, bullet points), text will naturally extend into empty cells to the right. However, text is **clipped** if right cells contain any content (including spaces).

**Decision logic**:

| Condition | Action |
|-----------|--------|
| Right cells guaranteed empty | No action needed—text extends naturally |
| Right cells may have content | Merge cells to content width, or wrap text |
| Text exceeds content area width | Wrap text + set row height manually |

**Technical note**: Fill and border alone do NOT block text overflow—only actual cell content (including space characters) blocks it.

#### Navigation

For files with 3+ sheets, include a Sheet Index on Overview:

```python
# Sheet Index with hyperlinks
ws['B5'] = "CONTENTS"
ws['B5'].font = Font(name=SERIF_FONT, size=14, bold=True, color=THEME['accent'])

sheets = ["Overview", "Data", "Analysis"]
for i, sheet_name in enumerate(sheets, start=6):
    cell = ws.cell(row=i, column=2, value=sheet_name)
    cell.hyperlink = f"#'{sheet_name}'!A1"
    cell.font = Font(color=THEME['accent'], underline='single')
```

---

### Layer 2: Information (What They Learn)

**Goal**: Accurate, complete, insightful—user gains knowledge, not just data.

#### Number Formats

**Critical rules**:
1. **Every numeric cell must have `number_format` set** — both input values AND formula results
2. **Same column = same precision** — never mix `0.1074` and `1.0` in one column
3. **Formula results have no default format** — they display raw precision unless explicitly formatted

| Data Type | Format Code | Example |
|-----------|-------------|---------|
| Integer | `#,##0` | 1,234,567 |
| Decimal (1) | `#,##0.0` | 1,234.6 |
| Decimal (2) | `#,##0.00` | 1,234.56 |
| Percentage | `0.0%` | 12.3% |
| Currency | `$#,##0.00` | $1,234.56 |

**Common mistake**: Setting format only for input cells, forgetting formula cells.

```python
# WRONG: Formula cell without number_format
ws['C10'] = '=C7-C9'  # Will display raw precision like 14.123456789

# CORRECT: Always set number_format for formula cells
ws['C10'] = '=C7-C9'
ws['C10'].number_format = '#,##0.0'  # Displays as 14.1

# Best practice: Define format by column/data type, apply to ALL cells
for row in range(data_start, data_end + 1):
    cell = ws.cell(row=row, column=value_col)
    cell.number_format = '#,##0.0'  # Applies to both values and formulas
```

#### Data Context

Every data set needs context:

| Element | Location | Example |
|---------|----------|---------|
| Data source | Overview or sheet footer | "Source: Company Annual Report 2024" |
| Time range | Near title or in subtitle | "Data from Jan 2020 - Dec 2024" |
| Generation date | Overview footer | "Generated: 2024-01-15" |
| Definitions | Notes section or separate sheet | "Revenue = Net sales excluding returns" |

#### Key Insights

For analytical content, don't just present data—tell the user what it means:

```python
ws['B20'] = "KEY INSIGHTS"
ws['B20'].font = Font(name=SERIF_FONT, size=14, bold=True, color=THEME['accent'])

insights = [
    "• Revenue grew 23% YoY, driven primarily by APAC expansion",
    "• Top 3 customers account for 45% of total revenue",
    "• Q4 showed strongest performance across all metrics"
]
for i, insight in enumerate(insights, start=21):
    ws.cell(row=i, column=2, value=insight)
```

#### Content Completeness

| Check | Action |
|-------|--------|
| Missing values | Show as blank or "N/A", never 0 unless actually zero |
| Calculated fields | Include formula or note explaining calculation |
| Abbreviations | Define on first use or in notes |
| Units | Include in header (e.g., "Revenue ($M)") |

---

### Layer 3: Visual (What They See)

**Goal**: Professional appearance, immediate sense of value, visuals serve content.

#### Essential Setup

```python
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

# Hide gridlines for cleaner look
ws.sheet_view.showGridLines = False

# Left margin
ws.column_dimensions['A'].width = 3
```

#### Theme System

Choose ONE theme per workbook. All visual elements derive from the theme color.

**Available Themes** (select based on context, or let user specify):

| Theme | Primary | Light | Use Case |
|-------|---------|-------|----------|
| **Elegant Black** | `2D2D2D` | `E5E5E5` | Luxury, fashion, premium reports (recommended default) |
| Corporate Blue | `1F4E79` | `D6E3F0` | Finance, corporate analysis |
| Forest Green | `2E5A4C` | `D4E5DE` | Sustainability, environmental |
| Burgundy | `722F37` | `E8D5D7` | Luxury brands, wine industry |
| Slate Gray | `4A5568` | `E2E8F0` | Tech, modern, minimalist |
| Navy | `1E3A5F` | `D3DCE6` | Government, maritime, institutional |
| Charcoal | `36454F` | `DDE1E4` | Professional, executive |
| Deep Purple | `4A235A` | `E1D5E7` | Creative, innovation, premium tech |
| Teal | `1A5F5F` | `D3E5E5` | Healthcare, wellness |
| Warm Brown | `5D4037` | `E6DDD9` | Natural, organic, artisan |
| Royal Blue | `1A237E` | `D3D5E8` | Academic, institutional |
| Olive | `556B2F` | `E0E5D5` | Military, outdoor |

**Theme Configuration**:

```python
# === THEME CONFIGURATION ===
THEMES = {
    'elegant_black': {
        'primary': '2D2D2D',
        'light': 'E5E5E5',
        'accent': '2D2D2D',
        'chart_colors': ['2D2D2D', '4A4A4A', '6B6B6B', '8C8C8C', 'ADADAD', 'CFCFCF'],
    },
    'corporate_blue': {
        'primary': '1F4E79',
        'light': 'D6E3F0',
        'accent': '1F4E79',
        'chart_colors': ['1F4E79', '2E75B6', '5B9BD5', '9DC3E6', 'BDD7EE', 'DEEBF7'],
    },
    # ... other themes follow same pattern
}

THEME = THEMES['elegant_black']  # Default
SERIF_FONT = 'Source Serif Pro'   # or 'Georgia' as fallback
SANS_FONT = 'Source Sans Pro'     # or 'Calibri' as fallback
```

**How Theme Colors Apply**:

| Element | Color | Background |
|---------|-------|------------|
| Document title | `THEME['primary']` | None |
| Section header | `THEME['primary']` | None or `THEME['light']` |
| Table header | White | `THEME['primary']` |
| Data cells | Black | None or alternating `F9F9F9` |
| Chart elements | `THEME['chart_colors']` | — |

#### Semantic Colors

For data meaning (independent of theme):

| Semantic | Color | Use |
|----------|-------|-----|
| Positive | `2E7D32` | Growth, profit, success |
| Negative | `C62828` | Decline, loss, failure |
| Warning | `F57C00` | Caution, attention |

#### Row Highlight Colors

For row-level emphasis. Use **high-lightness tints** (85-95% lightness) for subtle distinction.

| Semantic | Hex | Hue | Use |
|----------|-----|-----|-----|
| Emphasis | `E6F3FF` | 209° | Top rated, important data |
| Section | `FFF3E0` | 37° | Section dividers |
| Input | `FFFDE7` | 55° | Editable cells |
| Special | `FFF9C4` | 55° | Base case, benchmarks |
| Success | `E8F5E9` | 125° | Passed, completed |
| Warning | `FFCCBC` | 14° | Needs attention |

**Rule**: Same semantic = same color. Different semantic = different color.

```python
HIGHLIGHT = {
    'emphasis': 'E6F3FF',
    'section': 'FFF3E0',
    'input': 'FFFDE7',
    'special': 'FFF9C4',
    'success': 'E8F5E9',
    'warning': 'FFCCBC',
}
```

#### Typography

Use **serif + sans-serif pairing**. Serif for hierarchy (titles, headers); sans-serif for data (tabular figures).

**Font Pairings** (in preference order):

| Serif (Titles) | Sans-Serif (Data) | Notes |
|----------------|-------------------|-------|
| Source Serif Pro | Source Sans Pro | Adobe superfamily, recommended |
| IBM Plex Serif | IBM Plex Sans | Modern, corporate |
| Georgia | Calibri | Pre-installed fallback |

**Hierarchy**:

| Element | Font | Size | Style |
|---------|------|------|-------|
| Document title | Serif | 18-22 | Bold, Primary color |
| Section header | Serif | 12-14 | Bold, Primary color |
| Table header | Serif | 10-11 | Bold, White |
| Data cells | Sans-Serif | 11 | Regular, Black |
| Notes | Sans-Serif | 9-10 | Italic, `666666` |

```python
# Document title
ws['B2'].font = Font(name=SERIF_FONT, size=18, bold=True, color=THEME['primary'])

# Section header
ws['B6'].font = Font(name=SERIF_FONT, size=14, bold=True, color=THEME['primary'])

# Table header
header_font = Font(name=SERIF_FONT, size=10, bold=True, color='FFFFFF')

# Data cells
data_font = Font(name=SANS_FONT, size=11)

# Notes
notes_font = Font(name=SANS_FONT, size=10, italic=True, color='666666')
```

#### Data Block Definition

A **Data Block** is a group of continuous, non-empty rows that form a visual unit requiring borders. Data Blocks are separated by empty rows.

**Identification rules**:
1. Scan from Section Header downward
2. Non-empty row starts a Data Block
3. Empty row ends the current Data Block
4. Each Data Block gets its own outer frame

**Data Block types**:

| Type | Structure | Example |
|------|-----------|---------|
| With Header | Header row + data rows | Table with column titles |
| Without Header | Data rows only | Continuation data, sub-tables |

**Example recognition**:

```
Row 5: Section Header "INCOME STATEMENT"   → No border (not a Data Block)
Row 6: Empty                               → Separator
Row 7: Header (Item, Year1, Year2...)      → Data Block 1 starts
Row 8: Revenue, 47061, 48943...            
Row 9: Growth Rate, 4.0%, 3.5%...          → Data Block 1 ends
Row 10: Empty                              → Separator
Row 11: EBITDA, 12121, 12627...            → Data Block 2 starts (no header)
Row 12: EBITDA Margin, 25.8%, 25.8%...     → Data Block 2 ends
Row 13: Empty                              → Separator
Row 14: D&A, 1200, 1224...                 → Data Block 3 starts (no header)
Row 15: EBIT, 10921, 11404...              
Row 16: EBIT Margin, 23.2%, 23.3%...       → Data Block 3 ends
```

Result: 3 separate Data Blocks, each with its own outer frame.

#### Border Rules

**Recommended style: Horizontal-only** — cleaner, more modern.

**Each Data Block must have**:

| Border Type | Where |
|-------------|-------|
| **Outer frame** | All 4 sides of Data Block (top, bottom, left, right) |
| **Header bottom** | Medium weight, theme primary color (if has header) |
| **Internal horizontal** | Thin, between all rows |
| **Internal vertical** | None (omit for cleaner look) |

**Critical**: Every cell in the Data Block must have its border set. Do not only set header and label cells—data cells need borders too.

```python
# Border definitions
outer_border = Side(style='thin', color='D1D1D1')
header_bottom = Side(style='medium', color=THEME['primary'])
inner_horizontal = Side(style='thin', color='D1D1D1')
no_border = Side(style=None)

def apply_data_block_borders(ws, start_row, end_row, start_col, end_col, has_header=True):
    """
    Apply borders to a Data Block.
(Content truncated due to size limit. Use line ranges to read remaining content)