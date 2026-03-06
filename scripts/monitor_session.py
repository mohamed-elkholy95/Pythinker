#!/usr/bin/env python3
"""
Comprehensive Pythinker Agent Session Monitor

Real-time monitoring of agent workflow across all signal sources:
- SSE event stream (tool calls, progress, plans, steps, errors)
- Prometheus metrics (LLM calls, tokens, tool efficiency)
- System health & pressure
- Agent MetricsCollector (cache, latency, token budget)

Usage:
    python scripts/monitor_session.py [SESSION_ID]
    python scripts/monitor_session.py --latest
    python scripts/monitor_session.py --dashboard

If no SESSION_ID given, monitors the most recent running session.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime
from typing import Any

# Force unbuffered output
sys.stdout.reconfigure(line_buffering=True)  # type: ignore[attr-defined]

# ─── Configuration ──────────────────────────────────────────────────────────
BASE_URL = os.getenv("PYTHINKER_URL", "http://localhost:8000")
EMAIL = os.getenv("PYTHINKER_EMAIL", "admin@pythinker.com")
PASSWORD = os.getenv("PYTHINKER_PASSWORD", "AdminPy@2026!")

# ─── ANSI Colors ────────────────────────────────────────────────────────────
C_RESET = "\033[0m"
C_BOLD = "\033[1m"
C_DIM = "\033[2m"
C_RED = "\033[31m"
C_GREEN = "\033[32m"
C_YELLOW = "\033[33m"
C_BLUE = "\033[34m"
C_MAGENTA = "\033[35m"
C_CYAN = "\033[36m"
C_WHITE = "\033[37m"
C_BG_RED = "\033[41m"
C_BG_GREEN = "\033[42m"
C_BG_BLUE = "\033[44m"
C_BG_YELLOW = "\033[43m"

# Event type → color mapping
EVENT_COLORS: dict[str, str] = {
    "message": C_WHITE,
    "progress": C_BLUE,
    "plan": C_CYAN,
    "step": C_GREEN,
    "tool": C_YELLOW,
    "tool_progress": C_YELLOW + C_DIM,
    "tool_stream": C_DIM,
    "flow_transition": C_MAGENTA,
    "flow_selection": C_MAGENTA,
    "research_mode": C_CYAN,
    "verification": C_GREEN,
    "reflection": C_MAGENTA,
    "report": C_WHITE + C_BOLD,
    "partial_result": C_CYAN,
    "stream": C_DIM,
    "title": C_BOLD,
    "error": C_RED + C_BOLD,
    "done": C_GREEN + C_BOLD,
    "wait": C_YELLOW + C_BOLD,
    "budget": C_YELLOW,
    "thought": C_DIM,
    "confidence": C_CYAN,
    "wide_research": C_BLUE,
    "phase_transition": C_BLUE,
    "checkpoint_saved": C_GREEN + C_DIM,
    "workspace": C_DIM,
    "eval_metrics": C_CYAN,
    "mcp_health": C_GREEN + C_DIM,
    "suggestion": C_CYAN + C_DIM,
    "skill_delivery": C_GREEN,
}


class SessionMonitor:
    """Real-time agent session monitor with statistics tracking."""

    def __init__(self, session_id: str, token: str) -> None:
        self.session_id = session_id
        self.token = token
        self.running = True
        self.start_time = time.time()

        # Statistics
        self.event_counts: Counter[str] = Counter()
        self.tool_calls: list[dict[str, Any]] = []
        self.llm_calls: int = 0
        self.total_tokens: dict[str, int] = {"prompt": 0, "completion": 0, "cached": 0}
        self.errors: list[dict[str, Any]] = []
        self.steps_completed: int = 0
        self.steps_total: int = 0
        self.current_phase: str = "idle"
        self.current_step: str = ""
        self.plan_steps: list[str] = []
        self.tool_durations: list[float] = []
        self.heartbeat_count: int = 0
        self.last_event_time: float = time.time()
        self.truncation_count: int = 0
        self.nudge_count: int = 0
        self.stream_events: int = 0

    def _api(self, path: str, method: str = "GET", data: dict | None = None) -> dict | None:
        """Make authenticated API call."""
        url = f"{BASE_URL}{path}"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        body = json.dumps(data).encode() if data else None
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            resp = urllib.request.urlopen(req, timeout=10)
            return json.loads(resp.read())
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
            return None

    def _ts(self) -> str:
        """Current timestamp string."""
        return datetime.now().strftime("%H:%M:%S")

    def _elapsed(self) -> str:
        """Elapsed time since monitoring started."""
        e = int(time.time() - self.start_time)
        m, s = divmod(e, 60)
        return f"{m:02d}:{s:02d}"

    def _print_header(self) -> None:
        """Print monitor header."""
        print(f"\n{C_BG_BLUE}{C_WHITE}{C_BOLD}  PYTHINKER AGENT MONITOR  {C_RESET}")
        print(f"{C_DIM}{'─' * 70}{C_RESET}")
        print(f"  Session:  {C_BOLD}{self.session_id}{C_RESET}")
        print(f"  Backend:  {BASE_URL}")
        print(f"  Started:  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{C_DIM}{'─' * 70}{C_RESET}\n")

    def _print_event(self, event_type: str, data: dict) -> None:
        """Print a formatted event line."""
        color = EVENT_COLORS.get(event_type, C_WHITE)
        # Use event's own timestamp if available, otherwise wall clock
        event_ts = data.get("timestamp")
        if event_ts and isinstance(event_ts, (int, float)):
            ts = datetime.fromtimestamp(event_ts).strftime("%H:%M:%S")
        else:
            ts = self._ts()
        # Format based on event type
        if event_type == "progress":
            phase = data.get("phase", "?")
            msg = data.get("message", "")
            pct = data.get("progress_percent")
            steps = data.get("estimated_steps")
            bar = ""
            if pct is not None:
                filled = int(pct / 5)
                bar = f" [{'█' * filled}{'░' * (20 - filled)}] {pct}%"
            step_info = f" ({steps} steps)" if steps else ""
            print(f"{C_DIM}{ts}{C_RESET} {color}▶ {phase.upper():<12}{C_RESET} {msg}{bar}{step_info}")
            self.current_phase = phase

        elif event_type == "plan":
            status = data.get("status", "?")
            # Backend may store steps at top level or nested under 'plan'
            plan = data.get("plan", {})
            steps = data.get("steps") or (plan.get("steps") if isinstance(plan, dict) else []) or []
            if steps:
                self.plan_steps = [s.get("title", s.get("description", "?")) for s in steps]
                self.steps_total = len(steps)
                print(f"\n{C_DIM}{ts}{C_RESET} {color}📋 PLAN ({status}) — {len(steps)} steps:{C_RESET}")
                for i, step in enumerate(steps, 1):
                    title = step.get("title", step.get("description", "?"))
                    print(f"         {C_DIM}{i}.{C_RESET} {title}")
                print()

        elif event_type == "step":
            status = data.get("status", "?")
            # Backend stores step fields flat (id, description) not nested
            step = data.get("step", {})
            if isinstance(step, dict):
                title = step.get("title", step.get("description", "?"))
            else:
                # Flat format: description is at top level
                title = data.get("description") or data.get("title") or "?"
            step_id = data.get("id") or (step.get("id") if isinstance(step, dict) else "?")
            icons = {"started": "▶", "running": "⏳", "completed": "✅", "failed": "❌", "skipped": "⏭"}
            icon = icons.get(status, "•")
            if status == "completed":
                self.steps_completed += 1
            self.current_step = title
            step_counter = f"[{self.steps_completed}/{self.steps_total}]" if self.steps_total else ""
            print(f"{C_DIM}{ts}{C_RESET} {color}{icon} STEP {step_id} {step_counter} {status.upper():<10}{C_RESET} {title}")

        elif event_type == "tool":
            # Backend uses: name, function, args, command, display_command
            tool = data.get("name") or data.get("tool_name") or "?"
            func = data.get("function") or data.get("function_name") or ""
            status = data.get("status", "?")
            dur = data.get("duration_ms")
            display = data.get("display_command") or data.get("command") or ""
            risk = data.get("security_risk", "")
            args = data.get("args") or data.get("function_args") or {}

            if status == "calling":
                args_str = ""
                if isinstance(args, dict):
                    # Show key args compactly
                    parts = []
                    for k, v in list(args.items())[:3]:
                        val = str(v)[:40]
                        parts.append(f"{k}={val}")
                    args_str = ", ".join(parts)
                cmd = display or f"{func}({args_str})"
                risk_badge = ""
                if risk and risk not in ("safe", "none", ""):
                    risk_badge = f" {C_BG_RED} {risk.upper()} {C_RESET}"
                print(f"{C_DIM}{ts}{C_RESET} {color}🔧 TOOL {C_BOLD}{tool}{C_RESET}{color}.{func} → {cmd}{risk_badge}{C_RESET}")
            elif status in ("called", "completed", "done"):
                dur_str = f" ({dur}ms)" if dur else ""
                self.tool_calls.append({"tool": tool, "func": func, "duration_ms": dur, "time": time.time()})
                if dur:
                    self.tool_durations.append(dur)
                # Show truncated output if available
                content = data.get("content", "")
                stdout = data.get("stdout", "")
                output_preview = ""
                if content and isinstance(content, str):
                    output_preview = f" → {content[:80]}..."
                elif stdout:
                    output_preview = f" → {stdout[:80]}..."
                print(f"{C_DIM}{ts}{C_RESET} {color}  └─ done{dur_str}{output_preview}{C_RESET}")

        elif event_type == "message":
            role = data.get("role", "?")
            content = data.get("content", "")
            if role == "user":
                print(f"\n{C_DIM}{ts}{C_RESET} {C_BOLD}💬 USER:{C_RESET} {content[:120]}")
            else:
                # Truncate long assistant messages
                preview = content[:200] + "..." if len(content) > 200 else content
                print(f"{C_DIM}{ts}{C_RESET} {C_BOLD}🤖 AGENT:{C_RESET} {preview}")

        elif event_type == "report":
            title = data.get("title", "?")
            content = data.get("content", "")
            sources = data.get("sources", [])
            lines = content.count("\n") + 1
            print(f"\n{C_DIM}{ts}{C_RESET} {color}📄 REPORT: {title}{C_RESET}")
            print(f"         {C_DIM}{lines} lines, {len(sources)} sources{C_RESET}")

        elif event_type == "partial_result":
            headline = data.get("headline", "?")
            step_idx = data.get("step_index", "?")
            sources = data.get("sources_count", 0)
            print(f"{C_DIM}{ts}{C_RESET} {color}💡 Finding [{step_idx}]:{C_RESET} {headline} {C_DIM}({sources} sources){C_RESET}")

        elif event_type == "error":
            error = data.get("error", "?")
            error_type = data.get("error_type", "")
            recoverable = data.get("recoverable", False)
            self.errors.append(data)
            rec_str = f"{C_GREEN}recoverable{C_RESET}" if recoverable else f"{C_RED}fatal{C_RESET}"
            print(f"\n{C_DIM}{ts}{C_RESET} {color}⚠ ERROR [{error_type}] ({rec_str}):{C_RESET}")
            print(f"         {error[:200]}")

        elif event_type == "done":
            print(f"\n{C_DIM}{ts}{C_RESET} {color}✨ SESSION COMPLETE{C_RESET}\n")

        elif event_type == "flow_transition":
            from_s = data.get("from_state", "?")
            to_s = data.get("to_state", "?")
            reason = data.get("reason", "")
            elapsed_ms = data.get("elapsed_ms", "")
            print(f"{C_DIM}{ts}{C_RESET} {color}⇄ FLOW:{C_RESET} {from_s} → {to_s} {C_DIM}({reason}) {elapsed_ms}ms{C_RESET}")

        elif event_type == "flow_selection":
            mode = data.get("flow_mode", "?")
            print(f"{C_DIM}{ts}{C_RESET} {color}⚙ FLOW MODE:{C_RESET} {mode}")

        elif event_type == "research_mode":
            mode = data.get("research_mode", "?")
            print(f"{C_DIM}{ts}{C_RESET} {color}🔬 RESEARCH MODE:{C_RESET} {mode}")

        elif event_type == "verification":
            status = data.get("status", "?")
            verdict = data.get("verdict", "")
            confidence = data.get("confidence", "")
            icons = {"started": "🔍", "passed": "✅", "revision_needed": "🔄", "failed": "❌"}
            icon = icons.get(status, "•")
            print(f"{C_DIM}{ts}{C_RESET} {color}{icon} VERIFY:{C_RESET} {status} {C_DIM}(conf={confidence}){C_RESET} {verdict[:100]}")

        elif event_type == "reflection":
            status = data.get("status", "?")
            decision = data.get("decision", "")
            print(f"{C_DIM}{ts}{C_RESET} {color}🪞 REFLECT:{C_RESET} {status} → {decision}")

        elif event_type == "wide_research":
            status = data.get("status", "?")
            total_q = data.get("total_queries", 0)
            completed_q = data.get("completed_queries", 0)
            sources = data.get("sources_found", 0)
            current = data.get("current_query", "")
            bar = ""
            if total_q > 0:
                pct = int((completed_q / total_q) * 100)
                filled = int(pct / 5)
                bar = f" [{'█' * filled}{'░' * (20 - filled)}] {completed_q}/{total_q}"
            print(f"{C_DIM}{ts}{C_RESET} {color}🔎 RESEARCH:{C_RESET} {status}{bar} {C_DIM}({sources} sources){C_RESET}")
            if current:
                print(f"         {C_DIM}Query: {current[:80]}{C_RESET}")

        elif event_type == "phase_transition":
            phase = data.get("phase", "?")
            label = data.get("label", "")
            print(f"{C_DIM}{ts}{C_RESET} {color}📌 PHASE:{C_RESET} {phase} — {label}")

        elif event_type == "budget":
            action = data.get("action", "?")
            pct = data.get("percentage_used", 0)
            remaining = data.get("remaining", 0)
            icons = {"warning": "⚠", "exhausted": "🚫", "resumed": "▶"}
            icon = icons.get(action, "•")
            print(f"{C_DIM}{ts}{C_RESET} {color}{icon} BUDGET:{C_RESET} {action} ({pct:.0f}% used, {remaining} remaining)")

        elif event_type == "thought":
            content = data.get("content", "")
            if content:
                print(f"{C_DIM}{ts} 💭 {content[:100]}{C_RESET}")

        elif event_type == "title":
            title = data.get("title", "?")
            print(f"{C_DIM}{ts}{C_RESET} {color}📝 Title:{C_RESET} {title}")

        elif event_type == "stream":
            # Skip stream events from display (too noisy) but count them
            self.stream_events += 1
            return  # Don't count in event_counts

        elif event_type == "workspace":
            action = data.get("action", "?")
            print(f"{C_DIM}{ts}{C_RESET} {color}📁 WORKSPACE:{C_RESET} {action}")

        elif event_type == "checkpoint_saved":
            phase = data.get("phase", "?")
            print(f"{C_DIM}{ts}{C_RESET} {color}💾 CHECKPOINT:{C_RESET} {phase}")

        elif event_type == "eval_metrics":
            score = data.get("hallucination_score", "?")
            passed = data.get("passed", False)
            status = "✅ PASSED" if passed else "❌ FAILED"
            print(f"{C_DIM}{ts}{C_RESET} {color}📊 EVAL: {status}{C_RESET} (hallucination={score})")

        elif event_type == "mcp_health":
            server = data.get("server_name", "?")
            healthy = data.get("healthy", False)
            icon = "✅" if healthy else "❌"
            print(f"{C_DIM}{ts}{C_RESET} {color}{icon} MCP: {server}{C_RESET}")

        elif event_type == "confidence":
            decision = data.get("decision", "?")
            level = data.get("level", "?")
            conf = data.get("confidence", "?")
            print(f"{C_DIM}{ts}{C_RESET} {color}🎯 CONF: {decision} ({level}, {conf}){C_RESET}")

        elif event_type == "suggestion":
            suggestions = data.get("suggestions", [])
            print(f"{C_DIM}{ts}{C_RESET} {color}💡 SUGGESTIONS:{C_RESET} {', '.join(suggestions[:3])}")

        elif event_type == "skill_delivery":
            name = data.get("name", "?")
            print(f"{C_DIM}{ts}{C_RESET} {color}📦 SKILL: {name}{C_RESET}")

        else:
            # Unknown event type — still show it
            print(f"{C_DIM}{ts}{C_RESET} {color}[{event_type}]{C_RESET} {json.dumps(data)[:120]}")

        self.event_counts[event_type] += 1
        self.last_event_time = time.time()

    def _print_stats_bar(self) -> None:
        """Print a compact status bar."""
        elapsed = self._elapsed()
        events = sum(self.event_counts.values())
        tools = len(self.tool_calls)
        errs = len(self.errors)

        avg_tool_ms = 0
        if self.tool_durations:
            avg_tool_ms = sum(self.tool_durations) / len(self.tool_durations)

        err_color = C_RED if errs > 0 else C_GREEN
        step_str = f"{self.steps_completed}/{self.steps_total}" if self.steps_total else "0/?"

        bar = (
            f"{C_DIM}┌─ {elapsed} │ "
            f"phase={self.current_phase} │ "
            f"steps={step_str} │ "
            f"events={events} │ "
            f"tools={tools} │ "
            f"avg_tool={avg_tool_ms:.0f}ms │ "
            f"{err_color}errors={errs}{C_DIM} │ "
            f"stream={self.stream_events}"
            f" ─┐{C_RESET}"
        )
        print(f"\n{bar}\n")

    def _print_final_summary(self) -> None:
        """Print final session summary with statistics."""
        elapsed = self._elapsed()
        total_events = sum(self.event_counts.values())

        print(f"\n{C_BG_GREEN}{C_WHITE}{C_BOLD}  SESSION MONITOR SUMMARY  {C_RESET}")
        print(f"{C_DIM}{'─' * 70}{C_RESET}")
        print(f"  Duration:       {elapsed}")
        print(f"  Total events:   {total_events} ({self.stream_events} stream chunks filtered)")
        print(f"  Steps:          {self.steps_completed}/{self.steps_total}")
        print(f"  Tool calls:     {len(self.tool_calls)}")
        print(f"  Errors:         {len(self.errors)}")

        if self.tool_durations:
            avg = sum(self.tool_durations) / len(self.tool_durations)
            p95 = sorted(self.tool_durations)[int(len(self.tool_durations) * 0.95)] if len(self.tool_durations) > 1 else self.tool_durations[0]
            mx = max(self.tool_durations)
            print(f"\n  Tool Latency:   avg={avg:.0f}ms  p95={p95:.0f}ms  max={mx:.0f}ms")

        if self.tool_calls:
            tool_counter: Counter[str] = Counter()
            for tc in self.tool_calls:
                tool_counter[tc["tool"]] += 1
            print("\n  Tool Breakdown:")
            for tool, count in tool_counter.most_common(10):
                print(f"    {tool:<25} {count:>4}x")

        if self.event_counts:
            print("\n  Event Breakdown:")
            for evt, count in self.event_counts.most_common(15):
                print(f"    {evt:<25} {count:>4}")

        if self.errors:
            print(f"\n  {C_RED}Errors:{C_RESET}")
            for err in self.errors[:5]:
                print(f"    [{err.get('error_type', '?')}] {err.get('error', '?')[:80]}")

        # Fetch final prometheus metrics
        self._print_prometheus_snapshot()

        print(f"\n{C_DIM}{'─' * 70}{C_RESET}\n")

    def _print_prometheus_snapshot(self) -> None:
        """Fetch and display key Prometheus metrics."""
        try:
            req = urllib.request.Request(f"{BASE_URL}/metrics")
            resp = urllib.request.urlopen(req, timeout=5)
            text = resp.read().decode()

            interesting = {}
            for line in text.split("\n"):
                if line.startswith("#"):
                    continue
                for prefix in [
                    "pythinker_llm_calls_total",
                    "pythinker_tokens_total",
                    "pythinker_tool_calls_total",
                    "pythinker_active_sessions",
                    "pythinker_active_agents",
                    "pythinker_tool_efficiency_nudges",
                    "pythinker_output_truncations",
                    "pythinker_model_tier_selections",
                    "pythinker_hallucination_detected",
                    "pythinker_sse_stream_events_total",
                ]:
                    if line.startswith(prefix):
                        interesting[line.split(" ")[0]] = line.split(" ")[-1]

            if interesting:
                print("\n  Prometheus Snapshot:")
                for k, v in sorted(interesting.items()):
                    print(f"    {k:<55} {v}")
        except Exception:
            pass

    def monitor_from_events(self) -> None:
        """Monitor by polling session events (works without SSE client)."""
        self._print_header()

        # First, fetch existing events to show history
        session_data = self._api(f"/api/v1/sessions/{self.session_id}")
        if not session_data:
            print(f"{C_RED}Failed to fetch session{C_RESET}")
            return

        data = session_data.get("data", session_data)
        status = data.get("status", "?")
        title = data.get("title", "?")
        research_mode = data.get("research_mode", "?")

        print(f"  Title:    {title}")
        print(f"  Status:   {status}")
        print(f"  Mode:     {research_mode}")
        print(f"{C_DIM}{'─' * 70}{C_RESET}\n")

        # Process existing events
        events = data.get("events", [])
        seen_ids: set[str] = set()

        print(f"{C_DIM}── Replaying {len(events)} existing events ──{C_RESET}\n")
        for ev in events:
            event_type = ev.get("event", "unknown")
            ev_data = ev.get("data", {})
            event_id = ev_data.get("event_id", "")
            seen_ids.add(event_id)
            self._print_event(event_type, ev_data)

        self._print_stats_bar()

        if status in ("completed", "failed", "cancelled"):
            print(f"{C_YELLOW}Session already {status}. Showing final summary.{C_RESET}")
            self._print_final_summary()
            return

        # Poll for new events
        print(f"\n{C_DIM}── Live monitoring (polling every 3s, Ctrl+C to stop) ──{C_RESET}\n")
        poll_interval = 3
        stats_interval = 30
        last_stats = time.time()

        while self.running:
            try:
                time.sleep(poll_interval)

                session_data = self._api(f"/api/v1/sessions/{self.session_id}")
                if not session_data:
                    continue

                data = session_data.get("data", session_data)
                new_status = data.get("status", "?")
                events = data.get("events", [])

                # Process new events
                for ev in events:
                    event_type = ev.get("event", "unknown")
                    ev_data = ev.get("data", {})
                    event_id = ev_data.get("event_id", "")
                    if event_id and event_id not in seen_ids:
                        seen_ids.add(event_id)
                        self._print_event(event_type, ev_data)

                # Periodic stats bar
                if time.time() - last_stats > stats_interval:
                    self._print_stats_bar()
                    last_stats = time.time()

                # Check if session ended
                if new_status in ("completed", "failed", "cancelled"):
                    self._print_final_summary()
                    break

                # Stale detection
                idle = time.time() - self.last_event_time
                if idle > 120:
                    print(f"{C_YELLOW}⚠ No events for {idle:.0f}s — session may be stale{C_RESET}")

            except KeyboardInterrupt:
                break

    def monitor_dashboard(self) -> None:
        """Dashboard mode — show system overview without specific session."""
        self._print_header()
        print(f"{C_BOLD}System Dashboard Mode{C_RESET}\n")

        while self.running:
            try:
                # Clear and reprint
                os.system("clear")

                now = datetime.now().strftime("%H:%M:%S")
                print(f"{C_BG_BLUE}{C_WHITE}{C_BOLD}  PYTHINKER DASHBOARD — {now}  {C_RESET}\n")

                # Health
                health = self._api("/api/v1/monitoring/health")
                if health:
                    overall = health.get("overall_status", "?")
                    components = health.get("components", {})
                    color = C_GREEN if overall == "healthy" else C_RED
                    print(f"  {C_BOLD}Health:{C_RESET} {color}{overall.upper()}{C_RESET}")
                    for comp, status in components.items():
                        icon = "✅" if status == "healthy" else "❌"
                        print(f"    {icon} {comp}")

                # Pressure
                pressure = self._api("/api/v1/monitoring/pressure")
                if pressure:
                    print(f"\n  {C_BOLD}Pressure:{C_RESET}")
                    print(f"    CPU:      {pressure.get('cpu_percent', '?')}%")
                    print(f"    Memory:   {pressure.get('memory_percent', '?')}%")
                    print(f"    Avail:    {pressure.get('memory_available_gb', '?')} GB")
                    can = pressure.get("can_accept_new_task", False)
                    icon = "✅" if can else "❌"
                    print(f"    Accept:   {icon}")

                # Active sessions
                sessions = self._api("/api/v1/sessions?page=1&limit=5")
                if sessions and "data" in sessions:
                    slist = sessions["data"].get("sessions", [])
                    running = [s for s in slist if s.get("status") == "running"]
                    print(f"\n  {C_BOLD}Sessions:{C_RESET} {len(running)} running, {len(slist)} recent")
                    for s in slist[:5]:
                        status = s.get("status", "?")
                        title = s.get("title") or "untitled"
                        sid = s.get("session_id", "?")[:8]
                        icons = {"running": "▶", "completed": "✅", "failed": "❌", "cancelled": "⏹"}
                        icon = icons.get(status, "•")
                        print(f"    {icon} {sid}  {title[:40]} ({status})")

                # Prometheus metrics snapshot
                self._print_prometheus_snapshot()

                print(f"\n{C_DIM}Refreshing every 10s... Ctrl+C to stop{C_RESET}")
                time.sleep(10)

            except KeyboardInterrupt:
                break


def get_token() -> str:
    """Authenticate and get JWT token."""
    data = json.dumps({"email": EMAIL, "password": PASSWORD}).encode()
    req = urllib.request.Request(
        f"{BASE_URL}/api/v1/auth/login",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        result = json.loads(resp.read())
        return result["data"]["access_token"]
    except Exception as e:
        print(f"{C_RED}Auth failed: {e}{C_RESET}")
        sys.exit(1)


def find_latest_session(token: str) -> str | None:
    """Find the most recent running session, or latest session."""
    req = urllib.request.Request(
        f"{BASE_URL}/api/v1/sessions?page=1&limit=10",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        result = json.loads(resp.read())
        sessions = result.get("data", {}).get("sessions", [])
        # Prefer running sessions
        for s in sessions:
            if s.get("status") == "running":
                return s["session_id"]
        # Fall back to most recent
        if sessions:
            return sessions[0]["session_id"]
    except Exception:
        pass
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Pythinker Agent Session Monitor")
    parser.add_argument("session_id", nargs="?", help="Session ID to monitor")
    parser.add_argument("--latest", action="store_true", help="Monitor latest session")
    parser.add_argument("--dashboard", action="store_true", help="System dashboard mode")
    args = parser.parse_args()

    token = get_token()

    if args.dashboard:
        monitor = SessionMonitor("dashboard", token)
        signal.signal(signal.SIGINT, lambda *_: setattr(monitor, "running", False))
        monitor.monitor_dashboard()
        return

    session_id = args.session_id
    if not session_id or args.latest:
        session_id = find_latest_session(token)
        if not session_id:
            print(f"{C_RED}No sessions found{C_RESET}")
            sys.exit(1)
        print(f"Auto-selected session: {session_id}")

    monitor = SessionMonitor(session_id, token)
    signal.signal(signal.SIGINT, lambda *_: setattr(monitor, "running", False))
    monitor.monitor_from_events()


if __name__ == "__main__":
    main()
