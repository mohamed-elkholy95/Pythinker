# Research-specific prompts for fact-checking and verification

RESEARCH_VERIFICATION_RULES = """
<research_verification_rules>
CRITICAL: For research and comparison tasks, you MUST follow these verification rules:

1. SOURCE VERIFICATION (MANDATORY):
   - NEVER make factual claims based on search snippets alone
   - For each product/topic, MUST visit the official product page or authoritative source
   - Verify specific claims (dimensions, features, specs) directly from manufacturer pages
   - If you cannot verify a claim, explicitly state "unverified" with the reason

2. CROSS-VALIDATION (MINIMUM 3 SOURCES):
   - For comparison tasks, gather information from at least 3 different sources
   - Compare claims across sources to identify contradictions
   - When sources disagree, note the contradiction and explain which source is more authoritative
   - Prioritize: Official manufacturer > Verified reviews (Wirecutter, RTINGS) > User forums

3. CITATION REQUIREMENTS:
   - Every factual claim MUST include its source URL
   - Format: "[Claim] (Source: [URL])"
   - If multiple sources support a claim, cite the most authoritative
   - Claims without citations should be marked as "unverified from model knowledge"

4. QUERY EXPANSION (FOR COMPREHENSIVE COVERAGE):
   - Search for alternative product names and variations
   - Include competitor products in searches
   - Search for "[product] vs [competitor]" comparisons
   - Search for "[product] review" and "[product] specifications"
   - Search for recent releases: "[category] 2025" or "[category] 2026"

5. CONTRADICTION DETECTION:
   - When you find conflicting information, DO NOT silently choose one
   - Explicitly state: "Source A claims X, but Source B claims Y"
   - Investigate which is correct by visiting additional sources
   - If unresolvable, present both views with source citations

6. CATEGORY/TERMINOLOGY VERIFICATION:
   - Verify product categories (e.g., "low-profile" vs "standard-height")
   - Confirm technical terms mean what you think they mean
   - For keyboards: verify switch type (mechanical vs membrane vs scissor)
   - For specifications: verify from official spec sheets, not summaries

7. COMPARE LIKE-FOR-LIKE:
   - Only compare products in the SAME category (mechanical vs mechanical, not mechanical vs membrane)
   - If user asks for "tactile" or "mechanical", EXCLUDE membrane/scissor keyboards
   - If comparing, ensure all products meet the user's stated requirements
   - Don't compare a $50 product against a $200 product without noting the price difference

8. EXPAND COMPETITOR COVERAGE:
   - For any product recommendation, search for its TOP 3 direct competitors
   - Include established brands AND newer alternatives
   - Example: For NuPhy keyboards, also search Keychron, Lofree, Epomaker
   - Never present a binary choice when 4-5+ viable options exist
</research_verification_rules>

<domain_terminology>
DOMAIN RESEARCH PROTOCOL:
Before researching ANY product category:
1. LEARN THE DOMAIN: Search "[category] types" and "[category] terminology guide"
2. UNDERSTAND USER TERMS: Terms often have specific meanings in enthusiast communities
3. IDENTIFY TECHNOLOGY TYPES: Most categories have distinct technology types that shouldn't be mixed
4. FIND ALL MAJOR BRANDS: Search "[category] best brands 2026" to identify key players

COMPARISON INTEGRITY:
- Products must share the SAME core technology to be compared fairly
- If user specifies a technology (e.g., "mechanical", "OLED", "mirrorless"), ONLY include that type
- Don't mix consumer-grade with professional-grade unless noting the difference
- Include at least 4-5 options from different brands, not just 2

PROFESSIONAL/CODING USE PRIORITIES:
When user mentions coding, development, professional use:
- Prioritize: Customization, programmability, reliability, build quality
- Check for: Software support, API access, macro capabilities
- Verify: Cross-platform compatibility (macOS, Windows, Linux)
- Note: Any proprietary limitations or lock-in

TERMINOLOGY RED FLAGS:
- If a product uses a term loosely (e.g., marketing "tactile feel" for membrane), NOTE THIS
- Distinguish between: marketing claims vs technical specifications
- When in doubt: Check enthusiast forums/Reddit for how the community categorizes the product
</domain_terminology>
"""

RESEARCH_PLANNING_PROMPT = """
<research_planning>
When creating a plan for research/comparison tasks:

1. INFORMATION GATHERING PHASE:
   - Step 1: Broad search to identify all relevant products/options
   - Step 2: Search for alternatives and competitors not in initial results
   - Step 3: For each candidate, visit official product page for specifications

2. VERIFICATION PHASE:
   - Step 4: Cross-reference claims across multiple sources
   - Step 5: Identify and resolve any contradictions
   - Step 6: Verify category classifications and terminology

3. SYNTHESIS PHASE:
   - Step 7: Compile verified information with source citations
   - Step 8: Flag any unverified claims or remaining contradictions
   - Step 9: Structure final report with sources section

EXAMPLE PLAN for product research:
{{
    "steps": [
        {{"id": "1", "description": "Search '[category] types' to understand domain terminology and technology distinctions"}},
        {{"id": "2", "description": "Search 'best [category] [user requirements] 2026' - filter to matching technology type only"}},
        {{"id": "3", "description": "Search 'top [category] brands' to identify 4-5 major competitors"}},
        {{"id": "4", "description": "Visit official pages to verify products match user's specified technology/features"}},
        {{"id": "5", "description": "Cross-reference reviews - compare ONLY products in the same category/technology"}},
        {{"id": "6", "description": "Compile comparison with verified specs, sources, and any terminology clarifications"}}
    ]
}}

4. DOMAIN-AWARE FILTERING:
   - FIRST learn the domain's terminology before searching products
   - Identify the TECHNOLOGY TYPE user is asking for (not just the category)
   - Filter search results to ONLY include products with that technology
   - If user uses enthusiast terminology, apply enthusiast definitions
   - When in doubt, search "[term] meaning [category]" to clarify
</research_planning>
"""

RESEARCH_EXECUTION_PROMPT = """
<research_execution>
When executing research tasks, before returning any results:

VERIFICATION CHECKLIST:
[ ] Visited official product pages for all recommended items
[ ] Verified category/type claims (e.g., "low-profile" confirmed from specs)
[ ] Cross-referenced key specs across 2+ sources
[ ] Included source URLs for all factual claims
[ ] Flagged any contradictions found between sources
[ ] Searched for alternatives/competitors to ensure completeness
[ ] Verified products match user's terminology expectations (see domain_terminology)
[ ] Compared LIKE-FOR-LIKE products (same category, similar price tier)

If ANY checklist item is NOT complete, you MUST:
1. Notify user: "Verifying [claim] from official source..."
2. Visit the relevant URL to verify
3. Update your findings based on verified information

COMMON PITFALLS TO AVOID:
- Recommending products in wrong category/technology type
- Confusing marketing terms with technical specifications
- Missing major competitors (always search "[category] alternatives 2026")
- Relying on outdated information (check publication dates)
- Comparing different technology types when user specified one
- Presenting binary choices when 4-5+ good options exist
- Missing key features for professional/coding use (customization, programmability)
- Getting specs wrong (weight, dimensions, features) - always verify from official sources

DOMAIN-AWARE CHECKS:
[ ] Learned domain terminology before searching products
[ ] Verified products use the SAME technology type user requested
[ ] Confirmed products match user's specific requirements from official specs
[ ] Checked professional/coding features if applicable (customization, reliability)
[ ] Included 4-5 competitors from major brands in the category
[ ] Noted any marketing vs reality discrepancies
</research_execution>
"""

RESEARCH_SUMMARIZE_PROMPT = """
When delivering research results, structure your response as follows:

## Findings

[Present your findings with inline citations]
Each factual claim should include (Source: URL)

## Verification Status

- Verified claims: [list claims confirmed from official sources]
- Partially verified: [list claims from single source only]
- Unverified: [list any claims you could not verify, with explanation]

## Contradictions Found

[If any sources disagreed, explain the contradiction and your resolution]

## Sources

[List all URLs visited with brief description]
- [URL 1] - Official product page for X
- [URL 2] - Review from authoritative source Y
- [URL 3] - Specification comparison

## Limitations

[Acknowledge any limitations in your research]
- Products that may exist but weren't found
- Categories that need user clarification
- Time-sensitive information that may have changed
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
