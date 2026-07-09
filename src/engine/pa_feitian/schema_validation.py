"""JSON Schema validation helpers for PA / Feitian contracts."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


SCHEMA_DIR = Path(__file__).resolve().parents[3] / "doc" / "schemas"


class JsonSchemaValidationError(ValueError):
    """Raised when a contract payload does not satisfy its JSON Schema."""


def _path_label(path: Sequence[str | int]) -> str:
    if not path:
        return "$"
    label = "$"
    for part in path:
        if isinstance(part, int):
            label += f"[{part}]"
        else:
            label += f".{part}"
    return label


def _schema_name(ref: str) -> str:
    parsed = urlparse(ref)
    if parsed.scheme and parsed.path:
        return Path(parsed.path).name
    return ref


def _decode_pointer_part(part: str) -> str:
    return part.replace("~1", "/").replace("~0", "~")


class _SchemaValidator:
    def __init__(self, schema_dir: Path) -> None:
        self.schema_dir = schema_dir
        self._schemas: dict[str, dict[str, Any]] = {}

    def load_schema(self, schema_name: str | Path) -> dict[str, Any]:
        name = _schema_name(str(schema_name))
        if name not in self._schemas:
            path = self.schema_dir / name
            with path.open(encoding="utf-8") as f:
                schema = json.load(f)
            self._schemas[name] = schema
            schema_id = schema.get("$id")
            if isinstance(schema_id, str):
                self._schemas[schema_id] = schema
        return self._schemas[name]

    def validate(self, data: Any, schema_name: str | Path) -> None:
        schema = self.load_schema(schema_name)
        self._validate(data, schema, schema, ())

    def _resolve_ref(
        self,
        ref: str,
        root_schema: Mapping[str, Any],
    ) -> tuple[Mapping[str, Any] | bool, Mapping[str, Any]]:
        ref_target, _, fragment = ref.partition("#")
        target_root = root_schema if not ref_target else self.load_schema(ref_target)
        if not fragment:
            return target_root, target_root
        if not fragment.startswith("/"):
            raise JsonSchemaValidationError(f"unsupported JSON Schema ref fragment: {ref}")
        node: Mapping[str, Any] | bool | Any = target_root
        for raw_part in fragment.lstrip("/").split("/"):
            part = _decode_pointer_part(raw_part)
            if not isinstance(node, Mapping) or part not in node:
                raise JsonSchemaValidationError(f"unresolvable JSON Schema ref: {ref}")
            node = node[part]
        if not isinstance(node, (Mapping, bool)):
            raise JsonSchemaValidationError(f"JSON Schema ref does not target a schema: {ref}")
        return node, target_root

    def _validate(
        self,
        data: Any,
        schema: Mapping[str, Any] | bool,
        root_schema: Mapping[str, Any],
        data_path: tuple[str | int, ...],
    ) -> None:
        if schema is True:
            return
        if schema is False:
            raise self._error("boolean false schema rejected value", data_path)

        ref = schema.get("$ref")
        if isinstance(ref, str):
            target_schema, target_root = self._resolve_ref(ref, root_schema)
            self._validate(data, target_schema, target_root, data_path)
            if len(schema) == 1:
                return

        if "const" in schema and data != schema["const"]:
            raise self._error(f"expected const {schema['const']!r}, got {data!r}", data_path)

        if "enum" in schema and data not in schema["enum"]:
            raise self._error(f"expected one of {schema['enum']!r}, got {data!r}", data_path)

        schema_type = schema.get("type")
        if schema_type is not None and not self._matches_type(data, schema_type):
            raise self._error(f"expected type {schema_type!r}, got {type(data).__name__}", data_path)

        if isinstance(data, Mapping):
            self._validate_object(data, schema, root_schema, data_path)
        elif isinstance(data, list):
            self._validate_array(data, schema, root_schema, data_path)
        elif isinstance(data, str):
            self._validate_string(data, schema, data_path)
        elif isinstance(data, int | float) and not isinstance(data, bool):
            self._validate_number(data, schema, data_path)

    def _matches_type(self, data: Any, schema_type: str | Sequence[str]) -> bool:
        types = [schema_type] if isinstance(schema_type, str) else list(schema_type)
        return any(self._matches_one_type(data, candidate) for candidate in types)

    def _matches_one_type(self, data: Any, schema_type: str) -> bool:
        if schema_type == "object":
            return isinstance(data, Mapping)
        if schema_type == "array":
            return isinstance(data, list)
        if schema_type == "string":
            return isinstance(data, str)
        if schema_type == "integer":
            return isinstance(data, int) and not isinstance(data, bool)
        if schema_type == "number":
            return isinstance(data, int | float) and not isinstance(data, bool)
        if schema_type == "boolean":
            return isinstance(data, bool)
        if schema_type == "null":
            return data is None
        raise JsonSchemaValidationError(f"unsupported JSON Schema type: {schema_type}")

    def _validate_object(
        self,
        data: Mapping[str, Any],
        schema: Mapping[str, Any],
        root_schema: Mapping[str, Any],
        data_path: tuple[str | int, ...],
    ) -> None:
        required = schema.get("required", [])
        for key in required:
            if key not in data:
                raise self._error(f"missing required property {key!r}", data_path)

        properties = schema.get("properties", {})
        if not isinstance(properties, Mapping):
            raise JsonSchemaValidationError("schema properties must be an object")

        additional = schema.get("additionalProperties", True)
        for key, value in data.items():
            if key in properties:
                self._validate(value, properties[key], root_schema, (*data_path, key))
            elif additional is False:
                raise self._error(f"unexpected property {key!r}", data_path)
            elif isinstance(additional, Mapping) or isinstance(additional, bool):
                self._validate(value, additional, root_schema, (*data_path, key))

    def _validate_array(
        self,
        data: list[Any],
        schema: Mapping[str, Any],
        root_schema: Mapping[str, Any],
        data_path: tuple[str | int, ...],
    ) -> None:
        min_items = schema.get("minItems")
        if min_items is not None and len(data) < min_items:
            raise self._error(f"expected at least {min_items} items", data_path)
        items_schema = schema.get("items")
        if items_schema is None:
            return
        for index, value in enumerate(data):
            self._validate(value, items_schema, root_schema, (*data_path, index))

    def _validate_string(
        self,
        data: str,
        schema: Mapping[str, Any],
        data_path: tuple[str | int, ...],
    ) -> None:
        min_length = schema.get("minLength")
        if min_length is not None and len(data) < min_length:
            raise self._error(f"expected string length >= {min_length}", data_path)
        max_length = schema.get("maxLength")
        if max_length is not None and len(data) > max_length:
            raise self._error(f"expected string length <= {max_length}", data_path)
        pattern = schema.get("pattern")
        if pattern is not None and re.search(pattern, data) is None:
            raise self._error(f"expected string to match pattern {pattern!r}", data_path)
        if schema.get("format") == "date-time":
            self._validate_datetime(data, data_path)

    def _validate_number(
        self,
        data: int | float,
        schema: Mapping[str, Any],
        data_path: tuple[str | int, ...],
    ) -> None:
        minimum = schema.get("minimum")
        if minimum is not None and data < minimum:
            raise self._error(f"expected number >= {minimum}", data_path)
        maximum = schema.get("maximum")
        if maximum is not None and data > maximum:
            raise self._error(f"expected number <= {maximum}", data_path)

    def _validate_datetime(self, data: str, data_path: tuple[str | int, ...]) -> None:
        try:
            parsed = datetime.fromisoformat(data.replace("Z", "+00:00"))
        except ValueError as exc:
            raise self._error("expected RFC 3339 date-time string", data_path) from exc
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise self._error("expected timezone-aware date-time string", data_path)

    def _error(self, message: str, data_path: tuple[str | int, ...]) -> JsonSchemaValidationError:
        return JsonSchemaValidationError(f"{_path_label(data_path)}: {message}")


def validate_json_schema(
    data: Any,
    schema_name: str | Path,
    *,
    schema_dir: str | Path = SCHEMA_DIR,
) -> None:
    """Validate data against a local JSON Schema file.

    Relative and URL-like external refs are resolved against ``schema_dir`` by
    schema filename. This keeps snapshot v1 validation deterministic without
    network access.
    """
    _SchemaValidator(Path(schema_dir)).validate(data, schema_name)


def validate_pa_feitian_snapshot_v1_schema(
    data: Any,
    *,
    schema_dir: str | Path = SCHEMA_DIR,
) -> None:
    validate_json_schema(data, "pa_feitian_snapshot_v1.schema.json", schema_dir=schema_dir)


def validate_pa_feitian_run_manifest_schema(
    data: Any,
    *,
    schema_dir: str | Path = SCHEMA_DIR,
) -> None:
    validate_json_schema(data, "pa_feitian_run_manifest_v1.schema.json", schema_dir=schema_dir)


def validate_pa_feitian_decision_intent_schema(
    data: Any,
    *,
    schema_dir: str | Path = SCHEMA_DIR,
) -> None:
    validate_json_schema(data, "pa_feitian_decision_intent_v1.schema.json", schema_dir=schema_dir)
