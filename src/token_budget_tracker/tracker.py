"""The main tracker: record usage, check budgets, fire alerts."""

from __future__ import annotations

import functools
import os
import time
from contextlib import contextmanager
from typing import Callable, Dict, Iterator, List, Optional

from .pricing import ModelPriceTable
from .storage import UsageLog, UsageRecord
from .budgets import Budget, BudgetStore, AlertHandler, print_alert

DEFAULT_DIR = os.path.expanduser("~/.token_budget_tracker")


class UsageTracker:
    """Record LLM usage, compute costs, enforce budgets, aggregate spend."""

    def __init__(
        self,
        log_path: str = os.path.join(DEFAULT_DIR, "usage.jsonl"),
        budget_path: str = os.path.join(DEFAULT_DIR, "budgets.json"),
        price_path: Optional[str] = os.path.join(DEFAULT_DIR, "prices.json"),
        on_alert: Optional[AlertHandler] = None,
    ) -> None:
        self.prices = ModelPriceTable()
        if price_path and os.path.exists(price_path):
            self.prices = ModelPriceTable.load(price_path)
        self.price_path = price_path
        self.log = UsageLog(log_path)
        self.budgets = BudgetStore(budget_path)
        self._alert_handlers: List[AlertHandler] = [on_alert or print_alert]

    # ---- alert handling ----------------------------------------------
    def add_alert_handler(self, handler: AlertHandler) -> None:
        self._alert_handlers.append(handler)

    def _fire_alert(self, event: dict) -> None:
        for handler in self._alert_handlers:
            handler(event)

    # ---- recording ----------------------------------------------------
    def record(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        project: str = "default",
        team: str = "",
        app: str = "",
        metadata: Optional[Dict] = None,
    ) -> UsageRecord:
        """Record one LLM call and return the stored record."""
        cost = self.prices.cost(model, input_tokens, output_tokens)
        rec = UsageRecord(
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            project=project,
            team=team,
            app=app,
            cost_usd=round(cost, 6),
            metadata=metadata or {},
        )
        self.log.append(rec)
        self.check_budgets()
        return rec

    def add_model(self, model: str, input_per_1k: float, output_per_1k: float,
                  notes: str = ""):
        price = self.prices.add_model(model, input_per_1k, output_per_1k, notes)
        if self.price_path:
            self.prices.save(self.price_path)
        return price

    # ---- decorator & context manager ----------------------------------
    def track(
        self,
        model: str,
        project: str = "default",
        team: str = "",
        app: str = "",
    ):
        """Decorator/context-manager that records one call.

        Works in two ways::

            @tracker.track(model="gpt-4o-mini", project="demo")
            def summarize(text):
                ...  # return dict with usage info, or set tokens

            with tracker.track(model="gpt-4o-mini") as call:
                response = llm.complete(prompt)  # your code
                call.set_usage(input_tokens=120, output_tokens=45)

        When used as a decorator, the wrapped function may optionally return
        a dict containing ``input_tokens`` / ``output_tokens`` keys, which
        are picked up automatically.
        """
        tracker = self

        class _Call:
            def __init__(self):
                self.input_tokens = 0
                self.output_tokens = 0
                self.record: Optional[UsageRecord] = None

            def set_usage(self, input_tokens: int, output_tokens: int) -> None:
                self.input_tokens = int(input_tokens)
                self.output_tokens = int(output_tokens)

            def _finish(self):
                self.record = tracker.record(
                    model=model,
                    input_tokens=self.input_tokens,
                    output_tokens=self.output_tokens,
                    project=project,
                    team=team,
                    app=app,
                )

        @contextmanager
        def _ctx() -> Iterator[_Call]:
            call = _Call()
            try:
                yield call
            finally:
                call._finish()

        def decorator(fn):
            @functools.wraps(fn)
            def wrapper(*args, **kwargs):
                with _ctx() as call:
                    result = fn(*args, **kwargs)
                    if isinstance(result, dict):
                        try:
                            call.set_usage(
                                result.get("input_tokens", 0),
                                result.get("output_tokens", 0),
                            )
                        except (TypeError, ValueError):
                            pass
                return result
            return wrapper

        # Allow bare `with tracker.track(...)` and `@tracker.track(...)`.
        _ctx.decorator = decorator  # type: ignore[attr-defined]
        return _Proxy(_ctx, decorator)

    # ---- budgets ------------------------------------------------------
    def set_budget(self, name: str, limit_usd: float, scope: str = "project",
                   scope_value: str = "default", period: str = "month",
                   warn_at: float = 0.8) -> Budget:
        budget = Budget(name=name, limit_usd=limit_usd, scope=scope,
                        scope_value=scope_value, period=period, warn_at=warn_at)
        self.budgets.set(budget)
        return budget

    def budget_status(self, name: str, now: Optional[float] = None) -> dict:
        """Current spend vs limit for one budget."""
        budget = self.budgets.get(name)
        now = now if now is not None else time.time()
        records = self.log.query(since=budget.period_start(now), until=now)
        if budget.scope == "project":
            records = [r for r in records if r.project == budget.scope_value]
        elif budget.scope == "team":
            records = [r for r in records if r.team == budget.scope_value]
        elif budget.scope == "app":
            records = [r for r in records if r.app == budget.scope_value]
        spent = sum(r.cost_usd for r in records)
        return {
            "budget": budget.name,
            "scope": budget.scope,
            "scope_value": budget.scope_value,
            "period": budget.period,
            "limit_usd": budget.limit_usd,
            "spent_usd": round(spent, 6),
            "remaining_usd": round(budget.limit_usd - spent, 6),
            "pct": spent / budget.limit_usd if budget.limit_usd else 0.0,
            "calls": len(records),
        }

    def check_budgets(self, now: Optional[float] = None) -> List[dict]:
        """Evaluate all budgets; fire warn/breach alerts on crossings."""
        events = []
        for budget in self.budgets.all():
            status = self.budget_status(budget.name, now=now)
            pct = status["pct"]
            if pct >= budget.alert_at and not budget._alerted:
                budget._alerted = True
                budget._warned = True
                event = {**status, "level": "breach"}
            elif pct >= budget.warn_at and not budget._warned:
                budget._warned = True
                event = {**status, "level": "warn"}
            else:
                continue
            events.append(event)
            self._fire_alert(event)
        if events:
            self.budgets._save()
        return events

    def reset_budget_flags(self, name: Optional[str] = None) -> None:
        """Reset warn/breach flags (e.g. at the start of a new period)."""
        targets = [self.budgets.get(name)] if name else self.budgets.all()
        for b in targets:
            b._warned = False
            b._alerted = False
        self.budgets._save()

    # ---- aggregation --------------------------------------------------
    def aggregate(self, by: str = "project", **query_kwargs) -> Dict[str, dict]:
        records = self.log.query(**query_kwargs) if query_kwargs else None
        return self.log.aggregate(by=by, records=records)

    def total_cost(self, **query_kwargs) -> float:
        records = self.log.query(**query_kwargs)
        return self.log.total_cost(records)


class _Proxy:
    """Lets tracker.track(...) act as both context manager and decorator."""

    def __init__(self, ctx_factory, decorator):
        self._ctx_factory = ctx_factory
        self._decorator = decorator

    def __enter__(self):
        self._ctx = self._ctx_factory()
        return self._ctx.__enter__()

    def __exit__(self, *exc):
        return self._ctx.__exit__(*exc)

    def __call__(self, fn):
        return self._decorator(fn)


def track_call(tracker: UsageTracker, **kwargs):
    """Module-level helper: ``track_call(tracker, model=...)`` as decorator."""
    return tracker.track(**kwargs)
