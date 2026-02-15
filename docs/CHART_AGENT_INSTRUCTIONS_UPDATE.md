# Chart Agent Instructions Enhancement (2026-02-15)

## Overview

Enhanced Pythinker's chart creation agent with comprehensive data type classification guidance and chart selection decision-making process, based on industry best practices from data visualization experts.

## Changes Made

### 1. Enhanced Tool Description (`backend/app/domain/services/tools/chart.py`)

**Added 4-Step Decision Framework:**

#### STEP 1: IDENTIFY YOUR DATA TYPE
- Categorical/Ordinal: Groups with no inherent order or ordered categories
- Time Series: Numerical values over ordered time points
- Numerical Continuous: Measurements on continuous scale
- Part-to-Whole: Components that sum to a total
- Relationship/Correlation: Two or more variables to explore connections
- Distribution: Spread of values, frequency, quartiles, outliers

#### STEP 2: MATCH DATA TYPE TO CHART TYPE
Organized by data purpose with real-world examples:

**COMPARISON & CATEGORICAL DATA:**
- `bar`: Categorical comparisons (e.g., "Compare response time across 5 LLM models")
- `grouped_bar`: Multi-series comparisons (e.g., "Q1 vs Q2 sales by region")
- `stacked_bar`: Part-to-whole across categories (e.g., "Budget by department, broken down by expense type")

**TRENDS & TIME-SERIES DATA:**
- `line`: Trends over time (e.g., "Daily active users over past 6 months")
- `area`: Cumulative trends (e.g., "Revenue accumulation over quarters")

**DISTRIBUTION & SPREAD:**
- `box`: Distribution quartiles, median, outliers (e.g., "Response time distribution across API endpoints")

**RELATIONSHIP & CORRELATION:**
- `scatter`: Two-variable correlation (e.g., "Model size vs inference speed")

**PART-TO-WHOLE:**
- `pie`: Proportions of total, max 5-7 categories (e.g., "Market share among top 5 vendors")

#### STEP 3: APPLY BEST PRACTICES
- Orientation rules (vertical vs horizontal based on label length)
- Auto-sorting for comparisons
- Professional color palettes
- Smart number formatting
- Data sanitization (automatic markdown removal)
- Smart scaling (automatic log scale for extreme outliers)

#### STEP 4: AVOID COMMON MISTAKES
- Clear anti-patterns for each chart type
- When to use alternative chart types

#### DECISION FLOWCHART
Quick 5-question flowchart for rapid chart type selection

---

### 2. Enhanced Documentation (`docs/PLOTLY_CHART_BEST_PRACTICES.md`)

**Added Section 1: Data Type Classification**

New comprehensive data type classification table:
- Data Variable Types table (6 types with examples and best chart recommendations)
- Chart Selection Decision Tree (3-step process)
- Question-based selection guide
- Variable-based selection guide
- Formatting decision rules
- Common mistake prevention matrix

**Expanded Section 2: Choosing the Right Chart Type**

For EACH chart type, added:
- **Data Requirements**: Specific X-axis and Y-axis variable types
- **Real-world examples**: 3-4 concrete use cases per chart type
- **Best practices**: Specific tips for each chart type
- **When to avoid**: Clear guidance on inappropriate use cases

Updated sections:
- Bar Charts
- Line Charts
- Scatter Charts
- Pie Charts
- Area Charts
- Grouped Bar Charts
- Stacked Bar Charts
- Box Charts

**Enhanced Section 9: Chart Type Decision Tree**

Replaced simple tree with comprehensive 3-level decision framework:
1. **Primary Question-Based Selection**: Start with the question you're answering
2. **Data Type-Based Selection**: Match your data structure to chart types
3. **Formatting Decision**: Apply orientation, scaling, and formatting rules
4. **Common Mistake Prevention**: Explicit anti-patterns to avoid

**Updated Section 10: Implementation Checklist**

Reorganized into 3 phases:
1. **Pre-Implementation**: Data type validation, question identification, chart type verification
2. **Implementation**: Visual design elements, accessibility, professional styling
3. **Post-Implementation**: Validation, accuracy checks, anti-pattern detection

---

## Impact & Benefits

### For the Agent (LLM)
1. **Clear Decision Framework**: 4-step process guides chart selection systematically
2. **Data Type First**: Emphasizes understanding data before choosing visualization
3. **Real Examples**: Concrete use cases help LLM understand appropriate applications
4. **Anti-Pattern Awareness**: Explicit guidance on what NOT to do prevents common mistakes

### For Users
1. **Better Chart Selection**: Agent will choose more appropriate chart types for data
2. **Improved Accuracy**: Data type classification reduces visualization errors
3. **Professional Output**: Charts follow industry best practices automatically
4. **Educational Value**: Users learn best practices through agent's explanations

### Design Principles Applied
- **Question-First Approach**: Start with the question, not the chart type
- **Data-Driven Selection**: Match data structure to appropriate visualization
- **Real-World Context**: Examples from actual use cases (API monitoring, sales analysis, etc.)
- **Progressive Guidance**: Simple decision tree → detailed examples → comprehensive checklist

---

## Validation

✅ **Context7 MCP Validated**: All chart types and best practices verified against official Plotly documentation
✅ **Industry Standards**: Aligned with ThoughtSpot, Infographic Kit, ChartExpo, Dataquest best practices
✅ **Accessibility**: Includes color-blind safe palettes, grayscale testing, contrast guidelines
✅ **Production-Ready**: Builds on existing sanitization, log scaling, and auto-formatting features

---

## Usage Example

**Before:**
```python
# Agent might create inappropriate chart
chart_create(
    chart_type="pie",  # Wrong for 12 categories
    title="Sales by Product",
    labels=[...12 products...],  # Too many slices
    datasets=[{"values": [...]}]
)
```

**After:**
```python
# Agent follows decision framework:
# STEP 1: Data type = Categorical (product names) + Numerical (sales)
# STEP 2: Question = "Which product has highest sales?" → COMPARISON
# STEP 3: Labels >4 chars → Use horizontal orientation
# STEP 4: Avoid pie with >7 categories → Use bar instead

chart_create(
    chart_type="bar",
    title="Sales by Product",
    labels=[...12 products...],
    datasets=[{"values": [...]}],
    orientation="h",  # Horizontal for long product names
    lower_is_better=False  # Higher sales is better
)
```

---

## Files Modified

1. `backend/app/domain/services/tools/chart.py` - Tool description (lines 49-134)
2. `docs/PLOTLY_CHART_BEST_PRACTICES.md` - Comprehensive documentation

## Files Created

1. `docs/CHART_AGENT_INSTRUCTIONS_UPDATE.md` - This summary document

---

## Next Steps (Optional Future Enhancements)

1. **Add chart recommendation API**: Endpoint that analyzes data and recommends chart type
2. **Interactive examples**: Create gallery of example charts with data characteristics
3. **Validation warnings**: Agent warns when data doesn't match chart type requirements
4. **Multi-chart suggestions**: Offer 2-3 chart options with pros/cons for ambiguous cases

---

## References

- **Plotly Official Docs**: `/plotly/plotly.py` (Context7 MCP, Score: 93.2/100)
- **ThoughtSpot**: 24 types of charts and graphs for data visualization
- **Infographic Kit**: Choosing the Right Chart Type Guide
- **ChartExpo**: Best Graphs for Categorical Data
- **Dataquest**: Choosing the Right Chart for Your Data
