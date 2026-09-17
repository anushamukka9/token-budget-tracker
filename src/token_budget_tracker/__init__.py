"""Token Budget Tracker.

Track LLM token usage and estimated cost across models, with per-model
pricing, per-project/team budgets and alerts, usage aggregation, and a
CLI + reporting layer.

Public API::

    from token_budget_tracker import UsageTracker, ModelPriceTable, Budget

    tracker = UsageTracker("~/.token_budget_tracker/usage.jsonl")
    tracker.add_model("my-local-llm", input_per_1k=0.0, output_per_1k=0.0)
    tracker.set_budget("research", monthly_usd=50.0)

    with tracker.track(model="gpt-4o-mini", project="research"):
        ...  # your LLM call happens here; set tokens afterwards
"""
from .pricing import ModelPriceTable
from .budgets import Budget, BudgetStore
from .storage import UsageLog, UsageRecord
from .tracker import UsageTracker, track_call
from .report import text_summary, html_summary

__all__ = [
    "ModelPriceTable",
    "Budget",
    "BudgetStore",
    "UsageLog",
    "UsageRecord",
    "UsageTracker",
    "track_call",
    "text_summary",
    "html_summary",
]

__version__ = "0.1.0"
