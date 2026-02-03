# Agent Monitoring Guide

## System Status ✅

All services configured and running with GPT-OSS-120B model:
- **Model:** openai/gpt-oss-120b (117B MoE)
- **Temperature:** 1.0 (optimal for agentic AI)
- **Max Tokens:** 30,000 (recommended for complex tasks)
- **API:** OpenRouter (https://openrouter.ai/api/v1)

## Access Points

### Frontend UI
**URL:** http://localhost:5174

Use this to:
- Create new sessions with your research prompts
- Watch agent planning and execution in real-time
- View VNC browser interactions
- See renamed tool labels (search, web search)

### Backend API
**Base:** http://localhost:8000/api/v1

Sessions endpoint: `GET /api/v1/sessions?user_id=anonymous`

## Testing the Research Task

### 1. Via Frontend (Recommended)
1. Open http://localhost:5174
2. Create new session
3. Enter the comprehensive research prompt about OpenRouter free tier LLMs
4. Observe:
   - **Planning Phase**: Agent creates structured plan using GPT-OSS-120B
   - **Execution Phase**: Agent executes steps using renamed tools
   - **Tool Usage**: "Searching" appears instead of "Fetching"
   - **Browser Activity**: VNC shows actual browser interactions

### 2. Monitor Backend Logs

```bash
# Watch all agent activity
docker logs -f pythinker-backend-1

# Filter for key events only
docker logs -f pythinker-backend-1 | grep -E "session_id|Planning|Executing|search|tool"

# Check for errors
docker logs -f pythinker-backend-1 | grep -iE "error|exception|failed"

# Monitor specific session (replace SESSION_ID)
docker logs -f pythinker-backend-1 | grep "SESSION_ID"
```

### 3. What to Look For

#### ✅ Successful Planning
```
Creating plan for session...
Plan created successfully
Steps: [list of planned actions]
```

#### ✅ Tool Execution
```
Executing tool: search (URL: https://...)
Executing tool: web_search (query: "...")
```

#### ✅ GPT-OSS-120B Usage
```
Using model: openai/gpt-oss-120b
Temperature: 1.0
Max tokens: 30000
```

#### ⚠️ Issues to Watch For
```
error: json_object format not supported     # Should NOT appear with GPT-OSS-120B
Plan creation failed                         # Should NOT appear anymore
Tool naming confusion                         # Should show 'search' not 'browser_get_content'
```

## Tool Naming Changes

### Backend (Python)
- `browser_get_content` → `search`
- `info_search_web` → `web_search`

### Frontend (Vue)
- Tool function map updated to show:
  - "Searching" for `search` tool
  - "Web Search" for `web_search` tool
- Removed confusing "Fetching" label

## Verification Checklist

- [ ] Frontend accessible at http://localhost:5174
- [ ] Can create new session
- [ ] Agent creates plan successfully (GPT-OSS-120B)
- [ ] Tools execute with correct names (search, web_search)
- [ ] UI shows "Searching" not "Fetching"
- [ ] VNC shows browser interactions when using search
- [ ] No json_object format errors in logs
- [ ] Temperature=1.0 and max_tokens=30000 being used

## Research Prompt (Ready to Test)

```
Generate a comprehensive research report evaluating the most suitable large language models (LLMs) for running an autonomous agent that performs search functions, specifically focusing on models accessible via the OpenRouter platform's free tier.

Include the following details:

1. Identify and list at least five LLMs available on OpenRouter's free tier that are suitable for agent search tasks.

2. For each model, detail the following:
   - Name and version
   - Underlying architecture
   - Maximum token limit
   - Known performance benchmarks related to search or agent tasks

3. Compare and rank these models based on their operating costs once the free tier usage limits are exceeded, from cheapest to most expensive.

4. For each model, specify the approximate cost per use or per token, considering typical usage scenarios.

5. Summarize the advantages and disadvantages of each model in the context of agent search functionalities.

6. Conclude with recommendations for selecting the optimal model based on cost-efficiency, performance, and suitability for agent search applications.
```

## Expected Agent Workflow

1. **Planning Phase** (~10-30s)
   - GPT-OSS-120B analyzes the research task
   - Creates structured plan with multiple steps
   - Identifies need for web search and content analysis

2. **Execution Phase** (varies)
   - Step 1: Search OpenRouter free tier models
   - Step 2: Gather pricing information
   - Step 3: Search benchmarks for each model
   - Step 4: Compare and analyze findings
   - Step 5: Generate comprehensive report

3. **Reflection Phase** (optional)
   - Reviews completeness of research
   - Identifies gaps or additional needed searches
   - May trigger additional execution steps

## Troubleshooting

### Session doesn't start
```bash
# Check backend health
curl http://localhost:8000/api/v1/health

# Restart backend if needed
docker compose restart backend
```

### Planning fails
```bash
# Verify model configuration
docker exec pythinker-backend-1 printenv | grep -E "MODEL_NAME|TEMPERATURE|MAX_TOKENS"

# Expected output:
# MODEL_NAME=openai/gpt-oss-120b
# TEMPERATURE=1.0
# MAX_TOKENS=30000
```

### Tools not executing
```bash
# Check sandbox connection
docker exec pythinker-backend-1 curl -s http://sandbox:8080/health

# Check browser agent
docker logs pythinker-sandbox-1 | tail -20
```

## Success Indicators

When everything is working correctly, you should see:

1. **In Frontend:**
   - Smooth session creation
   - Plan displayed with clear steps
   - Progress indicators for each tool
   - "Searching" labels (not "Fetching")
   - VNC viewer shows browser when needed

2. **In Backend Logs:**
   - Clean session creation
   - Successful plan generation
   - Tool execution without errors
   - Proper model usage (temp=1.0, max=30k)

3. **Final Output:**
   - Comprehensive research report
   - All 6 requirements addressed
   - Proper formatting and citations
   - Recommendations based on findings

---

**Ready to test!** Open http://localhost:5174 and start a new session with the research prompt above.
