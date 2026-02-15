# Plotly Chart Design Best Practices

**Source:** Official Plotly.py Documentation (Context7 MCP Validated - 2026-02-15)
**Library ID:** `/plotly/plotly.py` (Benchmark Score: 93.2/100, 2696 snippets)

---

## 1. Data Type Classification (CRITICAL FIRST STEP)

Before choosing any chart, you MUST classify your data type. This determines the appropriate visualization:

### Data Variable Types

| Data Type | Description | Examples | Best Charts |
|-----------|-------------|----------|-------------|
| **Categorical/Ordinal** | Groups with no inherent order, or ordered categories | Product types, regions, satisfaction levels (Low/Med/High) | bar, grouped_bar, stacked_bar, pie |
| **Time Series** | Numerical values measured over ordered time points | Sales by month, daily active users, quarterly revenue | line, area |
| **Numerical Continuous** | Measurements on a continuous scale | Price, speed, weight, temperature, response time | box, scatter, line |
| **Part-to-Whole** | Components that sum to a meaningful total | Market share, budget breakdown, percentage composition | pie, stacked_bar |
| **Relationship/Correlation** | Two or more variables to explore connections | Ad spend vs conversions, model size vs speed, height vs weight | scatter |
| **Distribution** | Spread of values, frequency, quartiles | Response time distribution, score ranges, outlier detection | box, scatter |

### Chart Selection Decision Tree

```
STEP 1: What question are you answering?
├─ "Which category is largest/smallest?" → COMPARISON
├─ "How does it change over time?" → TREND
├─ "What's the spread/range of values?" → DISTRIBUTION
├─ "Are two variables related?" → RELATIONSHIP
└─ "What are the proportions of the total?" → PART-TO-WHOLE

STEP 2: What type of variables do you have?
├─ Categorical + Numerical → bar, grouped_bar, stacked_bar
├─ Time/Ordered + Numerical → line, area
├─ Two Numerical → scatter
├─ Categorical + Percentage (total=100%) → pie
└─ Numerical Continuous (single variable) → box

STEP 3: Apply formatting rules:
├─ Are labels >4 characters? → Use orientation='h' for bar charts
├─ Are values vastly different (>5x range)? → Log scale applied automatically
└─ Do you need to compare order? → Charts auto-sort by value
```

---

## 2. Choosing the Right Chart Type

### Bar Charts
**When to use:**
- Categorical comparisons (comparing different categories)
- Ranking data (showing order by value)
- Discrete values (not continuous time series)
- Frequency distributions

**Data Requirements:**
- X-axis: Categorical variable (product names, regions, model types)
- Y-axis: Numerical metric (count, average, total, percentage)

**Real-world examples:**
- "Compare average API response time across 5 different endpoints"
- "Show total sales by product category"
- "Rank LLM models by inference speed (tokens/sec)"
- "Display error counts by error type"

**Horizontal vs Vertical:**
- **Vertical (`orientation='v'`)**: ✅ DEFAULT for:
  - Rankings and categorical comparisons
  - Histograms (frequency distributions)
  - Short category labels (1-3 characters)
  - Traditional bar chart appearance

- **Horizontal (`orientation='h'`)**: Switch to this when:
  - Category labels are longer than 3-4 characters
  - Prevents label rotation issues
  - Natural left-to-right reading pattern for comparisons
  - Long model names, product names, or text labels

**Rule of thumb:** Start vertical, switch to horizontal if labels are cramped or rotated.

### Line Charts
**When to use:**
- Time-series data (trends over time)
- Continuous data relationships
- Multiple series comparisons over ordered range

**Data Requirements:**
- X-axis: Time or ordered continuous variable (dates, time periods, sequential steps)
- Y-axis: Numerical metric (count, average, measurement)

**Real-world examples:**
- "Show daily active users over the past 6 months"
- "Display server CPU usage hour by hour for the last 24 hours"
- "Compare revenue trends across Q1, Q2, Q3, Q4"
- "Track model accuracy improvement over training epochs"

**Best practices:**
- Add markers (`mode='lines+markers'`) for discrete data points
- Use multiple lines for comparing trends between groups
- Avoid line charts for unordered categorical data (use bar instead)

---

### Scatter Charts
**When to use:**
- Correlation analysis (relationship between two variables)
- Distribution patterns
- Outlier detection
- Cluster identification

**Data Requirements:**
- X-axis: Numerical variable (e.g., model size in parameters)
- Y-axis: Numerical variable (e.g., inference speed)
- Optional: Color/size for third dimension (creates bubble chart effect)

**Real-world examples:**
- "Explore correlation between ad spend and conversion rate"
- "Plot model parameter count vs inference latency"
- "Show relationship between user engagement time and retention rate"
- "Identify outliers in API response time vs request payload size"

**Best practices:**
- Use color to encode categorical groupings (e.g., different model families)
- Use marker size for magnitude of third variable
- Add trend line for correlation visualization (not built-in, requires custom calc)

---

### Pie Charts
**When to use:**
- Part-to-whole relationships (components sum to 100%)
- Limited categories (max 5-7 slices for readability)
- Emphasizing proportions over exact values

**Data Requirements:**
- Categories: Categorical variable (market segments, expense categories)
- Values: Numerical or percentage that sums to a meaningful total

**Real-world examples:**
- "Market share distribution among top 5 cloud providers"
- "Budget allocation across departments (HR, Engineering, Marketing, Sales)"
- "Traffic sources breakdown (Direct: 40%, Organic: 35%, Paid: 15%, Referral: 10%)"

**Avoid when:**
- More than 7 categories (slices become too small → use bar chart)
- Values are very similar (hard to visually distinguish small differences → use bar chart)
- Precise comparison needed (bar charts are better for magnitude comparison)
- Time-series data (use line or area chart)

**Best practices:**
- Sort slices by size (largest to smallest) for clarity
- Use labels + percentages inside slices (`textinfo='label+percent'`)
- Consider donut chart (set `hole=0.4`) for modern appearance
- Limit to <7 slices maximum for visual clarity

---

### Area Charts
**When to use:**
- Cumulative trends over time
- Emphasizing volume/magnitude of change
- Stacked contributions showing part-to-whole over time

**Data Requirements:**
- X-axis: Time or ordered continuous variable
- Y-axis: Numerical metric (volume, cumulative count, magnitude)

**Real-world examples:**
- "Revenue accumulation by quarter over 3 years"
- "Cumulative user signups over time"
- "Stacked area showing traffic by source over 12 months"

**Best practices:**
- Use semi-transparent fills (alpha=0.25) for overlapping series
- Stacked area charts show part-to-whole composition over time
- Avoid area charts when precise value reading is critical (use line instead)

---

### Grouped Bar Charts
**When to use:**
- Multi-series categorical comparison (side-by-side bars)
- Comparing multiple metrics per category
- When both individual values AND cross-category comparison matter

**Data Requirements:**
- X-axis: Categorical variable (regions, product types, time periods)
- Y-axis: Numerical metric
- Multiple datasets: 2-4 series for optimal readability

**Real-world examples:**
- "Compare Q1 vs Q2 sales performance by region"
- "Show speed and accuracy scores side-by-side for each LLM model"
- "Display actual vs target performance across departments"

**Best practices:**
- Limit to 2-4 series maximum (more becomes cluttered)
- Use distinct colors from qualitative palette (applied automatically)
- Consider horizontal orientation for long category labels

---

### Stacked Bar Charts
**When to use:**
- Part-to-whole composition across categories
- When both total AND breakdown per category are important
- Showing multiple components that sum to a meaningful total

**Data Requirements:**
- X-axis: Categorical variable
- Y-axis: Numerical metric
- Multiple datasets: Components that stack to form total

**Real-world examples:**
- "Total budget by department, broken down by expense type (Salaries, Equipment, Marketing)"
- "Monthly revenue by product line, stacked to show total monthly revenue"
- "Support ticket volume by priority level (High, Medium, Low) stacked by week"

**Best practices:**
- Use for 2-5 components maximum (more becomes hard to read)
- Bottom component should be most important (easiest to compare across categories)
- Consider 100% stacked bars for proportion comparison
- Text positioning is 'inside' to avoid overlap

---

### Box Charts (Box Plots)
**When to use:**
- Distribution analysis (quartiles, median, outliers)
- Comparing distributions across groups
- Identifying outliers and spread

**Data Requirements:**
- Single numerical continuous variable OR
- Numerical variable grouped by categorical variable

**Real-world examples:**
- "Distribution of API response times across different endpoints"
- "Compare salary ranges across job levels (Junior, Mid, Senior)"
- "Show test score distributions by student cohort"

**Best practices:**
- Include mean + standard deviation markers (`boxmean='sd'`)
- Useful for detecting outliers (points beyond whiskers)
- Good for comparing spread across multiple groups
- Not ideal for small datasets (<10 points) - use scatter instead

---

## 2. Color Palette Best Practices

### Built-in Color Scales (Recommended)

Plotly provides three types of built-in color scales:

#### **Qualitative (Discrete/Categorical Data)**
Use for distinct categories with no meaningful order:

```python
import plotly.express as px

# Available qualitative palettes:
# - px.colors.qualitative.Plotly (default)
# - px.colors.qualitative.D3
# - px.colors.qualitative.G10
# - px.colors.qualitative.T10
# - px.colors.qualitative.Alphabet
# - px.colors.qualitative.Safe (color-blind safe)
# - px.colors.qualitative.Vivid

# Example: Use color-blind safe palette
fig = px.bar(df, x='category', y='value',
             color='category',
             color_discrete_sequence=px.colors.qualitative.Safe)
```

#### **Sequential (Continuous Data)**
Use for continuous data with one endpoint:

```python
# Available sequential palettes:
# - px.colors.sequential.Blues
# - px.colors.sequential.Viridis
# - px.colors.sequential.Plasma
# - px.colors.sequential.Inferno
# - px.colors.sequential.RdBu

# Example: Sequential color scale
fig = px.scatter(df, x='x', y='y', color='value',
                 color_continuous_scale=px.colors.sequential.Viridis)
```

#### **Diverging (Data with Meaningful Midpoint)**
Use for data with natural midpoint (e.g., 0, average):

```python
# Available diverging palettes:
# - px.colors.diverging.BrBG
# - px.colors.diverging.RdBu
# - px.colors.diverging.Spectral

# Example: Diverging scale with midpoint
fig = px.choropleth(df, locations='country', color='value',
                    color_continuous_scale=px.colors.diverging.RdBu,
                    color_continuous_midpoint=0)
```

### Custom Color Palettes

For single-series bar charts with distinct categories:

```python
# Professional palette (diverse, visually distinct)
color_palette = [
    "#2563eb",  # Blue-600
    "#0891b2",  # Cyan-600
    "#06b6d4",  # Cyan-500
    "#3b82f6",  # Blue-500
    "#0ea5e9",  # Sky-500
    "#6366f1",  # Indigo-500
    "#8b5cf6",  # Violet-500
    "#a855f7",  # Purple-500
]

# Apply to bar chart
fig = go.Bar(x=labels, y=values,
             marker=dict(color=[color_palette[i % len(color_palette)]
                                for i in range(len(labels))]))
```

### Color Accessibility Guidelines

1. **Use color-blind safe palettes**: `px.colors.qualitative.Safe`
2. **Ensure sufficient contrast**: Dark text on light bars, light text on dark bars
3. **Don't rely solely on color**: Use patterns, labels, or other visual cues
4. **Test with grayscale**: Chart should be readable in black & white

---

## 3. Templates and Themes

### Available Built-in Templates

```python
import plotly.io as pio

# Set global default template
pio.templates.default = "plotly_white"

# Available templates:
# - "plotly" (default, colorful)
# - "plotly_white" (clean, minimal) ✅ RECOMMENDED FOR PROFESSIONAL CHARTS
# - "plotly_dark" (dark mode)
# - "ggplot2" (R ggplot2 style)
# - "seaborn" (Seaborn style)
# - "simple_white" (minimalist)
# - "none" (no styling)
```

### Recommended Template: `plotly_white`

```python
fig = px.bar(df, x='category', y='value',
             template='plotly_white')  # Clean, professional appearance
```

### Custom Templates

```python
# Create custom template based on plotly_white
pio.templates["custom_professional"] = pio.templates["plotly_white"]
pio.templates["custom_professional"].layout.colorway = [
    '#2563eb', '#0891b2', '#06b6d4', '#3b82f6'
]
pio.templates["custom_professional"].layout.font.family = "Arial, sans-serif"
pio.templates["custom_professional"].layout.font.size = 14

# Use custom template
fig = px.bar(df, x='x', y='y', template='custom_professional')
```

---

## 4. Bar Chart Specific Best Practices

### Sorting Categories

Always sort bar charts for better readability:

```python
import plotly.graph_objects as go

# Sort by value (descending)
fig.update_xaxes(categoryorder='total descending')  # ✅ RECOMMENDED for comparisons

# Sort alphabetically
fig.update_xaxes(categoryorder='category ascending')

# Custom order
fig.update_xaxes(categoryorder='array',
                 categoryarray=['High', 'Medium', 'Low'])
```

### Text Labels on Bars

```python
fig = go.Bar(x=labels, y=values,
             text=values,
             textposition='outside',  # ✅ RECOMMENDED for readability
             texttemplate='%{text:.2s}',  # Format numbers (2 significant digits)
             textfont=dict(size=14, color='#1f2937'))

# Ensure consistent font sizes
fig.update_layout(uniformtext_minsize=8, uniformtext_mode='hide')
```

### Bar Styling

```python
fig = go.Bar(
    x=labels, y=values,
    marker=dict(
        color=colors,
        line=dict(color='rgba(255,255,255,0.8)', width=2),  # Subtle border
    )
)
```

### Gap and Width

```python
fig.update_layout(
    bargap=0.15,       # Space between bars (0-1)
    bargroupgap=0.1    # Space between groups (0-1)
)
```

---

## 5. Layout and Grid Best Practices

### Professional Layout Configuration

```python
fig.update_layout(
    title=dict(
        text="Chart Title",
        font=dict(size=24, color="#111827", family="Arial, sans-serif"),
    ),
    xaxis=dict(
        title="X-Axis Label",
        showgrid=True,
        gridcolor="rgba(0,0,0,0.1)",  # Subtle grid lines
        gridwidth=1,
        zeroline=True,
        zerolinecolor="rgba(0,0,0,0.2)",
        zerolinewidth=2,
    ),
    yaxis=dict(
        title="Y-Axis Label",
        showgrid=True,
        gridcolor="rgba(0,0,0,0.1)",
        gridwidth=1,
    ),
    template="plotly_white",
    height=600,
    width=1000,
    margin=dict(l=80, r=100, t=100, b=80),  # Adequate spacing
    font=dict(size=14, family="Arial, sans-serif", color="#374151"),
    plot_bgcolor="rgba(0,0,0,0)",  # Transparent plot background
    paper_bgcolor="white",
)
```

### Margins

- **Horizontal bars**: Left margin 200px for long labels
- **Vertical bars**: Left margin 80px
- **Top margin**: 100px (for title)
- **Bottom margin**: 80px (for x-axis labels)
- **Right margin**: 100px (for padding)

---

## 6. Responsive Design

### Size Recommendations

```python
# Desktop (default)
fig.update_layout(width=1000, height=600)

# Mobile-friendly (if needed)
fig.update_layout(width=800, height=500)

# For dashboards (compact)
fig.update_layout(width=600, height=400)
```

### Autosizing

```python
fig.update_layout(
    autosize=True,  # Allow responsive sizing
    width=None,     # Let container define width
    height=600,     # Fix height
)
```

---

## 7. Data Sanitization & Smart Scaling (NEW - 2026-02-15)

### Automatic Label Cleaning

All chart types automatically remove markdown formatting from labels:

```python
# Input labels with markdown
labels = ["**Claude 3.7 Sonnet**", "*GPT-4*", "`Gemini Pro`"]

# Automatically cleaned to:
# ["Claude 3.7 Sonnet", "GPT-4", "Gemini Pro"]
```

**Removed patterns:**
- Bold: `**text**` → `text`
- Italic: `*text*` → `text`
- Code: `` `text` `` → `text`
- Underscores: `__text__` or `_text_` → `text`
- Extra whitespace collapsed

### Automatic Log Scale for Extreme Outliers

Bar charts automatically detect extreme outliers (value range > 5x median) and apply log scale:

```python
# Example: Pricing data with outlier
values = [0.55, 0.60, 0.75, 3.00]  # 3.00 is 5x larger than median

# Automatically applies log scale to prevent crushing small values
# Adds subtitle: "• Log scale applied due to wide value range"
```

**When log scale is applied:**
- Value range exceeds 5× the median value
- Prevents small values from being visually crushed
- Maintains proportional comparison
- User is notified via subtitle

**Manual control:** Use normalized values instead if log scale isn't appropriate:

```python
# Option 1: Normalize to "X times cheaper than baseline"
base = values[0]
normalized = [base / v for v in values]

# Option 2: Show as percentage difference from baseline
percentage = [(v - base) / base * 100 for v in values]
```

### Handling Extreme Outliers (Best Practices)

**Option 1: Log Scale (automatic)**
```python
# Just pass the data - log scale auto-detected
chart_create(
    chart_type="bar",
    labels=model_names,
    datasets=[{"values": prices}],
    orientation="h",
)
```

**Option 2: Normalize Values**
```python
# Show relative to cheapest option
baseline = min(prices)
normalized = [baseline / p for p in prices]

chart_create(
    chart_type="bar",
    title="Price Comparison (relative to cheapest)",
    labels=model_names,
    datasets=[{"values": normalized}],
    y_label="Times cheaper than cheapest option",
)
```

**Option 3: Split into Tiers**
```python
# Separate expensive and cheap options
cheap = [(name, price) for name, price in zip(names, prices) if price < 1.0]
expensive = [(name, price) for name, price in zip(names, prices) if price >= 1.0]

# Create two separate charts
```

---

## 8. Common Anti-Patterns to Avoid

❌ **Don't:**
- Use 3D charts (harder to read, distorts values)
- Use too many colors (max 8-10 distinct colors)
- Rotate text labels excessively (use horizontal bars instead)
- Use pie charts for more than 7 categories
- Use dual y-axes (confusing, hard to compare)
- Truncate y-axis (misrepresents data)
- Use rainbow color scales for continuous data
- Pass markdown-formatted text to chart labels (now auto-cleaned)
- Ignore extreme outliers that crush visual scale (now auto-detected)

✅ **Do:**
- Sort bars by value for comparisons
- Use consistent color schemes across related charts
- Include clear axis labels and titles
- Use appropriate chart type for data
- Ensure text is readable (min 10-12px)
- Test in grayscale for accessibility
- Clean data before charting (markdown removal now automatic)
- Consider log scale for wide value ranges (now automatic)

---

## 9. Chart Type Decision Tree (Step-by-Step Selection)

### Primary Question-Based Selection

```
STEP 1: What question are you trying to answer?
├─ "Which category has the highest/lowest value?" → COMPARISON (bar, grouped_bar)
├─ "How does this change over time?" → TREND (line, area)
├─ "What's the distribution of values?" → DISTRIBUTION (box, scatter)
├─ "Are these two variables related?" → RELATIONSHIP (scatter)
├─ "What are the proportions of the total?" → PART-TO-WHOLE (pie, stacked_bar)
└─ "How do multiple groups compare over time?" → MULTI-SERIES TREND (line, grouped_bar)
```

### Data Type-Based Selection

```
STEP 2: What type of data do you have?

Categorical + Numerical
├─ Single metric → bar chart
│  └─ Labels >4 chars? → orientation='h', else orientation='v'
├─ Multiple metrics (2-4) → grouped_bar
└─ Components sum to total → stacked_bar

Time/Ordered + Numerical
├─ Trend over time → line chart
├─ Cumulative/volume emphasis → area chart
└─ Multiple series comparison → multi-line chart

Two Numerical Variables
└─ Correlation/relationship → scatter plot

Categorical + Percentage (total=100%)
├─ Categories ≤7 → pie chart
└─ Categories >7 → bar chart instead

Single Numerical Variable
├─ Show distribution → box plot
└─ Show frequency → bar chart (histogram)
```

### Formatting Decision

```
STEP 3: Apply formatting rules

For BAR charts:
├─ Labels ≤3 characters? → orientation='v' (vertical) ✅
├─ Labels >4 characters? → orientation='h' (horizontal) ✅
├─ Comparison chart? → Auto-sort by value (descending)
└─ Value range >5x? → Log scale applied automatically

For PIE charts:
├─ Categories >7? → Use bar chart instead ❌
├─ Values very similar? → Use bar chart instead ❌
└─ Valid pie → Use textinfo='label+percent'

For LINE charts:
├─ Data is time-series? → Use line ✅
├─ Data is categorical? → Use bar instead ❌
└─ Multiple series? → Use different colors per series

For SCATTER plots:
├─ Two numerical variables? → Use scatter ✅
├─ Add grouping? → Use color encoding
└─ Show magnitude? → Use marker size (bubble effect)
```

### Common Mistake Prevention

```
AVOID THESE COMBINATIONS:
❌ Pie chart with >7 slices → Use bar chart
❌ Pie chart with similar values → Use bar chart
❌ Line chart for unordered categories → Use bar chart
❌ Bar chart for time-series → Use line chart
❌ Vertical bars with long labels → Use orientation='h'
❌ Scatter plot for categorical comparison → Use bar chart
❌ 3D charts (any type) → Use 2D versions for accuracy
```

---

## 10. Implementation Checklist

Before creating any chart, verify:

### Pre-Implementation (Data & Chart Type)
- [ ] **Data type classified** (categorical, time-series, numerical, part-to-whole, relationship, distribution)
- [ ] **Question identified** (comparison, trend, distribution, relationship, proportion)
- [ ] **Chart type matches data type** (use decision tree above)
- [ ] **Variables validated** (X-axis type, Y-axis type, number of series)
- [ ] **Data shape verified** (labels match values length, no missing data)

### Implementation (Visual Design)
- [ ] **Appropriate chart type for question** (use selection guide)
- [ ] **Sorted correctly** (by value for comparisons, chronologically for time-series)
- [ ] **Orientation appropriate** (horizontal for labels >4 chars)
- [ ] **Color palette accessible** (using Plotly qualitative palette automatically)
- [ ] **Text labels readable** (size, position, contrast, auto-formatting applied)
- [ ] **Consistent font family and sizes** (Arial, 14px body, 24px title)
- [ ] **Subtle grid lines** (rgba(0,0,0,0.08), not overpowering)
- [ ] **Adequate margins** (200px left for horizontal, 100px top for title)
- [ ] **Clear title and axis labels** (descriptive, not abbreviations)
- [ ] **Professional template applied** (`plotly_white` recommended)

### Post-Implementation (Validation)
- [ ] **Chart answers the question** (user can extract insight in <5 seconds)
- [ ] **Values are accurate** (no data transformation errors)
- [ ] **Tested in grayscale** (accessible without color)
- [ ] **No common anti-patterns** (see section 8)
- [ ] **Markdown artifacts removed** (automatic sanitization applied)
- [ ] **Log scale appropriate** (automatic detection for >5x range)

---

## 11. References

- **Official Documentation**: https://plotly.com/python/
- **Color Scales**: https://plotly.com/python/builtin-colorscales/
- **Templates**: https://plotly.com/python/templates/
- **Bar Charts**: https://plotly.com/python/bar-charts/
- **Accessibility**: https://plotly.com/python/accessibility/

**Validated Against:** Context7 MCP `/plotly/plotly.py` (2696 code snippets, 93.2/100 score)
