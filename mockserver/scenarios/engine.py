from __future__ import annotations
import asyncio
import uuid
import time
from typing import AsyncGenerator

def eid() -> str:
    return uuid.uuid4().hex[:12]

def ts() -> int:
    return int(time.time())

def tc() -> str:
    return f"tc_{uuid.uuid4().hex[:8]}"

async def delay(seconds: float = 0.3) -> None:
    await asyncio.sleep(seconds)

def select_scenario(message: str, deep_research: bool = False):
    """Select a scenario based on message keywords."""
    msg = message.lower()

    if deep_research or "deep research" in msg:
        from scenarios.deep_research import run
        return run
    if "wide research" in msg:
        from scenarios.wide_research import run
        return run
    if any(kw in msg for kw in ["research", "find", "search", "look up", "investigate"]):
        from scenarios.research_report import run
        return run
    if any(kw in msg for kw in ["browse", "website", "visit", "url", "http"]):
        from scenarios.browser_navigation import run
        return run
    if any(kw in msg for kw in ["run", "execute", "install", "pip", "npm", "command", "terminal"]):
        from scenarios.shell_execution import run
        return run
    if any(kw in msg for kw in ["write", "create", "build", "make", "generate", "code"]):
        from scenarios.file_editing import run
        return run
    if any(kw in msg for kw in ["skill", "plugin"]):
        from scenarios.skill_demo import run
        return run

    # Default: multi-step plan
    from scenarios.multi_step_plan import run
    return run

async def run_scenario(message: str, session_id: str, deep_research: bool = False) -> AsyncGenerator[tuple[str, dict], None]:
    """Run a scenario and yield (event_type, data) tuples."""
    scenario_fn = select_scenario(message, deep_research)
    async for event_type, data in scenario_fn(message, session_id):
        yield event_type, data
