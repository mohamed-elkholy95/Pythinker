"""Browser interaction choreography engine.

Wraps browser actions with human-like timing profiles for professional
visual feedback in CDP screencast. Three profiles: fast (development),
professional (production default), cinematic (demos/presentations).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChoreographyProfile:
    """Timing profile for browser interactions."""

    name: str
    dwell_after_navigate: float  # seconds to pause after page load (user sees the page)
    hover_before_click: float  # hover pause before clicking
    cursor_move_steps: int  # Playwright mouse.move() subdivisions for smooth travel
    cursor_move_duration: float  # total cursor travel time (informational)
    typing_delay_ms: int  # per-character delay (Playwright delay= param)
    scroll_step_pause: float  # between scroll increments
    post_click_settle: float  # after click, let page react visibly
    post_type_pause: float  # after finishing typing
    pre_action_pause: float  # brief pause before any action


PROFILES: dict[str, ChoreographyProfile] = {
    "fast": ChoreographyProfile(
        name="fast",
        dwell_after_navigate=1.0,
        hover_before_click=0.1,
        cursor_move_steps=5,
        cursor_move_duration=0.15,
        typing_delay_ms=10,
        scroll_step_pause=0.3,
        post_click_settle=0.3,
        post_type_pause=0.1,
        pre_action_pause=0.05,
    ),
    "professional": ChoreographyProfile(
        name="professional",
        dwell_after_navigate=3.5,
        hover_before_click=0.4,
        cursor_move_steps=20,
        cursor_move_duration=0.6,
        typing_delay_ms=65,
        scroll_step_pause=0.8,
        post_click_settle=1.5,
        post_type_pause=0.5,
        pre_action_pause=0.3,
    ),
    "cinematic": ChoreographyProfile(
        name="cinematic",
        dwell_after_navigate=10.0,
        hover_before_click=0.8,
        cursor_move_steps=40,
        cursor_move_duration=1.2,
        typing_delay_ms=100,
        scroll_step_pause=1.2,
        post_click_settle=2.5,
        post_type_pause=1.0,
        pre_action_pause=0.5,
    ),
}

DEFAULT_PROFILE = "professional"


class BrowserChoreographer:
    """Controls timing and visual choreography for browser actions.

    Injected into PlaywrightBrowser to wrap navigate/click/type/scroll
    with human-like delays. When disabled, all timing methods return
    zero/minimal values so the browser operates at machine speed.
    """

    def __init__(self, profile_name: str = DEFAULT_PROFILE, enabled: bool = True) -> None:
        self.enabled = enabled
        if profile_name not in PROFILES:
            logger.warning(
                "Unknown choreography profile '%s', falling back to '%s'",
                profile_name,
                DEFAULT_PROFILE,
            )
            profile_name = DEFAULT_PROFILE
        self.profile = PROFILES[profile_name]

    def get_navigate_dwell(self) -> float:
        """Seconds to dwell on page after navigation before extracting content."""
        return self.profile.dwell_after_navigate if self.enabled else 0.0

    def get_click_params(self) -> dict[str, Any]:
        """Parameters for click choreography."""
        if not self.enabled:
            return {
                "hover_pause": 0.0,
                "cursor_steps": 1,
                "settle_pause": 0.0,
                "pre_pause": 0.0,
            }
        return {
            "hover_pause": self.profile.hover_before_click,
            "cursor_steps": self.profile.cursor_move_steps,
            "settle_pause": self.profile.post_click_settle,
            "pre_pause": self.profile.pre_action_pause,
        }

    def get_type_delay_ms(self) -> int:
        """Per-character typing delay in milliseconds."""
        return self.profile.typing_delay_ms if self.enabled else 10

    def get_post_type_pause(self) -> float:
        """Seconds to pause after finishing typing."""
        return self.profile.post_type_pause if self.enabled else 0.0

    def get_scroll_pause(self) -> float:
        """Seconds to pause between scroll increments."""
        return self.profile.scroll_step_pause if self.enabled else 0.3

    def get_pre_action_pause(self) -> float:
        """Brief pause before any browser action."""
        return self.profile.pre_action_pause if self.enabled else 0.0
