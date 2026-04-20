"""backtest.cli: argparse 파싱."""
from __future__ import annotations

import pytest

from sajucandle.backtest.cli import _parse_args


def test_parse_run_required_args():
    args = _parse_args(["run", "--ticker", "BTCUSDT",
                         "--from", "2024-04-01", "--to", "2026-04-01"])
    assert args.subcommand == "run"
    assert args.ticker == "BTCUSDT"
    assert str(args.from_dt.date()) == "2024-04-01"


def test_parse_run_optional_run_id():
    args = _parse_args([
        "run", "--ticker", "AAPL",
        "--from", "2026-01-01", "--to", "2026-03-01",
        "--run-id", "phase1-test-manual",
    ])
    assert args.run_id == "phase1-test-manual"


def test_parse_run_bad_date_raises():
    with pytest.raises(SystemExit):
        _parse_args(["run", "--ticker", "BTCUSDT",
                     "--from", "not-a-date", "--to", "2026-04-01"])


def test_parse_aggregate_required_run_id():
    args = _parse_args(["aggregate", "--run-id", "phase1-abc-baseline"])
    assert args.subcommand == "aggregate"
    assert args.run_id == "phase1-abc-baseline"


def test_parse_aggregate_json_flag():
    args = _parse_args(["aggregate", "--run-id", "r1", "--json"])
    assert args.json is True


def test_parse_aggregate_text_default():
    args = _parse_args(["aggregate", "--run-id", "r1"])
    assert args.json is False
