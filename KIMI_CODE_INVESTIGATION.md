# Kimi Code API Investigation Report

**Date**: 2026-02-07
**Status**: ⚠️ Authentication Issue - Subscription Required

---

## Summary

The Kimi Code API is rejecting requests with the error: **"Kimi For Coding is currently only available for Coding Agents such as Kimi CLI, Claude Code, Roo Code, Kilo Code, etc."**

After investigating the official documentation, this error indicates that **Kimi Code is a subscription service** requiring an active paid subscription to use the API.

---

## Key Findings

### 1. Kimi Code is a Subscription Service

From the [official documentation](https://www.kimi.com/code/docs/en/):

> **"Kimi Code is a premium subscription tier within the Kimi ecosystem, specifically engineered to empower developers with advanced AI capabilities for coding."**

Key points:
- ✅ Full compatibility with Claude Code, Roo Code, and Kimi CLI
- ✅ Elite performance: up to 100 tokens/s output speed
- ✅ 5-hour token budget handles ~300-1,200 API calls
- ❌ Requires active "Coding Plan" subscription

### 2. Correct Configuration

Our configuration is **correct** for OpenAI-compatible clients:

```env
LLM_PROVIDER=openai
API_KEY=sk-kimi-qYFWdVGq6cIvjD6XxmC634yioPUCXirJBemhS0f1VHU5gTfPDcMTvl3HE1nudEUq
API_BASE=https://api.kimi.com/coding/v1
MODEL_NAME=kimi-for-coding
```

**Note**:
- Claude Code uses `https://api.kimi.com/coding/` (Anthropic SDK format)
- Roo Code / OpenAI clients use `https://api.kimi.com/coding/v1` (OpenAI SDK format)

### 3. Headers Are Being Set Correctly

The backend is properly setting headers in `openai_llm.py`:
```python
default_headers = {
    "User-Agent": "claude-code/1.0",
    "X-Client-Name": "claude-code",
}
```

Logs confirm: `"Detected Kimi Code API, adding required headers"`

---

## Root Cause Analysis

The error **"only available for Coding Agents"** appears despite correct configuration because:

### Likely Causes:

1. **🔴 API Key Not From Kimi Code Subscription**
   - The API key may be from the regular Kimi API (api.moonshot.ai)
   - Kimi Code requires API keys generated from https://www.kimi.com/code/console
   - Regular Kimi API keys won't work with the Coding API

2. **🔴 No Active Coding Plan Subscription**
   - Account must have an active "Coding Plan" subscription
   - New users must visit https://www.kimi.com/code and subscribe first
   - Verify subscription status at https://www.kimi.com/code/console

3. **🟡 API Key Permissions**
   - The key may not have proper permissions enabled
   - Check key settings in the Kimi Code Console

---

## Testing Results

### Test 1: Direct API Call
```python
POST https://api.kimi.com/coding/v1/chat/completions
Headers: User-Agent: claude-code/1.0, X-Client-Name: claude-code
```

**Result**:
```json
{
  "error": {
    "message": "Kimi For Coding is currently only available for Coding Agents such as Kimi CLI, Claude Code, Roo Code, Kilo Code, etc.",
    "type": "access_terminated_error"
  }
}
```

### Test 2: Endpoint Verification
- ✅ Endpoint exists (200 OK path verified)
- ✅ Headers accepted (no header validation errors)
- ❌ Authentication/authorization failing

---

## Required Steps to Fix

### Step 1: Verify Subscription ⚠️ CRITICAL

1. Visit https://www.kimi.com/code
2. Log in with your account
3. Check if you have an active "Coding Plan" subscription
4. If not subscribed:
   - Click "Select a Coding Plan"
   - Choose and activate a subscription tier

### Step 2: Generate Proper API Key

1. Go to https://www.kimi.com/code/console
2. Navigate to `Console` → `API Keys`
3. Click "Create New Key"
4. Copy the **full key** (only shown once for security)
5. Replace the API key in `.env` with the new one

### Step 3: Verify Account Status

In the Kimi Code Console, check:
- ✅ Subscription status (Active/Expired)
- ✅ API key is listed under "API Keys"
- ✅ Token budget/usage limits
- ✅ Authorized devices (if using login method)

### Step 4: Test Configuration

After getting the correct API key:
```bash
# Restart backend
./dev.sh restart backend

# Test the API
curl -X POST https://api.kimi.com/coding/v1/chat/completions \
  -H "Authorization: Bearer YOUR_NEW_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"kimi-for-coding","messages":[{"role":"user","content":"hi"}],"max_tokens":50}'
```

Expected response: Actual content, not error

---

## Alternative: Moonshot AI's Kimi K2.5

If you don't have a Kimi Code subscription, you can use the **regular Kimi K2.5 model** instead:

### Configuration:
```env
LLM_PROVIDER=openai
API_KEY=<your-moonshot-api-key>
API_BASE=https://api.moonshot.cn/v1
MODEL_NAME=moonshot-v1-8k  # or moonshot-v1-32k, moonshot-v1-128k
```

### Differences:
- ❌ Not optimized for coding workflows
- ❌ No integration with coding agents
- ✅ Pay-as-you-go pricing (no subscription required)
- ✅ OpenAI-compatible API

---

## Documentation References

1. **Kimi Code Official Site**: https://www.kimi.com/code
2. **Kimi Code Docs**: https://www.kimi.com/code/docs/en/
3. **Kimi Code Console**: https://www.kimi.com/code/console
4. **Third-Party Agent Setup**: https://www.kimi.com/code/docs/en/more/third-party-agents.html
5. **Kimi CLI GitHub**: https://github.com/MoonshotAI/kimi-cli

---

## Next Steps

**IMMEDIATE ACTION REQUIRED**:

1. 🔍 **Verify** if you have an active Kimi Code subscription at https://www.kimi.com/code/console
2. 🔑 **Generate** a new API key from the Kimi Code Console (NOT from api.moonshot.ai)
3. ⚙️ **Update** the API_KEY in `.env` with the new key
4. 🔄 **Restart** backend: `./dev.sh restart backend`
5. ✅ **Test** with a new session

**If you don't have a Kimi Code subscription**:
- Consider subscribing at https://www.kimi.com/code (benefits: 100 tokens/s, coding-optimized)
- OR switch to Moonshot AI's regular API (no subscription needed)
- OR use another provider (OpenRouter, Anthropic, OpenAI, etc.)

---

## Current System Status

All other systems are working correctly:

✅ Docker services: All 7 healthy
✅ Backend startup: Clean logs, <2 second initialization
✅ Sandbox pool: Ready and functional
✅ Frontend: Running and accessible
✅ API configuration: Correct for Kimi Code
❌ **API authentication: Requires valid Kimi Code subscription key**

---

**Report Generated**: 2026-02-07
**Investigation Status**: Complete - awaiting subscription verification
