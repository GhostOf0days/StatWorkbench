"""Shared data boundaries for StatWorkbench (MIT licensed)."""

from __future__ import annotations

import math
from numbers import Integral, Real
from collections.abc import Mapping

MAX_ROWS = 100_000
MAX_COLUMNS = 1_000
MAX_CELLS = 2_000_000
MAX_TEXT_CHARACTERS = 16_000_000
MAX_CELL_CHARACTERS = 1_000_000
MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_REQUEST_BYTES = 64 * 1024 * 1024


def validate_dataset(data: dict) -> dict:
    """Return an independent, rectangular dataset with explicit missing cells."""
    if not isinstance(data, dict):
        raise ValueError("A dataset must be an object containing columns and rows.")
    columns, rows = data.get("columns"), data.get("rows")
    if not isinstance(columns, list) or not columns:
        raise ValueError("The dataset must have at least one column.")
    if len(columns) > MAX_COLUMNS:
        raise ValueError(f"Datasets may have at most {MAX_COLUMNS:,} columns.")
    if any(not isinstance(c, str) or not c.strip() for c in columns):
        raise ValueError("Every column must have a nonempty text name.")
    if any(len(c) > 1024 for c in columns):
        raise ValueError("Column names must not exceed 1,024 characters.")
    if len(set(columns)) != len(columns):
        raise ValueError("Duplicate column names are not allowed; rename them before continuing.")
    if not isinstance(rows, list):
        raise ValueError("Dataset rows must be an array.")
    if len(rows) > MAX_ROWS or len(rows) * len(columns) > MAX_CELLS:
        raise ValueError(f"Dataset limit: {MAX_ROWS:,} rows and {MAX_CELLS:,} cells.")
    name = data.get("name", "Dataset")
    if not isinstance(name, str) or len(name) > 1024:
        raise ValueError("Dataset name must be text of at most 1,024 characters.")
    text_count = sum(map(len, columns))
    copied = []
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, list) or len(row) != len(columns):
            raise ValueError(f"Row {index} must contain exactly {len(columns)} cells.")
        for value in row:
            if value is None or isinstance(value, bool):
                continue
            if isinstance(value, (int, float)):
                try:
                    finite = math.isfinite(value)
                except (OverflowError, ValueError):
                    finite = False
                if not finite:
                    raise ValueError(f"Row {index} contains a nonfinite number; use null for missing values.")
            elif isinstance(value, str):
                if len(value) > MAX_CELL_CHARACTERS:
                    raise ValueError(f"Row {index} contains text longer than {MAX_CELL_CHARACTERS:,} characters.")
                text_count += len(value)
            else:
                raise ValueError(f"Row {index} contains an unsupported cell type; cells must be scalar values.")
        if text_count > MAX_TEXT_CHARACTERS:
            raise ValueError("Dataset text exceeds the 16-million-character limit.")
        copied.append(list(row))
    return {"columns": list(columns), "rows": copied, "name": name or "Dataset"}


def sanitize_json(value, _depth=0):
    """Convert scientific scalars/arrays to strict JSON; undefined numbers become null."""
    if _depth > 64:
        raise ValueError("Result structure is too deeply nested.")
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, Integral):
        return int(value)
    if isinstance(value, Real):
        number = float(value)
        return number if math.isfinite(number) else None
    if isinstance(value, Mapping):
        return {str(k): sanitize_json(v, _depth + 1) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize_json(v, _depth + 1) for v in value]
    if hasattr(value, "tolist"):
        return sanitize_json(value.tolist(), _depth + 1)
    if hasattr(value, "item"):
        return sanitize_json(value.item(), _depth + 1)
    raise TypeError(f"Unsupported result type: {type(value).__name__}")


def reject_json_constant(value):
    raise ValueError(f"Nonstandard JSON number {value} is not allowed; use null for missing values.")


def unique_json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON field: {key}")
        result[key] = value
    return result
