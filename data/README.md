# Data requirements

## Minimum

NIFTY futures/underlying intraday data with:
- timestamp
- open
- high
- low
- close
- volume
- open interest where available

NIFTY option history with:
- timestamp
- expiry
- strike
- CE/PE
- OHLC
- volume
- open interest
- spot
- IV/Greeks where available

## Preferred

Tick data:
- timestamp
- traded price
- quantity
- bid/ask or aggressor side

Level-2:
- timestamp
- bid price/quantity levels
- ask price/quantity levels

## Data principle

Heat-map images are not required for research. The raw trade/order-book data behind the heat map is what matters.

Do not upload broker API secrets. Keep credentials on the user's own machine and export/download the resulting data files for research.
