from __future__ import annotations

from pydantic import BaseModel

from app.domain.services.validation.schema_profile import SchemaComplexityProfile


class _NestedInner(BaseModel):
    label: str


class _NestedOuter(BaseModel):
    inner: _NestedInner
    maybe_text: str | None = None
    score: int | str


def test_schema_profile_computes_expected_counts() -> None:
    profile = SchemaComplexityProfile.from_model(_NestedOuter)

    assert profile.optional_field_count >= 1
    assert profile.union_count >= 2  # maybe_text + score
    assert profile.max_nesting_depth >= 2
    assert profile.total_property_count >= 3


def test_schema_profile_strict_eligibility_for_simple_model() -> None:
    class _Simple(BaseModel):
        name: str
        value: int

    profile = SchemaComplexityProfile.from_model(_Simple)

    assert profile.is_strict_eligible is True


def test_schema_profile_rejects_overly_complex_schema() -> None:
    class _Complex(BaseModel):
        f01: str | None = None
        f02: str | None = None
        f03: str | None = None
        f04: str | None = None
        f05: str | None = None
        f06: str | None = None
        f07: str | None = None
        f08: str | None = None
        f09: str | None = None
        f10: str | None = None
        f11: str | None = None
        f12: str | None = None
        f13: str | None = None
        f14: str | None = None
        f15: str | None = None
        f16: str | None = None
        f17: str | None = None
        f18: str | None = None
        f19: str | None = None
        f20: str | None = None
        f21: str | None = None
        f22: str | None = None
        f23: str | None = None
        f24: str | None = None
        f25: str | None = None
        f26: str | None = None
        f27: str | None = None
        f28: str | None = None
        f29: str | None = None
        f30: str | None = None
        f31: str | None = None
        f32: str | None = None
        f33: str | None = None
        f34: str | None = None
        f35: str | None = None
        mixed: int | str | float | None = None

    profile = SchemaComplexityProfile.from_model(_Complex)

    assert profile.total_property_count >= 36
    assert profile.is_strict_eligible is False
