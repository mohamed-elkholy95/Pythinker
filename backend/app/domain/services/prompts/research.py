# Research-specific prompts for fact-checking and verification

RESEARCH_VERIFICATION_RULES = """
<research_verification>
Research standards for comparison and recommendation tasks:

Source verification:
- Visit official product pages rather than relying on search snippets
- Verify specifications directly from manufacturer documentation
- Mark unverifiable claims explicitly

Cross-validation:
- Gather information from at least 3 sources
- Source priority: official manufacturer > verified reviews > user forums
- Note contradictions between sources and cite the more authoritative

Citations:
- Include source URLs for factual claims
- Mark claims from prior knowledge as "unverified"

Coverage:
- Search for alternatives, competitors, and recent releases
- Include 4-5 options from different brands
- Expand searches with comparison and review queries

Consistency:
- Compare products within the same category and technology type
- Honor user-specified technologies and requirements
- Note price tier differences when relevant
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
- Flag unverified claims
- Structure report with sources section

Domain-aware approach:
- Learn terminology before searching products
- Identify the technology type specified
- Filter results to matching products
- Apply domain-specific definitions
</research_planning>
"""

RESEARCH_EXECUTION_PROMPT = """
<research_execution>
Before delivering results, verify:
- Official pages visited for recommended items
- Category and type claims confirmed from specifications
- Key specs cross-referenced across sources
- Source URLs included for factual claims
- Contradictions flagged
- Alternatives and competitors searched
- Products match user specifications
- Like-for-like comparison (same category, similar tier)

Quality considerations:
- Verify technology type matches user request
- Distinguish marketing from specifications
- Include competitors from major brands
- Confirm professional features if applicable
- Check data freshness
</research_execution>
"""

RESEARCH_SUMMARIZE_PROMPT = """
Structure research results as a clean, professional report:

## Introduction
Brief context of the research scope (1-2 sentences).

## Key Findings
Present findings organized by topic with inline citations [1].
Use **bold** for key terms. Use tables for comparisons.

## Recommendations
Actionable conclusions based on the research.

## References
[1] Source Title - URL
[2] Source Title - URL

AVOID these sections entirely:
- "Verification Status" sections
- "Contradictions" sections
- "Limitations" or "Caveats" sections
- Disclaimers or revision notes

Keep the report CONCISE and FOCUSED on delivering value.
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
]

def is_research_task(message: str) -> bool:
    """Detect if a task requires research-mode verification"""
    message_lower = message.lower()
    return any(indicator in message_lower for indicator in RESEARCH_TASK_INDICATORS)
