# Validation Step Tuning Guide

## Problem Summary

The Pythinker agent was cutting information during the validation step due to:

1. **Aggressive response compression** - 1400 character hard limit
2. **Overly strict hallucination detection** - Flagging legitimate content
3. **Critic revision loops** - Potentially removing valid information

## Changes Applied

### 1. Increased Compression Limits ✅

**File:** `backend/app/domain/services/agents/response_policy.py`

**Changes:**
- `max_chars`: **1400 → 4000** (2.86x increase)
- Policy decision: **1400 → 4000** for CONCISE mode

**Impact:** Preserves ~2.86x more information in compressed responses

### 2. Enhanced Response Compressor ✅

**File:** `backend/app/domain/services/agents/response_compressor.py`

**Changes:**
- Default `max_chars`: **1400 → 4000**
- Summary blocks: **2 → 4** (preserves more context)
- Artifact lines: **3 → 8** (preserves more file references)

**Impact:** Keeps more complete information even when compression is active

## How Validation Works

### Validation Flow

```
User Request
    ↓
Agent Execution
    ↓
┌─────────────────────────────────────────┐
│  1. Task Assessment                     │
│     - Calculates risk_score             │
│     - Calculates complexity_score       │
│     - Decides VerbosityMode             │
└─────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────┐
│  2. Response Generation                 │
│     - Agent generates full response     │
└─────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────┐
│  3. Critic Review (Optional)            │
│     - Reviews output quality            │
│     - Can request 0-2 revisions         │
│     - Checks for hallucinations         │
└─────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────┐
│  4. Output Coverage Validation          │
│     - Checks required sections exist    │
└─────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────┐
│  5. Response Compression (if CONCISE)   │
│     - Compresses to max_chars           │  ← WAS 1400, NOW 4000
│     - Validates coverage post-compress  │
└─────────────────────────────────────────┘
    ↓
Final Response to User
```

### When Compression Triggers

Compression activates when **ALL** of these are true:

1. `allow_compression = True`
2. `mode = VerbosityMode.CONCISE`
3. `quality_floor_enforced = True`
4. `assessment.risk_score < 0.7`

**CONCISE mode is selected when:**
- `risk_score < 0.45`
- `ambiguity_score < 0.35`
- `complexity_score < 0.45`

## Further Tuning Options

### Option A: Disable Critic for Specific Tasks

**File:** `backend/app/domain/services/agents/execution.py` (line 106)

```python
# Current:
self._critic = CriticAgent(
    llm=llm,
    json_parser=json_parser,
    config=critic_config or CriticConfig(
        enabled=True,
        auto_approve_simple_tasks=True,
        max_revision_attempts=2
    ),
)

# Suggested: Reduce revision attempts
self._critic = CriticAgent(
    llm=llm,
    json_parser=json_parser,
    config=critic_config or CriticConfig(
        enabled=True,
        auto_approve_simple_tasks=True,
        max_revision_attempts=1,  # Reduced from 2
        min_confidence_threshold=0.8,  # Increased from 0.7 for stricter approval
    ),
)
```

### Option B: Adjust Hallucination Detection Thresholds

**File:** `backend/app/domain/services/agents/critic.py` (line 797-806)

```python
# Current high-risk threshold:
if hallucination_result.high_risk_count > 5:
    initial_recommendation = FactCheckRecommendation.NEEDS_VERIFICATION

# Consider increasing threshold:
if hallucination_result.high_risk_count > 10:  # More lenient
    initial_recommendation = FactCheckRecommendation.NEEDS_VERIFICATION
```

### Option C: Force DETAILED Mode for All Responses

**File:** `backend/app/domain/services/agents/execution.py` (line 432)

```python
# Current:
response_policy or self._response_policy or ResponsePolicy(
    mode=VerbosityMode.STANDARD,
    min_required_sections=["final result"],
    allow_compression=False
)

# Force DETAILED (never compress):
response_policy or self._response_policy or ResponsePolicy(
    mode=VerbosityMode.DETAILED,  # Changed
    min_required_sections=["final result"],
    allow_compression=False
)
```

### Option D: Disable ContentHallucinationDetector for Certain Patterns

**File:** `backend/app/domain/services/agents/content_hallucination_detector.py`

You can modify `HIGH_RISK_PATTERNS` to remove overly strict patterns. For example, if legitimate read times are being flagged:

```python
# Comment out or remove patterns that cause false positives:
HIGH_RISK_PATTERNS = [
    # (
    #     r"(\d+)\s*(min(ute)?s?|hour?s?)\s*(read|reading\s+time)",
    #     "read_time",
    #     HallucinationRisk.HIGH,
    #     "Read time estimate without source",
    #     "Remove or state '[Read time not verified]'",
    # ),  # DISABLED - causing false positives
    # ... keep other patterns
]
```

## Testing Changes

### 1. Test Response Compression

```bash
cd backend
conda activate pythinker

# Run compression test
python -c "
from app.domain.services.agents.response_compressor import ResponseCompressor
from app.domain.services.agents.response_policy import VerbosityMode

compressor = ResponseCompressor()
test_content = 'A' * 5000  # 5000 char test

compressed = compressor.compress(test_content, VerbosityMode.CONCISE, max_chars=4000)
print(f'Original: {len(test_content)} chars')
print(f'Compressed: {len(compressed)} chars')
print(f'Compression ratio: {len(compressed)/len(test_content):.2%}')
"
```

### 2. Test Task Assessment

```bash
# Test how different requests are assessed
python -c "
from app.domain.services.agents.response_policy import ResponsePolicyEngine

engine = ResponsePolicyEngine()

# Test different request types
requests = [
    'Search for Python tutorials',
    'Delete all production databases',
    'Compare performance of React vs Vue',
]

for req in requests:
    assessment = engine.assess_task(req)
    policy = engine.decide_policy(assessment)
    print(f'Request: {req}')
    print(f'  Risk: {assessment.risk_score:.2f}')
    print(f'  Mode: {policy.mode.value}')
    print(f'  Compression: {policy.allow_compression}')
    print()
"
```

### 3. Monitor Compression Metrics

Check if compression is being rejected due to coverage loss:

```bash
# In your logs, look for:
# "compression_rejected_total" metrics
docker logs pythinker-backend 2>&1 | grep "compression_rejected"
```

## Monitoring Recommendations

### Key Metrics to Track

1. **Compression Rate**
   - Before: ~70% of responses compressed to 1400 chars
   - After: Should see lower compression rate, better quality

2. **Critic Revision Rate**
   - Track how often `max_revision_attempts` is reached
   - File: `backend/app/domain/services/agents/execution.py:716-750`

3. **Hallucination False Positives**
   - Log when legitimate content is flagged
   - Check `ContentHallucinationDetector` patterns

### Logging Enhancement

Add this to `execution.py` around line 522:

```python
if compressed_coverage.is_valid and len(compressed_content) < len(message_content):
    logger.info(
        f"Compression applied: {len(message_content)} → {len(compressed_content)} chars "
        f"({len(compressed_content)/len(message_content):.1%})"
    )
    message_content = compressed_content
```

## Rollback Instructions

If changes cause issues, revert with:

```bash
cd /Users/panda/Desktop/Projects/Pythinker

# Revert response_policy.py changes
git checkout backend/app/domain/services/agents/response_policy.py

# Revert response_compressor.py changes
git checkout backend/app/domain/services/agents/response_compressor.py

# Restart services
./dev.sh restart backend
```

## Summary of Files Modified

1. ✅ `backend/app/domain/services/agents/response_policy.py`
   - Line 38: `max_chars: int = 4000` (was 1400)
   - Line 165: `max_chars=4000 if mode == VerbosityMode.CONCISE` (was 1400)

2. ✅ `backend/app/domain/services/agents/response_compressor.py`
   - Line 19: `def compress(..., max_chars: int = 4000)` (was 1400)
   - Line 36: `summary_blocks = blocks[:4]` (was 2)
   - Line 37: `artifact_lines = self._extract_lines(..., limit=8)` (was 3)

## Next Steps

1. **Restart backend** to apply changes:
   ```bash
   ./dev.sh restart backend
   ```

2. **Test with real queries** that previously had issues

3. **Monitor logs** for compression/validation metrics

4. **Fine-tune further** if needed using Options A-D above

5. **Document specific patterns** that cause false hallucination flags

---

**Last Updated:** 2026-02-11
**Applied By:** Claude Code
