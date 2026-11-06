"""
Gold strategy shoot-out: Andrea Unger's published gold systems vs TJR, on years of 5m gold.

- every strategy x setting x account size (£200 / £500 / £1000, 0.01 lots, max 2% risk)
- settings PICKED on in-sample years only (before OOS_START), then judged on the years they never saw
- entries at the close of the signal candle (what a Telegram alert lets you do), spread included,
  a candle that hits stop and target counts as a loss, no look-ahead
Writes reports/backtest.md, reports/backtest.json, reports/summary.json
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from tjr import ET, INSTRUMENTS, Context, simulate  # noqa: E402
from strategies import GRIDS, STRATEGIES  # noqa: E402
from data import yahoo  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
HIST = ROOT / "data" / "hist" / "xauusd_m5.csv"
OOS_START = pd.Timestamp(os.getenv("OOS_START", "2025-01-01"), tz=ET)
COST = INSTRUMENTS["XAUUSD"]["cost"]
GBPUSD, LOT_OZ, RISK_PCT = 1.30, 1.0, 2.0
ACCOUNTS = [int(x) for x in os.getenv("ACCOUNTS", "200,1000,2000").split(",")]


def cap_for(acct):
    return round(acct * RISK_PCT / 100 * GBPUSD / LOT_OZ, 2)


def load_hist():
    if not HIST.exists():
        return None, None
    df = pd.read_csv(HIST)
    df.index = pd.DatetimeIndex(pd.to_datetime(df[df.columns[0]], unit="ms", utc=True)).tz_convert(ET)
    df = df[["open", "high", "low", "close"]].astype(float).dropna()
    src = (HIST.parent / "source.txt").read_text().strip() if (HIST.parent / "source.txt").exists() else "history"
    return df[~df.index.duplicated()].sort_index(), src


def stats(t: pd.DataFrame, acct: float) -> dict:
    if t is None or not len(t):
        return dict(n=0, win_rate=None, avg_r=None, total_r=0.0, pf=None, max_dd_r=0.0, streak=0,
                    pnl_gbp=0.0, max_dd_gbp=0.0, per_month=0.0, avg_risk_pct=None)
    r = t["r"].values
    wins, losses = r[r > 0], r[r <= 0]
    eq = np.concatenate([[0], np.cumsum(r)])
    sign = np.where(t["side"] == "BUY", 1, -1)
    pnl = ((t["exit_price"] - t["entry"]) * sign - COST) * LOT_OZ / GBPUSD
    risk = ((t["entry"] - t["stop"]).abs() + COST) * LOT_OZ / GBPUSD
    eqg = acct + np.concatenate([[0], np.cumsum(pnl.values)])
    streak = best = 0
    for x in r:
        streak = streak + 1 if x <= 0 else 0; best = max(best, streak)
    months = max(1.0, (t["confirm_time"].max() - t["confirm_time"].min()).days / 30.4)
    return dict(n=int(len(r)), win_rate=round(100 * len(wins) / len(r), 1), avg_r=round(float(r.mean()), 3),
                total_r=round(float(r.sum()), 1), pf=round(float(wins.sum() / -losses.sum()), 2) if losses.sum() < 0 else None,
                max_dd_r=round(float((np.maximum.accumulate(eq) - eq).max()), 1), streak=int(best),
                pnl_gbp=round(float(pnl.sum()), 2), max_dd_gbp=round(float((np.maximum.accumulate(eqg) - eqg).max()), 2),
                per_month=round(len(r) / months, 1), avg_risk_pct=round(float(risk.mean() / acct * 100), 2))


def run(ctx, name, params, cap):
    rows = []
    for s in STRATEGIES[name](ctx, cap=cap, **params):
        s = simulate(s, ctx.df, COST)
        if s.status in ("win", "loss"):
            d = s.to_dict(); d["notes"] = ";".join(d["notes"]); rows.append(d)
    t = pd.DataFrame(rows)
    if len(t):
        t["confirm_time"] = pd.to_datetime(t["confirm_time"], utc=True).dt.tz_convert(ET)
        t = t.sort_values("confirm_time")
    return t


def main():
    t0 = time.time()
    hist, src = load_hist()
    if hist is None:
        hist, src = yahoo("GC=F", "5m", "60d"), "yahoo_futures_60d"
    print(f"{src}: {len(hist):,} bars {hist.index[0]} -> {hist.index[-1]}", flush=True)
    ctx = Context(hist, "XAUUSD")
    print(f"prepared in {time.time() - t0:.0f}s", flush=True)
    only = os.getenv("STRATS", "").split(",") if os.getenv("STRATS") else list(GRIDS)

    results, cache = [], {}
    for name in only:
        for params in GRIDS[name]:
            for acct in ACCOUNTS:
                cap = cap_for(acct)
                key = (name, json.dumps(params, sort_keys=True), cap)
                if name in ("pdbreak", "compress", "cci") and params["sl_usd"] + COST > cap:
                    continue
                t = run(ctx, name, params, cap)
                ins = t[t.confirm_time < OOS_START] if len(t) else t
                oos = t[t.confirm_time >= OOS_START] if len(t) else t
                years = {str(y): stats(g, acct) for y, g in t.groupby(t.confirm_time.dt.year)} if len(t) else {}
                res = dict(strategy=name, params=params, account=acct, cap=cap,
                           all=stats(t, acct), ins=stats(ins, acct), oos=stats(oos, acct), years=years)
                results.append(res)
                a, o = res["all"], res["oos"]
                print(f"{name:9s} £{acct:<5} {json.dumps(params):95s} n={a['n']:4d} wr={a['win_rate']} avgR={a['avg_r']} | "
                      f"OOS n={o['n']} wr={o['win_rate']} avgR={o['avg_r']} £{o['pnl_gbp']}", flush=True)

    picks = {}
    for acct in ACCOUNTS:
        el = [r for r in results if r["account"] == acct and r["ins"]["n"] >= 40 and (r["ins"]["avg_r"] or -9) > 0]
        if el:
            best = max(el, key=lambda r: r["ins"]["avg_r"] * min(1.0, r["ins"]["n"] / 150))
            picks[str(acct)] = best
        # best per strategy too
        for name in only:
            e2 = [r for r in results if r["account"] == acct and r["strategy"] == name and r["ins"]["n"] >= 40]
            if e2:
                picks[f"{acct}_{name}"] = max(e2, key=lambda r: (r["ins"]["avg_r"] or -9) * min(1.0, r["ins"]["n"] / 150))

    # PORTFOLIO: every strategy whose pick made money in-sample, all running together
    port = {}
    for acct in ACCOUNTS:
        legs = [picks.get(f"{acct}_{n}") for n in only]
        legs = [r for r in legs if r and (r["ins"]["avg_r"] or -9) > 0]
        if not legs:
            continue
        ts = [run(ctx, r["strategy"], r["params"], r["cap"]) for r in legs]
        ts = [t for t in ts if len(t)]
        if not ts:
            continue
        t = pd.concat(ts).sort_values("confirm_time")
        ins, oos = t[t.confirm_time < OOS_START], t[t.confirm_time >= OOS_START]
        days = t.confirm_time.dt.date.nunique()
        tdays = pd.bdate_range(t.confirm_time.min().date(), t.confirm_time.max().date()).size
        monthly = t.groupby(t.confirm_time.dt.to_period("M"))["r"].sum()
        port[str(acct)] = dict(legs=[dict(strategy=r["strategy"], params=r["params"]) for r in legs],
                               all=stats(t, acct), ins=stats(ins, acct), oos=stats(oos, acct),
                               years={str(y): stats(g, acct) for y, g in t.groupby(t.confirm_time.dt.year)},
                               days_with_trade_pct=round(100 * days / max(1, tdays), 1),
                               per_day=round(len(t) / max(1, tdays), 2),
                               green_months_pct=round(100 * (monthly > 0).mean(), 1))

    summary = dict(portfolio=port, generated=pd.Timestamp.now(tz="UTC").isoformat(), feed=src, first=str(hist.index[0].date()),
                   last=str(hist.index[-1].date()), oos_start=str(OOS_START.date()), combos=len(results),
                   picks=picks, runtime_s=round(time.time() - t0))
    out = ROOT / "reports"; out.mkdir(exist_ok=True)
    (out / "summary.json").write_text(json.dumps(summary, indent=1, default=str))
    (out / "backtest.json").write_text(json.dumps(results, indent=1, default=str))

    md = ["# Gold strategy shoot-out: Andrea Unger's gold systems vs TJR", "",
          f"Data: **{src}** 5m, {summary['first']} → {summary['last']}. Settings picked on data before {summary['oos_start']}, "
          f"judged on data after it. 0.01 lots, max {RISK_PCT:g}% risk, spread ${COST} per trade, entries at signal-candle close, UK hours 07–20.", ""]
    for acct in ACCOUNTS:
        md += [f"## £{acct} account (stop ≤ ${cap_for(acct)})", "",
               "| strategy | settings | IS trades | IS win % | IS avg R | **OOS trades** | **OOS win %** | **OOS avg R** | OOS PF | OOS £ | trades/mo | worst streak |",
               "|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for name in only:
            r = picks.get(f"{acct}_{name}")
            if not r:
                md.append(f"| {name} | — not enough trades within this risk limit | | | | | | | | | | |"); continue
            i, o = r["ins"], r["oos"]
            md.append(f"| {name} | `{json.dumps(r['params'])}` | {i['n']} | {i['win_rate']} | {i['avg_r']} | {o['n']} | {o['win_rate']} | {o['avg_r']} | {o['pf']} | £{o['pnl_gbp']} | {r['all']['per_month']} | {r['all']['streak']} |")
        b = picks.get(str(acct))
        md += ["", f"**Pick for £{acct}:** " + (f"{b['strategy']} `{json.dumps(b['params'])}`" if b else "nothing profitable in-sample"), ""]
    for acct, pr in port.items():
        a, i, o = pr["all"], pr["ins"], pr["oos"]
        md += [f"## Portfolio £{acct}: " + " + ".join(l["strategy"] for l in pr["legs"]), "",
               f"- {a['n']} trades, {pr['per_day']} per trading day, a trade on {pr['days_with_trade_pct']}% of days",
               f"- win {a['win_rate']}% · PF {a['pf']} · avg {a['avg_r']}R · £{a['pnl_gbp']} · max DD £{a['max_dd_gbp']} · worst streak {a['streak']} · green months {pr['green_months_pct']}%",
               f"- in-sample avg {i['avg_r']}R ({i['n']}) · out-of-sample avg {o['avg_r']}R ({o['n']}), win {o['win_rate']}%, PF {o['pf']}, £{o['pnl_gbp']}",
               "- years: " + " · ".join(f"{y} {s_['avg_r']:+.2f}R/{s_['n']}" for y, s_ in pr["years"].items()), ""]
    (out / "backtest.md").write_text("\n".join(md))
    print("\n".join(md))
    print(f"done in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
