"""Shared output for the performance commands (HIMS-DATA-002, HIMS-OPS-017)."""

import json
from pathlib import Path

from django.core.serializers.json import DjangoJSONEncoder


def write_json(path: str, *, started_at, results: list[dict], rows: dict) -> None:
    Path(path).write_text(
        json.dumps(
            {"started_at": started_at, "results": results, "dataset": rows},
            cls=DjangoJSONEncoder,
            indent=1,
        ),
        encoding="utf-8",
    )


def mark(item: dict) -> str:
    return "ok  " if item.get("passed") else "FAIL"
