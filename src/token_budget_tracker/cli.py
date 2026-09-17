"""CLI: ``token-budget`` (also ``python -m token_budget_tracker``).

Subcommands:
  log        record one LLM call's usage
  budgets    list/set/remove budgets, or check them against current spend
  summary    print a text dashboard (or write an HTML report)
  prices     list/add model prices
"""

from __future__ import annotations

import argparse
import sys

from .tracker import UsageTracker, DEFAULT_DIR
from .report import text_summary, html_summary


def _tracker(args) -> UsageTracker:
    import os
    data_dir = os.path.expanduser(args.data_dir)
    return UsageTracker(
        log_path=os.path.join(data_dir, "usage.jsonl"),
        budget_path=os.path.join(data_dir, "budgets.json"),
        price_path=os.path.join(data_dir, "prices.json"),
    )


def cmd_log(args) -> int:
    t = _tracker(args)
    try:
        rec = t.record(
            model=args.model,
            input_tokens=args.input_tokens,
            output_tokens=args.output_tokens,
            project=args.project,
            team=args.team,
            app=args.app,
        )
    except Exception as exc:  # unknown model, bad counts, ...
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"logged: {rec.model} {rec.input_tokens}+{rec.output_tokens} tokens "
          f"(${rec.cost_usd:.4f}) -> project {rec.project!r}")
    return 0


def cmd_budgets(args) -> int:
    t = _tracker(args)
    action = args.budget_action
    if action == "list":
        budgets = t.budgets.all()
        if not budgets:
            print("no budgets defined")
            return 0
        for b in budgets:
            s = t.budget_status(b.name)
            print(f"{b.name}: ${s['spent_usd']:.2f}/${b.limit_usd:.2f} "
                  f"({s['pct']:.0%}) scope={b.scope}:{b.scope_value} period={b.period}")
        return 0
    if action == "set":
        t.set_budget(args.name, args.limit, scope=args.scope,
                     scope_value=args.scope_value, period=args.period,
                     warn_at=args.warn_at)
        print(f"budget {args.name!r} set: ${args.limit:.2f} "
              f"({args.scope}:{args.scope_value}, {args.period})")
        return 0
    if action == "remove":
        try:
            t.budgets.remove(args.name)
        except KeyError:
            print(f"error: no budget named {args.name!r}", file=sys.stderr)
            return 2
        print(f"budget {args.name!r} removed")
        return 0
    if action == "check":
        events = t.check_budgets()
        if not events:
            print("all budgets within thresholds")
        return 0
    raise AssertionError(f"unknown budgets action {action!r}")


def cmd_summary(args) -> int:
    t = _tracker(args)
    if args.format == "html":
        out = html_summary(t, project=args.project)
    else:
        out = text_summary(t, project=args.project)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(out)
        print(f"wrote {args.output}")
    else:
        print(out)
    return 0


def cmd_prices(args) -> int:
    t = _tracker(args)
    action = args.price_action
    if action == "list":
        for name in sorted(t.prices):
            p = t.prices.get(name)
            print(f"{name:<24} in ${p.input_per_1k:>7.2f}/1K  out ${p.output_per_1k:>7.2f}/1K")
        return 0
    if action == "add":
        t.add_model(args.model, args.input_per_1k, args.output_per_1k, notes=args.notes or "")
        print(f"price added for {args.model!r}: "
              f"${args.input_per_1k}/1K in, ${args.output_per_1k}/1K out")
        return 0
    raise AssertionError(f"unknown prices action {action!r}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="token-budget",
                                description="Track LLM token usage and cost.")
    p.add_argument("--data-dir", default=DEFAULT_DIR,
                   help="directory holding usage.jsonl, budgets.json, prices.json")
    sub = p.add_subparsers(dest="command", required=True)

    pl = sub.add_parser("log", help="record one LLM call")
    pl.add_argument("--model", required=True)
    pl.add_argument("--input-tokens", type=int, required=True)
    pl.add_argument("--output-tokens", type=int, required=True)
    pl.add_argument("--project", default="default")
    pl.add_argument("--team", default="")
    pl.add_argument("--app", default="")
    pl.set_defaults(func=cmd_log)

    pb = sub.add_parser("budgets", help="manage budgets")
    bsub = pb.add_subparsers(dest="budget_action", required=True)
    bsub.add_parser("list", help="list budgets and current spend")
    bs = bsub.add_parser("set", help="create/update a budget")
    bs.add_argument("name")
    bs.add_argument("--limit", type=float, required=True)
    bs.add_argument("--scope", default="project", choices=["project", "team", "app", "global"])
    bs.add_argument("--scope-value", default="default")
    bs.add_argument("--period", default="month", choices=["day", "month", "total"])
    bs.add_argument("--warn-at", type=float, default=0.8)
    br = bsub.add_parser("remove", help="remove a budget")
    br.add_argument("name")
    bsub.add_parser("check", help="check budgets and fire alerts")
    pb.set_defaults(func=cmd_budgets)

    ps = sub.add_parser("summary", help="usage dashboard")
    ps.add_argument("--project", default=None)
    ps.add_argument("--format", default="text", choices=["text", "html"])
    ps.add_argument("--output", default=None, help="write report to file instead of stdout")
    ps.set_defaults(func=cmd_summary)

    pp = sub.add_parser("prices", help="manage model prices")
    psub = pp.add_subparsers(dest="price_action", required=True)
    psub.add_parser("list", help="list model prices")
    pa = psub.add_parser("add", help="add/override a model price")
    pa.add_argument("model")
    pa.add_argument("--input-per-1k", type=float, required=True)
    pa.add_argument("--output-per-1k", type=float, required=True)
    pa.add_argument("--notes", default="")
    pp.set_defaults(func=cmd_prices)

    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
