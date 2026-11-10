# Canonical market-data contract

This contract applies to every provider adapter before data is written to the research archive or used by a strategy.

## Required event identity

Every normalized event must preserve:

- `provider` and `venue`: the exact source, not a generic label such as "global".
- `instrument_id`: venue-native symbol plus normalized instrument identity.
- `asset_class` and `product_type`: crypto spot/perp, futures, options, equities, FX, etc.
- `event_type`: trade, quote, book snapshot, book delta, instrument definition, funding, open interest or liquidation.
- `ts_event`: provider/exchange event timestamp in UTC with original precision.
- `ts_recv`: local receive timestamp in UTC.
- `sequence` or provider event/trade ID where available.
- `source_schema`, `book_type`, `depth_levels` and instrument tick/lot metadata where applicable.
- `quality_status`: healthy, partial, stale, gap, resyncing or unavailable.

Never replace a missing field with zero unless zero is the actual provider value.

## Order-side provenance

Every signed trade quantity must carry one of these labels:

| Label | Meaning | Use |
|---|---|---|
| `exchange_reported` | Aggressor side comes from the exchange/vendor event semantics | Preferred source for true delta/CVD. |
| `quote_inferred` | Side inferred from the contemporaneous bid/ask or a documented tick rule | Estimated feature; keep separate from reported flow. |
| `bar_proxy` | Side estimated from OHLCV candle heuristics | Coarse proxy only; never call true footprint/order flow. |
| `unknown` | No defensible side classification | Preserve unsigned volume; exclude from signed delta. |

A provider's field name is not enough. Document and test its precise semantics before treating it as aggressor-side volume.

## Book reconstruction

- L2 requires a valid initial snapshot and correctly sequenced incremental updates.
- Detect sequence gaps, reconnects, duplicate updates and checksum failures.
- On any unresolved gap, invalidate the local book, mark it partial, fetch a new snapshot and resume only from a valid sequence boundary.
- Retain provider event time and receive time; do not hide feed delay.
- Preserve the actual available depth. Five levels must not be labelled ten levels.
- L3/MBO requires individual order identifiers and order-level add, modify, cancel and execution events. L2 depth cannot be promoted to L3.

## Derived features

### Footprint

Bucket executed volume by instrument tick and time interval. Buy/sell split is valid only when order-side provenance is retained. Keep price-level volume and signed delta as separate outputs.

### Delta and CVD

Signed volume = aggressor buy volume minus aggressor sell volume. Compute CVD per venue and instrument first. Do not sum venues unless the research question explicitly defines a cross-venue aggregation and timestamp alignment.

### DOM, heatmap and OFI

Derive from continuous book snapshots/deltas. Record the depth band, normalization method, event window and book quality status with every feature.

### Absorption / iceberg candidates

These are probabilistic observations. A repeated refill can be multiple ordinary orders; public L2 usually does not expose hidden order identity or participant intent. Do not publish a heuristic score as a calibrated probability.

### Options flow and GEX

Options flow requires individual trades on the actual option contract, with timestamp, price, size, contract terms and aggressor-side provenance. Open-interest changes and option-chain snapshots are not trade flow. GEX is a model-derived estimate; disclose gamma calculation, multiplier, spot/forward input, sign convention and dealer-position assumptions.

## Historical/live parity

Use the same normalization and feature code for historical replay and live events. Historical downloads must preserve provider sequence/time semantics and gaps. Record data version, adapter version and feature configuration with every research run.

## Minimum validation before a feed is strategy-eligible

1. Instrument mapping and tick/lot metadata verified.
2. Event-time ordering and duplicate handling tested.
3. Book snapshot/delta sequence continuity tested.
4. Aggressor-side semantics tested against provider documentation/sample events.
5. Missing/stale/gap states propagate to every downstream feature.
6. A fixed replay produces deterministic feature output.
7. A sample is compared against an independent source or vendor reference where possible.

No feature becomes a trading signal merely because it can be calculated.
