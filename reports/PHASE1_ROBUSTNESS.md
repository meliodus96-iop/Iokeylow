# Phase 1 First-Pass Robustness

This is still development, not formal validation.

## Base

- 477 trades
- 9.94 trades/month
- 32.70% win rate
- 2.481R average realized winner/loser ratio
- +0.1343R expectancy
- 1.206 profit factor
- -19.87% max drawdown at 1% risk/trade
- 11 maximum consecutive losses
- 30 min median holding time

## Nearby threshold sensitivity

| Variant | Trades | Win rate | Avg R | Avg realized R:R | PF | Max DD |
|---|---:|---:|---:|---:|---:|---:|
| Base | 477 | 32.70% | +0.134 | 2.481 | 1.206 | -19.87% |
| Lower participation threshold | 484 | 32.85% | +0.137 | 2.472 | 1.209 | -19.93% |
| Higher participation threshold | 464 | 32.11% | +0.129 | 2.528 | 1.196 | -21.23% |

The result does not collapse when the participation threshold moves modestly. This is a positive stability sign.

## Ablation

| Variant | Trades | Win rate | Avg R | Avg R:R | PF | Max DD |
|---|---:|---:|---:|---:|---:|---:|
| With context | 477 | 32.70% | +0.134 | 2.481 | 1.206 | -19.87% |
| Without context | 487 | 32.24% | +0.123 | 2.495 | 1.187 | -20.68% |
| Without room filter | 820 | 40.24% | +0.159 | 1.928 | 1.299 | -23.36% |

Interpretation:
- Removing context modestly reduces expectancy and PF.
- Removing the room filter creates many more trades and increases raw expectancy in this sample, but it worsens drawdown and materially reduces realized payoff asymmetry.
- The room filter is therefore aligned with the project's stated objective of asymmetric opportunities with controlled drawdown. It should not be removed merely because raw expectancy increases.

## Exit sensitivity

| Exit | Win rate | Avg winner | Avg loser | Avg realized R:R | Expectancy | Max DD |
|---|---:|---:|---:|---:|---:|---:|
| 2.5R | 35.43% | 2.130R | -0.971R | 2.192 | +0.127R | -17.33% |
| 3.0R (base) | 32.70% | 2.407R | -0.970R | 2.481 | +0.134R | -19.87% |
| 3.5R | 31.03% | 2.610R | -0.971R | 2.689 | +0.140R | -20.50% |

The 3.5R version does not collapse, and it increases realized R:R, but the improvement over 3R is small. For Phase 1 the simpler 3R baseline remains frozen rather than selecting a target purely because it maximizes this development sample.

## Simple cost-haircut stress

This is not a broker-specific fee model. It subtracts a fixed amount of R from every trade to show sensitivity.

| Per-trade haircut | Expectancy | PF | Max DD | End equity from ₹15k at 1% risk |
|---:|---:|---:|---:|---:|
| 0.00R | +0.134R | 1.206 | -19.87% | ₹26,618 |
| 0.02R | +0.114R | 1.172 | -21.20% | ₹24,198 |
| 0.05R | +0.084R | 1.123 | -23.46% | ₹20,974 |
| 0.10R | +0.034R | 1.048 | -29.34% | ₹16,525 |

The edge becomes thin under a large 0.10R per-trade haircut. This makes realistic option spreads/slippage a major Phase-2 issue.

## Tail/outlier sensitivity

Removing the best 5 trades reduces expectancy from +0.134R to approximately +0.104R.

Removing the best 10 trades reduces it to approximately +0.073R.

Removing roughly the top 5% of trades turns the mean slightly negative in this sample. This is an important characteristic to investigate: the strategy is intentionally asymmetric, so a portion of its economics comes from larger winners.

This does not by itself invalidate the mechanism, but Phase 2 should test whether the positive tail remains present across unseen periods and whether the observed concentration is stable.

## Bootstrap diagnostic

A 20,000-resample bootstrap of the 477-trade base sequence gave:
- mean expectancy: +0.134R
- 95% bootstrap interval: approximately [-0.015R, +0.284R]
- fraction of bootstrap samples with mean <= 0: approximately 3.8%

This is only a descriptive distributional diagnostic. It is NOT an out-of-sample validation or a proof of profitability.

## Phase-1 conclusion

The simplest candidate remains:

15m context + 5m execution
+ location
+ participation/price-response proxy
+ failed-auction / acceptance event
+ natural 2.5R room requirement
+ 3R baseline exit
+ one-trade-per-session and risk controls.

The development evidence is sufficient to justify Phase 2 research, but it is not sufficient to deploy capital.

## Important unresolved limitation

The current historical signal study does not contain a multi-year genuine exchange Level-2/aggressor feed. The order-flow component is still represented by defensible price/participation proxies.

The next order-flow upgrade should compare true tick/L2 features against the current proxy and measure incremental explanatory value. Do not assume L2 improves the strategy merely because it is more detailed.

## Phase status

PHASE 1 DEVELOPMENT COMPLETE — CANDIDATE FROZEN FOR PHASE 2.
