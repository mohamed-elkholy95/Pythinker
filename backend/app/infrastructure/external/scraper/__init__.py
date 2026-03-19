"""Scrapling infrastructure adapter package."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.infrastructure.external.scraper.scrapling_adapter import (
        ScraplingAdapter,
        get_scraping_adapter,
    )

__all__ = ["ScraplingAdapter", "get_scraping_adapter"]


def __getattr__(name: str) -> object:
    """Lazy-load scrapling adapter to avoid import errors when optional deps are missing."""
    if name in __all__:
        from app.infrastructure.external.scraper.scrapling_adapter import (
            ScraplingAdapter as _ScraplingAdapter,
        )
        from app.infrastructure.external.scraper.scrapling_adapter import (
            get_scraping_adapter as _get_scraping_adapter,
        )

        _exports = {
            "ScraplingAdapter": _ScraplingAdapter,
            "get_scraping_adapter": _get_scraping_adapter,
        }
        # Cache in module globals so subsequent accesses skip __getattr__
        globals().update(_exports)
        return _exports[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
