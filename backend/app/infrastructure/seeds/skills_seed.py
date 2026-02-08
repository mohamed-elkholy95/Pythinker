"""Official skills seed data.

This module defines the built-in skills that come with Pythinker.
Skills are prepackaged capabilities that group related tools together.

Implements Claude's skills architecture patterns:
- Invocation control (user, ai, both)
- Tool restrictions (allowed_tools)
- Dynamic context injection support
- Trigger patterns for automatic activation
"""

import contextlib
from datetime import UTC, datetime
from pathlib import Path

from app.domain.models.skill import Skill, SkillCategory, SkillInvocationType, SkillSource

# =============================================================================
# SKILL CREATOR PATHS
# =============================================================================

# Path to the skill-creator resources (relative to this file)
SKILL_CREATOR_DIR = Path(__file__).parent / "skills" / "skill-creator"
SKILL_CREATOR_SKILL_MD = SKILL_CREATOR_DIR / "SKILL.md"

# Workspace path where skill-creator will be available to agents
WORKSPACE_SKILL_CREATOR_PATH = "/workspace/skills/skill-creator"


def get_skill_creator_content() -> str:
    """Get the content of the skill-creator SKILL.md file.

    Returns:
        Content of SKILL.md or empty string if not found
    """
    if SKILL_CREATOR_SKILL_MD.exists():
        return SKILL_CREATOR_SKILL_MD.read_text()
    return ""


def get_skill_creator_resources() -> dict[str, str]:
    """Get all skill-creator resource files.

    Returns:
        Dict mapping relative paths to file contents
    """
    resources = {}
    if not SKILL_CREATOR_DIR.exists():
        return resources

    for file_path in SKILL_CREATOR_DIR.rglob("*"):
        if file_path.is_file():
            rel_path = file_path.relative_to(SKILL_CREATOR_DIR)
            with contextlib.suppress(UnicodeDecodeError):
                resources[str(rel_path)] = file_path.read_text()
    return resources


# =============================================================================
# OFFICIAL SKILLS DEFINITIONS
# =============================================================================

OFFICIAL_SKILLS: list[Skill] = [
    # -------------------------------------------------------------------------
    # Research Skill
    # -------------------------------------------------------------------------
    Skill(
        id="research",
        name="Research",
        description="Web research and information gathering. Search the web, browse sites, and compile findings.",
        category=SkillCategory.RESEARCH,
        source=SkillSource.OFFICIAL,
        icon="search",
        required_tools=[
            "info_search_web",
            "browser_navigate",
            "browser_get_content",
            "file_write",
        ],
        optional_tools=[
            "browser_agent_run",
            "browser_agent_extract",
        ],
        system_prompt_addition="""<research_skill>
## MANDATORY Research Workflow

### Step 1: Search (info_search_web)
- Find relevant sources with search queries
- Note the URLs returned in search results

### Step 2: BROWSE ACTUAL PAGES (CRITICAL)
- You MUST use browser_navigate or browser_get_content to visit URLs
- Do NOT rely on search snippets - they are often outdated or incomplete
- Extract actual content from the pages you visit
- Visit at least 3-5 sources for comprehensive research

### Step 3: Extract & Verify
- Pull specific data, specs, and facts from page content
- Cross-reference claims across multiple sources
- Note the current date context for time-sensitive information

### Step 4: Synthesize with Citations
- Compile findings from ACTUAL page content (not LLM knowledge)
- Include inline citations [1], [2] linking to visited URLs
- End with a References section listing all sources

## CRITICAL RULES
- NEVER generate research reports from search snippets alone
- ALWAYS browse to actual URLs before writing conclusions
- If browser_navigate fails, use browser_get_content as fallback
- Cite only pages you actually visited and extracted content from
</research_skill>""",
        default_enabled=True,
        version="1.0.0",
        author="Pythinker",
        is_premium=False,
        # Claude-style configuration
        invocation_type=SkillInvocationType.BOTH,
        trigger_patterns=[r"research\s+", r"find\s+information", r"look\s+up"],
    ),
    # -------------------------------------------------------------------------
    # Coding Skill
    # -------------------------------------------------------------------------
    Skill(
        id="coding",
        name="Coding",
        description="Code generation, debugging, and refactoring. Read, write, and execute code.",
        category=SkillCategory.CODING,
        source=SkillSource.OFFICIAL,
        icon="code",
        required_tools=[
            "file_read",
            "file_write",
            "file_str_replace",
            "file_find_in_content",
            "file_find_by_name",
            "shell_exec",
            "code_execute",
        ],
        optional_tools=[
            "code_execute_python",
            "code_execute_javascript",
        ],
        system_prompt_addition="""<coding_skill>
When writing or modifying code:

1. **Understand First**: Always read existing code before modifying
   - Use file_read to examine files
   - Use file_find_in_content to search for patterns
   - Understand the codebase structure

2. **Make Focused Changes**: Don't over-engineer
   - Only change what's necessary
   - Don't add features unless asked
   - Keep solutions simple

3. **Code Quality**:
   - Follow language-specific best practices
   - Handle errors gracefully
   - Write self-documenting code
   - Add comments only where logic isn't obvious

4. **Verify Changes**:
   - Test code before considering task complete
   - Use code_execute to run and verify
   - Check for syntax errors and edge cases

5. **Version Control**:
   - Stage specific files, not everything
   - Write clear commit messages
   - Don't commit sensitive data
</coding_skill>""",
        default_enabled=True,
        version="1.0.0",
        author="Pythinker",
        is_premium=False,
        # Claude-style configuration
        invocation_type=SkillInvocationType.BOTH,
        trigger_patterns=[r"write\s+code", r"debug", r"fix\s+", r"implement", r"refactor"],
    ),
    # -------------------------------------------------------------------------
    # Browser Skill
    # -------------------------------------------------------------------------
    Skill(
        id="browser",
        name="Browser",
        description="Web browsing and interaction. Navigate websites, fill forms, click buttons.",
        category=SkillCategory.BROWSER,
        source=SkillSource.OFFICIAL,
        icon="globe",
        required_tools=[
            "browser_navigate",
            "browser_view",
            "browser_click",
            "browser_input",
            "browser_scroll_down",
            "browser_scroll_up",
            "browser_get_content",
        ],
        optional_tools=[
            "browser_restart",
            "browser_press_key",
            "browser_select_option",
            "browser_move_mouse",
            "browser_console_exec",
            "browser_console_view",
        ],
        default_enabled=True,
        version="1.0.0",
        author="Pythinker",
        is_premium=False,
    ),
    # -------------------------------------------------------------------------
    # File Management Skill
    # -------------------------------------------------------------------------
    Skill(
        id="file-management",
        name="File Management",
        description="File operations and organization. Create, read, edit, and organize files.",
        category=SkillCategory.FILE_MANAGEMENT,
        source=SkillSource.OFFICIAL,
        icon="folder",
        required_tools=[
            "file_read",
            "file_write",
            "file_str_replace",
            "file_find_in_content",
            "file_find_by_name",
        ],
        optional_tools=[
            "shell_exec",
        ],
        default_enabled=True,
        version="1.0.0",
        author="Pythinker",
        is_premium=False,
    ),
    # -------------------------------------------------------------------------
    # Data Analysis Skill
    # -------------------------------------------------------------------------
    Skill(
        id="data-analysis",
        name="Data Analysis",
        description="Data processing, analysis, and visualization. Work with CSV, JSON, and create charts. Use for: analyzing datasets, creating visualizations, statistical analysis.",
        category=SkillCategory.DATA_ANALYSIS,
        source=SkillSource.OFFICIAL,
        icon="bar-chart",
        required_tools=[
            "file_read",
            "file_write",
            "code_execute_python",
            "shell_exec",
        ],
        optional_tools=[
            "code_execute",
        ],
        system_prompt_addition="""<data_analysis>
# Data Analysis Skill

## CRITICAL: Execute Code, Don't Just Describe
- You MUST use code_execute_python to perform actual analysis
- DO NOT write explanatory text without running code first
- ALWAYS save outputs (charts, processed data) to /workspace/

## Workflow
1. **Load Data**: Read CSV/JSON/Excel files using pandas
2. **Explore**: Run df.info(), df.describe(), df.head()
3. **Clean**: Handle missing values, fix data types
4. **Analyze**: Calculate statistics, find patterns
5. **Visualize**: Create charts with matplotlib/seaborn
6. **Export**: Save results to files

## Required Output
- Summary statistics (mean, median, std, etc.)
- Visualizations saved as PNG/SVG files
- Processed data saved to CSV/Excel if requested

## Python Pattern
```python
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

# Load data
df = pd.read_csv('/workspace/data.csv')

# Analysis
print(df.describe())

# Visualization
plt.figure(figsize=(10, 6))
sns.barplot(data=df, x='category', y='value')
plt.title('Analysis Result')
plt.savefig('/workspace/chart.png', dpi=150, bbox_inches='tight')
plt.close()
print("Chart saved to /workspace/chart.png")
```
</data_analysis>""",
        default_enabled=False,
        version="1.0.0",
        author="Pythinker",
        is_premium=False,
        invocation_type=SkillInvocationType.BOTH,
        trigger_patterns=[
            r"analyze\s+data",
            r"data\s+analysis",
            r"create\s+chart",
            r"visualize",
            r"statistics",
        ],
    ),
    # -------------------------------------------------------------------------
    # Excel Generator Skill
    # -------------------------------------------------------------------------
    Skill(
        id="excel-generator",
        name="Excel Generator",
        description="Create professional Excel spreadsheets with formatting, formulas, and charts. Use for: generating reports as Excel, data exports, spreadsheet creation.",
        category=SkillCategory.DATA_ANALYSIS,
        source=SkillSource.OFFICIAL,
        icon="file-spreadsheet",
        required_tools=[
            "code_execute_python",
            "file_write",
        ],
        optional_tools=[
            "file_read",
            "shell_exec",
        ],
        # Restrict to Python execution to ensure Excel file is generated
        allowed_tools=[
            "code_execute_python",
            "file_write",
            "file_read",
            "shell_exec",
            "message_notify_user",
            "message_ask_user",
            "idle_standby",
        ],
        system_prompt_addition="""<excel_generator>
# Excel Generator Skill - MANDATORY RULES

## CRITICAL: Output Format Requirement
**YOU MUST create an actual .xlsx Excel file using Python code.**
- DO NOT write markdown reports or plain text summaries
- DO NOT provide data as formatted text
- ALWAYS execute Python code to generate a real Excel file

## Workflow
1. **Understand Requirements**: Clarify what data/columns the user needs
2. **Write Python Script**: Use openpyxl or xlsxwriter
3. **Execute Code**: Use code_execute_python to create the .xlsx file
4. **Verify File**: Confirm the Excel file was created successfully
5. **Notify User**: Tell user the file location and what's in it

## Required Python Code Pattern
```python
from openpyxl import Workbook
from openpyxl.styles import Font, Border, Side, Alignment, PatternFill

wb = Workbook()
ws = wb.active
ws.title = "Sheet1"

# Add headers with formatting
headers = ["Column1", "Column2", "Column3"]
header_font = Font(bold=True, color="FFFFFF")
header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")

for col, header in enumerate(headers, 1):
    cell = ws.cell(row=1, column=col, value=header)
    cell.font = header_font
    cell.fill = header_fill

# Add data rows
data = [
    ["Value1", "Value2", "Value3"],
]
for row_idx, row_data in enumerate(data, 2):
    for col_idx, value in enumerate(row_data, 1):
        ws.cell(row=row_idx, column=col_idx, value=value)

# Save file
wb.save("/workspace/output.xlsx")
print("Excel file created: /workspace/output.xlsx")
```

## Formatting Requirements
- Headers: Bold, colored background, centered
- Borders: Thin borders around all cells
- Column widths: Auto-fit or reasonable defaults
- Number formats: Apply appropriate formats (currency, percentage, dates)

## DO NOT
- Write text-only responses explaining data
- Output markdown tables instead of Excel files
- Skip the code execution step
- Forget to save the file to /workspace/
</excel_generator>""",
        default_enabled=False,
        version="1.0.0",
        author="Pythinker",
        is_premium=False,
        invocation_type=SkillInvocationType.BOTH,
        trigger_patterns=[
            r"excel\s+",
            r"spreadsheet",
            r"\.xlsx",
            r"create\s+.*\s+excel",
            r"generate\s+.*\s+excel",
            r"export\s+to\s+excel",
        ],
    ),
    # -------------------------------------------------------------------------
    # Stock Analysis Skill (Premium)
    # -------------------------------------------------------------------------
    Skill(
        id="stock-analysis",
        name="Stock Analysis",
        description="Analyze stocks, financial data, and market trends. Get quotes, charts, and insights.",
        category=SkillCategory.DATA_ANALYSIS,
        source=SkillSource.OFFICIAL,
        icon="trending-up",
        required_tools=[
            "info_search_web",
            "browser_navigate",
            "code_execute_python",
            "file_write",
        ],
        optional_tools=[
            "browser_agent_run",
            "browser_agent_extract",
        ],
        system_prompt_addition="""When analyzing stocks:
- Use yfinance for historical data
- Calculate technical indicators (MA, RSI, MACD)
- Create price charts with matplotlib
- Provide clear buy/sell/hold recommendations with reasoning
- Include risk warnings and disclaimers""",
        default_enabled=False,
        version="1.0.0",
        author="Pythinker",
        is_premium=True,
    ),
    # -------------------------------------------------------------------------
    # Web Pilot Skill (Autonomous browsing)
    # -------------------------------------------------------------------------
    Skill(
        id="web-pilot",
        name="Web Pilot",
        description="Autonomous web browsing with AI. Navigate complex sites, fill forms, and extract data.",
        category=SkillCategory.BROWSER,
        source=SkillSource.OFFICIAL,
        icon="bot",
        required_tools=[
            "browser_agent_run",
            "browser_agent_extract",
        ],
        optional_tools=[
            "browser_navigate",
            "browser_view",
            "file_write",
        ],
        system_prompt_addition="""When using Web Pilot:
- Describe the browsing goal clearly
- Use extract for structured data retrieval
- Handle multi-step workflows automatically""",
        default_enabled=False,
        version="1.0.0",
        author="Pythinker",
        is_premium=False,
    ),
    # -------------------------------------------------------------------------
    # Skill Creator Meta-Skill (for creating custom skills)
    # -------------------------------------------------------------------------
    Skill(
        id="skill-creator",
        name="Skill Creator",
        description="Guide for creating effective skills. Use when users want to create a new skill (or update an existing skill) that extends Pythinker's capabilities with specialized knowledge, workflows, or tool integrations.",
        category=SkillCategory.CUSTOM,
        source=SkillSource.OFFICIAL,
        icon="puzzle",
        required_tools=[
            "message_ask_user",
            "message_notify_user",
            "skill_create",
            "file_write",
            "file_read",
            "shell_exec",
        ],
        optional_tools=[
            "skill_list_user",
            "skill_delete",
            "file_find_by_name",
            "code_execute_python",
        ],
        invocation_type=SkillInvocationType.BOTH,
        trigger_patterns=[
            r"create\s+(?:a\s+)?skill",
            r"make\s+(?:a\s+)?skill",
            r"build\s+(?:a\s+)?skill",
            r"new\s+skill",
        ],
        system_prompt_addition="""<skill_creator>
# Skill Creator

## IMPORTANT: First Step - Load Skill Creator Guide

When a user asks to create a skill, you MUST:

1. **First**, respond with: "I'll help you create the **[skill name]** skill. Let me first review the skill creation guidelines."

2. **Then**, use `file_read` to load and display the skill creator guide:
   ```
   file_read(path="/workspace/skills/skill-creator/SKILL.md")
   ```

   If the file doesn't exist at that path, the guide content is embedded below.

3. **Show the user** that you are reviewing the guidelines (this builds trust and transparency).

4. **Then** proceed with the skill creation process.

---

This skill provides guidance for creating effective skills.

## About Skills

Skills are modular, self-contained packages that extend Pythinker's capabilities by providing specialized knowledge, workflows, and tools. Think of them as "onboarding guides" for specific domains or tasks—they transform the agent from a general-purpose assistant into a specialized agent equipped with procedural knowledge that no model can fully possess.

### What Skills Provide

1. **Specialized workflows** - Multi-step procedures for specific domains
2. **Tool integrations** - Instructions for working with specific file formats or APIs
3. **Domain expertise** - Company-specific knowledge, schemas, business logic
4. **Bundled resources** - Scripts, references, and assets for complex and repetitive tasks

## Core Principles

### Concise is Key

The context window is a public good. Skills share the context window with everything else the agent needs: system prompt, conversation history, other skills' metadata, and the actual user request.

**Default assumption: The agent is already very smart.** Only add context the agent doesn't already have. Challenge each piece of information: "Does the agent really need this explanation?" and "Does this paragraph justify its token cost?"

Prefer concise examples over verbose explanations.

### Set Appropriate Degrees of Freedom

Match the level of specificity to the task's fragility and variability:

- **High freedom (text-based instructions)**: Multiple approaches valid, context-dependent decisions
- **Medium freedom (pseudocode/scripts with parameters)**: Preferred pattern exists, some variation OK
- **Low freedom (specific scripts, few parameters)**: Operations fragile, consistency critical

### Anatomy of a Skill

```
skill-name/
├── SKILL.md (required)
│   ├── YAML frontmatter (name, description)
│   └── Markdown instructions
└── Bundled Resources (optional)
    ├── scripts/      - Executable code (Python/Bash)
    ├── references/   - Documentation loaded as needed
    └── templates/    - Output assets (not loaded into context)
```

**Progressive Disclosure:**
1. **Metadata** - Always in context (~100 words)
2. **SKILL.md body** - When skill triggers (<500 lines)
3. **Bundled resources** - As needed

## Skill Creation Process

### Step 1: Understand the Skill with Concrete Examples

Skip only if usage patterns are already clearly understood.

Use `message_ask_user` to gather concrete examples:

```
message_ask_user(text="What functionality should this skill support? Can you give me examples of how you'd use it?")
```

**CRITICAL: Always use `message_ask_user` tool.** Without it, the system won't pause for user response.

### Step 2: Plan Reusable Skill Contents

Identify reusable resources for each use case:

| Resource Type | When to Use                     | Example                               |
|--------------|----------------------------------|---------------------------------------|
| `scripts/`   | Code rewritten repeatedly       | `rotate_pdf.py` for PDF rotation      |
| `templates/` | Same boilerplate each time      | HTML starter for webapp builder       |
| `references/`| Documentation needed repeatedly | Database schemas, API docs            |

Present the plan and use `message_ask_user` to confirm approach.

### Step 3: Define Skill Configuration

**Frontmatter:**
- `name`: Skill name (2-100 characters)
- `description`: MUST include what skill does AND when to use it
  - Good: "Code review with security focus. Use for: reviewing PRs, auditing security, analyzing code quality."
  - Bad: "Helps with code"

**Icon:** pen-tool, search, code, globe, folder, bar-chart, file-spreadsheet, trending-up, bot, sparkles, wand-2, file-text, puzzle, book-open, zap, shield

**Tools:** Select based on use case:
- **Search:** `info_search_web`
- **Browser:** `browser_navigate`, `browser_view`, `browser_get_content`, `browser_click`, `browser_input`, `browser_agent_run`, `browser_agent_extract`
- **Files:** `file_read`, `file_write`, `file_str_replace`, `file_find_in_content`, `file_find_by_name`
- **Code:** `code_execute`, `code_execute_python`, `code_execute_javascript`
- **Shell:** `shell_exec`
- **Communication:** `message_notify_user`, `message_ask_user`

### Step 4: Write SKILL.md Instructions

**Use imperative form:** "Read the file" not "You should read the file"

**Structure:**
```markdown
# [Skill Name]

## Overview
[One sentence: what this skill does]

## When to Use
[Specific triggers for this skill]

## Workflow
1. [First action]
2. [Second action]
3. [Third action]

## Guidelines
- [Specific guideline 1]
- [Specific guideline 2]

## Output Format
[How results should be presented]

## Example
Input: [example request]
Output: [example response]
```

**Keep under 4000 characters.** Focus on procedural "how to" rather than general knowledge.

### Step 5: Review and Confirm

Present complete skill definition and use `message_ask_user`:

```
message_ask_user(text="Does this skill definition look correct? Reply 'yes' to create it, or tell me what changes you'd like.")
```

**Wait for explicit user approval.**

### Step 6: Create and Deliver the Skill

**Only after user explicitly approves:**

Call `skill_create` with all parameters:

```python
skill_create(
  name="Human Blog Writer",
  description="Generates high-quality blog content with SEO optimization. Use for: writing blog posts, content outlines, SEO-optimized articles.",
  icon="pen-tool",
  required_tools=["file_write", "info_search_web", "browser_get_content"],
  system_prompt_addition="<human_blog_writer>\\n# Human Blog Writer\\n\\n## Overview\\n...\\n</human_blog_writer>",
  scripts=[
    {"filename": "seo_analyzer.py", "content": "# SEO analysis script\\nimport re\\n..."}
  ],
  references=[
    {"filename": "style_guide.md", "content": "# Writing Style Guide\\n..."},
    {"filename": "seo_best_practices.md", "content": "# SEO Best Practices\\n..."}
  ],
  templates=[
    {"filename": "blog_post_outline.md", "content": "# Blog Post Template\\n..."}
  ]
)
```

The system will automatically:
1. Validate skill structure
2. Package into `.skill` file
3. Display skill viewer with options: Add to My Skills, Download, Preview

## Design Patterns

For complex skills, consult these reference guides:
- **Sequential workflows**: `file_read(path="/workspace/skills/skill-creator/references/workflows.md")`
- **Output format patterns**: `file_read(path="/workspace/skills/skill-creator/references/output-patterns.md")`
- **Progressive disclosure**: `file_read(path="/workspace/skills/skill-creator/references/progressive-disclosure-patterns.md")`

### Sequential Workflow
```markdown
## Workflow
1. **Preparation**: [Setup actions]
2. **Execution**: [Main task actions]
3. **Verification**: [Quality checks]
4. **Delivery**: [Output actions]
```

### Conditional Logic
```markdown
## Decision Points
- If [condition A]: [action A]
- If [condition B]: [action B]
- Default: [fallback action]
```

### Progressive Disclosure (for complex skills)
Keep SKILL.md under 500 lines. When a skill supports multiple domains or variants:
- Put core workflow in SKILL.md
- Move variant-specific details to `references/` files
- Reference them clearly: "For AWS deployment, see references/aws.md"

### Output Template
```markdown
## Output Format
### Summary
[1-2 sentence overview]

### Findings
- [Finding 1]
- [Finding 2]

### Recommendations
[Actionable next steps]
```

## Quality Checklist

Before calling `skill_create`, verify:
- [ ] Description says WHAT the skill does AND WHEN to use it
- [ ] SKILL.md body uses imperative form ("Read the file" not "You should read")
- [ ] Skill is under 4000 characters (system_prompt_addition)
- [ ] No generic knowledge the agent already has — only procedural or domain-specific content
- [ ] Scripts tested via `code_execute_python` if included
- [ ] Example input/output pairs included where output quality matters

## CRITICAL RULES

1. **ALWAYS use `message_ask_user` tool** - Never write questions as plain text
2. **Wait for each response** before proceeding to next step
3. **Never create without approval** - Explicit user confirmation required
4. **Be concise** - Context window is a shared resource
5. **One question at a time** - Don't overwhelm with multiple questions
6. **Create bundled resources** - Scripts, references, templates for reusable content
7. **CALL skill_create** at the end - This packages and delivers the skill
8. **Load design pattern references** when the skill involves workflows, output formats, or multi-domain content

</skill_creator>""",
        default_enabled=False,
        version="1.0.0",
        author="Pythinker",
        is_premium=False,
    ),
]


async def seed_official_skills() -> int:
    """Seed official skills into the database.

    Returns:
        Number of skills seeded/updated
    """
    from app.application.services.skill_service import get_skill_service

    skill_service = get_skill_service()

    # Update timestamps for all skills
    now = datetime.now(UTC)
    for skill in OFFICIAL_SKILLS:
        skill.updated_at = now

    return await skill_service.seed_official_skills(OFFICIAL_SKILLS)


def get_skill_tool_map() -> dict[str, list[str]]:
    """Get a mapping of skill IDs to their required tools.

    Returns:
        Dict mapping skill_id to list of tool names
    """
    return {skill.id: skill.required_tools + skill.optional_tools for skill in OFFICIAL_SKILLS}


# Core tools that are always available regardless of skills
CORE_TOOLS = {
    "message_notify_user",
    "message_ask_user",
    "idle_standby",
}
