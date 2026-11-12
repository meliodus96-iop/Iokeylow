# Strategy variation and search protocol

## Why VectorBT is being added

VectorBT is the fast screening layer. It can broadcast many parameter combinations through a vectorized portfolio engine, allowing a bounded grid such as the first 240 ORB variants to be evaluated quickly. It does not invent a trading mechanism or prove that the highest-scoring historical variant has an edge.

Package: `vectorbt==1.2.1` from https://github.com/polakowo/vectorbt.

Important licence detail: the community edition is free for use, but is distributed under Apache 2.0 with the Commons Clause (fair-code), not a standard permissive MIT licence. The author says users may use it for free, but may not sell products or services primarily consisting of VectorBT. This project uses it for the user's own research; do not repackage it as a commercial backtesting product without checking the licence.

## Why Optuna is also installed

Optuna (`optuna==5.0.0`, MIT) is a search-space optimizer. It is not the backtester. It can later conduct a bounded second-stage search inside a carefully defined development parameter space after a coarse VectorBT screen. It must not be allowed to search the untouched holdout. Do not let it run indefinitely or use the best single trial as proof.

## Roles in the full system

| Component | Sole job | What it must not be used for |
|---|---|---|
| CCXT / Binance public endpoints | Fetch named-exchange crypto candles, recent trades and snapshots | Claim a snapshot is historical depth or globally consolidated volume |
| Hyperliquid public WebSocket collector | Persist forward trades, L2 snapshots and candles from start time | Claim pre-start history or L3 order-by-order history |
| Dukascopy Node | Historical OTC bid/ask ticks and bars for supported XAUUSD, metals and FX symbols | Claim centralized executions, COMEX/MCX books or true footprint/CVD |
| VectorBT | Fast broad signal/parameter grid screening | Final exchange-fill, queue, partial-fill or broker-specific validation |
| Optuna | Optional, finite, train-only refinement after a coarse screen | Repeatedly tune against holdout or search unbounded spaces |
| NautilusTrader | Replay shortlisted candidates with event-driven execution/cost logic | Make free data deeper or more accurate than the source actually is |
| HyperData Terminal | Live crypto context: multi-exchange CVD, funding/OI, liquidations and whale/position context | Long-term raw historical archive or replacement for the strategy backtester |
| Tape & Book | Binance-specific depth/tape and event-measurement/journaling reference | Another simultaneous copy of every collector in the stack |
| EdgeDepth Terminal | Optional local visual inspection/replay of depth/DOM/heatmap | A second always-on collector alongside Tape & Book unless there is a specific need |
| MarketBridge | Reference for broad crypto API/data-normalization concepts | Runtime dependency until the formal repository licence is clarified; duplicates CCXT/Nautilus collection roles |

These tool roles are intentionally separated. Do not run multiple terminals that subscribe to the same Binance depth stream just to collect the same events twice. Use one chosen collector/archive as the research source, and use viewers only when they answer a distinct inspection question.

## First screen: 240 controlled ORB variations

`tools/run_orb_screen.py` is the first working example. It tests a 240-member predeclared grid:

- Opening range: 5, 10, 15, 20, or 30 minutes.
- Breakout buffer: 0, 0.05, or 0.10 of prior ATR(14).
- Initial stop: opposite opening-range edge or breakout candle extreme.
- Target: 1.5R, 2R, 2.5R, or 3R.
- Last entry window: 60 or 120 minutes after the opening range.

The 5 × 3 × 2 × 4 × 2 combination is exactly 240. It is not a licence to add hundreds of extra filters. The point is to find a stable, interpretable neighborhood—or reject the ORB idea—not to find a magic combination.

### Data contract for this first ORB runner

- Input must be 1-minute OHLC data in Parquet or CSV with a timestamp column plus `open`, `high`, `low`, and `close`.
- No missing intervals are synthetically filled. An opening range is skipped if any of its one-minute bars is missing.
- Choose the local market session timezone and its start/end times explicitly. For UTC-origin data, the script converts timestamps to the requested IANA timezone.
- ATR(14) is shifted one bar so the breakout threshold uses only prior completed information.
- Breakout is confirmed at the candle close; entry is on the close of the next available one-minute bar. This is deliberately delayed rather than assuming a fill at the breakout close.
- Stop/target simulation uses one-minute OHLC. A candle that touches both levels is path-ambiguous; use tick data and NautilusTrader before promoting a candidate.
- Fees and slippage are charged per side. The R statistics are normalized by initial stop distance. The runner does not model a broker's contract multiplier, lot size, margin, queue position, partial fills or exchange rejection.
- `--dev-end` is an exclusive UTC cutoff. Rows at/after the cutoff are excluded before indicators and signals are calculated; no holdout results are computed in this screen.

### Command

~~~powershell
.\.venv-marketdata\Scripts\python.exe tools\run_orb_screen.py `
  --input data\raw\crypto\binanceusdm\BTC_USDT_USDT\1m_20240101_20250101.parquet `
  --timestamp-col ts_event `
  --timezone America/New_York `
  --session-start 09:30 --session-end 16:00 `
  --dev-end 2025-01-01 `
  --fees-bps 5 --slippage-bps 3
~~~

The input path is an example; use the actual Parquet filename produced by the data fetcher. The session hours above are an illustrative US session, not a universal default. Choose hours appropriate to the instrument and hypothesis. For XAUUSD, specify a precise London or New York session and match the intended broker's data.

Results are written to `output/strategy_lab/orb/`:

- `orb_240_variant_development_screen.csv` — one row per variant, development metrics and rank.
- `orb_240_variant_manifest.json` — source path, data cutoff, session, assumptions, fee/slippage and search-space record.

## Promotion rules

1. Run the predeclared grid only on the development segment. Require a minimum trade count (default 30); do not confuse 30 trades with sufficient statistical power.
2. Do not select only the highest expectancy or profit factor. Examine trade count, expectancy after costs, R distribution, drawdown at fixed risk, trade frequency, year/regime breakdown and nearby parameter stability.
3. Prefer a broad stable neighborhood with simple parameters over a lone peak. If only one narrow parameter point works, treat it as likely overfit.
4. Freeze one candidate (or a small, predeclared stable cluster) before opening the later untouched period. The script deliberately does not calculate holdout metrics.
5. Only then run an independent out-of-sample and walk-forward test. Log every attempt, including failed variants, so multiple-testing risk is visible.
6. Promote a shortlist to NautilusTrader for instrument-aware replay: actual contract multiplier/tick/lot, bid/ask spread, fees, slippage, funding, margin, stop gaps, time-in-force and realistic fills.
7. Run Monte Carlo/bootstrap and regime/cost stress on the frozen shortlist. Paper trade before any capital decision.

## Generalizing beyond ORB

For any new strategy, first write a strategy adapter that creates causal entry/exit signals from normalized data and declares a finite parameter space. VectorBT can screen signal/indicator variants; the instrument-specific execution model then goes through NautilusTrader. The ORB script is an initial example, not a claim that all strategies can be safely tested by one universal template.

## Current status

- VectorBT and Optuna are pinned as dependencies and checked by the install smoke test.
- The first 240-variant ORB runner is in the repository.
- Package smoke tests are software checks only; no real ORB dataset has been screened by this change.
- The local PC still needs `git pull` and the installer rerun to install the new packages.