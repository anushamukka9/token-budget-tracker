"""Budget alerts, per-project rollups, and CSV export.

Simulates a month of LLM usage across two projects, shows warn/breach
alerts firing through a custom handler, prints a per-project cost rollup,
and exports the raw usage log to CSV.

Runs from the repo root (no third-party dependencies):
    python examples/budget_alerts.py
"""

import csv
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from token_budget_tracker import UsageTracker, text_summary  # noqa: E402


def main():
    tmp = tempfile.mkdtemp(prefix="tbt-example-")
    tracker = UsageTracker(
        log_path=os.path.join(tmp, "usage.jsonl"),
        budget_path=os.path.join(tmp, "budgets.json"),
        price_path=None,  # use built-in (approximate) prices
    )

    # 1. Collect alerts in a list instead of printing them.
    events = []
    tracker.add_alert_handler(events.append)

    # 2. A $2.00 monthly budget on the research project; warn at 50%.
    tracker.set_budget("research-monthly", limit_usd=2.00, scope="project",
                       scope_value="research", period="month", warn_at=0.5)

    # 3. Log some usage: cheap model for research, pricier one for prod.
    tracker.record("gpt-4o-mini", 5_000, 1_000, project="research", team="ml")
    tracker.record("gpt-4o-mini", 20_000, 5_000, project="research", team="ml")
    tracker.record("gpt-4o", 500, 200, project="prod", team="ml")
    tracker.record("claude-3-5-haiku", 3_000, 1_000, project="prod", team="ml")

    print("=== alerts fired ===")
    for e in events:
        print(f"  [{e['level'].upper()}] {e['budget']}: "
              f"${e['spent_usd']:.2f} of ${e['limit_usd']:.2f} ({e['pct']:.0%})")

    print("\n=== per-project rollup ===")
    for project, agg in sorted(tracker.aggregate("project").items(),
                               key=lambda kv: -kv[1]["cost_usd"]):
        print(f"  {project:<10} {agg['calls']:>3} calls  "
              f"{agg['total_tokens']:>8,} tokens  ${agg['cost_usd']:.2f}")

    print("\n=== per-model rollup ===")
    for model, agg in sorted(tracker.aggregate("model").items(),
                             key=lambda kv: -kv[1]["cost_usd"]):
        print(f"  {model:<18} ${agg['cost_usd']:.2f}")

    # 4. Export the raw log to CSV for spreadsheets / finance.
    csv_path = os.path.join(tmp, "usage.csv")
    n = tracker.export_csv(csv_path)
    with open(csv_path, newline="", encoding="utf-8") as fh:
        columns = next(csv.reader(fh))
    print(f"\n=== exported {n} rows to {csv_path} ===")
    print("columns:", ", ".join(columns))

    print("\n" + text_summary(tracker))


if __name__ == "__main__":
    main()
