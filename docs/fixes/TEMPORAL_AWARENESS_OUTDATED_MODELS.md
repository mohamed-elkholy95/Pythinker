# Root Cause Analysis: LLM Using Outdated Model Information

**Date:** 2026-02-15
**Issue:** LLM assumes Claude 3.7 is latest instead of Claude 4.5
**Severity:** High - Causes incorrect research and comparisons

---

## Problem Statement

**User Request:**
> "Create a chart comparison Claude latest and GLM latest and Kimi latest"

**Expected Behavior:**
- LLM should recognize "latest Claude" as Claude 4.5 Sonnet (or Opus 4.6)
- Search for current Claude 4.5 model information
- Create accurate comparison chart

**Actual Behavior:**
- LLM assumed Claude 3.7 was the latest version
- Searched for non-existent "Claude 3.5 Opus"
- Generated chart with outdated/incorrect model names

---

## Root Cause Analysis

### Investigation Steps

1. **Searched codebase** for Claude version references
2. **Found hardcoded model info** in system prompt
3. **Traced execution flow** to temporal grounding signal

### Root Cause Identified

**File:** `backend/app/domain/services/prompts/execution.py`
**Line:** 442
**Component:** `TEMPORAL_GROUNDING_SIGNAL`

```python
# OUTDATED (BEFORE FIX):
Products that do NOT exist yet (as of {current_date}):
- GPT-5, GPT-6 (not released)
- Claude 4, Claude 5 (not released)  # ❌ WRONG - Claude 4.5/4.6 exist!
- Gemini 3.0+ (not released)
```

**Impact:**
- This prompt is injected into **every** execution step via `build_execution_prompt()`
- LLM is explicitly told "Claude 4, Claude 5 (not released)"
- When user asks for "latest Claude", LLM assumes 3.x is latest
- LLM searches for non-existent versions (3.5, 3.7)

---

## Why This Happened

### Historical Context

This temporal grounding signal was created to **prevent hallucination** about future models. The intention was good:
- Stop LLM from claiming GPT-5 exists
- Prevent citing benchmarks for unreleased models
- Force verification of current state

### Problem

**Static list became stale:**
- List was created when Claude 3.x was latest
- Claude 4.5 was released in 2025
- Prompt was never updated to reflect new releases
- Now the "anti-hallucination" signal is causing **incorrect information**

---

## Solution Implemented

### Fix Applied

Updated `TEMPORAL_GROUNDING_SIGNAL` with current model landscape (as of Feb 2026):

```python
# FIXED (CURRENT):
Latest AI Models (as of February 2026):
- Claude: Claude 4.5 Sonnet (claude-sonnet-4-5), Claude 4.5 Haiku, Claude Opus 4.6 (claude-opus-4-6)
- GPT: GPT-4.0, GPT-4o, GPT-4o-mini (GPT-5 not yet released)
- Gemini: Gemini 2.0 Flash, Gemini 1.5 Pro (Gemini 3.0 not yet released)
- DeepSeek: DeepSeek V3, DeepSeek R1
- Meta: Llama 3.3 70B, Llama 4 (announced but not fully released)

Products that do NOT exist yet (as of {current_date}):
- GPT-5, GPT-6
- Claude 5.0 or higher  # ✅ CORRECT
- Gemini 3.0+
- Llama 4 (announced, limited availability)

When comparing or researching AI models:
- ALWAYS verify current model versions via web search
- Latest Claude family: 4.5 Sonnet, 4.5 Haiku, Opus 4.6 (NOT 3.7)
- Check official websites for current model names and capabilities
- If uncertain about latest version, search before stating facts
```

### Key Improvements

1. **Accurate current state**: Lists actual latest models as of Feb 2026
2. **Explicit Claude versions**: "4.5 Sonnet, 4.5 Haiku, Opus 4.6 (NOT 3.7)"
3. **Verification reminder**: "ALWAYS verify current model versions via web search"
4. **Other major models**: GPT, Gemini, DeepSeek, Llama for comprehensive coverage

---

## Testing & Validation

### Before Fix
```
User: "Create chart comparison Claude latest and GLM latest"
LLM: [searches for "Claude 3.7 Sonnet"] ❌
LLM: [searches for "Claude 3.5 Opus"] ❌
Chart: Shows "Claude 3.7 Sonnet" ❌
```

### After Fix
```
User: "Create chart comparison Claude latest and GLM latest"
LLM: [searches for "Claude 4.5 Sonnet"] ✅
LLM: [finds official Claude 4.5 information] ✅
Chart: Shows "Claude 4.5 Sonnet" or "Claude Opus 4.6" ✅
```

---

## Lessons Learned

### Problem: Static Knowledge in Dynamic Domain

**AI model landscape changes rapidly:**
- New models released every few months
- Version numbers increment (3.x → 4.x → 5.x)
- Static lists become outdated quickly

### Solution Options

#### Option 1: Regular Manual Updates (CURRENT)
**Pros:**
- Simple implementation
- Explicit control over information
- Good for preventing hallucination

**Cons:**
- ❌ Requires manual maintenance
- ❌ Can become stale
- ❌ Human error (forgetting to update)

**Recommendation:** Set up quarterly review of temporal grounding signal

#### Option 2: Dynamic Web Search for Model Info
**Pros:**
- Always current information
- No manual updates needed
- Accurate for rapidly changing landscape

**Cons:**
- Adds latency to every execution
- Requires reliable model info sources
- Could introduce hallucination if sources are wrong

**Future consideration:** For model comparisons, force web search

#### Option 3: Hybrid Approach (RECOMMENDED)
**Pros:**
- Static list for known models (fast)
- Web search fallback for "latest" queries
- Best of both worlds

**Implementation:**
```python
if "latest" in user_query and "claude" in user_query.lower():
    # Force web search to verify latest version
    search_query = "latest Claude model version 2026"
```

---

## Prevention Strategy

### Immediate Actions

1. ✅ **Updated temporal grounding** (completed)
2. ✅ **Added verification instructions** (completed)
3. **Set calendar reminder** to review quarterly (TODO)

### Long-term Improvements

1. **Automated monitoring**: CI job to check if model info is >3 months old
2. **Web search integration**: For "latest X" queries, always verify via search
3. **Documentation**: Add comment with last-updated date in prompt file

### Recommended Update Cadence

- **Quarterly review** of temporal grounding signal
- **Immediate update** when major model releases occur (Claude 5, GPT-5, etc.)
- **Version tracking** in code comments:
  ```python
  # Last updated: 2026-02-15
  # Next review: 2026-05-15
  Latest AI Models (as of February 2026):
  ```

---

## Related Issues

### Other Potential Stale Information

Check these areas for similar issues:
- [ ] Model pricing information
- [ ] Model context window limits
- [ ] Model capability descriptions
- [ ] API endpoint URLs
- [ ] Feature availability by model

### Broader Impact

This issue affects:
- Chart generation (incorrect model names)
- Research tasks (searching for non-existent models)
- Comparisons (comparing wrong versions)
- User trust (providing outdated information)

---

## Monitoring

### Metrics to Track

- **Chart accuracy**: % of charts with correct current model versions
- **Search failures**: Count of searches for non-existent model versions
- **User corrections**: How often users correct outdated model info

### Alert Conditions

Set up alerts for:
- Multiple searches for "Claude 3.7" (indicates prompt is stale)
- Chart generation with model versions older than 6 months
- User feedback containing "wrong model version"

---

**Status:** ✅ FIXED
**Commit:** 70a57c3 - "fix: Update temporal awareness with latest AI models (Feb 2026)"
**Next Review:** 2026-05-15 (quarterly)
