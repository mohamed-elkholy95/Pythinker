"""Prompts for the CriticAgent that reviews outputs before delivery.

The critic agent provides quality assurance by:
- Verifying output accuracy and completeness
- Checking for hallucinations or unsupported claims
- Ensuring alignment with user requirements
- Validating code correctness (if applicable)
"""

CRITIC_SYSTEM_PROMPT = """You are a critical reviewer responsible for quality assurance of AI-generated outputs.

Your role is to:
1. Verify the output addresses the user's original request
2. Check for accuracy, completeness, and factual correctness
3. Identify potential hallucinations or unsupported claims
4. Validate code correctness and security (if code is present)
5. Ensure the output format matches requirements

Be thorough but fair. Not every output needs revision - approve good work.

## Review Guidelines

### For Research/Information Tasks:
- Are claims supported by evidence found during research?
- Is the information current and accurate?
- Are sources properly attributed?
- Is anything important missing?

### For Code Tasks:
- Does the code compile/run correctly?
- Are there security vulnerabilities (injection, XSS, etc.)?
- Is error handling appropriate?
- Does it follow the language's best practices?

### For Writing Tasks:
- Is the tone appropriate for the audience?
- Is the structure logical and clear?
- Are there grammatical or spelling errors?
- Is the length appropriate?

## Response Format

You must respond with a JSON object containing:
- verdict: "approve" | "revise" | "reject"
- confidence: float 0.0-1.0 (how confident in the verdict)
- issues: list of identified issues (empty if approved)
- suggestions: list of improvement suggestions
- summary: brief explanation of the verdict

Example:
{
    "verdict": "revise",
    "confidence": 0.85,
    "issues": [
        "Code lacks input validation on user email field",
        "Missing error handling for network failures"
    ],
    "suggestions": [
        "Add email format validation using regex",
        "Wrap API calls in try-catch with retry logic"
    ],
    "summary": "The code functionally meets requirements but has security and reliability gaps that should be addressed before delivery."
}
"""

REVIEW_OUTPUT_PROMPT = """Review the following output that was generated in response to a user request.

## Original User Request:
{user_request}

## Task Context:
{task_context}

## Generated Output:
{output}

## Files Created/Modified:
{files}

---

Carefully review this output against the original request. Consider:
1. Does it fully address what the user asked for?
2. Is the output accurate and free of hallucinations?
3. Is anything important missing or incomplete?
4. Are there any quality issues that should be fixed?

Provide your review as a JSON object with verdict, confidence, issues, suggestions, and summary."""


REVIEW_CODE_PROMPT = """Review the following code output for correctness and security.

## Original Request:
{user_request}

## Code Output:
```{language}
{code}
```

## Context:
{context}

---

Review this code for:
1. **Correctness**: Does it implement the requested functionality?
2. **Security**: Any vulnerabilities (injection, XSS, hardcoded secrets, etc.)?
3. **Best Practices**: Follows language conventions and patterns?
4. **Error Handling**: Appropriate handling of edge cases and errors?
5. **Completeness**: Any missing functionality or TODOs?

Provide your review as a JSON object with verdict, confidence, issues, suggestions, and summary."""


REVIEW_RESEARCH_PROMPT = """Review the following research output for accuracy and completeness.

## Original Research Request:
{user_request}

## Research Output:
{output}

## Sources Used:
{sources}

---

Review this research for:
1. **Accuracy**: Are claims factually correct and well-supported?
2. **Completeness**: Does it cover all aspects of the request?
3. **Recency**: Is the information current (if time-sensitive)?
4. **Balance**: Are multiple perspectives represented (if applicable)?
5. **Attribution**: Are sources properly credited?

Provide your review as a JSON object with verdict, confidence, issues, suggestions, and summary."""


REVISION_PROMPT = """Based on the following review, revise the output to address the identified issues.

## Original Output:
{original_output}

## Review Feedback:
Verdict: {verdict}
Issues:
{issues}

Suggestions:
{suggestions}

Reviewer Summary: {summary}

---

Provide the REVISED OUTPUT ONLY. Do not include:
- "Changes Made:" sections
- Explanations of what was changed
- Revision notes or disclaimers
- Meta-commentary about the revision process

The output should read as if it were the original - clean and professional."""


# Pre-delivery fact checking prompt for hallucination prevention
FACT_CHECK_PROMPT = """Perform a fact-checking analysis on the following output before delivery.

## Output to Verify:
{output}

## Task Context:
{task_context}

---

## Fact-Checking Process:

1. **Claim Extraction**: Identify all factual claims made in the output.

2. **Verification Status**: For each claim, categorize as:
   - VERIFIED: Evidence supports this claim (cite source)
   - UNVERIFIED: Could not find supporting evidence
   - CONTRADICTED: Evidence contradicts this claim
   - OPINION: This is an opinion, not a factual claim

3. **Red Flags**: Check for common hallucination patterns:
   - Specific statistics without sources
   - Quotes without attribution
   - Historical dates or events
   - Technical specifications
   - Current prices or availability
   - Named individuals or organizations

Respond with a JSON object:
{{
    "claims_analyzed": int,
    "verified": int,
    "unverified": int,
    "contradicted": int,
    "red_flags": ["list of specific concerns"],
    "confidence_score": float 0.0-1.0,
    "recommendation": "deliver" | "needs_verification" | "reject",
    "issues_to_fix": ["list of specific claims to verify or remove - NOT disclaimers to add"]
}}

NOTE: Never recommend adding disclaimers or caveats to the output. Either the content is accurate enough to deliver, or specific claims need verification/removal."""


# Structured feedback template for actionable improvements
STRUCTURED_FEEDBACK_PROMPT = """Provide structured, actionable feedback for improving this output.

## Output:
{output}

## Original Request:
{user_request}

## Review Focus Areas:
{focus_areas}

---

Provide feedback in the following structured format:

{{
    "overall_quality": float 0.0-1.0,
    "strengths": ["list of things done well"],
    "improvements": [
        {{
            "category": "accuracy|completeness|clarity|security|performance",
            "severity": "critical|major|minor|suggestion",
            "issue": "specific issue description",
            "fix": "how to fix it",
            "location": "where in the output (line/section/reference)"
        }}
    ],
    "missing_elements": ["list of things that should be added"],
    "priority_order": ["ordered list of improvement IDs by importance"]
}}"""


# 5-Check Framework Prompt (Phase 3/5 Enhancement)
# Addresses data asymmetry, comparison consistency, and pre-verification issues
FIVE_CHECK_PROMPT = """Perform a comprehensive 5-check review on this output.

## Output to Review:
{output}

## Original User Request:
{user_request}

## Available Sources/Context:
{sources_context}

## Pre-Verification Issues (Automated Checks)
{pre_verification_issues}

---

## THE 5-CHECK FRAMEWORK

IMPORTANT: The "Pre-Verification Issues" section above contains issues detected by automated
systems BEFORE this LLM review. These are FACTS, not opinions. If the pre-verification found:
- URL does not exist → the URL is definitively fabricated
- Number not in source → the metric was not found in any visited source
- Entity claim unverified → no source contained information about this entity

You MUST incorporate these pre-verified issues into your check results. Do NOT override them.

Perform each check carefully and provide detailed findings:

### CHECK 1: FACTUAL ACCURACY
Are all claims verifiable and accurate?
- Identify specific factual claims (numbers, dates, statistics, benchmarks)
- Determine if each claim is supported by evidence
- Flag unsupported or potentially hallucinated claims

### CHECK 2: COMPLETENESS
Does the output fully address the user's request?
- Compare output against all aspects of the original request
- Identify any missing components or partially addressed points
- Check if conclusions/summaries capture all findings

### CHECK 3: INTERNAL CONSISTENCY
Is the output internally consistent?
- Check for contradictions between statements
- Verify numbers/statistics are used consistently throughout
- Ensure claims in different sections don't conflict

### CHECK 4: DATA SYMMETRY (CRITICAL FOR COMPARISONS)
Are comparisons using equivalent metrics?

This is CRITICAL. When comparing items, they MUST be evaluated using the same criteria.

EXAMPLES OF ASYMMETRY TO DETECT:
❌ "Model A: 92.0% on MMLU" vs "Model B: Strong reasoning capabilities"
   - Item A has quantitative metric (92.0%)
   - Item B has qualitative description (no number)
   - This is ASYMMETRIC and UNACCEPTABLE

❌ "Framework X: 2.3ms response time" vs "Framework Y: Easy to configure"
   - Item X has performance metric
   - Item Y has usability description
   - Comparing different dimensions

✅ SYMMETRIC COMPARISONS:
   "Model A: 92.0% on MMLU" vs "Model B: 88.5% on MMLU" (same metric)
   "Model A: 92.0% on MMLU" vs "Model B: MMLU score not published" (explicitly notes missing data)

For EACH comparison in the output, verify:
1. Are the same metrics/criteria applied to all items?
2. If a metric exists for one item, is it provided for all items?
3. Are qualitative and quantitative descriptions mixed inappropriately?

### CHECK 5: SOURCE GROUNDING
Is the output grounded in actual sources/tools?
- Are factual claims traceable to sources used?
- Were claims inferred beyond what sources state?
- Are there claims that appear to come from nowhere?

---

## Response Format

Respond with this JSON structure:
{{
    "accuracy_check": {{
        "passed": boolean,
        "severity": "critical|major|minor|pass",
        "issues": ["list of accuracy issues"],
        "confidence": 0.0-1.0,
        "remediation": "how to fix, or null if passed"
    }},
    "completeness_check": {{
        "passed": boolean,
        "severity": "critical|major|minor|pass",
        "issues": ["list of completeness issues"],
        "confidence": 0.0-1.0,
        "remediation": "how to fix, or null if passed"
    }},
    "consistency_check": {{
        "passed": boolean,
        "severity": "critical|major|minor|pass",
        "issues": ["list of consistency issues"],
        "confidence": 0.0-1.0,
        "remediation": "how to fix, or null if passed"
    }},
    "symmetry_check": {{
        "passed": boolean,
        "severity": "critical|major|minor|pass",
        "issues": ["list of data asymmetry issues found"],
        "confidence": 0.0-1.0,
        "remediation": "how to fix, or null if passed"
    }},
    "grounding_check": {{
        "passed": boolean,
        "severity": "critical|major|minor|pass",
        "issues": ["list of grounding issues"],
        "confidence": 0.0-1.0,
        "remediation": "how to fix, or null if passed"
    }},
    "overall_passed": boolean,
    "overall_confidence": 0.0-1.0,
    "critical_issues": ["list of most critical issues to address first"],
    "asymmetry_issues": [
        {{
            "item_a": "first item name",
            "item_a_metric_type": "quantitative|qualitative|none",
            "item_b": "second item name",
            "item_b_metric_type": "quantitative|qualitative|none",
            "context": "the comparison being made",
            "suggestion": "how to make this symmetric"
        }}
    ]
}}"""


# Quick validation prompt for simple checks
QUICK_VALIDATE_PROMPT = """Perform a quick validation check on this output.

## Output:
{output}

## Validation Criteria:
- Addresses the user request: {user_request}
- Expected format: {expected_format}
- Must include: {required_elements}

Quick check (respond with JSON):
{{
    "passes_validation": boolean,
    "missing_requirements": ["list of any missing required elements"],
    "format_issues": ["list of any format problems"],
    "quick_fix": "single sentence describing fix needed, or null if passes"
}}"""
