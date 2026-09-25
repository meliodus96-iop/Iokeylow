import json, glob
from pathlib import Path
import numpy as np
import pandas as pd

START=pd.Timestamp("2026-09-04"); END=pd.Timestamp("2026-09-24")

def load():
    dfs=[]
    for f in glob.glob("data/15s/*.csv"):
        x=pd.read_csv(f)
        req={"Epoch","Timestamp","Open","High","Low","Close"}
        if not req.issubset(x.columns): raise ValueError(f"schema {f}: {x.columns.tolist()}")
        x=x[["Timestamp","Open","High","Low","Close"]].rename(columns={"Timestamp":"timestamp","Open":"open","High":"high","Low":"low","Close":"close"})
        x["timestamp"]=pd.to_datetime(x.timestamp,errors="coerce")
        dfs.append(x.dropna())
    d=pd.concat(dfs,ignore_index=True).drop_duplicates("timestamp").sort_values("timestamp")
    d=d[(d.timestamp.dt.time>=pd.Timestamp("09:15").time())&(d.timestamp.dt.time<=pd.Timestamp("15:29").time())]
    d["date"]=d.timestamp.dt.date
    return d.reset_index(drop=True)

def make5(d):
    d=d.copy(); d["bucket"]=d.timestamp.dt.floor("5min")
    g=d.groupby(["date","bucket"],sort=True).agg(open=("open","first"),high=("high","max"),low=("low","min"),close=("close","last"),n=("close","size")).reset_index().rename(columns={"bucket":"timestamp"})
    return g[g.n==20].copy()

def make15_from5(g):
    out=[]
    for d,day in g.groupby("date",sort=True):
        x=day.reset_index(drop=True); n=(len(x)//3)*3
        if n<3: continue
        y=pd.DataFrame({
          "date":d,
          "timestamp":[x.timestamp.iloc[i+2] for i in range(0,n,3)],
          "open":[x.open.iloc[i] for i in range(0,n,3)],
          "high":[x.high.iloc[i:i+3].max() for i in range(0,n,3)],
          "low":[x.low.iloc[i:i+3].min() for i in range(0,n,3)],
          "close":[x.close.iloc[i+2] for i in range(0,n,3)]
        })
        out.append(y)
    return pd.concat(out,ignore_index=True)

def signal_rows(g):
    days={d:x.reset_index(drop=True) for d,x in g.groupby("date",sort=True)}
    dates=sorted(days); out=[]
    for k,d in enumerate(dates):
        if pd.Timestamp(d)<START or k==0: continue
        day=days[d]; prev=days[dates[k-1]]
        if len(day)<60: continue
        prev_hi=float(prev.high.max()); prev_lo=float(prev.low.min())
        o=day.open.to_numpy(float); h=day.high.to_numpy(float); l=day.low.to_numpy(float); c=day.close.to_numpy(float)
        ts=day.timestamp.reset_index(drop=True); rng=h-l
        med=pd.Series(rng).shift(1).rolling(20,min_periods=20).median().to_numpy()
        body=np.divide(np.abs(c-o),rng,out=np.zeros_like(rng),where=rng!=0)
        orh=float(h[:3].max()); orl=float(l[:3].min())
        # causal 15m context
        p15=make15_from5(day)
        cmid=(p15.high-p15.low)
        cm=cmid.rolling(20,min_periods=20).median().to_numpy()
        prevclose=np.r_[np.full(3,np.nan),p15.close.to_numpy()[:-3]]
        ctx=np.where((cm>0)&(np.abs(p15.close.to_numpy()-prevclose)>=0.5*cm),np.sign(p15.close.to_numpy()-prevclose),0.0)
        # context value applies only after the corresponding 15m bar closes, then to next 3 5m bars
        ctx_map=np.zeros(len(day))
        for m,row in p15.iterrows():
            start=3*(m+1); endi=min(start+3,len(day))
            if start<endi: ctx_map[start:endi]=ctx[m]
        mins=ts.dt.hour.to_numpy()*60+ts.dt.minute.to_numpy()
        valid=(mins>=570)&(mins<=885)
        sb=(c>o)&(rng>=1.25*med)&(body>=.60)
        ss=(c<o)&(rng>=1.25*med)&(body>=.60)
        loc=np.divide(c-l,rng,out=np.zeros_like(rng),where=rng!=0); loc2=np.divide(h-c,rng,out=np.zeros_like(rng),where=rng!=0)
        bf=(l<=prev_lo)&(c>prev_lo)&(loc>=.70)
        sf=(h>=prev_hi)&(c<prev_hi)&(loc2>=.70)
        pc=np.r_[np.nan,c[:-1]]
        ba=(pc>orh)&(c>orh)&sb
        sa=(pc<orl)&(c<orl)&ss
        cand=np.flatnonzero(valid&((bf&(ctx_map>=0))|(sf&(ctx_map<=0))|(ba&(ctx_map>=0))|(sa&(ctx_map<=0))))
        traded=False
        for i in cand:
            if traded or i+1>=len(day) or not np.isfinite(med[i]) or med[i]<=0: continue
            if bf[i] and ctx_map[i]>=0: setup,side="bull_failed_auction",1
            elif sf[i] and ctx_map[i]<=0: setup,side="bear_failed_auction",-1
            elif ba[i] and ctx_map[i]>=0: setup,side="bull_acceptance",1
            elif sa[i] and ctx_map[i]<=0: setup,side="bear_acceptance",-1
            else: continue
            entry=o[i+1]
            if side==1:
                stop=min(l[i],prev_lo)-.05*med[i]; risk=entry-stop; room=prev_hi-entry; target=entry+3*risk
            else:
                stop=max(h[i],prev_hi)+.05*med[i]; risk=stop-entry; room=entry-prev_lo; target=entry-3*risk
            if risk<=0 or room<2.5*risk: continue
            out.append({"date":str(d),"signal_time":str(ts.iloc[i]),"entry_time":str(ts.iloc[i+1]),"setup":setup,"side":side,"entry":entry,"stop":stop,"target":target,"risk":risk})
            traded=True
    return pd.DataFrame(out)

def exit_path(signals,d15):
    rows=[]
    days={d:x.reset_index(drop=True) for d,x in d15.groupby("date",sort=True)}
    for _,s in signals.iterrows():
        day=days.get(pd.to_datetime(s.date).date())
        if day is None: continue
        x=day[day.timestamp>=pd.Timestamp(s.entry_time)].reset_index(drop=True)
        side=int(s.side); entry=float(s.entry); stop=float(s.stop); target=float(s.target)
        exit_price=None; reason=None; ambig5=0
        for _,r in x.iterrows():
            if side==1:
                hit_stop=float(r.low)<=stop; hit_target=float(r.high)>=target
                if hit_stop and hit_target:
                    ambig5+=1
                if hit_stop:
                    exit_price=stop; reason="stop"; break
                if hit_target:
                    exit_price=target; reason="target"; break
                if r.timestamp.time()>=pd.Timestamp("15:25").time():
                    exit_price=float(r.open); reason="squareoff"; break
            else:
                hit_stop=float(r.high)>=stop; hit_target=float(r.low)<=target
                if hit_stop and hit_target: ambig5+=1
                if hit_stop:
                    exit_price=stop; reason="stop"; break
                if hit_target:
                    exit_price=target; reason="target"; break
                if r.timestamp.time()>=pd.Timestamp("15:25").time():
                    exit_price=float(r.open); reason="squareoff"; break
        if exit_price is not None:
            rr=(exit_price-entry)/float(s.risk) if side==1 else (entry-exit_price)/float(s.risk)
            rows.append({**s.to_dict(),"exit_price_15s":exit_price,"reason_15s":reason,"realized_R_15s":rr})
    return pd.DataFrame(rows)

Path("output").mkdir(exist_ok=True)
d=load(); g=make5(d); sig=signal_rows(g); res=exit_path(sig,d)
meta={"rows_15s":len(d),"sessions":int(d.date.nunique()),"first":str(d.timestamp.min()),"last":str(d.timestamp.max()),"signals":len(sig)}
res.to_csv("output/15s_execution_verification.csv",index=False)
Path("output/15s_execution_meta.json").write_text(json.dumps(meta,indent=2))
if len(res):
    m={"signals":len(res),"wins":int((res.realized_R_15s>0).sum()),"win_rate":float((res.realized_R_15s>0).mean()),"avg_R":float(res.realized_R_15s.mean()),"avg_winner_R":float(res.loc[res.realized_R_15s>0,"realized_R_15s"].mean()),"avg_loser_R":float(res.loc[res.realized_R_15s<=0,"realized_R_15s"].mean()),"median_hold_min":None}
else: m={"signals":0}
Path("output/15s_execution_metrics.json").write_text(json.dumps(m,indent=2))
print(json.dumps(meta,indent=2)); print(json.dumps(m,indent=2))
