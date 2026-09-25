import json
from pathlib import Path
import numpy as np
import pandas as pd

fut=pd.read_csv("data/tick/NIFTY_FUT.csv")
fut["datetime"]=pd.to_datetime(fut["datetime"],errors="coerce")
fut=fut.dropna(subset=["datetime"]).sort_values("datetime").reset_index(drop=True)

bid_px=["bid_px"]+[f"bid_px_{i}" for i in range(2,6)]
ask_px=["ask_px"]+[f"ask_px_{i}" for i in range(2,6)]
bid_qty=["bid_qty"]+[f"bid_qty_{i}" for i in range(2,6)]
ask_qty=["ask_qty"]+[f"ask_qty_{i}" for i in range(2,6)]

required=bid_px+ask_px+bid_qty+ask_qty+["ltp","ltq","tbq","tsq","volume","oi"]
missing=[c for c in required if c not in fut.columns]
if missing:
    raise ValueError(f"Missing required TickBytes columns: {missing}")

for c in required:
    fut[c]=pd.to_numeric(fut[c],errors="coerce")

# 5-level displayed-book imbalance.
fut["bid_depth_5"]=fut[bid_qty].fillna(0).sum(axis=1)
fut["ask_depth_5"]=fut[ask_qty].fillna(0).sum(axis=1)
den=fut.bid_depth_5+fut.ask_depth_5
fut["book_imbalance_5"]=np.where(den>0,(fut.bid_depth_5-fut.ask_depth_5)/den,np.nan)

# Quote-inferred aggressive direction.
# This is deliberately labelled an inference, not an exchange aggressor flag.
fut["signed_ltq"]=np.where(
    fut.ltp>=fut.ask_px, fut.ltq,
    np.where(fut.ltp<=fut.bid_px, -fut.ltq, 0.0)
)

# Simple top-of-book OFI proxy based on changes in displayed best quotes/sizes.
pb=fut.bid_px.to_numpy(); qb=fut.bid_qty.to_numpy()
pa=fut.ask_px.to_numpy(); qa=fut.ask_qty.to_numpy()
ofi=np.zeros(len(fut),dtype=float)
for i in range(1,len(fut)):
    ofi[i] = (
        (qb[i] if pb[i]>=pb[i-1] else (-qb[i-1] if pb[i]<pb[i-1] else 0.0))
        - (qa[i] if pa[i]<=pa[i-1] else (-qa[i-1] if pa[i]>pa[i-1] else 0.0))
    )
fut["ofi_top1"]=ofi

spread=fut.ask_px-fut.bid_px

out={
    "rows":int(len(fut)),
    "first_timestamp":str(fut.datetime.min()),
    "last_timestamp":str(fut.datetime.max()),
    "unique_days":int(fut.datetime.dt.date.nunique()),
    "l2_levels":5,
    "finite_book_imbalance_share":float(np.isfinite(fut.book_imbalance_5).mean()),
    "positive_best_quote_spread_share":float((spread>0).mean()),
    "nonnegative_depth_share":float(((fut.bid_depth_5>=0)&(fut.ask_depth_5>=0)).mean()),
    "quote_inferred_buy_share":float((fut.signed_ltq>0).mean()),
    "quote_inferred_sell_share":float((fut.signed_ltq<0).mean()),
    "quote_inferred_unclassified_share":float((fut.signed_ltq==0).mean()),
    "tbq_present":True,
    "tsq_present":True,
    "tbq_tsq_mean_gap":float((fut.tbq-fut.tsq).mean()),
    "ofi_finite_share":float(np.isfinite(fut.ofi_top1).mean()),
}

# Basic sample-quality flags.
out["quality_flag_short_sample"]=bool(out["unique_days"]<5)
out["quality_flag_preopen_present"]=bool((fut.datetime.dt.time<pd.Timestamp("09:15").time()).any())
out["warning"]="Sample is sufficient for feature/schema validation, not historical strategy performance."

Path("output").mkdir(exist_ok=True)
Path("output/microstructure_feature_capability.json").write_text(json.dumps(out,indent=2,default=str))
fut[["datetime","ltp","ltq","bid_px","bid_qty","ask_px","ask_qty","bid_depth_5","ask_depth_5","book_imbalance_5","signed_ltq","ofi_top1","tbq","tsq"]].head(200).to_csv(
    "output/microstructure_feature_sample.csv",index=False
)
print(json.dumps(out,indent=2,default=str))
