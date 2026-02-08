# Pythinker Agent Tools — Complete Inventory

> Scanned: 2026-02-06 | **99 static tools** across 22 tool classes + dynamic MCP tools

---

## 1. ShellTool (`shell.py`) — 5 tools

| # | Tool Name | Params |
|---|-----------|--------|
| 1 | `shell_exec` | id, exec_dir, command |
| 2 | `shell_view` | id |
| 3 | `shell_wait` | id, seconds? |
| 4 | `shell_write_to_process` | id, input, press_enter |
| 5 | `shell_kill_process` | id |

## 2. FileTool (`file.py`) — 6 tools

| # | Tool Name | Params |
|---|-----------|--------|
| 6 | `file_read` | file, start_line?, end_line?, sudo? |
| 7 | `file_write` | file, content, append?, leading_newline?, trailing_newline?, sudo? |
| 8 | `file_str_replace` | file, old_str, new_str, sudo? |
| 9 | `file_find_in_content` | file, regex, sudo? |
| 10 | `file_find_by_name` | path, glob |
| 11 | `file_view` | file, page_range?, extract_text?, analyze_charts? |

## 3. BrowserTool (`browser.py`) — 13 tools

| # | Tool Name | Params |
|---|-----------|--------|
| 12 | `search` | url, focus? |
| 13 | `browser_view` | (none) |
| 14 | `browser_navigate` | url, intent?, focus? |
| 15 | `browser_restart` | url |
| 16 | `browser_click` | index?, coordinate_x?, coordinate_y? |
| 17 | `browser_input` | text, press_enter, index?, coordinate_x?, coordinate_y? |
| 18 | `browser_move_mouse` | coordinate_x, coordinate_y |
| 19 | `browser_press_key` | key |
| 20 | `browser_select_option` | index, option |
| 21 | `browser_scroll_up` | to_top? |
| 22 | `browser_scroll_down` | to_bottom? |
| 23 | `browser_console_exec` | javascript |
| 24 | `browser_console_view` | max_lines? |

## 4. SearchTool (`search.py`) — 2 tools

| # | Tool Name | Params |
|---|-----------|--------|
| 25 | `info_search_web` | query, date_range? |
| 26 | `wide_research` | topic, queries, search_types?, date_range? |

## 5. MessageTool (`message.py`) — 2 tools

| # | Tool Name | Params |
|---|-----------|--------|
| 27 | `message_notify_user` | text, attachments? |
| 28 | `message_ask_user` | text, attachments?, suggest_user_takeover? |

## 6. IdleTool (`idle.py`) — 1 tool

| # | Tool Name | Params |
|---|-----------|--------|
| 29 | `idle` | (none) |

## 7. GitTool (`git.py`) — 5 tools

| # | Tool Name | Params |
|---|-----------|--------|
| 30 | `git_clone` | url, path?, branch? |
| 31 | `git_status` | path |
| 32 | `git_diff` | path, file? |
| 33 | `git_log` | path, count? |
| 34 | `git_branches` | path |

## 8. CodeExecutorTool (`code_executor.py`) — 7 tools

| # | Tool Name | Params |
|---|-----------|--------|
| 35 | `code_execute` | language, code, timeout?, working_dir? |
| 36 | `code_execute_python` | code, timeout?, working_dir? |
| 37 | `code_execute_javascript` | code, timeout?, working_dir? |
| 38 | `code_list_artifacts` | working_dir? |
| 39 | `code_read_artifact` | path |
| 40 | `code_cleanup_workspace` | working_dir? |
| 41 | `code_save_artifact` | path, content |

## 9. CodeDevTool (`code_dev.py`) — 4 tools

| # | Tool Name | Params |
|---|-----------|--------|
| 42 | `code_format` | file, formatter? |
| 43 | `code_lint` | file, linter? |
| 44 | `code_analyze` | file |
| 45 | `code_search` | query, path?, pattern? |

## 10. TestRunnerTool (`test_runner.py`) — 3 tools

| # | Tool Name | Params |
|---|-----------|--------|
| 46 | `test_run` | path, framework?, pattern?, verbose? |
| 47 | `test_list` | path, framework? |
| 48 | `test_coverage` | path, framework? |

## 11. ExportTool (`export.py`) — 4 tools

| # | Tool Name | Params |
|---|-----------|--------|
| 49 | `export_organize` | source_dir, categories? |
| 50 | `export_archive` | source_dir, output_path?, include?, exclude? |
| 51 | `export_report` | source_dir, format? |
| 52 | `export_list` | source_dir, pattern? |

## 12. WorkspaceTool (`workspace.py`) — 5 tools

| # | Tool Name | Params |
|---|-----------|--------|
| 53 | `workspace_init` | name, template? |
| 54 | `workspace_info` | path? |
| 55 | `workspace_tree` | path?, depth? |
| 56 | `workspace_clean` | path?, pattern? |
| 57 | `workspace_exists` | path |

## 13. ScheduleTool (`schedule.py`) — 3 tools

| # | Tool Name | Params |
|---|-----------|--------|
| 58 | `agent_schedule_task` | task_description, interval_minutes?, cron_expression? |
| 59 | `agent_cancel_scheduled_task` | task_id |
| 60 | `agent_list_scheduled_tasks` | (none) |

## 14. AgentModeTool (`agent_mode.py`) — 1 tool

| # | Tool Name | Params |
|---|-----------|--------|
| 61 | `agent_start_task` | task_description |

## 15. SkillCreatorTool (`skill_creator.py`) — 3 tools

| # | Tool Name | Params |
|---|-----------|--------|
| 62 | `skill_create` | id, description, system_prompt_addition, ... |
| 63 | `skill_list_user` | (none) |
| 64 | `skill_delete` | skill_id |

## 16. SkillInvokeTool (`skill_invoke.py`) — 1 tool (meta-tool)

| # | Tool Name | Params |
|---|-----------|--------|
| 65 | `skill_invoke` | skill_name, arguments? |

## 17. SkillListTool (`skill_invoke.py`) — 1 tool

| # | Tool Name | Params |
|---|-----------|--------|
| 66 | `skill_list` | category?, include_user_only? |

## 18. SlidesTool (`slides.py`) — 3 tools (ToolSchema-based)

| # | Tool Name | Params |
|---|-----------|--------|
| 67 | `slides_create` | title, slides, theme? |
| 68 | `slides_add_chart` | presentation_id, chart_type, data |
| 69 | `slides_export` | presentation_id, format |

## 19. DeepScanAnalyzerTool (`deep_scan_analyzer.py`) — 5 tools

| # | Tool Name | Params |
|---|-----------|--------|
| 70 | `deep_scan_code` | path, analysis_type? |
| 71 | `deep_scan_security` | path |
| 72 | `deep_scan_quality` | path |
| 73 | `deep_scan_dependencies` | path |
| 74 | `deep_scan_project` | path |

## 20. BrowserAgentTool (`browser_agent.py`) — 2 tools

| # | Tool Name | Params |
|---|-----------|--------|
| 75 | `browsing` | task, url?, max_steps? |
| 76 | `browser_agent_extract` | url, schema?, fields? |

## 21. PlaywrightTool (`playwright_tool.py`) — 16 tools

| # | Tool Name | Params |
|---|-----------|--------|
| 77 | `playwright_launch` | browser_type?, headless? |
| 78 | `playwright_navigate` | url, wait_until? |
| 79 | `playwright_click` | selector, button?, double_click? |
| 80 | `playwright_fill` | selector, value |
| 81 | `playwright_type` | selector, text, delay? |
| 82 | `playwright_screenshot` | path?, full_page?, selector? |
| 83 | `playwright_pdf` | path? |
| 84 | `playwright_wait_for_selector` | selector, state?, timeout? |
| 85 | `playwright_get_cookies` | url? |
| 86 | `playwright_set_cookies` | cookies |
| 87 | `playwright_get_content` | selector? |
| 88 | `playwright_evaluate` | expression |
| 89 | `playwright_select_option` | selector, value? |
| 90 | `playwright_stealth_navigate` | url, wait_until? |
| 91 | `playwright_detect_protection` | url? |
| 92 | `playwright_intercept_requests` | url_patterns, action? |
| 93 | `playwright_solve_recaptcha` | (auto-detect) |
| 94 | `playwright_cloudflare_bypass` | url |
| 95 | `playwright_fill_2fa_code` | code, selector? |
| 96 | `playwright_login_with_2fa` | url, username, password, ... |

## 22. MCPTool (`mcp.py`) — 3 built-in + dynamic

| # | Tool Name | Params |
|---|-----------|--------|
| 97 | `mcp_list_resources` | server_name? |
| 98 | `mcp_read_resource` | uri, server_name? |
| 99 | `mcp_server_status` | (none) |
| + | *(dynamic MCP server tools)* | *(varies per server)* |

---

## Non-tool files (infrastructure, no `@tool` decorators)

| File | Purpose |
|------|---------|
| `map_tool.py` | Parallel batch execution utility (MapTool) |
| `repo_map.py` | RepoMapGenerator utility class |
| `plan.py` | Empty/no tool class |
| `cache_layer.py` | Caching infrastructure |
| `paywall_detector.py` | Paywall detection utility |
| `schemas.py` | Pydantic validation schemas |
| `command_formatter.py` | Command formatting utility |
| `dynamic_toolset.py` | Tool filtering/selection logic |
| `tool_profiler.py` | Profiling infrastructure |
| `tool_tracing.py` | Tracing infrastructure |
| `result_analyzer.py` | Result analysis utility |
| `github_skill_seeker.py` | GitHub skill discovery utility |

---

## Comparison vs `system/tools.json` (Manus reference)

### Matching tools (26 of 29 Manus tools present)

19 exact matches + 7 with enhanced descriptions:

| Tool | Status |
|------|--------|
| `message_notify_user` | Exact match |
| `message_ask_user` | Exact match |
| `file_read` | Exact match |
| `file_write` | Exact match |
| `file_str_replace` | Exact match |
| `file_find_in_content` | Exact match |
| `file_find_by_name` | Exact match |
| `shell_exec` | Exact match |
| `shell_view` | Exact match |
| `shell_wait` | Exact match |
| `shell_write_to_process` | Exact match |
| `shell_kill_process` | Exact match |
| `browser_restart` | Exact match |
| `browser_move_mouse` | Exact match |
| `browser_press_key` | Exact match |
| `browser_select_option` | Exact match |
| `browser_console_exec` | Exact match |
| `browser_console_view` | Exact match |
| `info_search_web` | Exact match (params) |
| `browser_navigate` | Diverged: adds `intent`, `focus` params |
| `browser_view` | Enhanced description |
| `browser_click` | Enhanced description |
| `browser_input` | Enhanced description |
| `browser_scroll_up` | Enhanced description |
| `browser_scroll_down` | Enhanced description |
| `idle` | Different description wording |

### Missing from agent (3 Manus-platform tools)

| Tool | Description |
|------|-------------|
| `deploy_expose_port` | Expose local port for public access |
| `deploy_apply_deployment` | Deploy static/nextjs app to production |
| `make_manus_page` | Make Manus Page from MDX file |

### Pythinker-only tools (73 tools beyond Manus base)

All tools not in the matching list above are Pythinker-specific additions.
