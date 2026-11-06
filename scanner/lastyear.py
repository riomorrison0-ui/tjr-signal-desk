"""Last 12 months of the live strategy on a given account, in £, at 0.01 lots."""
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from tjr import ET, Context  # noqa: E402
from backtest import load_hist, run, COST, GBPUSD  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
cfg = json.loads((ROOT / "config.json").read_text())
hist, src = load_hist()
ctx = Context(hist, "XAUUSD")
end = hist.index[-1]
start = end - pd.Timedelta(days=365)
out = {"feed": src, "from": str(start.date()), "to": str(end.date()), "strategy": cfg["strategy"], "params": cfg["strategy_params"]}
for label, acct, cap in (("200_at_2pct", 200, round(200 * 0.02 * GBPUSD, 2)), ("200_all_calls", 200, None),
                         ("2000_at_2pct", 2000, round(2000 * 0.02 * GBPUSD, 2))):
    t = run(ctx, cfg["strategy"], cfg["strategy_params"], cap)
    t = t[t.confirm_time >= start]
    sign = np.where(t["side"] == "BUY", 1, -1)
    pnl = ((t["exit_price"] - t["entry"]) * sign - COST) / GBPUSD
    risk = ((t["entry"] - t["stop"]).abs() + COST) / GBPUSD
    eq = acct + np.concatenate([[0], np.cumsum(pnl.values)])
    days = t.confirm_time.dt.date.nunique()
    tdays = pd.bdate_range(start.date(), end.date()).size
    monthly = pnl.groupby(t.confirm_time.dt.to_period("M")).sum()
    out[label] = dict(account=acct, cap_usd=cap, trades=int(len(t)), win_rate=round(100 * (t["r"] > 0).mean(), 1) if len(t) else None,
                      pnl_gbp=round(float(pnl.sum()), 2), end_balance=round(float(eq[-1]), 2),
                      return_pct=round(100 * float(pnl.sum()) / acct, 1),
                      max_dd_gbp=round(float((np.maximum.accumulate(eq) - eq).max()), 2),
                      lowest_balance=round(float(eq.min()), 2),
                      avg_risk_gbp=round(float(risk.mean()), 2) if len(t) else None,
                      max_risk_gbp=round(float(risk.max()), 2) if len(t) else None,
                      days_with_trade_pct=round(100 * days / tdays, 1), per_day=round(len(t) / tdays, 2),
                      green_months=f"{int((monthly > 0).sum())}/{len(monthly)}",
                      monthly={str(k): round(float(v), 2) for k, v in monthly.items()})
(ROOT / "reports" / "lastyear.json").write_text(json.dumps(out, indent=1))
print(json.dumps(out, indent=1))
