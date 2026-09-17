"""Budgets with threshold alerts.

A Budget caps spend for one scope (project/team/app/global) over a
period (day/month/total). When recorded spend crosses a threshold, the
tracker fires alert callbacks (email/webhook/slack/print by default).
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, asdict, field
from typing import Callable, Dict, List, Optional

AlertHandler = Callable[[dict], None]


@dataclass
class Budget:
    """A spend budget for one scope."""

    name: str
    limit_usd: float
    scope: str = "project"          # project | team | app | global
    scope_value: str = "default"    # e.g. the project name; ignored for global
    period: str = "month"          # day | month | total
    warn_at: float = 0.8           # warn when spend >= 80% of limit
    alert_at: float = 1.0          # alert when spend >= 100% of limit
    _warned: bool = field(default=False, repr=False)
    _alerted: bool = field(default=False, repr=False)

    def __post_init__(self) -> None:
        if self.limit_usd <= 0:
            raise ValueError("limit_usd must be positive.")
        if self.scope not in {"project", "team", "app", "global"}:
            raise ValueError(f"Bad scope {self.scope!r}.")
        if self.period not in {"day", "month", "total"}:
            raise ValueError(f"Bad period {self.period!r}.")

    def period_start(self, now: Optional[float] = None) -> float:
        if self.period == "total":
            return 0.0
        now = now if now is not None else time.time()
        lt = time.localtime(now)
        if self.period == "day":
            day_start = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0,
                                     lt.tm_wday, lt.tm_yday, lt.tm_isdst))
            return day_start
        month_start = time.mktime((lt.tm_year, lt.tm_mon, 1, 0, 0, 0,
                                   lt.tm_wday, lt.tm_yday, lt.tm_isdst))
        return month_start


def print_alert(event: dict) -> None:
    level = event["level"].upper()
    print(f"[{level}] Budget '{event['budget']}' "
          f"({event['scope']}:{event['scope_value']}, {event['period']}): "
          f"spent ${event['spent_usd']:.2f} of ${event['limit_usd']:.2f} "
          f"({event['pct']:.0%}).")


class BudgetStore:
    """Named budget collection, persisted as JSON."""

    def __init__(self, path: Optional[str] = None) -> None:
        self.path = os.path.expanduser(path) if path else None
        self._budgets: Dict[str, Budget] = {}
        if self.path and os.path.exists(self.path):
            self._load()

    def set(self, budget: Budget) -> None:
        self._budgets[budget.name] = budget
        self._save()

    def get(self, name: str) -> Budget:
        return self._budgets[name]

    def remove(self, name: str) -> None:
        del self._budgets[name]
        self._save()

    def all(self) -> List[Budget]:
        return list(self._budgets.values())

    def _save(self) -> None:
        if not self.path:
            return
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump({n: asdict(b) for n, b in self._budgets.items()}, fh, indent=2)

    def _load(self) -> None:
        with open(self.path, encoding="utf-8") as fh:
            data = json.load(fh)
        self._budgets = {n: Budget(**b) for n, b in data.items()}
