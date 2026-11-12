"""What the live strategy would have called on recent days (real data, same code the bot runs)."""
import json
import os
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from tjr import Context, simulate  # noqa: E402
from data import binance_paxg  # noqa: E402
from live import lot_size, make_legs, CONTRACT_OZ  # noqa: E402
from strategies import STRATEGIES  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
cfg = json.loads((ROOT / "config.json").read_text())
df = binance_paxg("5m", 6000)
ctx = Context(df, "XAUUSD")
b30 = df.resample("30min").last()
print("5m candles:", len(df), df.index[0], "->", df.index[-1])
since = pd.Timestamp(os.getenv("SINCE", "2026-11-09"), tz="Europe/London")
setups = [s for s in STRATEGIES[cfg["strategy"]](ctx, cap=None, **cfg["strategy_params"]) if pd.Timestamp(s.confirm_time) >= since]
fx, cost, bal = 1.33, 0.30, 2000.0
out = []
for s in setups:
    lots = lot_size(bal, 2.0, abs(s.entry - s.stop), fx, cost)
    legs = make_legs(s.side, s.entry, s.stop, lots)
    pnl = 0.0; res = []
    for l in legs:
        import copy
        x = copy.deepcopy(s); x.target = l["tp"]
        r = simulate(x, ctx.df, cost)
        if r.exit_price is not None:
            mv = (r.exit_price - s.entry) * (1 if s.side == "BUY" else -1) - cost
            pnl += mv * l["lots"] * CONTRACT_OZ / fx
        res.append(f"TP{l['n']}:{r.status}" + ("(early)" if any('closed at' in n for n in r.notes) else ""))
    bal += pnl
    t = pd.Timestamp(s.confirm_time).tz_convert("Europe/London")
    out.append(dict(time=f"{t:%a %d %b %H:%M}", side=s.side, entry=s.entry, stop=s.stop, lots=lots, legs=res, pnl_gbp=round(pnl, 2)))
    print(f"{t:%a %d %b %H:%M} {s.side:4s} entry {s.entry:,.2f} stop {s.stop:,.2f} lots {lots:.2f} {' '.join(res)} £{pnl:+.2f}")
print(f"{len(out)} calls since {since:%a %d %b} · end balance £{bal:,.2f}")
(ROOT / "reports" / "recent.json").write_text(json.dumps(dict(calls=out, end_balance=round(bal, 2)), indent=1))
