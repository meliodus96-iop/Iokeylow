# Microstructure Capability Check

Tested public TickBytes NIFTY futures tick sample.

Source:
https://github.com/QuantDev-stack/TickBytes

Observed sample:
- 50 tick rows
- one trading day
- 2026-08-03 09:07:10.627 through 10:52:48.678
- top-5 bid/ask depth fields present
- finite 5-level book imbalance for 100% of rows
- positive best-quote spread for 84% of rows
- trade LTP/LTQ fields present
- quote-inferred buy classification 36%
- quote-inferred sell classification 36%
- unclassified 28%
- TBQ/TSQ present
- top-of-book OFI-style feature computable

Important semantics:
- TBQ/TSQ are documented as aggregate order-book buy/sell quantities, not aggressor-side traded volume.
- Aggressor-side direction must be inferred carefully from trades/quotes; it is not assumed to be an exchange-provided field.
- The sample is far too small for any performance conclusion.

Use in project:
This confirms the data schema and demonstrates that a genuine microstructure feature module can be built. It does not provide enough historical observations to test whether L2 improves expectancy.

Next:
When a freely accessible multi-session historical tick/L2 archive is found, compare:
1. existing price/participation proxy
2. quote-inferred signed trade flow
3. 5-level book imbalance
4. top-of-book OFI

Do not select L2 features because they look sophisticated. Keep only features that add independent explanatory value.
