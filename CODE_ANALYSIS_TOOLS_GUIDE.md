# Code Analysis Tools - Usage Guide

**Status:** ✅ PRODUCTION-READY
**Date:** 2026-02-15

---

## Overview

Two new tools are now available to agents for advanced code analysis:

1. **`segment_document`** - Intelligently chunk long documents while preserving structure
2. **`track_implementation`** - Validate code completeness across multiple files

**Availability:** Automatically provided to agents with `CODE_EXECUTION` capability

---

## Tool 1: segment_document

### Purpose

Segments long documents/code files into manageable chunks with intelligent boundary preservation. Prevents context truncation while maintaining semantic coherence.

### When to Use

- ✅ Processing files >200 lines
- ✅ Need to analyze large Python modules without losing function/class context
- ✅ Working with long Markdown documents (preserves section structure)
- ✅ Splitting large JSON/YAML files for processing
- ✅ Preparing documents for LLM context windows

### Tool Signature

```json
{
  "name": "segment_document",
  "parameters": {
    "file": "<absolute_path>",           // Required
    "max_chunk_lines": 200,              // Optional (default: 200)
    "overlap_lines": 10,                 // Optional (default: 10)
    "strategy": "semantic"               // Optional: semantic|fixed_size|hybrid
  }
}
```

### Strategies Explained

**`semantic` (Default - Recommended):**
- **Python**: Respects function/class boundaries using AST parsing
  - Never splits mid-function
  - Preserves decorators with their functions
  - Detects: `def`, `class`, `async def`, `@decorator`

- **Markdown**: Respects heading boundaries
  - Never splits inside code blocks (```)
  - Splits at `# Heading`, `## Subheading`, etc.

- **Plain Text**: Respects paragraph boundaries (empty lines)

**`fixed_size`:**
- Simple line-based chunks (every N lines)
- Fast, predictable, no boundary analysis
- Use when structure doesn't matter

**`hybrid`:**
- Tries `semantic` first
- Falls back to `fixed_size` if chunks exceed 2x max_chunk_lines
- Best of both worlds for unpredictable content

### Example Usage Scenarios

**Scenario 1: Analyzing a Large Python Module**
```python
# Agent needs to understand a 500-line Python file
{
  "name": "segment_document",
  "parameters": {
    "file": "/workspace/large_module.py",
    "max_chunk_lines": 150,
    "overlap_lines": 15,
    "strategy": "semantic"
  }
}

# Response:
# {
#   "total_chunks": 4,
#   "boundaries_preserved": 12,  # 12 functions preserved
#   "chunks": [
#     {"index": 1, "start_line": 0, "end_line": 148, "type": "boundary"},
#     {"index": 2, "start_line": 134, "end_line": 298, "type": "boundary"},
#     ...
#   ]
# }
```

**Scenario 2: Processing Long Markdown Documentation**
```python
# Agent needs to summarize a 1000-line README
{
  "name": "segment_document",
  "parameters": {
    "file": "/workspace/README.md",
    "max_chunk_lines": 200,
    "strategy": "semantic"
  }
}

# Response:
# {
#   "total_chunks": 6,
#   "boundaries_preserved": 15,  # 15 heading boundaries
#   "document_type": "markdown"
# }
```

**Scenario 3: Quick Fixed-Size Chunking**
```python
# Agent just needs to split a log file quickly
{
  "name": "segment_document",
  "parameters": {
    "file": "/workspace/logs/app.log",
    "max_chunk_lines": 100,
    "strategy": "fixed_size"
  }
}
```

### Best Practices

1. **Use `semantic` for code files** - Preserves function/class boundaries
2. **Increase `overlap_lines` for complex code** - More context between chunks
3. **Use `hybrid` for unknown content** - Automatic fallback if structure too complex
4. **Reduce `max_chunk_lines` for deep nesting** - Smaller chunks for heavily nested code

### Output Format

```json
{
  "success": true,
  "message": "Segmented file.py into 4 chunks (python, 500 lines, 12 boundaries preserved)",
  "data": {
    "file": "/workspace/file.py",
    "document_type": "python",
    "total_lines": 500,
    "total_chunks": 4,
    "boundaries_preserved": 12,
    "strategy_used": "semantic",
    "chunks": [
      {
        "index": 1,
        "total": 4,
        "start_line": 0,
        "end_line": 148,
        "line_count": 149,
        "type": "boundary",
        "content_preview": "import logging\nfrom typing import Any\n\nclass MyClass:..."
      },
      ...
    ]
  }
}
```

---

## Tool 2: track_implementation

### Purpose

Validates code completeness across multiple files by detecting incomplete implementations (TODO, FIXME, NotImplementedError, empty functions) and generating actionable completion checklists.

### When to Use

- ✅ Validating multi-file code generation results
- ✅ Checking if implementation is complete before deployment
- ✅ Identifying placeholder code that needs implementation
- ✅ Generating completion checklists for partially implemented features
- ✅ Quality assurance for generated code

### Tool Signature

```json
{
  "name": "track_implementation",
  "parameters": {
    "files": ["<path1>", "<path2>", ...],  // Required (list of absolute paths)
    "check_todos": true,                   // Optional (default: true)
    "check_fixmes": true,                  // Optional (default: true)
    "check_empty_functions": true          // Optional (default: true)
  }
}
```

### Detection Capabilities

**1. AST-Based Detection (High Confidence):**
- `raise NotImplementedError(...)` - **High severity**
- Functions with only `pass` - **Medium severity**
- Functions with only `...` (ellipsis) - **Medium severity**

**2. Pattern-Based Detection (Marker Comments):**
- `# TODO`, `# HACK`, `# XXX` - **Low severity**
- `# FIXME` - **Medium severity**
- `# placeholder`, `# to be implemented` - **Medium severity**

**3. Completeness Scoring:**
```python
score = 1.0 - sum(severity_weights[issue.severity] for issue in issues)
# Severity weights: low=0.1, medium=0.3, high=0.5

# Score → Status:
# ≥ 0.9: COMPLETE
# 0.6-0.9: PARTIAL
# 0.3-0.6: INCOMPLETE
# < 0.3: PLACEHOLDER
# High severity issues: ERROR
```

### Example Usage Scenarios

**Scenario 1: Single File Validation**
```python
# Agent just wrote a new API endpoint, validate completeness
{
  "name": "track_implementation",
  "parameters": {
    "files": ["/workspace/api/endpoints.py"]
  }
}

# Response:
# {
#   "overall_status": "partial",
#   "overall_completeness": "75%",
#   "total_issues": 3,
#   "file_summaries": [
#     {
#       "file": "/workspace/api/endpoints.py",
#       "status": "partial",
#       "completeness": "75%",
#       "issues": 3,
#       "functions": "5/6"  # 5 complete, 1 incomplete
#     }
#   ],
#   "completion_checklist": [
#     "[ ] /workspace/api/endpoints.py: partial (3 issues, 75% complete)",
#     "  - Line 45: Implement function body for 'create_user'",
#     "  - Line 78: Complete TODO item"
#   ]
# }
```

**Scenario 2: Multi-File Project Validation**
```python
# Agent generated a full feature across 3 files, validate all
{
  "name": "track_implementation",
  "parameters": {
    "files": [
      "/workspace/api.py",
      "/workspace/models.py",
      "/workspace/tests.py"
    ],
    "check_todos": true,
    "check_fixmes": true,
    "check_empty_functions": true
  }
}

# Response:
# {
#   "overall_status": "incomplete",  # Worst-case status
#   "overall_completeness": "65%",    # Average score
#   "total_issues": 12,
#   "high_priority_issues": 2,
#   "files_analyzed": 3,
#   "file_summaries": [
#     {"file": "api.py", "status": "partial", "completeness": "75%", "issues": 3},
#     {"file": "models.py", "status": "complete", "completeness": "100%", "issues": 0},
#     {"file": "tests.py", "status": "incomplete", "completeness": "40%", "issues": 9}
#   ],
#   "completion_checklist": [
#     "[ ] api.py: partial (3 issues, 75% complete)",
#     "  - Line 45: Implement function body",
#     "[ ] models.py: complete (0 issues, 100% complete)",
#     "[ ] tests.py: incomplete (9 issues, 40% complete)",
#     "  - Line 12: Fix FIXME issue",
#     "  - Line 23: Replace placeholder with implementation"
#   ]
# }
```

**Scenario 3: Pre-Deployment Validation**
```python
# Agent about to finish task, final validation
{
  "name": "track_implementation",
  "parameters": {
    "files": [
      "/workspace/feature/module1.py",
      "/workspace/feature/module2.py",
      "/workspace/feature/module3.py"
    ]
  }
}

# If overall_status == "complete":
#   ✅ Safe to deploy
# Else:
#   ⚠️ Review completion_checklist before deploying
```

### Best Practices

1. **Always validate after multi-file generation** - Catch incomplete implementations early
2. **Use completion checklist** - Provides actionable next steps
3. **Check high_priority_issues first** - NotImplementedError, broken functions
4. **Aim for ≥80% completeness** - Below 80% likely has significant gaps
5. **Disable TODO checks for exploratory code** - `check_todos: false` if TODOs are intentional

### Output Format

```json
{
  "success": true,
  "message": "Implementation Status: PARTIAL (75% complete)\nFiles: 2/3 complete, 5 total issues, 1 high priority\n\nCompletion Checklist:\n[ ] api.py: partial (3 issues, 75% complete)\n  - Line 45: Implement function body",
  "data": {
    "overall_status": "partial",
    "overall_completeness": "75%",
    "total_issues": 5,
    "high_priority_issues": 1,
    "files_analyzed": 3,
    "file_summaries": [...],
    "high_priority_details": [
      {
        "file": "/workspace/api.py",
        "line": 45,
        "reason": "not_implemented_error",
        "snippet": "raise NotImplementedError('TODO')",
        "suggestion": "Implement this function/method"
      }
    ],
    "completion_checklist": [...]
  }
}
```

---

## Common Patterns

### Pattern 1: Process Large File with Segmentation

```python
# 1. Segment the file
segment_result = await agent.use_tool("segment_document", {
    "file": "/workspace/large_module.py",
    "max_chunk_lines": 200,
    "strategy": "semantic"
})

# 2. Process each chunk
for chunk in segment_result.data["chunks"]:
    # Read specific chunk using file_read with start_line/end_line
    chunk_content = await agent.use_tool("file_read", {
        "file": "/workspace/large_module.py",
        "start_line": chunk["start_line"],
        "end_line": chunk["end_line"]
    })

    # Analyze chunk...
```

### Pattern 2: Generate Code with Validation

```python
# 1. Generate code files
await agent.use_tool("file_write", {
    "file": "/workspace/api.py",
    "content": generated_api_code
})

await agent.use_tool("file_write", {
    "file": "/workspace/models.py",
    "content": generated_models_code
})

# 2. Validate completeness
validation_result = await agent.use_tool("track_implementation", {
    "files": ["/workspace/api.py", "/workspace/models.py"]
})

# 3. Check status
if validation_result.data["overall_status"] != "complete":
    # Review completion_checklist and fix issues
    print(validation_result.data["completion_checklist"])
else:
    # Ready to deploy
    print("✅ Implementation complete")
```

### Pattern 3: Iterative Development with Tracking

```python
# Development loop
while True:
    # Write some code
    await agent.use_tool("file_write", {...})

    # Check progress
    status = await agent.use_tool("track_implementation", {
        "files": ["/workspace/myfile.py"]
    })

    # If complete, break
    if status.data["overall_completeness"] == "100%":
        break

    # Otherwise, review checklist and continue
    next_steps = status.data["completion_checklist"]
    # Implement next step...
```

---

## Integration Notes

**Tool Registration:**
- Tools are automatically available to agents with `CODE_EXECUTION` capability
- Registered in `agent_factory.py` via `CodeAnalysisTool` class
- No manual registration required

**Performance:**
- `segment_document`: ~50-100ms for 1000-line files
- `track_implementation`: ~20-25ms per file (500 lines)
- Both use singleton factories for efficiency

**Error Handling:**
- File read failures are gracefully handled
- Syntax errors in code files are reported as high-severity issues
- Invalid strategy names default to `semantic`

**Limitations:**
- AST parsing only works for valid Python syntax
- Document type auto-detection may fail on ambiguous files
- Very large files (>10k lines) may take longer to process

---

## Related Documentation

- **Complete Integration**: `DEEPCODE_INTEGRATION_COMPLETE.md`
- **Phase 3 Details**: `DEEPCODE_PHASE_3_COMPLETE.md`
- **CLAUDE.md**: Updated with DeepCode integration status

---

**Status:** ✅ Tools are production-ready and available to all agents with CODE_EXECUTION capability
