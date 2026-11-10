from datetime import datetime

import pytest

from propfirm_lab.rules import EquityEvent, PropFirmRuleEngine, calculate_payout


def profile(mode="static_initial", daily_evaluation="intraday"):
    return {
        "profile_id": "test-only",
        "account": {"initial_balance": 100000, "currency": "USD"},
        "session": {"timezone": "UTC", "reset_time": "00:00"},
        "overall_loss": {
            "amount": 10000,
            "amount_type": "fixed",
            "mode": mode,
            "metric": "equity",
            "evaluation": "intraday",
        },
        "daily_loss": {
            "amount": 5000,
            "amount_type": "fixed",
            "anchor": "prior_day_equity",
            "includes_open_pnl": True,
            "evaluation": daily_evaluation,
        },
        "target": {"profit_target_pct": 8, "minimum_trading_days": 1, "consistency_max_best_day_pct": None},
        "payout": {
            "profit_split_pct": 80,
            "minimum_winning_days": 0,
            "profit_buffer": 1000,
            "maximum_gross_payout": None,
            "withdrawal_cap_pct_of_profit": None,
        },
    }


def event(ts, balance, equity, kind="mark"):
    return EquityEvent(datetime.fromisoformat(ts.replace("Z", "+00:00")), balance, equity, kind)


def test_static_overall_floor_breaches_at_or_below_limit():
    engine = PropFirmRuleEngine(profile())
    summary = engine.run([event("2026-01-01T10:00:00Z", 90000, 90000)])
    assert summary["breach"]["reason"] == "overall_loss"


def test_intraday_trailing_equity_tracks_open_profit_peak():
    engine = PropFirmRuleEngine(profile("trailing_intraday_equity"))
    summary = engine.run([
        event("2026-01-01T10:00:00Z", 100000, 102000),
        event("2026-01-01T10:05:00Z", 100000, 91900),
    ])
    assert summary["breach"]["reason"] == "overall_loss"
    assert summary["breach"]["overall_floor"] == pytest.approx(92000)


def test_trailing_floor_can_lock_at_initial_balance():
    engine = PropFirmRuleEngine(profile("trailing_intraday_equity_lock_initial"))
    summary = engine.run([
        event("2026-01-01T10:00:00Z", 100000, 104000),
        event("2026-01-01T10:05:00Z", 100000, 100100),
    ])
    assert summary["breach"] is None
    assert summary["final_equity"] == 100100


def test_daily_end_of_day_rule_ignores_intraday_dip_until_day_end():
    engine = PropFirmRuleEngine(profile(daily_evaluation="end_of_day"))
    summary = engine.run([
        event("2026-01-01T10:00:00Z", 100000, 94000, "mark"),
        event("2026-01-01T23:59:00Z", 94000, 94000, "day_end"),
    ])
    assert summary["breach"]["reason"] == "daily_loss"


def test_trade_days_count_only_trade_close_events():
    engine = PropFirmRuleEngine(profile())
    summary = engine.run([
        event("2026-01-01T10:00:00Z", 101000, 101000, "mark"),
        event("2026-01-01T15:00:00Z", 101000, 101000, "trade_close"),
    ])
    assert summary["trading_days"] == 1


def test_payout_respects_profit_buffer_and_loss_floor():
    result = calculate_payout(profile(), balance=112000, equity=112000, current_overall_floor=90000)
    assert result["eligible"] is True
    assert result["gross_withdrawal"] == pytest.approx(11000)
    assert result["trader_reward"] == pytest.approx(8800)


def test_minimum_winning_days_are_enforced():
    p = profile()
    p["payout"]["minimum_winning_days"] = 3
    result = calculate_payout(p, balance=112000, equity=112000, current_overall_floor=90000, winning_days=2)
    assert result["eligible"] is False
    assert result["reason"] == "minimum_winning_days_not_met"


def test_zero_or_negative_equity_is_a_breach_event_not_a_parser_error():
    engine = PropFirmRuleEngine(profile())
    summary = engine.run([event("2026-01-01T10:00:00Z", 0, 0)])
    assert summary["breach"]["reason"] == "overall_loss"


def test_intraday_equity_trailing_rejects_balance_metric():
    p = profile("trailing_intraday_equity")
    p["overall_loss"]["metric"] = "balance"
    with pytest.raises(ValueError, match="require overall_loss.metric='equity'"):
        PropFirmRuleEngine(p)
