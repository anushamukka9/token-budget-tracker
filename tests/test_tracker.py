"""Tests for token-budget-tracker. Run with: python -m pytest -q"""
import os
import tempfile

import pytest

from token_budget_tracker import (
    UsageTracker, ModelPriceTable, Budget, BudgetStore,
    UsageLog, UsageRecord, text_summary, html_summary,
)
from token_budget_tracker.pricing import UnknownModelError
from token_budget_tracker.cli import build_parser, main


@pytest.fixture()
def tracker():
    tmp = tempfile.mkdtemp(prefix="tbt-test-")
    t = UsageTracker(
        log_path=os.path.join(tmp, "usage.jsonl"),
        budget_path=os.path.join(tmp, "budgets.json"),
        price_path=None,  # don't persist built-in defaults in tests
    )
    # silence the default print-alert handler
    t._alert_handlers = []
    return t


# ---- pricing ---------------------------------------------------------
def test_cost_math():
    table = ModelPriceTable()
    cost = table.cost("gpt-4o-mini", input_tokens=1000, output_tokens=1000)
    assert cost == pytest.approx((0.15 + 0.60) / 1000 * 1000)


def test_add_model_and_unknown():
    table = ModelPriceTable()
    table.add_model("custom-x", 1.0, 2.0)
    assert table.cost("custom-x", 1000, 1000) == pytest.approx(3.0)
    with pytest.raises(UnknownModelError):
        table.cost("nope-not-a-model", 10, 10)
    with pytest.raises(ValueError):
        table.add_model("bad", -1.0, 1.0)


def test_price_table_persistence(tmp_path):
    p = tmp_path / "prices.json"
    table = ModelPriceTable()
    table.add_model("custom-x", 1.0, 2.0, notes="test")
    table.save(str(p))
    loaded = ModelPriceTable.load(str(p))
    assert loaded.cost("custom-x", 1000, 1000) == pytest.approx(3.0)


# ---- recording -------------------------------------------------------
def test_record_computes_cost(tracker):
    rec = tracker.record("gpt-4o-mini", 1000, 500, project="research")
    assert rec.cost_usd == pytest.approx((0.15 * 1 + 0.60 * 0.5))
    assert rec.project == "research"
    assert len(tracker.log) == 1


def test_record_unknown_model_raises(tracker):
    with pytest.raises(UnknownModelError):
        tracker.record("definitely-not-a-model", 10, 10)


def test_record_negative_tokens_raises(tracker):
    with pytest.raises(ValueError):
        tracker.record("gpt-4o-mini", -5, 10)


# ---- aggregation -----------------------------------------------------
def test_aggregation_by_model_and_project(tracker):
    tracker.record("gpt-4o-mini", 1000, 0, project="a")
    tracker.record("gpt-4o-mini", 1000, 0, project="a")
    tracker.record("claude-3-5-haiku", 1000, 0, project="b")
    by_model = tracker.aggregate("model")
    assert by_model["gpt-4o-mini"]["calls"] == 2
    assert by_model["claude-3-5-haiku"]["calls"] == 1
    by_project = tracker.aggregate("project")
    assert by_project["a"]["calls"] == 2
    assert by_project["b"]["total_tokens"] == 1000
    assert tracker.total_cost() == pytest.approx(
        sum(r.cost_usd for r in tracker.log.iter_records()))


def test_query_filters(tracker):
    tracker.record("gpt-4o-mini", 100, 0, project="a", team="t1")
    tracker.record("gpt-4o-mini", 100, 0, project="b", team="t2")
    assert len(tracker.log.query(project="a")) == 1
    assert len(tracker.log.query(model="gpt-4o-mini")) == 2
    assert tracker.aggregate("team")["t1"]["calls"] == 1


# ---- decorator / context manager --------------------------------------
def test_decorator_records_from_return_dict(tracker):
    @tracker.track(model="gpt-4o-mini", project="demo")
    def fake_call():
        return {"input_tokens": 400, "output_tokens": 100}

    fake_call()
    recs = tracker.log.query(project="demo")
    assert len(recs) == 1
    assert recs[0].input_tokens == 400
    assert recs[0].output_tokens == 100
    assert recs[0].cost_usd > 0


def test_context_manager_set_usage(tracker):
    with tracker.track(model="gpt-4o-mini", project="cm") as call:
        call.set_usage(250, 50)
    recs = tracker.log.query(project="cm")
    assert len(recs) == 1
    assert recs[0].total_tokens == 300


# ---- budgets ---------------------------------------------------------
def test_budget_warn_and_breach_events(tracker):
    events = []
    tracker.add_alert_handler(events.append)
    tracker.set_budget("cap", limit_usd=1.0, scope="project",
                       scope_value="p1", period="total", warn_at=0.5)
    # gpt-4o input $2.50/1K: 300 tokens -> $0.75 >= 50% warn, < 100%
    tracker.record("gpt-4o", 300, 0, project="p1")
    assert [e["level"] for e in events] == ["warn"]
    tracker.record("gpt-4o", 300, 0, project="p1")  # now $1.50 -> breach
    assert [e["level"] for e in events] == ["warn", "breach"]
    status = tracker.budget_status("cap")
    assert status["spent_usd"] == pytest.approx(1.50)
    assert status["pct"] == pytest.approx(1.5)
    assert status["remaining_usd"] == pytest.approx(-0.5)


def test_budget_no_repeat_alerts_until_reset(tracker):
    events = []
    tracker.add_alert_handler(events.append)
    tracker.set_budget("cap", limit_usd=0.10, scope="project",
                       scope_value="p1", period="total", warn_at=0.5)
    tracker.record("gpt-4o", 100, 0, project="p1")  # $0.25 -> breach latch
    first_count = len(events)
    assert [e["level"] for e in events] == ["breach"]
    tracker.record("gpt-4o", 100, 0, project="p1")  # latched: no new alerts
    assert len(events) == first_count
    tracker.reset_budget_flags("cap")
    tracker.record("gpt-4o", 100, 0, project="p1")  # fires again
    assert len(events) == first_count + 1
    assert events[-1]["level"] == "breach"


def test_budget_validation():
    with pytest.raises(ValueError):
        Budget(name="x", limit_usd=0)
    with pytest.raises(ValueError):
        Budget(name="x", limit_usd=5, scope="galaxy")
    with pytest.raises(ValueError):
        Budget(name="x", limit_usd=5, period="fortnight")


def test_global_and_team_scopes(tracker):
    tracker.set_budget("team-cap", limit_usd=10.0, scope="team",
                       scope_value="ml", period="total")
    tracker.record("gpt-4o-mini", 1000, 0, project="a", team="ml")
    tracker.record("gpt-4o-mini", 1000, 0, project="b", team="other")
    s = tracker.budget_status("team-cap")
    assert s["calls"] == 1
    tracker.set_budget("all-cap", limit_usd=100.0, scope="global", period="total")
    assert tracker.budget_status("all-cap")["calls"] == 2


# ---- persistence -----------------------------------------------------
def test_log_and_budget_persistence(tmp_path):
    log_path = str(tmp_path / "u.jsonl")
    bud_path = str(tmp_path / "b.json")
    t1 = UsageTracker(log_path=log_path, budget_path=bud_path, price_path=None)
    t1._alert_handlers = []
    t1.record("gpt-4o-mini", 100, 50, project="p")
    t1.set_budget("cap", 5.0, scope_value="p")
    t2 = UsageTracker(log_path=log_path, budget_path=bud_path, price_path=None)
    assert len(t2.log) == 1
    assert t2.budget_status("cap")["limit_usd"] == 5.0


def test_usage_log_roundtrip(tmp_path):
    log = UsageLog(str(tmp_path / "u.jsonl"))
    rec = UsageRecord(model="m", input_tokens=10, output_tokens=20,
                      project="p", cost_usd=0.01)
    log.append(rec)
    back = list(log.iter_records())
    assert len(back) == 1
    assert back[0] == rec
    assert back[0].total_tokens == 30


# ---- reports ---------------------------------------------------------
def test_reports_contain_data(tracker):
    tracker.record("gpt-4o-mini", 1000, 500, project="research")
    tracker.set_budget("cap", 5.0, scope_value="research")
    txt = text_summary(tracker)
    assert "research" in txt and "gpt-4o-mini" in txt and "cap" in txt
    html = html_summary(tracker)
    assert "<html" in html and "gpt-4o-mini" in html and "research" in html


# ---- CLI --------------------------------------------------------------
def test_cli_log_and_summary(tmp_path, capsys):
    d = str(tmp_path)
    argv = ["--data-dir", d, "log", "--model", "gpt-4o-mini",
            "--input-tokens", "100", "--output-tokens", "50",
            "--project", "cli-proj"]
    assert main(argv) == 0
    out = capsys.readouterr().out
    assert "logged" in out
    assert main(["--data-dir", d, "summary"]) == 0
    assert "cli-proj" in capsys.readouterr().out


def test_cli_budgets_and_prices(tmp_path, capsys):
    d = str(tmp_path)
    assert main(["--data-dir", d, "budgets", "set", "b1", "--limit", "3.0"]) == 0
    assert main(["--data-dir", d, "budgets", "list"]) == 0
    assert "b1" in capsys.readouterr().out
    assert main(["--data-dir", d, "budgets", "check"]) == 0
    assert main(["--data-dir", d, "prices", "add", "x-model",
                 "--input-per-1k", "1.0", "--output-per-1k", "2.0"]) == 0
    assert main(["--data-dir", d, "prices", "list"]) == 0
    assert "x-model" in capsys.readouterr().out
    assert main(["--data-dir", d, "log", "--model", "bogus-model",
                 "--input-tokens", "1", "--output-tokens", "1"]) == 2


def test_cli_parser_requires_subcommand():
    with pytest.raises(SystemExit):
        build_parser().parse_args([])
