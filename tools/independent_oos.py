import json, glob, os
from pathlib import Path
import numpy as np, pandas as pd

START=pd.Timestamp("2026-04-17"); CAP=15000.; RISK=.01

def load():
    files=glob.glob("data/oos_source/*.csv")
    dfs=[]
    for f in files:
        x=pd.read_csv(f)
        req=["Epoch","Timestamp","Open","High","Low","Close"]
        if not set(req).issubset(x.columns):
            raise ValueError(f"Schema mismatch: {f}: {x.columns.tolist()}")
        x=x[req].copy()
        x["timestamp"]=pd.to_datetime(x["Timestamp"], errors="coerce")
        x=x.dropna(subset=["timestamp","Open","High","Low","Close"])
        dfs.append(x[["timestamp","Open","High","Low","Close"]].rename(columns={"Open":"open","High":"high","Low":"low","Close":"close"}))
    d=pd.concat(dfs,ignore_index=True).drop_duplicates("timestamp").sort_values("timestamp")
    # Source timestamps are local-market timestamps.
    d=d[(d.timestamp.dt.time>=pd.Timestamp("09:15").time())&(d.timestamp.dt.time<=pd.Timestamp("15:29").time())]
    d["date"]=d.timestamp.dt.date
    return d.reset_index(drop=True)

def to5(d):
    d=d.copy()
    d["bucket"]=d.timestamp.dt.floor("5min")
    g=d.groupby(["date","bucket"],sort=True).agg(open=("open","first"),high=("high","max"),low=("low","min"),close=("close","last"),n=("close","size")).reset_index().rename(columns={"bucket":"timestamp"})
    return g[g.n==5].copy()

def run(df5):
    days={d:g.reset_index(drop=True) for d,g in df5.groupby("date",sort=True)}
    dates=sorted(days)
    rows=[]
    for k,d in enumerate(dates):
        if pd.Timestamp(d)<START or k==0: continue
        g=days[d]; pg=days[dates[k-1]]
        if len(g)<60: continue
        prev_hi=float(pg.high.max()); prev_lo=float(pg.low.min())
        ts=g.timestamp.reset_index(drop=True); o=g.open.to_numpy(float); h=g.high.to_numpy(float); l=g.low.to_numpy(float); c=g.close.to_numpy(float)
        rng=h-l
        med=pd.Series(rng).shift(1).rolling(20,min_periods=20).median().to_numpy()
        body=np.divide(np.abs(c-o),rng,out=np.zeros_like(rng),where=rng!=0)
        orh=float(h[:3].max()); orl=float(l[:3].min())
        n=(len(g)//3)*3
        c15=c[:n].reshape(-1,3)[:,-1]; h15=h[:n].reshape(-1,3).max(1); l15=l[:n].reshape(-1,3).min(1)
        ctx_med=pd.Series(h15-l15).rolling(20,min_periods=20).median().to_numpy()
        lag3=np.r_[np.full(3,np.nan),c15[:-3]]
        ctx=np.where((ctx_med>0)&(np.abs(c15-lag3)>=0.5*ctx_med),np.sign(c15-lag3),0.0)
        ctx5=np.repeat(np.r_[0.0,ctx[:-1]],3)[:len(g)]
        mins=ts.dt.hour.to_numpy()*60+ts.dt.minute.to_numpy()
        valid=(mins>=570)&(mins<=885)
        strong_bull=(c>o)&(rng>=1.25*med)&(body>=.60)
        strong_bear=(c<o)&(rng>=1.25*med)&(body>=.60)
        loc=np.divide(c-l,rng,out=np.zeros_like(rng),where=rng!=0)
        loc2=np.divide(h-c,rng,out=np.zeros_like(rng),where=rng!=0)
        bull_fail=(l<=prev_lo)&(c>prev_lo)&(loc>=.70)
        bear_fail=(h>=prev_hi)&(c<prev_hi)&(loc2>=.70)
        pc=np.r_[np.nan,c[:-1]]
        bull_acc=(pc>orh)&(c>orh)&strong_bull
        bear_acc=(pc<orl)&(c<orl)&strong_bear
        candidates=np.flatnonzero(valid&((bull_fail&(ctx5>=0))|(bear_fail&(ctx5<=0))|(bull_acc&(ctx5>=0))|(bear_acc&(ctx5<=0))))
        traded=False
        for i in candidates:
            if traded or i+1>=len(g) or not np.isfinite(med[i]) or med[i]<=0: continue
            if bull_fail[i] and ctx5[i]>=0: setup,side="bull_failed_auction",1
            elif bear_fail[i] and ctx5[i]<=0: setup,side="bear_failed_auction",-1
            elif bull_acc[i] and ctx5[i]>=0: setup,side="bull_acceptance",1
            elif bear_acc[i] and ctx5[i]<=0: setup,side="bear_acceptance",-1
            else: continue
            entry=o[i+1]
            if side==1:
                stop=min(l[i],prev_lo)-.05*med[i]; risk=entry-stop; room=prev_hi-entry; target=entry+3*risk
            else:
                stop=max(h[i],prev_hi)+.05*med[i]; risk=stop-entry; room=entry-prev_lo; target=entry-3*risk
            if risk<=0 or room<2.5*risk: continue
            exit_i=None; xp=None; reason=None; mfe=mae=0.
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
            rows.append({"date":str(d),"signal_time":str(ts.iloc[i]),"entry_time":str(ts.iloc[i+1]),"setup":setup,"side":side,"realized_R":float(rr),"reason":reason,"mfe_R":float(mfe),"mae_R":float(mae),"holding_min":float((ts.iloc[exit_i]-ts.iloc[i+1]).total_seconds()/60)})
            traded=True
    return pd.DataFrame(rows)

def metrics(t):
    if t.empty: return {"trades":0}
    w=t.realized_R>0; aw=t.loc[w,"realized_R"].mean(); al=t.loc[~w,"realized_R"].mean()
    eq=CAP*np.cumprod(1+RISK*t.realized_R.to_numpy())
    dd=float(np.min(eq/np.maximum.accumulate(eq)-1))
    streak=cur=0
    for x in t.realized_R:
        cur=cur+1 if x<0 else 0; streak=max(streak,cur)
    return {"start":str(pd.to_datetime(t.signal_time).min()),"end":str(pd.to_datetime(t.signal_time).max()),"trades":len(t),"win_rate":float(w.mean()),"avg_winner_R":float(aw),"avg_loser_R":float(al),"avg_realized_RR":float(aw/abs(al)),"expectancy_R":float(t.realized_R.mean()),"profit_factor":float(t.loc[w,"realized_R"].sum()/abs(t.loc[~w,"realized_R"].sum())),"max_dd_1pct":dd,"end_equity_1pct":float(eq[-1]),"max_consecutive_losses":streak,"median_holding_min":float(t.holding_min.median()),"trades_per_month":float(len(t)/6)}
    
Path("output").mkdir(exist_ok=True)
d=load()
meta={"files":len(glob.glob("data/oos_source/*.csv")),"rows":len(d),"first":str(d.timestamp.min()),"last":str(d.timestamp.max()),"sessions":int(d.date.nunique())}
t=run(to5(d))
t.to_csv("output/independent_oos_trades.csv",index=False)
Path("output/independent_oos_metrics.json").write_text(json.dumps(metrics(t),indent=2))
Path("output/independent_oos_data_meta.json").write_text(json.dumps(meta,indent=2))
print(json.dumps(meta,indent=2)); print(json.dumps(metrics(t),indent=2))
