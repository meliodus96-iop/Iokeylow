import json
from pathlib import Path
import numpy as np
import pandas as pd

fut=pd.read_csv("data/tick/NIFTY_FUT.csv")
opt=pd.read_csv("data/tick/NIFTY_OPT.csv")

out={
  "futures_rows":int(len(fut)),
  "options_rows":int(len(opt)),
  "futures_columns":list(fut.columns),
  "options_columns":list(opt.columns),
}

# TickBytes uses bid_px/ask_px for level 1 and _2..._5 for levels 2...5.
bid_px=["bid_px"]+[f"bid_px_{i}" for i in range(2,6)]
ask_px=["ask_px"]+[f"ask_px_{i}" for i in range(2,6)]
bid_qty=["bid_qty"]+[f"bid_qty_{i}" for i in range(2,6)]
ask_qty=["ask_qty"]+[f"ask_qty_{i}" for i in range(2,6)]

missing=[c for c in bid_px+ask_px+bid_qty+ask_qty if c not in fut.columns]
if missing:
    raise ValueError(f"Missing expected TickBytes L2 fields: {missing}")

for c in bid_qty+ask_qty:
    fut[c]=pd.to_numeric(fut[c],errors="coerce")

for c in ["ltp","ltq","tbq","tsq","bid_px","ask_px"]:
    if c in fut.columns:
        fut[c]=pd.to_numeric(fut[c],errors="coerce")

fut["depth_bid_5"]=fut[bid_qty].fillna(0).sum(axis=1)
fut["depth_ask_5"]=fut[ask_qty].fillna(0).sum(axis=1)
den=fut.depth_bid_5+fut.depth_ask_5
fut["book_imbalance_5"]=np.where(den>0,(fut.depth_bid_5-fut.depth_ask_5)/den,np.nan)

spread=fut["ask_px"]-fut["bid_px"]
out["level2_fields_present"]=True
out["finite_book_imbalance_share"]=float(np.isfinite(fut.book_imbalance_5).mean())
out["positive_best_quote_spread_share"]=float((spread>0).mean())
out["nonnegative_depth_share"]=float(((fut.depth_bid_5>=0)&(fut.depth_ask_5>=0)).mean())

ts=pd.to_datetime(fut["datetime"],errors="coerce")
out["timestamp_parse_failures"]=int(ts.isna().sum())
out["duplicate_timestamps"]=int(ts.duplicated().sum())
out["first_timestamp"]=str(ts.min())
out["last_timestamp"]=str(ts.max())

# Candidate aggressor-side classifier:
# If LTP >= best ask -> buy aggression; LTP <= best bid -> sell aggression.
# Otherwise leave unclassified. This is a quote-based inference, NOT a reported aggressor flag.
if {"ltp","bid_px","ask_px","ltq"}.issubset(fut.columns):
    ltp=pd.to_numeric(fut.ltp,errors="coerce")
    bid=pd.to_numeric(fut.bid_px,errors="coerce")
    ask=pd.to_numeric(fut.ask_px,errors="coerce")
    qty=pd.to_numeric(fut.ltq,errors="coerce").fillna(0)
    buy=(ltp>=ask)&(qty>0)
    sell=(ltp<=bid)&(qty>0)
    out["quote_inferred_buy_share"]=float(buy.mean())
    out["quote_inferred_sell_share"]=float(sell.mean())
    out["quote_inferred_classified_share"]=float((buy|sell).mean())
else:
    out["quote_inferred_classified_share"]=0.0

for c in ["delta","gamma","theta","vega","iv","bid_px","ask_px","bid_qty","ask_qty"]:
    out[f"option_{c}_present"]=c in opt.columns

# Crucial semantic note from TickBytes documentation:
# tbq/tsq are aggregate order-book buy/sell quantities, not aggressor trade volume.
out["tbq_tsq_semantics"]="aggregate order-book buy/sell depth; not aggressor-side traded volume"
out["aggressor_side_status"]="quote-inferred candidate only; no explicit aggressor-side flag observed"

Path("output").mkdir(exist_ok=True)
Path("output/tickbytes_microstructure_capability.json").write_text(json.dumps(out,indent=2,default=str))
print(json.dumps(out,indent=2,default=str))
