"""Persistent usage log.

Records are appended to a JSONL file, one JSON object per line, so the
log is crash-safe and easy to process with external tools.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, asdict, field
from typing import Callable, Dict, Iterable, Iterator, List, Optional


@dataclass
class UsageRecord:
    """One logged LLM call."""

    model: str
    input_tokens: int
    output_tokens: int
    project: str = "default"
    team: str = ""
    app: str = ""
    timestamp: float = field(default_factory=time.time)
    cost_usd: float = 0.0
    metadata: Dict = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "UsageRecord":
        return cls(**data)


class UsageLog:
    """Append-only JSONL usage log with in-memory querying."""

    def __init__(self, path: str) -> None:
        self.path = os.path.expanduser(path)
        if os.path.dirname(self.path):
            os.makedirs(os.path.dirname(self.path), exist_ok=True)

    def append(self, record: UsageRecord) -> None:
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record.to_dict()) + "\n")

    def iter_records(self) -> Iterator[UsageRecord]:
        if not os.path.exists(self.path):
            return
        with open(self.path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    yield UsageRecord.from_dict(json.loads(line))

    def query(
        self,
        project: Optional[str] = None,
        model: Optional[str] = None,
        since: Optional[float] = None,
        until: Optional[float] = None,
        predicate: Optional[Callable[[UsageRecord], bool]] = None,
    ) -> List[UsageRecord]:
        out = []
        for rec in self.iter_records():
            if project is not None and rec.project != project:
                continue
            if model is not None and rec.model != model:
                continue
            if since is not None and rec.timestamp < since:
                continue
            if until is not None and rec.timestamp > until:
                continue
            if predicate is not None and not predicate(rec):
                continue
            out.append(rec)
        return out

    def __len__(self) -> int:
        return sum(1 for _ in self.iter_records())

    def clear(self) -> None:
        if os.path.exists(self.path):
            os.remove(self.path)

    # ---- aggregation -------------------------------------------------
    def aggregate(
        self,
        by: str = "project",
        records: Optional[Iterable[UsageRecord]] = None,
    ) -> Dict[str, dict]:
        """Aggregate cost/tokens keyed by `by` (project, model, team, app, or day)."""
        valid = {"project", "model", "team", "app", "day"}
        if by not in valid:
            raise ValueError(f"by must be one of {sorted(valid)}, got {by!r}")
        totals: Dict[str, dict] = {}
        for rec in records if records is not None else self.iter_records():
            key = self._bucket_key(rec, by)
            agg = totals.setdefault(
                key,
                {"calls": 0, "input_tokens": 0, "output_tokens": 0,
                 "total_tokens": 0, "cost_usd": 0.0},
            )
            agg["calls"] += 1
            agg["input_tokens"] += rec.input_tokens
            agg["output_tokens"] += rec.output_tokens
            agg["total_tokens"] += rec.total_tokens
            agg["cost_usd"] += rec.cost_usd
        return totals

    @staticmethod
    def _bucket_key(rec: UsageRecord, by: str) -> str:
        if by == "project":
            return rec.project
        if by == "model":
            return rec.model
        if by == "team":
            return rec.team or "(no team)"
        if by == "app":
            return rec.app or "(no app)"
        # day: local calendar date of the record
        return time.strftime("%Y-%m-%d", time.localtime(rec.timestamp))

    def total_cost(self, records: Optional[Iterable[UsageRecord]] = None) -> float:
        return sum(
            r.cost_usd for r in (records if records is not None else self.iter_records())
        )
