import json
from pathlib import Path
import numpy as np
import pandas as pd

DATA="NIFTY50-INDEX-2026.parquet"
START=pd.Timestamp("2026-04-17")
CAP=15000.0
RISK=0.01

def normalize(df):
    cols={c.lower().strip():c for c in df.columns}
    def pick(*names):
        for n in names:
            if n in cols: return cols[n]
        raise KeyError((names, list(df.columns)))
    t=pick("timestamp","datetime","date","time")
    o=pick("open"); h=pick("high"); l=pick("low"); c=pick("close")
    out=df[[t,o,h,l,c]].copy()
    out.columns=["timestamp","open","high","low","close"]
    out["timestamp"]=pd.to_datetime(out["timestamp"], errors="coerce")
    if getattr(out["timestamp"].dt,"tz",None) is not None:
        out["timestamp"]=out["timestamp"].dt.tz_convert("Asia/Kolkata").dt.tz_localize(None)
    out=out.dropna().sort_values("timestamp")
    # Keep normal continuous session; no pre-open.
    out=out[(out.timestamp.dt.time>=pd.Timestamp("09:15").time()) & (out.timestamp.dt.time<=pd.Timestamp("15:29").time())]
    out["date"]=out.timestamp.dt.date
    return out

def aggregate_5m(d):
    d=d.sort_values("timestamp").copy()
    # Source is expected to be one-minute bars timestamped by interval start.
    d["bucket"]=d.timestamp.dt.floor("5min")
    g=d.groupby(["date","bucket"],sort=True).agg(
        open=("open","first"),high=("high","max"),low=("low","min"),close=("close","last"),
        n=("close","size")
    ).reset_index().rename(columns={"bucket":"timestamp"})
    # Only full 5-minute bars.
    g=g[g.n==5].copy()
    return g

def run(df5):
    days={d:g.reset_index(drop=True) for d,g in df5.groupby("date",sort=True)}
    sessions=sorted(days)
    prev={sessions[i]:sessions[i-1] for i in range(1,len(sessions))}
    rows=[]
    for d in sessions:
        if pd.Timestamp(d)<START: continue
        if d not in prev: continue
        g=days[d]
        if len(g)<60: continue
        pg=days[prev[d]]
        prev_hi=float(pg.high.max()); prev_lo=float(pg.low.min())
        ts=g.timestamp.to_numpy(); o=g.open.to_numpy(float); h=g.high.to_numpy(float); l=g.low.to_numpy(float); c=g.close.to_numpy(float)
        rng=h-l
        med=pd.Series(rng).shift(1).rolling(20,min_periods=20).median().to_numpy()
        body=np.divide(np.abs(c-o),rng,out=np.zeros_like(rng),where=rng!=0)
        orh=h[:3].max(); orl=l[:3].min()
        n=(len(g)//3)*3
        c15=c[:n].reshape(-1,3)[:,-1]; h15=h[:n].reshape(-1,3).max(1); l15=l[:n].reshape(-1,3).min(1)
        ctx_med=pd.Series(h15-l15).rolling(20,min_periods=20).median().to_numpy()
        lag3=np.r_[np.full(3,np.nan),c15[:-3]]
        ctx=np.where((ctx_med>0)&(np.abs(c15-lag3)>=0.5*ctx_med),np.sign(c15-lag3),0.0)
        ctx5=np.repeat(np.r_[0.0,ctx[:-1]],3)[:len(g)]
        mins=pd.to_datetime(ts).hour.to_numpy()*60+pd.to_datetime(ts).minute.to_numpy()
        valid=(mins>=570)&(mins<=885)
        sb=(c>o)&(rng>=1.25*med)&(body>=.60)
        ss=(c<o)&(rng>=1.25*med)&(body>=.60)
        bull_fail=(l<=prev_lo)&(c>prev_lo)&(np.divide(c-l,rng,out=np.zeros_like(rng),where=rng!=0)>=.70)
        bear_fail=(h>=prev_hi)&(c<prev_hi)&(np.divide(h-c,rng,out=np.zeros_like(rng),where=rng!=0)>=.70)
        prev_c=np.r_[np.nan,c[:-1]]
        bull_acc=(prev_c>orh)&(c>orh)&sb
        bear_acc=(prev_c<orl)&(c<orl)&ss
        long_ok=ctx5>=0; short_ok=ctx5<=0
        # Frozen Phase-1 candidate: failed auction or 2-close acceptance.
        candidates=np.flatnonzero(valid & ((bull_fail&long_ok)|(bear_fail&short_ok)|(bull_acc&long_ok)|(bear_acc&short_ok)))
        traded=False
        for i in candidates:
            if traded or i+1>=len(g): continue
            if bull_fail[i] and long_ok[i]: setup,side="bull_failed_auction",1
            elif bear_fail[i] and short_ok[i]: setup,side="bear_failed_auction",-1
            elif bull_acc[i] and long_ok[i]: setup,side="bull_acceptance",1
            elif bear_acc[i] and short_ok[i]: setup,side="bear_acceptance",-1
            else: continue
            entry=o[i+1]
            if side==1:
                stop=min(l[i],prev_lo)-.05*med[i]; risk=entry-stop; room=prev_hi-entry; target=entry+3*risk
            else:
                stop=max(h[i],prev_hi)+.05*med[i]; risk=stop-entry; room=entry-prev_lo; target=entry-3*risk
            if not np.isfinite(risk) or risk<=0 or room<2.5*risk: continue
            mfe=mae=0.; xp=None; reason=None; exit_i=None
            for j in range(i+1,len(g)):
                if mins[j]>=925:
                    exit_i=j; xp=o[j]; reason="squareoff"; break
                if side==1:
                    mfe=max(mfe,(h[j]-entry)/risk); mae=max(mae,(entry-l[j])/risk)
                    if l[j]<=stop: exit_i=j; xp=stop; reason="stop"; break
                    if h[j]>=target: exit_i=j; xp=target; reason="target"; break
                else:
                    mfe=max(mfe,(entry-l[j])/risk); mae=max(mae,(h[j]-entry)/risk)
                    if h[j]>=stop: exit_i=j; xp=stop; reason="stop"; break
                    if l[j]<=target: exit_i=j; xp=target; reason="target"; break
            if exit_i is None: continue
            rr=(xp-entry)/risk if side==1 else (entry-xp)/risk
            rows.append({
                "date":str(d),"signal_time":str(ts[i]),"entry_time":str(ts[i+1]),
                "side":side,"setup":setup,"realized_R":float(rr),"reason":reason,
                "mfe_R":float(mfe),"mae_R":float(mae),
                "holding_min":float((pd.Timestamp(ts[exit_i])-pd.Timestamp(ts[i+1])).total_seconds()/60)
            })
            traded=True
    return pd.DataFrame(rows)

def metrics(tr):
    if tr.empty: return {"trades":0}
    w=tr.realized_R>0
    aw=tr.loc[w,"realized_R"].mean(); al=tr.loc[~w,"realized_R"].mean()
    eq=CAP*np.cumprod(1+RISK*tr.realized_R.to_numpy())
    dd=np.min(eq/np.maximum.accumulate(eq)-1)
    cur=streak=0
    for x in tr.realized_R:
        cur=cur+1 if x<0 else 0; streak=max(streak,cur)
    return {
        "oos_start":str(pd.to_datetime(tr.signal_time).min()),
        "oos_end":str(pd.to_datetime(tr.signal_time).max()),
        "trades":int(len(tr)),
        "trades_per_month":float(len(tr)/max(1,len(pd.period_range(START,pd.to_datetime(tr.signal_time).max(),freq="M")))),
        "win_rate":float(w.mean()),
        "avg_winner_R":float(aw),"avg_loser_R":float(al),
        "avg_realized_RR":float(aw/abs(al)),
        "expectancy_R":float(tr.realized_R.mean()),
        "profit_factor":float(tr.loc[w,"realized_R"].sum()/abs(tr.loc[~w,"realized_R"].sum())) if (~w).any() else None,
        "max_dd_1pct":float(dd),"end_equity_1pct":float(eq[-1]),
        "max_consecutive_losses":int(streak),
        "median_holding_min":float(tr.holding_min.median())
    }

df=pd.read_parquet(DATA)
meta={"columns":list(df.columns),"rows":int(len(df))}
d=normalize(df)
meta.update({"normalized_rows":int(len(d)),"first":str(d.timestamp.min()),"last":str(d.timestamp.max()),"sessions":int(d.date.nunique())})
df5=aggregate_5m(d)
tr=run(df5)
Path("output").mkdir(exist_ok=True)
tr.to_csv("output/oos_2026_signal_trades.csv",index=False)
Path("output/oos_2026_metrics.json").write_text(json.dumps(metrics(tr),indent=2))
Path("output/oos_2026_data_meta.json").write_text(json.dumps(meta,indent=2))
print(json.dumps(meta,indent=2))
print(json.dumps(metrics(tr),indent=2))
