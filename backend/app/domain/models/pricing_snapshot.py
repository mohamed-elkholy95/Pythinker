"""Versioned pricing snapshots for provider billing estimates."""

import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, Field, field_validator


class PricingSnapshot(BaseModel):
    """Versioned pricing information for a provider/model pattern."""

    pricing_snapshot_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:16])
    provider: str
    model_pattern: str
    effective_from: datetime
    effective_to: datetime | None = None
    input_price_per_1m: float
    output_price_per_1m: float
    cached_read_price_per_1m: float | None = None
    cache_write_price_per_1m: float | None = None
    currency: str = "USD"
    source_url: str
    source_retrieved_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("effective_from", "effective_to", "source_retrieved_at")
    @classmethod
    def _require_timezone_aware_datetime(cls, value: datetime | None) -> datetime | None:
        """Reject naive datetimes so pricing snapshots compare deterministically."""
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Pricing snapshot datetimes must be timezone-aware")
        return value.astimezone(UTC)

    def is_effective_at(self, at_time: datetime) -> bool:
        """Return True when the snapshot applies at the given timestamp."""
        if at_time.tzinfo is None or at_time.utcoffset() is None:
            raise ValueError("Pricing snapshot lookup time must be timezone-aware")
        at_time = at_time.astimezone(UTC)
        if at_time < self.effective_from:
            return False
        return self.effective_to is None or at_time <= self.effective_to

    def matches_model(self, model_name: str) -> bool:
        """Return True when the snapshot matches the given model name."""
        pattern = self.model_pattern.lower().strip()
        model = model_name.lower().strip()
        if model == pattern:
            return True
        return model.startswith(f"{pattern}-")
