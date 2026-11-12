#!/usr/bin/env python3
"""Deterministic synthetic smoke test for the VectorBT ORB screen."""

from __future__ import annotations

import numpy as np
import pandas as pd
import vectorbt as vbt

from run_orb_screen import (
    Variant,
    calculate_trade_metrics,
    create_signals_for_batch,
    make_variants,
)


def main() -> int:
    if len(make_variants()) != 240:
        raise AssertionError("Expected exactly 240 predeclared ORB variants")

    # One UTC session: data begins before the ORB so ATR has a causal warmup.
    index = pd.date_range("2026-01-02 09:00:00+00:00", periods=60, freq="1min")
    open_ = np.full(60, 100.0, dtype=float)
    high = np.full(60, 100.05, dtype=float)
    low = np.full(60, 99.95, dtype=float)
    close = np.full(60, 100.0, dtype=float)

    # 09:30-09:34 opening range.
    for i in range(30, 35):
        open_[i], high[i], low[i], close[i] = 100.0, 100.05, 99.95, 100.0

    # 09:35 closes above the range; entry is the next minute's close.
    open_[35], high[35], low[35], close[35] = 100.45, 100.65, 100.40, 100.60
    open_[36], high[36], low[36], close[36] = 100.60, 100.75, 100.55, 100.70
    # A later bar reaches the target; the remaining bars stay away from the stop.
    open_[37], high[37], low[37], close[37] = 100.70, 102.00, 100.65, 101.90

    raw = pd.DataFrame({
        "timestamp_utc": index,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
    })
    raw["local_timestamp"] = raw["timestamp_utc"]
    raw["local_date"] = raw["local_timestamp"].dt.date
    raw["minute_of_day"] = raw["local_timestamp"].dt.hour * 60 + raw["local_timestamp"].dt.minute
    previous_close = raw["close"].shift(1)
    tr = pd.concat(
        [
            raw["high"] - raw["low"],
            (raw["high"] - previous_close).abs(),
            (raw["low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    raw["atr14"] = tr.rolling(14, min_periods=14).mean().shift(1)

    variant = Variant("smoke_orb", 5, 0.0, "opposite_range", 1.5, 20)
    arrays, risks, _ = create_signals_for_batch(
        raw, [variant], session_start=570, session_end=600
    )
    entries = pd.DataFrame(arrays["entries"], index=index, columns=[variant.variant_id])
    exits = pd.DataFrame(arrays["exits"], index=index, columns=[variant.variant_id])
    short_entries = pd.DataFrame(arrays["short_entries"], index=index, columns=[variant.variant_id])
    short_exits = pd.DataFrame(arrays["short_exits"], index=index, columns=[variant.variant_id])
    sl_stop = pd.DataFrame(arrays["sl_stop"], index=index, columns=[variant.variant_id])
    tp_stop = pd.DataFrame(arrays["tp_stop"], index=index, columns=[variant.variant_id])

    portfolio = vbt.Portfolio.from_signals(
        pd.Series(close, index=index),
        entries=entries,
        exits=exits,
        short_entries=short_entries,
        short_exits=short_exits,
        open=pd.Series(open_, index=index),
        high=pd.Series(high, index=index),
        low=pd.Series(low, index=index),
        sl_stop=sl_stop,
        tp_stop=tp_stop,
        stop_entry_price="price",
        size=1.0,
        fees=0.0001,
        slippage=0.0001,
        init_cash=1_000_000.0,
        cash_sharing=False,
        lock_cash=False,
        freq="1min",
    )
    records = portfolio.trades.records_readable
    if len(records) != 1:
        raise AssertionError(f"Expected one closed ORB trade, got {len(records)}")
    metrics = calculate_trade_metrics(
        records,
        variant,
        risks["smoke_orb"],
        pd.DatetimeIndex(index),
        months_covered=1,
        risk_fraction=0.01,
    )
    if metrics["trades"] != 1 or not np.isfinite(metrics["expectancy_R"]):
        raise AssertionError(f"ORB trade metrics invalid: {metrics}")

    print("OK: 240-variant grid is constructed")
    print("OK: synthetic ORB breakout -> next-bar entry -> OHLC stop/target -> R metrics")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
