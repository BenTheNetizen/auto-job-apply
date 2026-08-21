"""Pydantic-backed CSV persistence engine.

One CsvStore per CSV file; row models live in the subsystems that own the
files. Supports JSON-in-column for structured fields (list/dict/nested
models), atomic writes via temp-file + os.replace, and cross-process safety
via filelock.

Concurrency contract: the engine is synchronous and holds the file lock only
for the duration of a single method call. Callers must never hold engine
locks across LLM/Playwright work.

Datetimes: store tz-aware UTC values in models; ``model_dump(mode="json")``
serializes them as ISO-8601 strings which pydantic re-parses on load.
"""

from __future__ import annotations

import csv
import json
import os
import types
import typing
from pathlib import Path
from typing import Any, Generic, TypeVar, get_args, get_origin

from filelock import FileLock
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


def _is_str_field(annotation: Any) -> bool:
    """True if the field annotation is (or may be) a plain string."""
    if annotation is str:
        return True
    origin = get_origin(annotation)
    if origin in (typing.Union, types.UnionType):
        return str in get_args(annotation)
    return False


def _is_structured_field(annotation: Any) -> bool:
    """True if the field value should be JSON-encoded in its CSV cell."""
    if _is_str_field(annotation):
        return False
    origin = get_origin(annotation)
    if origin in (list, dict, tuple, set):
        return True
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return True
    if origin in (typing.Union, types.UnionType):
        return any(
            _is_structured_field(a) for a in get_args(annotation) if a is not type(None)
        )
    return False


class CsvStore(Generic[T]):
    """Generic CSV store keyed by a model field (default ``id``)."""

    def __init__(self, path: str | Path, model: type[T], key_field: str = "id") -> None:
        self.path = Path(path)
        self.model = model
        self.key_field = key_field
        # Header order is stable and matches model_fields declaration order.
        self.fieldnames: list[str] = list(model.model_fields.keys())
        self._lock = FileLock(str(self.path) + ".lock")

    # ---- serialization -------------------------------------------------

    def _encode_cell(self, name: str, value: Any) -> str:
        if value is None:
            return ""
        if _is_structured_field(self.model.model_fields[name].annotation):
            return json.dumps(value)
        return str(value)

    def _row_to_cells(self, row: T) -> dict[str, str]:
        dumped = row.model_dump(mode="json")
        return {name: self._encode_cell(name, dumped.get(name)) for name in self.fieldnames}

    def _cells_to_row(self, cells: dict[str, str]) -> T:
        data: dict[str, Any] = {}
        for name in self.fieldnames:
            raw = cells.get(name)
            if raw is None or raw == "":
                continue  # missing column or empty cell -> model default/None
            field = self.model.model_fields[name]
            if _is_structured_field(field.annotation):
                data[name] = json.loads(raw)
            else:
                # pydantic coerces scalars, incl. datetime from ISO-8601 str
                data[name] = raw
        return self.model.model_validate(data)

    # ---- io ------------------------------------------------------------

    def read_all(self) -> list[T]:
        """Read every row; empty list when the file does not exist yet."""
        with self._lock:
            return self._read_all_unlocked()

    def _read_all_unlocked(self) -> list[T]:
        if not self.path.exists():
            return []
        with self.path.open(newline="", encoding="utf-8") as f:
            return [self._cells_to_row(r) for r in csv.DictReader(f)]

    def _write_all(self, rows: list[T]) -> None:
        with self._lock:
            self._write_all_unlocked(rows)

    def _write_all_unlocked(self, rows: list[T]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        with tmp.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=self.fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow(self._row_to_cells(row))
        os.replace(tmp, self.path)

    # ---- public api ----------------------------------------------------
    # Compound read-modify-write ops hold the file lock across the whole
    # operation (FileLock is re-entrant within a process), so two writers
    # cannot interleave and lose rows. Single ops never span LLM/browser
    # work, so lock hold time stays in the microseconds-to-ms range.

    def append(self, row: T) -> None:
        """Append one row (rewrites the file atomically)."""
        with self._lock:
            self._write_all_unlocked([*self._read_all_unlocked(), row])

    def get(self, key: Any) -> T | None:
        """First row whose key field matches, else None."""
        key = str(key)
        for row in self.read_all():
            if str(getattr(row, self.key_field, None)) == key:
                return row
        return None

    def update(self, key: Any, row: T) -> bool:
        """Replace the row matching ``key``. False if no such row."""
        key = str(key)
        with self._lock:
            rows = self._read_all_unlocked()
            for i, existing in enumerate(rows):
                if str(getattr(existing, self.key_field, None)) == key:
                    rows[i] = row
                    self._write_all_unlocked(rows)
                    return True
            return False

    def upsert(self, key_field: str, row: T) -> None:
        """Insert or replace by an arbitrary key field."""
        key = str(getattr(row, key_field))
        with self._lock:
            rows = self._read_all_unlocked()
            for i, existing in enumerate(rows):
                if str(getattr(existing, key_field, None)) == key:
                    rows[i] = row
                    self._write_all_unlocked(rows)
                    return
            self._write_all_unlocked([*rows, row])

    def append_event(self, key: Any, list_field: str, event: BaseModel) -> None:
        """Append ``event`` to a list-typed field of the row matching ``key``."""
        key = str(key)
        with self._lock:
            rows = self._read_all_unlocked()
            for i, existing in enumerate(rows):
                if str(getattr(existing, self.key_field, None)) == key:
                    current = list(getattr(existing, list_field) or [])
                    current.append(event)
                    rows[i] = existing.model_copy(update={list_field: current})
                    self._write_all_unlocked(rows)
                    return
            raise KeyError(f"{self.model.__name__} with {self.key_field}={key!r} not found")


__all__ = ["CsvStore"]
