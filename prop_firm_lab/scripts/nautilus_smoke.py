"""Synthetic software-only NautilusTrader 2.x smoke test.

This is adapted from the official NautilusTrader 2.x quickstart pattern.
It is not a trading strategy recommendation or market-performance evidence.
"""
from decimal import Decimal

import numpy as np
import pandas as pd

from nautilus_trader.backtest import BacktestEngine
from nautilus_trader.common import LogLevel
from nautilus_trader.config import BacktestEngineConfig, LoggerConfig, StrategyConfig
from nautilus_trader.execution import MakerTakerFeeModel
from nautilus_trader.indicators import ExponentialMovingAverage
from nautilus_trader.model import (
    AccountType,
    Bar,
    BarType,
    Currency,
    CurrencyPair,
    InstrumentId,
    Money,
    OmsType,
    OrderSide,
    Price,
    Quantity,
    Symbol,
    Venue,
)
from nautilus_trader.trading import Strategy


class SmokeConfig(StrategyConfig):
    def __init__(self, *, instrument_id, bar_type, trade_size, **kwargs):
        super().__init__()
        self.instrument_id = instrument_id
        self.bar_type = bar_type
        self.trade_size = trade_size


class SmokeEmaStrategy(Strategy):
    def __init__(self, config):
        super().__init__(config)
        self.fast = ExponentialMovingAverage(5)
        self.slow = ExponentialMovingAverage(12)

    def on_start(self):
        self.register_indicator_for_bars(self.config.bar_type, self.fast)
        self.register_indicator_for_bars(self.config.bar_type, self.slow)
        self.subscribe_bars(self.config.bar_type)

    def on_bar(self, bar):
        if not self.indicators_initialized():
            return
        instrument = self.cache.instrument(self.config.instrument_id)
        if self.fast.value > self.slow.value and self.portfolio.is_net_flat(self.config.instrument_id):
            order = self.order_factory.market(
                self.config.instrument_id, OrderSide.BUY, instrument.make_qty(self.config.trade_size)
            )
            self.submit_order(order)
        elif self.fast.value < self.slow.value and self.portfolio.is_net_long(self.config.instrument_id):
            self.close_all_positions(self.config.instrument_id)

    def on_stop(self):
        self.close_all_positions(self.config.instrument_id)


def main():
    import nautilus_trader
    if not nautilus_trader.__version__.startswith("2."):
        raise RuntimeError(f"Expected NautilusTrader 2.x; got {nautilus_trader.__version__}")

    usd = Currency.from_str("USD")
    eur = Currency.from_str("EUR")
    instrument = CurrencyPair(
        instrument_id=InstrumentId.from_str("EUR/USD.SIM"),
        raw_symbol=Symbol("EUR/USD"),
        base_currency=eur,
        quote_currency=usd,
        price_precision=5,
        size_precision=0,
        price_increment=Price.from_str("0.00001"),
        size_increment=Quantity.from_int(1),
        ts_event=0,
        ts_init=0,
        lot_size=Quantity.from_int(1000),
        margin_init=Decimal("0.03"),
        margin_maint=Decimal("0.03"),
    )

    rng = np.random.default_rng(42)
    count = 500
    prices = 1.10 + np.cumsum(rng.normal(0, 0.0002, count))
    spreads = np.abs(rng.normal(0, 0.0002, count))
    frame = pd.DataFrame({
        "open": prices,
        "high": prices + spreads,
        "low": prices - spreads,
        "close": prices + rng.normal(0, 0.00004, count),
    }, index=pd.date_range("2025-01-01", periods=count, freq="1min", tz="UTC"))
    frame["high"] = frame[["open", "high", "close"]].max(axis=1)
    frame["low"] = frame[["open", "low", "close"]].min(axis=1)

    bar_type = BarType.from_str("EUR/USD.SIM-1-MINUTE-LAST-EXTERNAL")
    bars = [
        Bar(
            bar_type=bar_type,
            open=Price(row.open, precision=5),
            high=Price(row.high, precision=5),
            low=Price(row.low, precision=5),
            close=Price(row.close, precision=5),
            volume=Quantity.from_int(1000000),
            ts_event=int(timestamp.value),
            ts_init=int(timestamp.value),
        )
        for timestamp, row in frame.iterrows()
    ]

    engine = BacktestEngine(BacktestEngineConfig(
        logging=LoggerConfig(stdout_level=LogLevel.ERROR),
    ))
    venue = Venue("SIM")
    engine.add_venue(
        venue=venue,
        oms_type=OmsType.NETTING,
        account_type=AccountType.MARGIN,
        starting_balances=[Money(100000, usd)],
        base_currency=usd,
        default_leverage=Decimal(1),
        fee_model=MakerTakerFeeModel(maker_rate=Decimal("0"), taker_rate=Decimal("0")),
    )
    engine.add_instrument(instrument)
    engine.add_data(bars)
    engine.add_strategy(SmokeEmaStrategy(SmokeConfig(
        instrument_id=instrument.id,
        bar_type=bar_type,
        trade_size=Decimal(1000),
    )))
    engine.run()
    engine.generate_account_report(venue=venue)
    engine.generate_positions_report()
    engine.dispose()
    print("NAUTILUS_SYNTHETIC_SMOKE_OK: 500 synthetic EUR/USD bars; not market evidence")


if __name__ == "__main__":
    main()
