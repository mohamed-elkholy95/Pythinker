from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel


@dataclass(frozen=True)
class SchemaComplexityProfile:
    optional_field_count: int
    union_count: int
    max_nesting_depth: int
    total_property_count: int
    strict_tool_count: int
    score: float

    @property
    def is_strict_eligible(self) -> bool:
        return (
            self.union_count <= 5
            and self.max_nesting_depth <= 4
            and self.total_property_count <= 30
            and self.strict_tool_count <= 10
        )

    @classmethod
    def from_model(cls, model: type[BaseModel], *, strict_tool_count: int = 0) -> SchemaComplexityProfile:
        return cls.from_schema(model.model_json_schema(), strict_tool_count=strict_tool_count)

    @classmethod
    def from_schema(cls, schema: dict[str, Any], *, strict_tool_count: int = 0) -> SchemaComplexityProfile:
        defs = schema.get("$defs") or schema.get("definitions") or {}

        optional_field_count = 0
        union_count = 0
        max_nesting_depth = 0
        total_property_count = 0

        def resolve_ref(node: dict[str, Any]) -> dict[str, Any]:
            ref = node.get("$ref")
            if not isinstance(ref, str):
                return node
            if "#/$defs/" in ref:
                key = ref.split("#/$defs/", 1)[1]
                candidate = defs.get(key)
                if isinstance(candidate, dict):
                    return candidate
            if "#/definitions/" in ref:
                key = ref.split("#/definitions/", 1)[1]
                candidate = defs.get(key)
                if isinstance(candidate, dict):
                    return candidate
            return node

        def walk(node: Any, depth: int) -> None:
            nonlocal optional_field_count, union_count, max_nesting_depth, total_property_count
            if not isinstance(node, dict):
                return

            node = resolve_ref(node)
            max_nesting_depth = max(max_nesting_depth, depth)

            any_of = node.get("anyOf")
            one_of = node.get("oneOf")
            if isinstance(any_of, list):
                union_count += 1
                for item in any_of:
                    walk(item, depth + 1)
            if isinstance(one_of, list):
                union_count += 1
                for item in one_of:
                    walk(item, depth + 1)

            node_type = node.get("type")
            if isinstance(node_type, list) and len(node_type) > 1:
                union_count += 1

            if node.get("type") == "object" or "properties" in node:
                properties = node.get("properties", {})
                if isinstance(properties, dict):
                    total_property_count += len(properties)
                    required = node.get("required", [])
                    required_set = set(required) if isinstance(required, list) else set()
                    for key, value in properties.items():
                        if key not in required_set:
                            optional_field_count += 1
                        walk(value, depth + 1)

            items = node.get("items")
            if isinstance(items, dict):
                walk(items, depth + 1)
            elif isinstance(items, list):
                for item in items:
                    walk(item, depth + 1)

        walk(schema, 1)

        score = (
            optional_field_count * 0.25
            + union_count * 2.0
            + max_nesting_depth * 1.0
            + total_property_count * 0.3
            + strict_tool_count * 1.0
        )
        return cls(
            optional_field_count=optional_field_count,
            union_count=union_count,
            max_nesting_depth=max_nesting_depth,
            total_property_count=total_property_count,
            strict_tool_count=strict_tool_count,
            score=score,
        )
