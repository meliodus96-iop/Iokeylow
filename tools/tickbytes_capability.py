import json, subprocess
from pathlib import Path
import pandas as pd, numpy as np

def read_csv(path):
    return pd.read_csv(path)

out={}
fut=read_csv("data/tick/NIFTY_FUT.csv")
opt=read_csv("data/tick/NIFTY_OPT.csv")

out["futures_columns"]=list(fut.columns)
out["options_columns"]=list(opt.columns)
out["futures_rows"]=len(fut); out["options_rows"]=len(opt)

bid=[f"bid_px_{i}" for i in range(1,6)]
ask=[f"ask_px_{i}" for i in range(1,6)]
bq=[f"bid_qty_{i}" for i in range(1,6)]
aq=[f"ask_qty_{i}" for i in range(1,6)]

for c in bid+ask+bq+aq:
    if c not in fut.columns:
        raise ValueError("Missing L2 field "+c)

fut["depth_bid_5"]=fut[bq].fillna(0).sum(axis=1)
fut["depth_ask_5"]=fut[aq].fillna(0).sum(axis=1)
den=fut.depth_bid_5+fut.depth_ask_5
fut["book_imbalance_5"]=np.where(den>0,(fut.depth_bid_5-fut.depth_ask_5)/den,np.nan)

# Cumulative TBQ/TSQ changes are only a derived feature candidate.
# We do not call them aggressor volume without a documented definition.
if {"tbq","tsq"}.issubset(fut.columns):
    fut["tbq_change"]=fut.tbq.diff()
    fut["tsq_change"]=fut.tsq.diff()
    out["tbq_tsq_present"]=True
    out["tbq_change_nonnegative_share"]=float((fut.tbq_change.dropna()>=0).mean())
    out["tsq_change_nonnegative_share"]=float((fut.tsq_change.dropna()>=0).mean())
else:
    out["tbq_tsq_present"]=False

# Basic sanity checks
spread=fut["ask_px"]-fut["bid_px"]
out["positive_best_quote_spread_share"]=float((spread>0).mean())
out["nonnegative_depth_share"]=float(((fut.depth_bid_5>=0)&(fut.depth_ask_5>=0)).mean())
out["finite_book_imbalance_share"]=float(np.isfinite(fut.book_imbalance_5).mean())

# Detect timestamp ordering/duplicates
ts=pd.to_datetime(fut.datetime,errors="coerce")
out["timestamp_parse_failures"]=int(ts.isna().sum())
out["duplicate_timestamps"]=int(ts.duplicated().sum())
out["first_timestamp"]=str(ts.min()); out["last_timestamp"]=str(ts.max())

# Option microstructure fields
for c in ["delta","gamma","theta","vega","iv","bid_px","ask_px","bid_qty","ask_qty"]:
    out[f"option_{c}_present"]=c in opt.columns

Path("output").mkdir(exist_ok=True)
Path("output/tickbytes_microstructure_capability.json").write_text(json.dumps(out,indent=2,default=str))
print(json.dumps(out,indent=2,default=str))
