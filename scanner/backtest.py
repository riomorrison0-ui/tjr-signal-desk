"""
Large gold backtest of the TJR model.

Data
  - Dukascopy spot XAUUSD 5m (years, free, same spot price a retail MT5 broker shows)
    downloaded by the workflow into data/hist/xauusd_m5.csv
  - Yahoo COMEX gold futures 5m, last 60 days (a second, independent feed)

Method
  - every combination in GRID is run on the whole history
  - settings are PICKED on the in-sample years only (before OOS_START)
  - the picked settings are then reported on the out-of-sample years they never saw
  - costs included, same-bar stop+target counted as a loss, no look-ahead

Writes reports/backtest.md, reports/backtest.json, reports/summary.json, reports/trades_best.csv
"""
from __future__ import annotations

import itertools
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from tjr import ET, FUNNEL, INSTRUMENTS, Context, Params, find_setups, simulate  # noqa: E402
from data import yahoo  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
HIST = ROOT / "data" / "hist" / "xauusd_m5.csv"
OOS_START = pd.Timestamp(os.getenv("OOS_START", "2025-01-01"), tz=ET)
COST = INSTRUMENTS["XAUUSD"]["cost"]

ACCOUNT_GBP = float(os.getenv("ACCOUNT_GBP", "200"))
GBPUSD = 1.30                      # fixed for the backtest; live uses the real rate
MAX_RISK_PCT = 2.0
LOT_OZ = 1.0                       # 0.01 lot of XAUUSD = 1 oz -> $1 per $1 move
STOP_CAP = round(ACCOUNT_GBP * MAX_RISK_PCT / 100 * GBPUSD / LOT_OZ, 2)   # ~$5.20

GRID = dict(
    entry=["fvg", "market"],
    target=["1R", "1.5R", "2R", "3R", "liq"],
    bias=["structure", "ema", "none"],
    zones=["both", "ny", "london"],
    max_stop_usd=[STOP_CAP, None],   # None = what the raw model does with no account limit
)


def load_dukascopy() -> pd.DataFrame | None:
    if not HIST.exists():
        print("no dukascopy file at", HIST)
        return None
    df = pd.read_csv(HIST)
    ts = df.columns[0]
    df.index = pd.DatetimeIndex(pd.to_datetime(df[ts], unit="ms", utc=True)).tz_convert(ET)
    df = df[["open", "high", "low", "close"]].astype(float).dropna()
    df = df[(df["high"] > df["low"]) | (df["high"] == df["low"])]
    return df[~df.index.duplicated()].sort_index()


def stats(rs) -> dict:
    a = np.array(list(rs), dtype=float)
    if len(a) == 0:
        return dict(n=0, win_rate=None, avg_r=None, total_r=0.0, pf=None, max_dd_r=0.0, max_losing_streak=0)
    wins, losses = a[a > 0], a[a <= 0]
    eq = np.concatenate([[0], np.cumsum(a)])
    streak = best = 0
    for r in a:
        streak = streak + 1 if r <= 0 else 0
        best = max(best, streak)
    return dict(n=int(len(a)), win_rate=round(100 * len(wins) / len(a), 1), avg_r=round(float(a.mean()), 3),
                total_r=round(float(a.sum()), 1),
                pf=round(float(wins.sum() / -losses.sum()), 2) if losses.sum() < 0 else None,
                max_dd_r=round(float((np.maximum.accumulate(eq) - eq).max()), 1), max_losing_streak=int(best))


def run(ctx: Context, p: Params) -> pd.DataFrame:
    rows = []
    for s in find_setups(ctx.df, "XAUUSD", p, ctx):
        s = simulate(s, ctx.df, COST)
        if s.status in ("win", "loss"):
            d = s.to_dict(); d["notes"] = ";".join(d["notes"]); rows.append(d)
    t = pd.DataFrame(rows)
    if len(t):
        t["confirm_time"] = pd.to_datetime(t["confirm_time"], utc=True).dt.tz_convert(ET)
    return t


def money(t: pd.DataFrame) -> dict:
    """Fixed 0.01 lot on a GBP account: P&L in £, worst drawdown in £ and as % of the start."""
    if not len(t):
        return dict(pnl_gbp=0.0, avg_risk_gbp=None, max_risk_pct=None, max_dd_gbp=0.0, end_balance=ACCOUNT_GBP)
    sign = np.where(t["side"] == "BUY", 1, -1)
    pnl = ((t["exit_price"] - t["entry"]) * sign - COST) * LOT_OZ / GBPUSD
    risk = ((t["entry"] - t["stop"]).abs() + COST) * LOT_OZ / GBPUSD
    eq = ACCOUNT_GBP + np.concatenate([[0], np.cumsum(pnl.values)])
    return dict(pnl_gbp=round(float(pnl.sum()), 2), avg_risk_gbp=round(float(risk.mean()), 2),
                max_risk_pct=round(float(risk.max() / ACCOUNT_GBP * 100), 2),
                max_dd_gbp=round(float((np.maximum.accumulate(eq) - eq).max()), 2), end_balance=round(float(eq[-1]), 2))


def evaluate(t: pd.DataFrame) -> dict:
    if not len(t):
        return dict(all=stats([]), ins=stats([]), oos=stats([]), years={}, money_all={}, money_oos={})
    ins, oos = t[t.confirm_time < OOS_START], t[t.confirm_time >= OOS_START]
    years = {str(y): stats(g["r"]) for y, g in t.groupby(t.confirm_time.dt.year)}
    return dict(all=stats(t["r"]), ins=stats(ins["r"]), oos=stats(oos["r"]), years=years,
                money_all=money(t), money_oos=money(oos))


def main():
    t0 = time.time()
    feeds = {}
    d = load_dukascopy()
    if d is not None and len(d) > 1000:
        feeds["dukascopy_spot"] = d
    try:
        y = yahoo("GC=F", "5m", "60d")
        feeds["yahoo_futures_60d"] = y
    except Exception as e:  # noqa: BLE001
        print("yahoo failed", e)
    for k, v in feeds.items():
        print(f"{k}: {len(v):,} bars {v.index[0]} -> {v.index[-1]}")
    if "dukascopy_spot" not in feeds:
        print("!! no long history; backtest limited to 60 days")
    main_feed = "dukascopy_spot" if "dukascopy_spot" in feeds else "yahoo_futures_60d"

    ctxs = {k: Context(v, "XAUUSD") for k, v in feeds.items()}
    print(f"prepared in {time.time() - t0:.0f}s")

    keys = list(GRID)
    results = []
    best_trades = {}
    combos = list(itertools.product(*GRID.values()))
    if os.getenv("QUICK"):
        combos = combos[:int(os.getenv("QUICK"))]
    for combo in combos:
        p = Params(**dict(zip(keys, combo)))
        FUNNEL.clear()
        t = run(ctxs[main_feed], p)
        ev = evaluate(t)
        ev["funnel"] = dict(FUNNEL)
        ev["params"] = dict(zip(keys, combo))
        ev["label"] = p.label()
        results.append(ev)
        best_trades[p.label()] = t
        a, o = ev["all"], ev["oos"]
        print(f"{p.label():70s} n={a['n']:4d} wr={a['win_rate']} avgR={a['avg_r']} | OOS n={o['n']} wr={o['win_rate']} avgR={o['avg_r']}", flush=True)

    min_n = 40 if main_feed == "dukascopy_spot" else 10
    elig = [r for r in results if r["params"]["max_stop_usd"] and r["ins"]["n"] >= min_n and r["ins"]["avg_r"] is not None]
    pick_exp = max(elig, key=lambda r: r["ins"]["avg_r"]) if elig else None
    pos = [r for r in elig if r["ins"]["avg_r"] > 0.05]
    pick_wr = max(pos, key=lambda r: r["ins"]["win_rate"]) if pos else None

    # cross-check the picks on the independent Yahoo futures feed
    cross = {}
    if "yahoo_futures_60d" in ctxs and main_feed != "yahoo_futures_60d":
        for name, r in (("best_expectancy", pick_exp), ("best_win_rate", pick_wr)):
            if r:
                cross[name] = stats(run(ctxs["yahoo_futures_60d"], Params(**r["params"]))["r"]) if True else None

    hist = feeds[main_feed]
    summary = dict(
        generated=pd.Timestamp.now(tz="UTC").isoformat(), feed=main_feed,
        first=str(hist.index[0].date()), last=str(hist.index[-1].date()), oos_start=str(OOS_START.date()),
        account_gbp=ACCOUNT_GBP, stop_cap_usd=STOP_CAP, combos=len(results), best_expectancy=pick_exp, best_win_rate=pick_wr, cross_check_yahoo_60d=cross,
        runtime_s=round(time.time() - t0),
    )
    out = ROOT / "reports"; out.mkdir(exist_ok=True)
    (out / "summary.json").write_text(json.dumps(summary, indent=1, default=str))
    (out / "backtest.json").write_text(json.dumps(results, indent=1, default=str))
    for name, r in (("best", pick_exp), ("best_wr", pick_wr)):
        if r is not None:
            best_trades[r["label"]].to_csv(out / f"trades_{name}.csv", index=False)

    md = [f"# Gold (XAUUSD) TJR backtest — £{ACCOUNT_GBP:.0f} account, 0.01 lots, max {MAX_RISK_PCT}% risk (stop ≤ ${STOP_CAP})", "",
          f"Feed: **{main_feed}**, {summary['first']} → {summary['last']}. In-sample before {summary['oos_start']}, "
          f"out-of-sample after. {len(results)} setting combinations. Spread ${COST} per trade included. "
          "A candle that hits both stop and target counts as a loss.", ""]
    for title, r in (("Best expectancy (picked on in-sample)", pick_exp), ("Highest win rate that still makes money (picked on in-sample)", pick_wr)):
        if not r:
            continue
        md += [f"## {title}", f"`{r['label']}`", "",
               "| period | trades | win % | avg R | total R | profit factor | max drawdown R | worst losing streak |",
               "|---|---|---|---|---|---|---|---|"]
        for nm in ("ins", "oos", "all"):
            s = r[nm]
            md.append(f"| {dict(ins='in-sample', oos='**out-of-sample**', all='all')[nm]} | {s['n']} | {s['win_rate']} | {s['avg_r']} | {s['total_r']} | {s['pf']} | {s['max_dd_r']} | {s['max_losing_streak']} |")
        m, mo = r["money_all"], r["money_oos"]
        md.append("")
        md.append(f"On £{ACCOUNT_GBP:.0f} at 0.01 lots: all-period P&L **£{m['pnl_gbp']}** (end £{m['end_balance']}), "
                  f"out-of-sample P&L **£{mo['pnl_gbp']}**, average risk £{m['avg_risk_gbp']} per trade, "
                  f"largest risk {m['max_risk_pct']}% of £{ACCOUNT_GBP:.0f}, worst drawdown £{m['max_dd_gbp']}.")
        md.append("")
        md.append("| year | trades | win % | avg R | total R | profit factor | max drawdown R | worst losing streak |")
        md.append("|---|---|---|---|---|---|---|---|")
        for yr, s in r["years"].items():
            md.append(f"| {yr} | {s['n']} | {s['win_rate']} | {s['avg_r']} | {s['total_r']} | {s['pf']} | {s['max_dd_r']} | {s['max_losing_streak']} |")
        md.append("")
    if cross:
        md += ["## Cross-check on Yahoo futures feed (last 60 days)", ""]
        for k, s in cross.items():
            md.append(f"- {k}: {s['n']} trades, win {s['win_rate']}%, avg {s['avg_r']}R")
        md.append("")
    md += ["## All combinations (sorted by out-of-sample avg R)", "",
           "| settings | IS n | IS win % | IS avg R | OOS n | OOS win % | OOS avg R | all total R |", "|---|---|---|---|---|---|---|---|"]
    for r in sorted(results, key=lambda r: -(r["oos"]["avg_r"] if r["oos"]["avg_r"] is not None else -9)):
        i, o = r["ins"], r["oos"]
        md.append(f"| {r['label']} | {i['n']} | {i['win_rate']} | {i['avg_r']} | {o['n']} | {o['win_rate']} | {o['avg_r']} | {r['all']['total_r']} |")
    (out / "backtest.md").write_text("\n".join(md))
    print("\n".join(md[:40]))
    print(f"done in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
