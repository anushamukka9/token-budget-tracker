# Usage guide

`token-budget-tracker` records every LLM call (model, token counts, project /
team / app), prices it with a per-model price table, enforces budgets with
alerts, and aggregates spend by day, model, project, team, or app. Data lives
in `~/.token_budget_tracker/` by default (`usage.jsonl`, `budgets.json`,
`prices.json`) — plain JSON you can inspect or back up yourself.

## 1. Pricing

Built-in indicative prices cover common OpenAI / Anthropic / Google /
DeepSeek / Mistral / Llama models. They are starting points — verify current
rates with your provider and override what you use:

```python
from token_budget_tracker import UsageTracker

t = UsageTracker()
t.add_model("my-fine-tune", input_per_1k=1.25, output_per_1k=5.0,
            notes="internal fine-tune, Sept 2026 pricing")
t.prices.cost("gpt-4o-mini", input_tokens=1000, output_tokens=500)
```

The price table persists to `prices.json` automatically.

## 2. Recording usage

Three equivalent ways:

```python
# a) direct
t.record("gpt-4o-mini", input_tokens=1200, output_tokens=300,
         project="research", team="ml", app="rag-prototype")

# b) decorator — return token counts from the wrapped function
@t.track(model="gpt-4o-mini", project="research")
def summarize(text):
    resp = llm.complete(text)          # your call
    return {"answer": resp.text,
            "input_tokens": resp.usage.prompt_tokens,
            "output_tokens": resp.usage.completion_tokens}

# c) context manager — full control
with t.track(model="claude-3-5-haiku", project="research") as call:
    resp = llm.complete(prompt)
    call.set_usage(resp.usage.prompt_tokens, resp.usage.completion_tokens)
```

## 3. Budgets and alerts

A budget caps spend for one scope (`project` / `team` / `app` / `global`)
over a period (`day` / `month` / `total`):

```python
t.set_budget("research-monthly", limit_usd=50.0,
             scope="project", scope_value="research",
             period="month", warn_at=0.8)

t.budget_status("research-monthly")
# {'spent_usd': 12.4, 'limit_usd': 50.0, 'pct': 0.248, ...}

events = t.check_budgets()   # also runs automatically after each record()
```

When spend crosses `warn_at` (default 80%) a `warn` alert fires; at 100% a
`breach` alert fires. The default handler prints to stdout. Plug in your own:

```python
import requests
t.add_alert_handler(lambda event: requests.post(
    "https://hooks.slack.com/services/…", json={"text": str(event)}))

t.reset_budget_flags("research-monthly")  # reset warn/breach latch
```

## 4. Aggregation and reports

```python
t.aggregate("model")            # cost/tokens/calls per model
t.aggregate("day")              # per calendar day
t.aggregate("project", team="ml")
t.total_cost(project="research")

from token_budget_tracker import text_summary, html_summary
print(text_summary(t))
open("report.html", "w").write(html_summary(t, project="research"))
```

## 5. CLI

```bash
token-budget log --model gpt-4o-mini --input-tokens 1200 --output-tokens 300 \
    --project research --team ml --app rag-prototype

token-budget budgets set research-monthly --limit 50 \
    --scope project --scope-value research --period month
token-budget budgets check
token-budget budgets list

token-budget summary                      # text dashboard
token-budget summary --format html --output report.html

token-budget prices list
token-budget prices add my-fine-tune --input-per-1k 1.25 --output-per-1k 5.0
```

Pass `--data-dir <dir>` to any command to use a different data directory
(useful for tests or per-environment isolation). `python -m
token_budget_tracker` works the same as the `token-budget` entry point.
