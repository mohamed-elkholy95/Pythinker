# Plotly Chart Design Best Practices

**Source:** Official Plotly.py Documentation (Context7 MCP Validated - 2026-02-15)
**Library ID:** `/plotly/plotly.py` (Benchmark Score: 93.2/100, 2696 snippets)

---

## 1. Choosing the Right Chart Type

### Bar Charts
**When to use:**
- Categorical comparisons (comparing different categories)
- Ranking data (showing order by value)
- Discrete values (not continuous time series)
- Histograms (frequency distributions)

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
- Multiple series comparisons over continuous range

### Scatter Charts
**When to use:**
- Correlation analysis
- Distribution patterns
- Outlier detection

### Pie Charts
**When to use:**
- Part-to-whole relationships
- Limited categories (max 5-7 slices)
- Percentage distributions

**Avoid when:**
- Comparing similar values (hard to distinguish)
- More than 7 categories (use bar chart instead)

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

## 9. Chart Type Decision Tree

```
Is the data categorical?
├─ YES → Is there a natural order?
│  ├─ YES → Use vertical bar chart
│  └─ NO → Are labels long?
│     ├─ YES → Use horizontal bar chart ✅
│     └─ NO → Use vertical bar chart
│
└─ NO → Is it time-series?
   ├─ YES → Use line chart
   └─ NO → Is it continuous relationship?
      ├─ YES → Use scatter plot
      └─ NO → Use appropriate specialized chart
```

---

## 10. Implementation Checklist

Before finalizing any chart, verify:

- [ ] Appropriate chart type for data
- [ ] Sorted by value (for comparisons) or logical order
- [ ] Color palette is accessible and visually distinct
- [ ] Text labels are readable (size, position, contrast)
- [ ] Consistent font family and sizes
- [ ] Subtle grid lines (not overpowering)
- [ ] Adequate margins and spacing
- [ ] Clear title and axis labels
- [ ] Professional template applied (`plotly_white` recommended)
- [ ] Tested in grayscale for accessibility

---

## 11. References

- **Official Documentation**: https://plotly.com/python/
- **Color Scales**: https://plotly.com/python/builtin-colorscales/
- **Templates**: https://plotly.com/python/templates/
- **Bar Charts**: https://plotly.com/python/bar-charts/
- **Accessibility**: https://plotly.com/python/accessibility/

**Validated Against:** Context7 MCP `/plotly/plotly.py` (2696 code snippets, 93.2/100 score)
