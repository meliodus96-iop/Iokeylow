# PROJECT SPEC — NIFTY Phase 1

## Core architecture

15-minute context -> 5-minute execution -> location -> order-flow/auction event -> confirmation -> asymmetric opportunity -> stop/exit.

Do not add extra timeframes or indicators unless a later research result shows independent information value.

## Setup families

### 1. Absorption reversal
Aggressive participation appears at a meaningful location, but price makes disproportionately little progress. Price then reclaims the area and confirms reversal.

### 2. Aggression + acceptance continuation
Price breaks a meaningful level with directional participation and displacement, then accepts beyond the level. Entry occurs only after all required confirmation information is known.

### 3. Failed auction
Price moves beyond an important prior extreme, attracts participation, fails to gain acceptance, returns inside the prior area, and confirms reversal.

## Location candidates

- Previous-day high/low
- Previous-day value-area high/low
- VWAP
- Opening-range boundaries
- Recent confirmed swing highs/lows
- High/low-volume areas where objectively measurable

## Regime

Use one simple regime concept initially:
- directional vs non-directional, or
- volatility contraction vs expansion

No indicator soup.

## Order-flow

Prefer genuine trade/order-book data:
- aggressor buy/sell volume
- delta
- cumulative delta
- order-flow imbalance
- trade intensity
- depth/book imbalance where available

If unavailable, use explicit proxies and label them as proxies.

## Asymmetry

Before entry, require enough realistic room to the next opposing structural/auction level to support approximately 2.5R–3R. Do not manufacture R:R with unrealistic targets.

## Risk

Starting equity: INR 15,000.

No martingale, averaging down or pyramiding in Phase 1.

Position sizing must respect actual NIFTY option lot sizes and the minimum executable position.

## Session

NSE session context: 09:15–15:40. Strategy square-off is 15:25 unless explicitly changed after research.

No new entry after the defined last-entry time.

## Research dimensions

Record and analyze:
- setup family
- location
- regime
- time of day
- holding time
- MFE/MAE
- time to 1R/2R/3R
- realized R
- option contract characteristics
- costs and slippage

## Development period

Use a recent approximately 2–4 year development sample when clean data permits, without tuning across the entire historical record.

Older data can be used for context/stress checks, not parameter mining.

## Causality

Every signal must use information available at or before the decision timestamp. No look-ahead, repainting, backdated acceptance, or future-bar confirmation.

## Phase separation

Phase 1 = development + descriptive results + limited robustness.

Phase 2 = formal out-of-sample/walk-forward/Monte-Carlo/cost/capacity/live-paper validation.
