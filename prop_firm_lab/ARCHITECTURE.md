# Research architecture and evidence contract

## Pipeline

```text
ChatGPT / GitHub request file
          |
          v
GitHub Actions (reproducible runner)
          |
          +--> NautilusTrader BacktestEngine / BacktestNode
          |        |-- trade_log.csv (timestamped net R)
          |        |-- equity_events.csv (balance + marked equity)
          |        '-- run metadata (data hash, symbol, granularity)
          |
          +--> Custom prop-firm state machine
          |        |-- daily loss semantics
          |        |-- overall/static/trailing loss semantics
          |        |-- live equity and floating loss
          |        |-- session reset and trading-day count
          |        '-- payout buffer / withdrawal feasibility
          |
          '--> LuxAlgo Prop Firm Sim CLI
                   |-- bootstrap actual R series
                   |-- pass and failure probabilities
                   |-- expected attempts and fees
                   |-- funded-account payout probability
                   '-- explicit model assumptions
          |
          v
Versioned run outputs + Actions artifact
          |
          v
ChatGPT reviews result, detects weaknesses, writes next request
```

## Separation of responsibility

### NautilusTrader

NautilusTrader is the market simulator. It must own order lifecycle, instrument/venue configuration, order matching, fills, price precision, fees, latency/slippage model, financing/swap model and portfolio state. The user strategy is a plugin because no strategy has yet been selected for this separate prop-firm project.

### Custom rules engine

The custom engine is a stateful replay over timestamped equity marks. It checks the actual profile's configured semantics, not generic labels. It can only be as granular as the input events. Quote/tick-level marks are preferred for intraday equity rules; OHLC bars require a conservative intrabar path assumption, and close-only marks are inadequate for many prop rules.

Supported overall loss modes:
- `static_initial`
- `trailing_eod_balance`
- `trailing_intraday_equity`
- `trailing_intraday_equity_lock_initial`

Supported daily loss controls:
- fixed amount, percentage of initial balance, or percentage of day-start anchor;
- day-start anchor from prior-day balance or prior-day equity;
- floating P&L included or excluded;
- intraday or end-of-day enforcement;
- configurable timezone and session reset.

The rules engine records the first breach and stops treating later events as valid continuation. Payout calculation is deliberately separate from the breach monitor and checks whether a withdrawal leaves the account above the applicable floor and required profit buffer.

### LuxAlgo Prop Firm Sim

LuxAlgo receives the closed-trade R-multiple series and a reviewed challenge ruleset. Use timestamped trade logs (not only win rate/average R) so its bootstrap method preserves some streak dependence. The CLI is pinned to `@luxalgo/prop-firm-sim-cli@1.2.0`.

LuxAlgo is not the intratrade account monitor: its published disclaimer says same-day round trips are modelled and intra-trade excursions are not modelled. Do not merge the CLI output with custom rule results as though they were the same model. Compare them and explain the gap.

## Required report sections

Every full run should retain:
1. Git commit SHA, run ID, timestamp, Python/Nautilus/LuxAlgo versions.
2. Input filenames, checksums, symbol, data vendor, date range and resolution.
3. Strategy config hash and immutable strategy version.
4. Nautilus execution settings: account type, leverage/margin model, fee schedule, spread, slippage, latency, rollover/swap and fill assumptions.
5. Trade-level R history and a separate equity-event ledger.
6. Daily/overall drawdown breaches and time of first breach.
7. LuxAlgo seed, path count, rules provenance, confidence intervals and assumption flags.
8. Walk-forward / untouched holdout identifiers. Never optimize on the final holdout.
9. Software smoke results clearly separated from market evidence.

## Validation ladder

- Stage 0: software tests and synthetic smoke only.
- Stage 1: data integrity, timestamp/contract validation, missing bars, duplicates and timezone checks.
- Stage 2: initial historical backtest with realistic instrument, spread, commission, slippage, margin and financing.
- Stage 3: intratrade account-rule replay using marked equity.
- Stage 4: bootstrap Monte Carlo, including block bootstrap and a parametric sensitivity comparison.
- Stage 5: chronological train/validation/untouched holdout and walk-forward checks.
- Stage 6: adverse stress scenarios (higher costs, worse fills, gaps, volatility shocks, correlated loss clusters).
- Stage 7: paper/shadow execution before any real funded-account use.

No performance claim is valid until real market data, correct contracts, verified firm terms and all applicable cost assumptions have been supplied.
