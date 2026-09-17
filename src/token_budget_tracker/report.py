"""Usage summaries: plain-text dashboard and standalone HTML report."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Dict, Optional

if TYPE_CHECKING:  # avoid a hard import cycle
    from .tracker import UsageTracker


def _snapshot(tracker: "UsageTracker", project: Optional[str] = None) -> dict:
    kwargs = {"project": project} if project else {}
    by_project = tracker.aggregate("project", **kwargs)
    by_model = tracker.aggregate("model", **kwargs)
    by_day = tracker.aggregate("day", **kwargs)
    total_cost = tracker.total_cost(**kwargs)
    total_calls = sum(a["calls"] for a in by_project.values())
    total_tokens = sum(a["total_tokens"] for a in by_project.values())
    budgets = [tracker.budget_status(b.name) for b in tracker.budgets.all()]
    return {
        "generated": time.strftime("%Y-%m-%d %H:%M:%S %Z", time.localtime()),
        "project": project or "all projects",
        "total_cost": total_cost,
        "total_calls": total_calls,
        "total_tokens": total_tokens,
        "by_project": by_project,
        "by_model": by_model,
        "by_day": by_day,
        "budgets": budgets,
    }


def text_summary(tracker: "UsageTracker", project: Optional[str] = None) -> str:
    """Render a plain-text dashboard summary."""
    s = _snapshot(tracker, project)
    lines = [
        "=" * 58,
        "TOKEN BUDGET TRACKER — usage summary",
        f"Generated : {s['generated']}",
        f"Scope     : {s['project']}",
        "-" * 58,
        f"Total cost   : ${s['total_cost']:.2f}",
        f"Total calls  : {s['total_calls']}",
        f"Total tokens : {s['total_tokens']:,}",
        "",
        "By project:",
    ]
    for name, a in sorted(s["by_project"].items(), key=lambda kv: -kv[1]["cost_usd"]):
        lines.append(f"  {name:<22} {a['calls']:>5} calls  "
                     f"{a['total_tokens']:>10,} tok  ${a['cost_usd']:>8.2f}")
    lines.append("")
    lines.append("By model:")
    for name, a in sorted(s["by_model"].items(), key=lambda kv: -kv[1]["cost_usd"]):
        lines.append(f"  {name:<22} {a['calls']:>5} calls  "
                     f"{a['total_tokens']:>10,} tok  ${a['cost_usd']:>8.2f}")
    lines.append("")
    lines.append("By day:")
    for day in sorted(s["by_day"]):
        a = s["by_day"][day]
        lines.append(f"  {day}  {a['calls']:>4} calls  "
                     f"{a['total_tokens']:>10,} tok  ${a['cost_usd']:>8.2f}")
    if s["budgets"]:
        lines.append("")
        lines.append("Budgets:")
        for b in s["budgets"]:
            bar = "#" * int(20 * min(b["pct"], 1.0)) + "-" * (20 - int(20 * min(b["pct"], 1.0)))
            lines.append(f"  {b['budget']:<22} [{bar}] {b['pct']:>6.0%}  "
                         f"${b['spent_usd']:.2f}/${b['limit_usd']:.2f}")
    lines.append("=" * 58)
    return "\n".join(lines)


def html_summary(tracker: "UsageTracker", project: Optional[str] = None) -> str:
    """Render a standalone HTML dashboard (no external assets)."""
    s = _snapshot(tracker, project)

    def rows(agg: Dict[str, dict]) -> str:
        out = []
        for name, a in sorted(agg.items(), key=lambda kv: -kv[1]["cost_usd"]):
            out.append(
                f"<tr><td>{name}</td><td>{a['calls']}</td>"
                f"<td>{a['total_tokens']:,}</td><td>${a['cost_usd']:.2f}</td></tr>"
            )
        return "\n".join(out) or '<tr><td colspan="4">no data</td></tr>'

    budget_rows = []
    for b in s["budgets"]:
        pct = min(b["pct"] * 100, 100)
        color = "#c0392b" if b["pct"] >= 1 else "#e67e22" if b["pct"] >= 0.8 else "#27ae60"
        budget_rows.append(
            f"<tr><td>{b['budget']}</td><td>{b['scope']}:{b['scope_value']}</td>"
            f"<td><div class='bar'><div class='fill' style='width:{pct:.1f}%;"
            f"background:{color}'></div></div></td>"
            f"<td>${b['spent_usd']:.2f} / ${b['limit_usd']:.2f}</td></tr>"
        )

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>Token Budget Tracker — usage summary</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 2rem; color: #222; }}
h1 {{ font-size: 1.4rem; }} h2 {{ font-size: 1.1rem; margin-top: 1.6rem; }}
table {{ border-collapse: collapse; width: 100%; max-width: 760px; }}
th, td {{ border: 1px solid #ccc; padding: 0.35rem 0.6rem; text-align: left; }}
th {{ background: #f4f4f4; }}
.stat {{ display: inline-block; margin-right: 2rem; }}
.stat b {{ font-size: 1.3rem; }}
.bar {{ width: 160px; height: 12px; background: #eee; }}
.fill {{ height: 12px; }}
</style></head><body>
<h1>Token Budget Tracker — usage summary</h1>
<p>Generated {s['generated']} · scope: {s['project']}</p>
<div>
<span class="stat">Total cost<br><b>${s['total_cost']:.2f}</b></span>
<span class="stat">Calls<br><b>{s['total_calls']}</b></span>
<span class="stat">Tokens<br><b>{s['total_tokens']:,}</b></span>
</div>
<h2>By project</h2>
<table><tr><th>Project</th><th>Calls</th><th>Tokens</th><th>Cost</th></tr>
{rows(s['by_project'])}</table>
<h2>By model</h2>
<table><tr><th>Model</th><th>Calls</th><th>Tokens</th><th>Cost</th></tr>
{rows(s['by_model'])}</table>
<h2>By day</h2>
<table><tr><th>Day</th><th>Calls</th><th>Tokens</th><th>Cost</th></tr>
{rows(s['by_day'])}</table>
<h2>Budgets</h2>
<table><tr><th>Budget</th><th>Scope</th><th>Usage</th><th>Spent</th></tr>
{chr(10).join(budget_rows) or '<tr><td colspan="4">no budgets defined</td></tr>'}</table>
</body></html>
"""
