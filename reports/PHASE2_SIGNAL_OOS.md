# Phase 2 Signal OOS — Independent Public Source

## Dataset

Source:
https://github.com/technovusin/nifty50-historical-data

The source provides 1-minute NIFTY50 data from January 2026 and additional 15-second data from September 4, 2026. The test used the 1-minute files through September 24, 2026.

OOS decision period:
2026-04-17 onward.

No strategy parameters were changed for this test.

## Frozen rules

- 15-minute causal context
- 5-minute execution
- previous-day extremes
- opening range
- price/participation proxy
- failed-auction reversal
- acceptance continuation
- natural room >= 2.5R
- 3R baseline target
- one trade per session
- 1% risk illustration

## OOS results

| Metric | Result |
|---|---:|
| Trades | 48 |
| Win rate | 35.42% |
| Average winner | 2.588R |
| Average loser | -0.987R |
| Average realized R:R | 2.621R |
| Expectancy | +0.279R/trade |
| Profit factor | 1.437 |
| Max drawdown @ 1% risk | -6.79% |
| Ending equity from ₹15,000 @ 1% risk | ₹17,017 |
| Max consecutive losses | 7 |
| Median holding time | 25 min |
| Approx. trades/month | 8 |

The signal generated trades through September 17, with no qualifying trades from September 18–24 under the frozen rules.

## Interpretation

The asymmetric payoff profile seen in development remains present on this independent public source. However, 48 trades is still too small for a strong statistical conclusion. This is evidence to continue testing, not proof of a durable edge.

## Source comparison

A separate public NIFTY50 dataset from ganeshbiyer/Nse_Historical_Data_2026 produced only 4 trades under the same frozen evaluator. Its file had substantially more rows per session than expected for ordinary 1-minute bars, indicating a frequency/schema mismatch that reduces valid 5-minute aggregation. I therefore do not use that 4-trade result as primary performance evidence.

## 15-second execution check

A free 15-second NIFTY sample covering September 4–24 produced the same four recent signals:
- September 9
- September 10
- September 11
- September 17

The 15-second path confirmed the same directional outcomes for these four trades.

## True order-flow status

The historical OOS results above do NOT use true historical Level-2 or exchange-provided aggressor flags.

The order-flow component remains a price/participation proxy.

The public TickBytes sample contains the fields needed for a genuine microstructure upgrade:
- trade timestamp
- last traded price/quantity
- aggregate buy/sell quantity
- best bid/ask
- top-5 bid/ask depth
- option IV and Greeks

TickBytes documents TBQ/TSQ as aggregate buy/sell order-book quantities, not aggressor-side traded volume. Any aggressor label must therefore be derived carefully and explicitly identified as an inference.

## Next validation work

- True tick/L2 feature comparison where free data permits
- Independent execution and cost modeling
- Walk-forward validation
- Untouched OOS periods
- Monte Carlo / drawdown distribution
- Parameter stability
- Option-expression robustness
- Actual contract-size feasibility
- Paper-execution study
