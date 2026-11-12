#!/usr/bin/env python3
"""Verify free data, VectorBT and Optuna research dependencies."""

from __future__ import annotations

import importlib.metadata
import sys

EXPECTED = {
    "nautilus_trader": "1.231.0",
    "ccxt": "4.5.92",
    "websockets": "15.0.1",
    "vectorbt": "1.2.1",
    "optuna": "5.0.0",
}


def main() -> int:
    if sys.version_info < (3, 12) or sys.version_info >= (3, 15):
        print("ERROR: use Python 3.12, 3.13 or 3.14.", file=sys.stderr)
        return 2

    try:
        import ccxt  # noqa: F401
        import nautilus_trader  # noqa: F401
        import numpy as np
        import optuna
        import pandas as pd
        import pyarrow  # noqa: F401
        import vectorbt as vbt
        import websockets  # noqa: F401
    except Exception as exc:
        print(f"ERROR: research runtime import failed: {exc!r}", file=sys.stderr)
        return 1

    for distribution, expected in EXPECTED.items():
        try:
            actual = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            print(f"ERROR: missing distribution {distribution}", file=sys.stderr)
            return 1
        if actual != expected:
            print(
                f"ERROR: {distribution} version {actual}; expected {expected}",
                file=sys.stderr,
            )
            return 1

    # Exercise the installed VectorBT portfolio engine on a deterministic toy
    # series. This is a software smoke test, not evidence of a trading edge.
    index = pd.date_range("2026-01-01", periods=6, freq="1min", tz="UTC")
    close = pd.Series([100.0, 101.0, 102.0, 101.0, 103.0, 104.0], index=index)
    entries = pd.Series([True, False, False, False, False, False], index=index)
    exits = pd.Series([False, False, False, True, False, False], index=index)
    portfolio = vbt.Portfolio.from_signals(
        close,
        entries=entries,
        exits=exits,
        init_cash=10000.0,
        size=1.0,
        fees=0.0005,
        freq="1min",
    )
    if len(portfolio.trades.records) != 1:
        print("ERROR: VectorBT portfolio smoke test did not create one closed trade.", file=sys.stderr)
        return 1

    # Exercise Optuna's study/trial path without network access.
    study = optuna.create_study(
        direction="maximize",
        sampler=optuna.samplers.RandomSampler(seed=17),
    )
    study.optimize(lambda trial: trial.suggest_float("score", 0.0, 1.0), n_trials=2)
    if len(study.trials) != 2:
        print("ERROR: Optuna smoke test did not complete two trials.", file=sys.stderr)
        return 1

    print("OK: free market-data and strategy-research runtime installed")
    for package, version in EXPECTED.items():
        print(f"  {package}=={version}")
    print("OK: VectorBT generated a deterministic closed-trade record")
    print("OK: Optuna completed a two-trial local study")
    print("NOTE: software smoke tests only; no market data was downloaded or backtested")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
