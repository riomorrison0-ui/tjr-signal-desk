"""Does splitting each trade into TP1/TP2/TP3 beat the single 1R take profit? Same 6 years, same entries/stops."""
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from tjr import ET, Context, FLAT_TIME  # noqa: E402
from backtest import load_hist, COST, GBPUSD, OOS_START  # noqa: E402
from strategies import STRATEGIES  # noqa: E402
from live import lot_size  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
cfg = json.loads((ROOT / "config.json").read_text())
hist, src = load_hist()
ctx = Context(hist, "XAUUSD")
idx = ctx.df.index
ns = idx.asi8
H, L, C = (ctx.df[k].values for k in ("high", "low", "close"))
unit = pd.Timestamp(idx[0]).value // ns[0]


def tsv(x):
    return pd.Timestamp(x).value // unit


def sim(s, tps, weights, be_after=None):
    """Each leg closes at its TP; stop (moved to entry after leg `be_after` fills, if set) closes the rest;
    the strategy's own early exit (hold_until) closes whatever is left. Same-bar stop+target = stop first."""
    buy = s.side == "BUY"
    risk = abs(s.entry - s.stop)
    tgt = [s.entry + (m * risk if buy else -m * risk) for m in tps]
    open_legs = list(range(len(tps)))
    stop = s.stop
    res = [None] * len(tps)
    start = np.searchsorted(ns, tsv(s.confirm_time))
    hu = tsv(s.hold_until) if s.hold_until else None
    for q in range(start, len(ns)):
        hit_sl = L[q] <= stop if buy else H[q] >= stop
        if hit_sl:
            for k in open_legs:
                res[k] = (stop - s.entry) * (1 if buy else -1)
            open_legs = []
            break
        for k in list(open_legs):
            if (H[q] >= tgt[k]) if buy else (L[q] <= tgt[k]):
                res[k] = abs(tgt[k] - s.entry); open_legs.remove(k)
                if be_after is not None and k == be_after:
                    stop = s.entry
        if not open_legs:
            break
        if hu is not None and ns[q] >= hu:
            for k in open_legs:
                res[k] = (C[q] - s.entry) * (1 if buy else -1)
            open_legs = []
            break
    if open_legs:
        return None
    pnl = sum(w * r for w, r in zip(weights, res))          # $ per oz, weighted
    return (pnl - COST) / risk, pnl - COST, s


setups = STRATEGIES[cfg["strategy"]](ctx, cap=None, **cfg["strategy_params"])
VARIANTS = {
    "single TP 1R (current)": dict(tps=(1.0,), w=(1.0,), be=None),
    "TP 0.5/1/1.5R": dict(tps=(0.5, 1.0, 1.5), w=(1 / 3,) * 3, be=None),
    "TP 0.5/1/1.5R + BE after TP1": dict(tps=(0.5, 1.0, 1.5), w=(1 / 3,) * 3, be=0),
    "TP 0.5/1/2R": dict(tps=(0.5, 1.0, 2.0), w=(1 / 3,) * 3, be=None),
    "TP 0.5/1/2R + BE after TP1": dict(tps=(0.5, 1.0, 2.0), w=(1 / 3,) * 3, be=0),
    "TP 0.75/1.25/2R": dict(tps=(0.75, 1.25, 2.0), w=(1 / 3,) * 3, be=None),
    "TP 0.75/1.25/2R + BE after TP1": dict(tps=(0.75, 1.25, 2.0), w=(1 / 3,) * 3, be=0),
    "TP 1/1.5/2R": dict(tps=(1.0, 1.5, 2.0), w=(1 / 3,) * 3, be=None),
    "TP 1/1.5/2R + BE after TP1": dict(tps=(1.0, 1.5, 2.0), w=(1 / 3,) * 3, be=0),
}
out = {}
for name, v in VARIANTS.items():
    rows = []
    for s in setups:
        r = sim(s, v["tps"], v["w"], v["be"])
        if r:
            rows.append((pd.Timestamp(s.confirm_time), r[0], r[1], abs(s.entry - s.stop)))
    t = pd.DataFrame(rows, columns=["t", "r", "usd", "stop"])
    t["t"] = pd.to_datetime(t["t"], utc=True).dt.tz_convert(ET)
    t = t.sort_values("t")
    rr = t["r"].values
    wins, losses = rr[rr > 0], rr[rr <= 0]
    ins, oos = t[t.t < OOS_START], t[t.t >= OOS_START]
    # account: £2,000, 2% sizing rounded down to 0.01 lots, compounding
    bal, peak, dd = 2000.0, 2000.0, 0.0
    months = {}
    for _, x in t.iterrows():
        lots = lot_size(bal, 2.0, x["stop"], GBPUSD, COST)
        if lots <= 0:
            continue
        p = x["usd"] * lots * 100 / GBPUSD
        bal += p; peak = max(peak, bal); dd = max(dd, (peak - bal) / peak * 100)
        m = x["t"].strftime("%Y-%m"); months[m] = months.get(m, 0) + p
    yrs = {str(y): round(float(g["r"].mean()), 3) for y, g in t.groupby(t.t.dt.year)}
    out[name] = dict(n=len(t), win_rate=round(100 * (rr > 0).mean(), 1), avg_r=round(float(rr.mean()), 4),
                     pf=round(float(wins.sum() / -losses.sum()), 3), ins_avg_r=round(float(ins["r"].mean()), 4),
                     oos_avg_r=round(float(oos["r"].mean()), 4), green_years=sum(v_ > 0 for v_ in yrs.values()),
                     end_balance_6y=round(bal, 0), max_dd_pct=round(dd, 1),
                     green_months=f"{sum(v_ > 0 for v_ in months.values())}/{len(months)}", years=yrs)
    print(f"{name:34s} {out[name]}", flush=True)
(ROOT / "reports" / "tp3test.json").write_text(json.dumps(out, indent=1))
