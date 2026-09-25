# Phase 1 Development Results

## Scope

This is a **development-only** study. It is not Phase-2 validation.

Main development window: 2022-04-19 through 2026-04-16, using the available 5-minute NIFTY 50 public dataset. Older rows are used only as warm-up/context for rolling calculations.

The current signal uses:
- 15-minute causal context
- 5-minute execution
- previous-day high/low
- opening range
- abnormal range + candle-body participation proxy
- failed-auction reversal
- two-close opening-range acceptance
- 2.5R minimum natural-room filter
- 3R baseline target
- structural stop
- one trade per session
- 15:25 square-off

True historical Level-2/aggressor data is **not** used in this report.

## Main four-year development readout

| Metric | Result |
|---|---:|
| Trades | 477 |
| Trades/month | 9.96 |
| Win rate | 32.70% |
| Average winner | 2.407R |
| Average loser | -0.970R |
| Average realized winner/loser ratio | 2.481R |
| Expectancy | +0.134R/trade |
| Profit factor | 1.206 |
| Max drawdown at 1% risk/trade | -19.87% |
| Max consecutive losses | 11 |
| Median holding time | 30 min |
| Mean holding time | 57.2 min |

A simple 1%-of-equity compounding illustration over this development sample ends at approximately INR 26,618 from INR 15,000. This is only an analytical illustration and does not include option execution costs or represent a live-return forecast.

## Year breakdown

| Year | Trades | Win rate | Avg R |
|---|---:|---:|---:|
| 2022 | 96 | 34.38% | +0.162R |
| 2023 | 115 | 37.39% | +0.388R |
| 2024 | 122 | 31.97% | +0.059R |
| 2025 | 108 | 28.70% | -0.046R |
| 2026* | 36 | 27.78% | +0.046R |

*2026 is partial in the available development dataset.

The important observation is that the edge is **not uniform across years**. 2025 is negative in this raw development version, which is exactly the kind of regime dependence we need to investigate rather than hide.

## Setup breakdown

| Setup | Trades | Win rate | Avg R | Avg winner | Avg loser | Median hold |
|---|---:|---:|---:|---:|---:|---:|
| Bull failed auction | 171 | 29.82% | +0.145R | 2.819R | -0.991R | 20 min |
| Bear failed auction | 181 | 29.83% | +0.105R | 2.669R | -0.985R | 20 min |
| Bull acceptance | 55 | 41.82% | +0.148R | 1.549R | -0.858R | 105 min |
| Bear acceptance | 70 | 40.00% | +0.172R | 1.856R | -0.951R | 82.5 min |

This suggests the current framework is getting most of its asymmetry from the failed-auction setups, while the acceptance setups have higher hit rates but smaller average winners. That is an observation for further research, not a conclusion about which setup should ultimately survive.

## Time-of-day observation

| Signal hour | Trades | Win rate | Avg R | Median hold |
|---|---:|---:|---:|---:|
| 10 | 14 | 14.29% | -0.429R | 20 min |
| 11 | 187 | 32.09% | +0.142R | 35 min |
| 12 | 134 | 32.09% | +0.140R | 35 min |
| 13 | 92 | 38.04% | +0.278R | 30 min |
| 14 | 50 | 32.00% | -0.016R | 22.5 min |

No narrow trading window is being hard-coded. The hour distribution is being recorded for later hypothesis testing.

## Exit distribution

- Stops: 307
- 3R targets: 109
- Square-off exits: 61

The high average realized winner/loser ratio is therefore not coming from an assumption that every winner is exactly 3R; square-offs and other path-dependent outcomes are included.

## Option expression study

A separate exploratory run used the bundled real 1-minute NIFTY ATM option sample covering July 2025 through June 2026.

The ATM option data contains real 1-minute CE/PE candles, volume and open interest, but **does not contain bid/ask quotes** in the bundled sample.

A naive one-lot run produced negative cash feasibility because a one-lot option can represent a very large fraction of a INR 15,000 account. Therefore the cash-feasible subset must be treated separately from the underlying signal statistics.

The cash-feasible exploratory subset produced:
- 67 executed trades
- 37.31% win rate
- 2.175 average realized winner/loser ratio
- +0.170R option-premium expectancy
- INR 5,656 net P&L under the sampled one-lot cash-feasible sequence

This option result is **not validation** and is heavily constrained by the bundled ATM-only option sample, lack of bid/ask, and the inability to express exact 1% risk with a single exchange-listed contract.

## Order-flow data status

A separate public TickBytes repository documents NIFTY futures/option tick feeds with:
- trade timestamps
- last-traded price/quantity
- cumulative volume/OI
- total buy/sell quantity
- top-5 bid/ask depth
- option Greeks

Its repository provides small sample files, not a free multi-year historical archive.

Therefore:
- Phase 1 currently establishes a price/auction hypothesis.
- True historical order-flow/L2 must be introduced before we can claim that the strategy is genuinely an order-flow strategy.
- We will compare true microstructure features against the current price/participation proxy to determine whether they add incremental expectancy.

## Phase 1 interpretation

The current result is **promising enough to investigate further, but not strong enough to call proven**.

What is interesting:
- expectancy is positive in the four-year development sample
- average realized payoff is strongly asymmetric
- trade frequency is close to the intended 8–15/month region
- maximum drawdown is around the desired ceiling at 1% risk in the underlying point-based model
- the mechanism remains interpretable and simple

What is concerning:
- win rate is low
- 2025 is negative
- there is an 11-loss maximum streak
- the option implementation is much more fragile because of minimum contract size
- true historical order flow/L2 is not yet integrated
- bid/ask and realistic option slippage are not available in the bundled option sample

## Status

**PHASE 1: DEVELOPMENT CANDIDATE — NOT VALIDATED**

Next phase must be performed only after the candidate is frozen:
- independent out-of-sample
- walk-forward
- realistic execution/cost stress
- Monte Carlo
- parameter stability
- regime robustness
- capacity
- paper-trading execution checks
