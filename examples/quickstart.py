"""Runnable quickstart for token-budget-tracker.

Uses a temp directory so it never touches your real ~/.token_budget_tracker.
Run with:  python examples/quickstart.py
"""
import tempfile

from token_budget_tracker import UsageTracker, text_summary

tmp = tempfile.mkdtemp(prefix="tbt-demo-")
tracker = UsageTracker(
    log_path=f"{tmp}/usage.jsonl",
    budget_path=f"{tmp}/budgets.json",
    price_path=None,  # skip persistence of the price table in the demo
)

# 1. Register a custom (e.g. self-hosted) model price.
tracker.add_model("my-local-llm", input_per_1k=0.0, output_per_1k=0.0,
                  notes="self-hosted, no per-token cost")

# 2. Set a monthly budget for a project.
tracker.set_budget("research-cap", limit_usd=5.0, scope="project",
                   scope_value="research", period="month", warn_at=0.5)

# 3. Record calls directly.
tracker.record("gpt-4o-mini", input_tokens=1200, output_tokens=300,
               project="research", team="ml", app="rag-prototype")

# 4. Or wrap a function — returning token counts logs them automatically.
@tracker.track(model="gpt-4o-mini", project="research", team="ml")
def fake_llm_call(prompt: str) -> dict:
    return {"answer": f"processed {len(prompt)} chars",
            "input_tokens": 900, "output_tokens": 150}

fake_llm_call("summarize this")

# 5. Or use the context manager for full control.
with tracker.track(model="claude-3-5-haiku", project="research") as call:
    # ... your real LLM call goes here ...
    call.set_usage(input_tokens=2000, output_tokens=500)

print(text_summary(tracker))
print(f"\n(demo data lives in {tmp})")
