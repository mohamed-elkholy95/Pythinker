from __future__ import annotations
from datetime import datetime, timezone, timedelta

def _generate_daily_usage(days: int = 30) -> list[dict]:
    result = []
    now = datetime.now(timezone.utc)
    for i in range(days):
        d = now - timedelta(days=i)
        # More usage on recent days
        multiplier = max(0.3, 1.0 - i * 0.02)
        result.append({
            "date": d.strftime("%Y-%m-%d"),
            "total_prompt_tokens": int(45000 * multiplier),
            "total_completion_tokens": int(12000 * multiplier),
            "total_cached_tokens": int(8000 * multiplier),
            "total_cost": round(0.85 * multiplier, 4),
            "llm_call_count": int(35 * multiplier),
            "tool_call_count": int(28 * multiplier),
            "tokens_by_model": {"claude-sonnet-4-20250514": int(50000 * multiplier), "claude-haiku-4-5-20251001": int(7000 * multiplier)},
            "cost_by_model": {"claude-sonnet-4-20250514": round(0.72 * multiplier, 4), "claude-haiku-4-5-20251001": round(0.13 * multiplier, 4)},
        })
    return result

def get_usage_summary() -> dict:
    return {
        "today": {
            "tokens": 57200,
            "cost": 0.85,
            "llm_calls": 35,
            "tool_calls": 28,
        },
        "month": {
            "tokens": 1_450_000,
            "cost": 22.40,
            "llm_calls": 890,
            "tool_calls": 720,
            "sessions": 45,
            "active_days": 22,
        },
    }

def get_daily_usage(days: int = 30) -> dict:
    data = _generate_daily_usage(days)
    return {"days": data, "total_days": len(data)}

def get_monthly_usage(months: int = 6) -> dict:
    now = datetime.now(timezone.utc)
    result = []
    for i in range(months):
        d = now.replace(day=1) - timedelta(days=30 * i)
        multiplier = max(0.4, 1.0 - i * 0.1)
        result.append({
            "year": d.year,
            "month": d.month,
            "total_prompt_tokens": int(1_200_000 * multiplier),
            "total_completion_tokens": int(350_000 * multiplier),
            "total_cached_tokens": int(200_000 * multiplier),
            "total_cost": round(22.40 * multiplier, 2),
            "total_llm_calls": int(890 * multiplier),
            "total_tool_calls": int(720 * multiplier),
            "total_sessions": int(45 * multiplier),
            "active_days": int(22 * multiplier),
            "cost_by_model": {"claude-sonnet-4-20250514": round(18.50 * multiplier, 2), "claude-haiku-4-5-20251001": round(3.90 * multiplier, 2)},
        })
    return {"months": result, "total_months": len(result)}

def get_session_usage(session_id: str) -> dict:
    return {
        "session_id": session_id,
        "total_prompt_tokens": 12500,
        "total_completion_tokens": 3200,
        "total_cached_tokens": 2100,
        "total_cost": 0.23,
        "llm_call_count": 8,
        "tool_call_count": 6,
        "tokens_by_model": {"claude-sonnet-4-20250514": 15700},
        "cost_by_model": {"claude-sonnet-4-20250514": 0.23},
        "first_activity": "2025-12-20T10:30:00Z",
        "last_activity": "2025-12-20T10:45:00Z",
    }

def get_pricing() -> dict:
    return {
        "models": [
            {"model": "claude-sonnet-4-20250514", "prompt_price": 3.0, "completion_price": 15.0, "cached_price": 0.3},
            {"model": "claude-opus-4-20250514", "prompt_price": 15.0, "completion_price": 75.0, "cached_price": 1.5},
            {"model": "claude-haiku-4-5-20251001", "prompt_price": 0.8, "completion_price": 4.0, "cached_price": 0.08},
            {"model": "gpt-4o", "prompt_price": 2.5, "completion_price": 10.0, "cached_price": 1.25},
            {"model": "gpt-4o-mini", "prompt_price": 0.15, "completion_price": 0.6, "cached_price": 0.075},
        ]
    }
