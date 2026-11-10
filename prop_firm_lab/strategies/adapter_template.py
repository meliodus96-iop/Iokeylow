"""Template only: implement this adapter for a selected strategy and real dataset.

Set strategy_entrypoint to:
    strategies.adapter_template:run_backtest

Do not fabricate trades or equity marks. Replace the NotImplementedError only after
implementing a real NautilusTrader BacktestEngine/BacktestNode run with the correct
instrument, venue, fees, spread, slippage, margin and financing assumptions.
"""

from pathlib import Path
from typing import Any


def run_backtest(*, data_path: str, output_dir: str, config: dict[str, Any]) -> dict[str, str]:
    source = Path(data_path)
    destination = Path(output_dir)
    if not source.exists():
        raise FileNotFoundError(source)
    destination.mkdir(parents=True, exist_ok=True)

    raise NotImplementedError(
        "Replace this template with the selected strategy. Export timestamped trade_log.csv "
        "and marked-to-market equity_events.csv from a genuine NautilusTrader backtest."
    )
