# token-budget-tracker

Track LLM token usage and estimated cost across models: a user-extensible
per-model price table, per-project/team/app budgets with warn/breach alerts,
a JSONL usage log with aggregation (by day, model, project, team, app),
text and HTML dashboard reports, a decorator/context-manager API for
auto-recording calls, and a CLI.

## Install

```bash
pip install -e .        # from a checkout
# or: pip install token-budget-tracker
```

Requires Python ≥ 3.9, no third-party dependencies.

## Quickstart

```python
from token_budget_tracker import UsageTracker, text_summary

tracker = UsageTracker()  # data in ~/.token_budget_tracker/

tracker.set_budget("research-monthly", limit_usd=50.0,
                   scope="project", scope_value="research", period="month")

@tracker.track(model="gpt-4o-mini", project="research", team="ml")
def summarize(text):
    resp = llm.complete(text)   # your LLM call
    return {"answer": resp.text,
            "input_tokens": resp.usage.prompt_tokens,
            "output_tokens": resp.usage.completion_tokens}

with tracker.track(model="claude-3-5-haiku", project="research") as call:
    resp = llm.complete(prompt)
    call.set_usage(resp.usage.prompt_tokens, resp.usage.completion_tokens)

print(text_summary(tracker))
```

See `examples/quickstart.py` (runnable) and `docs/usage.md` for the full guide.

## CLI

```bash
token-budget log --model gpt-4o-mini --input-tokens 1200 --output-tokens 300 \
    --project research --team ml
token-budget budgets set research-monthly --limit 50 \
    --scope project --scope-value research --period month
token-budget budgets check
token-budget summary --format html --output report.html
token-budget prices list
```

## API

| Symbol | Purpose |
|---|---|
| `UsageTracker` | Main entry point: `record`, `track`, `set_budget`, `budget_status`, `check_budgets`, `aggregate`, `total_cost` |
| `ModelPriceTable` | Per-model USD/1K-token prices; `add_model`, `cost`, `save`/`load` |
| `UsageLog` / `UsageRecord` | Append-only JSONL log; `query`, `aggregate` by project/model/team/app/day |
| `Budget` / `BudgetStore` | Spend caps per scope and period, persisted as JSON |
| `text_summary` / `html_summary` | Dashboard reports |
| `token_budget_tracker.cli:main` | `token-budget` console script |

## Architecture

```
src/token_budget_tracker/
├── __init__.py     public API
├── pricing.py      ModelPriceTable (built-in defaults + user overrides)
├── storage.py      UsageLog: append-only JSONL, query + aggregation
├── budgets.py      Budget definitions, warn/breach thresholds, persistence
├── tracker.py      UsageTracker: record(), decorator/context manager, alert dispatch
├── report.py       text + standalone-HTML dashboards
└── cli.py          argparse CLI (token-budget / python -m token_budget_tracker)
```

`record()` prices each call, appends it to the JSONL log, then evaluates all
budgets and dispatches alerts through registered handlers (stdout by default;
plug in Slack/email/webhooks). Budgets latch warn/breach flags so you get one
alert per crossing; `reset_budget_flags()` clears them.

Price defaults are indicative — verify current provider rates and override
with `add_model()` or `token-budget prices add`.

## Development

```bash
python -m pytest -q
```

## License

MIT — Copyright 2026 Anusha Mukka. See [LICENSE](LICENSE).

Author: Anusha Mukka — [anushamukka.com](https://anushamukka.com)
