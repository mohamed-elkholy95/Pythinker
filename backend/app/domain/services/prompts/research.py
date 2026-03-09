# Research-specific prompts for fact-checking and verification

RESEARCH_VERIFICATION_RULES = """
<research_verification>
Research standards for comparison and recommendation tasks:

Source verification:
- Visit official product pages rather than relying on search snippets
- Verify specifications directly from manufacturer documentation
- Omit unverifiable claims rather than adding disclaimers
- NEVER fabricate benchmark scores, pricing, or statistics

Cross-validation:
- Gather information from at least 5-7 diverse sources
- Source priority: official manufacturer > benchmark leaderboards > verified reviews > user forums
- Note contradictions between sources and cite the more authoritative
- Cross-reference numeric claims (prices, scores, limits) across multiple sources

Conflict resolution:
- When sources contradict: cite BOTH sources, prefer the more official/recent one, and note the discrepancy
- When sources disagree on "best": present multiple perspectives in a comparison table rather than picking one
- For time-sensitive data (pricing, benchmarks): note the retrieval date and flag sources older than 3 months
- Check whether discrepancies are due to different methodologies, versions, or measurement criteria
- Source dates checked for recency — prefer data from the current year

Citations:
- Include source URLs for ALL factual claims
- Do not include claims that cannot be verified
- Every benchmark score MUST have a source URL

Coverage:
- Search for alternatives, competitors, and recent releases
- Include 5-8 options from different providers/brands
- Expand searches with comparison, benchmark, and review queries
- Search SPECIFICALLY for benchmark leaderboards and performance comparison sites

Consistency:
- Compare products within the same category and technology type
- Honor user-specified technologies and requirements
- Note price tier differences when relevant
- Include BOTH free-tier AND paid pricing when comparing services
</research_verification>

<domain_awareness>
Research approach:
- Learn domain terminology before searching products
- Understand terms as used in the relevant community
- Identify distinct technology types within the category
- Search for major brands and alternatives

Comparison integrity:
- Products must share the same core technology for fair comparison
- Include only products matching user specifications
- Distinguish consumer and professional grades when relevant

Professional use considerations:
- Customization, programmability, reliability, and build quality
- Software support and cross-platform compatibility
- Note proprietary limitations

Terminology clarity:
- Distinguish marketing claims from technical specifications
- Note when terms are used loosely or inconsistently
</domain_awareness>

<benchmark_research>
CRITICAL: When researching benchmarks, performance, or comparisons:

Benchmark source hunting:
- Search for "[topic] benchmark leaderboard" and "[topic] performance comparison"
- Look for established benchmark sites (e.g., Berkeley Function Calling Leaderboard, LMSYS, HuggingFace leaderboards)
- Search for "[product] benchmark scores [current year]"
- Find industry-specific evaluation frameworks

Benchmark verification:
- Visit the actual benchmark leaderboard pages
- Extract scores directly from benchmark tables
- Note the benchmark methodology and date
- If no benchmark data exists, state "No benchmark data available" - NEVER fabricate scores

Pricing research depth:
- Visit official pricing pages, not just overview pages
- Extract BOTH free-tier limits AND post-free-tier costs
- Note per-unit pricing (per token, per request, per GB, etc.)
- Calculate example costs for typical usage scenarios
- Search for "[product] pricing [current year]" to find current rates

Multi-tier comparison:
- When comparing services with free tiers:
  * Document what's included in free tier (limits, restrictions)
  * Document paid tier pricing (per-unit costs)
  * Compare across BOTH dimensions
- Do not limit research to only free-tier-only products
- Include products that have free tiers AS WELL AS paid options
</benchmark_research>
"""

RESEARCH_PLANNING_PROMPT = """
<research_planning>
Research task structure:

Information gathering:
- Broad search for relevant options
- Search for alternatives and competitors
- Visit official pages for specifications

Verification:
- Cross-reference claims across sources
- Resolve contradictions
- Verify terminology and classifications

Synthesis:
- Compile verified information with citations
- Structure report with references section

Domain-aware approach:
- Learn terminology before searching products
- Identify the technology type specified
- Filter results to matching products
- Apply domain-specific definitions
</research_planning>
"""

RESEARCH_EXECUTION_PROMPT = """
<research_execution>
FIRST: Send an acknowledgment message (1-2 sentences) stating what research you will conduct.
Example: "Understood. I will research this and provide a structured report with citations."
Keep it concise (max ~25 words).
Do NOT paste or restate the user's full prompt.
Do NOT copy the user's numbered requirement list into the acknowledgment.

THEN: Execute the research following this MANDATORY workflow:

## Tool Guide (All Browser-Visible)
| Tool | Use For | Live Preview |
|------|---------|-----|
| `info_search_web` | Search queries | Yes |
| `search` | Fast HTTP fetch for known URLs | No |
| `browser_navigate` | Navigate to URL (with optional intent/focus) | Yes |
| `browsing` | Complex multi-step browser tasks | Yes |

## Step 1: BROAD Search (visible in live preview)
- Use `info_search_web` to find relevant sources
- User can watch the search happen in the browser
- Note all URLs returned in results
- Run MULTIPLE search queries:
  * Main topic search
  * Benchmark/leaderboard search: "[topic] benchmark leaderboard [year]"
  * Pricing search: "[topic] pricing comparison [year]"
  * Review/analysis search: "[topic] analysis review [year]"

## Step 2: BROWSE PAGES WITH BROWSER (CRITICAL - DO NOT SKIP)
- You MUST use `browser_navigate` to visit at least 5 different URLs
- `browser_navigate` gives you FULL page content — search snippets are 200-word summaries
- After Step 1 search, pick the top 5-8 most relevant URLs and visit each one
- For each URL: call `browser_navigate` with url and focus describing what to extract
- Do NOT rely on `wide_research` or `info_search_web` snippets for your report
- Search snippets are incomplete and outdated — ALWAYS verify by browsing the actual page
- Visit at least 5-8 authoritative sources including:
  * Official product/service pages
  * Benchmark leaderboard sites
  * Pricing pages
  * Independent review/analysis sites
- NEVER write a report using only search API results without browsing actual pages

## Step 3: DEEP DIVE on Benchmarks & Pricing
- Visit SPECIFIC benchmark leaderboard URLs
- Extract actual scores from benchmark tables
- Visit official pricing pages (not just overview pages)
- Extract per-unit costs (per token, per request, etc.)
- If benchmark data not found, explicitly state "No benchmark data available"
- NEVER fabricate scores or pricing - only report what you actually found

## Conflict Resolution Protocol
When you encounter contradictory information across sources:
- **Contradicting facts**: Cite BOTH sources and state the discrepancy explicitly. Prefer the more official or recent source but acknowledge the alternative.
- **Disagreement on "best"**: Do NOT pick a winner — present a weighted comparison table showing how each option performs on different criteria.
- **Stale data**: Note the retrieval date for time-sensitive claims (pricing, benchmarks, availability). Flag any source older than 3 months.
- **Methodology differences**: Note when different benchmark scores stem from different test methodologies or versions.

## Step 4: Compile with Citations
- Base your report on ACTUAL extracted page content
- Include inline citations [1], [2] for ALL factual claims
- Every benchmark score MUST have a citation
- Every price point MUST have a citation
- Add comprehensive References section with all visited URLs
- For comparison tasks: structure key metrics in a markdown table (items as rows,
  numeric values in cells). The system will auto-generate an interactive Plotly
  chart from comparison tables—prefer Plotly-friendly tables for user value.

Before delivering results, verify:
- You actually VISITED pages (not just searched)
- Official pages visited for recommended items
- Key specs extracted from actual page content
- Source URLs are from pages you browsed
- Information is current (check page dates) — flag sources older than 6 months
- Benchmark scores have source citations
- Pricing data has source citations
- At least 4-5 references in the final report
- Conflicting claims are noted with both sources cited
- When sources disagree on rankings/ratings, present a comparison table with multiple perspectives

CRITICAL: Never write a research report based only on:
- Search result snippets
- Your training knowledge
- Assumptions about products/topics

CRITICAL: For benchmark/performance claims:
- If you cannot find benchmark data, state "No benchmark data found"
- NEVER invent benchmark scores
- NEVER estimate benchmark scores
- Only report scores you extracted from actual benchmark pages

You MUST browse actual pages to extract current, accurate information.
</research_execution>
"""

DECOMPOSITION_PROMPT = """
Decompose the following research question into independent sub-questions that
can each be answered with a single web search.

## Rules
1. Each sub-question must be independently searchable (no dependencies between them).
2. Each sub-question must focus on a single topic or entity.
3. Do NOT create compound questions (no "and", "as well as", "in addition to").
4. Return between 2 and 6 sub-questions.
5. Keep each sub-question concise (3-50 words).
6. Ensure full coverage — the union of sub-question answers should address
   the original question completely.

## Examples

**Question**: "Compare the pricing and features of GPT-4, Claude, and Gemini"
**sub_questions**:
- "What are the pricing plans and costs for GPT-4?"
- "What are the key features and capabilities of GPT-4?"
- "What are the pricing plans and costs for Claude?"
- "What are the key features and capabilities of Claude?"
- "What are the pricing plans and costs for Gemini?"
- "What are the key features and capabilities of Gemini?"

**Question**: "What are the best Python web frameworks in 2026?"
**sub_questions**:
- "What are the most popular Python web frameworks in 2026?"
- "What are the performance benchmarks for Python web frameworks?"
- "What are the key differences between FastAPI Django and Flask?"

## Question to decompose
{question}

Return your answer as a JSON object with a single key "sub_questions" containing
a list of strings.
"""

# Detection patterns for research-type tasks
RESEARCH_TASK_INDICATORS = [
    "compare",
    "comparison",
    "best",
    "recommend",
    "alternatives",
    "vs",
    "versus",
    "which",
    "research",
    "find",
    "options",
    "review",
    "analysis",
    "report",
    "detailed",
    "comprehensive",
    "thorough",
    "investigate",
    "explore",
    "study",
    "search for",
    "look into",
    "gather information",
    "everything about",
    "all about",
    "latest",
    "current state",
    "overview",
    "summary",
    "insights",
]


def is_research_task(message: str) -> bool:
    """Detect if a task requires research-mode verification"""
    message_lower = message.lower()
    return any(indicator in message_lower for indicator in RESEARCH_TASK_INDICATORS)
