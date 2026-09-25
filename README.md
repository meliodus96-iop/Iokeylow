# NIFTY Order-Flow / Auction Research

Phase-1 research project for a simple, non-overfit intraday NIFTY strategy.

## Objective

Develop and study a causal strategy based on:

**Location + Participation/Order Flow + Price Response + Asymmetric Opportunity**

The research signal is generated from NIFTY futures/underlying market behavior. NIFTY options are treated as a separate execution layer.

## Phase 1 status

- Strategy concept: defined
- ₹15,000 capital model: defined
- 15-minute context / 5-minute execution: defined
- Absorption reversal: defined
- Aggression + acceptance continuation: defined
- Failed auction: defined
- 2.5R–3R asymmetric opportunity target: defined as a research objective
- Time-of-day analysis: included
- Holding-time analysis: included
- Causality tests: required
- Final institutional validation: intentionally deferred to Phase 2

## Important

No profitability claim is made until real NIFTY data is processed.

Synthetic smoke-test results are software checks only and are not market evidence.

## Repository layout

- `PROJECT_SPEC.md` — frozen Phase-1 development specification
- `config.yaml` — research defaults
- `data/` — data requirements and schema
- `requirements.txt` — Python dependencies
- `../nifty_phase1_orderflow_strategy_final.zip` — complete local research package delivered separately in the ChatGPT workspace

## Research sequence

1. Ingest real NIFTY futures/underlying intraday data.
2. Add NIFTY option history for execution/P&L.
3. Use tick/L2 data when available; never label proxies as true order flow.
4. Run the predefined development study.
5. Decompose performance by setup, location, regime, time of day and holding time.
6. Perform limited robustness checks.
7. Freeze the simplest credible candidate.
8. Only then begin Phase-2 institutional validation.
