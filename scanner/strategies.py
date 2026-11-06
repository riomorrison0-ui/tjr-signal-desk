"""
Andrea Unger's published gold systems (Unger Academy, 2025-2026), made mechanical, plus TJR as a benchmark.

Unger only publishes the logic, not his exact parameters, so each system is tested over a small,
sensible grid and judged out-of-sample. Every entry is "market on the close of the signal candle",
which is exactly what a Telegram alert lets you do by hand.

  pdbreak   Breakout of the previous day's high/low, fixed $ stop and target, held up to N days
  compress  Same breakout, only after daily AND weekly volatility compression, 15m closes, out by session end
  channel   5m price-channel breakout (highest high / lowest low of N candles) with trend + candle filters
  cci       CCI(20) on 1H beyond +/-300 = ride the explosive move, out when CCI returns to 0 (backtest only)

All entries are restricted to UK waking hours (07:00-20:00 UK) because signals are taken by hand.
"""
from __future__ import annotations

from datetime import time, timedelta

import numpy as np
import pandas as pd

from tjr import ET, INSTRUMENTS, Context, Params, Setup, find_setups as tjr_find

UK = "Europe/London"
COST = INSTRUMENTS["XAUUSD"]["cost"]


def _uk_ok(ts: pd.Timestamp, start=7, end=20) -> bool:
    h = ts.tz_convert(UK).hour
    return start <= h < end


def _daily(ctx: Context) -> pd.DataFrame:
    if not hasattr(ctx, "_daily"):
        d = ctx.df.groupby(ctx.day).agg(open=("open", "first"), high=("high", "max"),
                                        low=("low", "min"), close=("close", "last"))
        d["range"] = d["high"] - d["low"]
        d["atr20"] = d["range"].rolling(20).mean().shift(1)          # known before the day starts
        d["prev_range"] = d["range"].shift(1)
        hi5 = d["high"].rolling(5).max(); lo5 = d["low"].rolling(5).min()
        d["wk_range"] = (hi5 - lo5).shift(1)                         # last 5 sessions' range
        d["wk_avg"] = (hi5 - lo5).rolling(20).mean().shift(1)
        d["pdh"], d["pdl"] = d["high"].shift(1), d["low"].shift(1)
        ctx._daily = d
    return ctx._daily


def _mk(ctx, i, side, entry, stop, target, name, why, hold_until=None, extra="") -> Setup:
    idx = ctx.df.index
    t = idx[i] + timedelta(minutes=5)       # signal = candle close
    risk = abs(entry - stop)
    return Setup(id=f"XAUUSD-{name}-{idx[i]:%Y%m%d-%H%M}-{side}", instrument="XAUUSD", side=side,
                 level_name=name, level=round(float(entry), 2), sweep_time=t.isoformat(), confirm_time=t.isoformat(),
                 entry=round(float(entry), 2), stop=round(float(stop), 2), target=round(float(target), 2),
                 rr=round(abs(target - entry) / risk, 2), bias="", killzone=extra, valid_until=t.isoformat(),
                 status="open", fill_time=t.isoformat(), strategy=name, entry_type="market",
                 hold_until=hold_until.isoformat() if hold_until is not None else None, why=why)


def _bracket(side, entry, sl, tp_mult):
    stop = entry - sl if side == "BUY" else entry + sl
    tgt = entry + sl * tp_mult if side == "BUY" else entry - sl * tp_mult
    return stop, tgt


# ------------------------------------------------------------------ Unger 1: previous-day breakout
def pdbreak(ctx: Context, sl_usd=12.0, tp_mult=2.0, hold_days=3, window_end_uk=17, cap=None) -> list[Setup]:
    if cap and sl_usd + COST > cap:
        return []
    d = _daily(ctx)
    c, idx, day = ctx.df["close"].values, ctx.df.index, ctx.day
    out, done = [], set()
    for i in range(1, len(c)):
        dy = day[i]
        if dy in done or not _uk_ok(idx[i], 7, window_end_uk):
            continue
        pdh, pdl = d.at[dy, "pdh"], d.at[dy, "pdl"]
        if np.isnan(pdh):
            continue
        side = "BUY" if c[i] > pdh and c[i - 1] <= pdh else "SELL" if c[i] < pdl and c[i - 1] >= pdl else None
        if not side:
            continue
        stop, tgt = _bracket(side, c[i], sl_usd, tp_mult)
        why = f"5m close {'above previous-day high' if side == 'BUY' else 'below previous-day low'} {pdh if side == 'BUY' else pdl:,.2f}"
        out.append(_mk(ctx, i, side, c[i], stop, tgt, "pdbreak", why, idx[i] + timedelta(days=hold_days)))
        done.add(dy)
    return out


# ------------------------------------------------------------------ Unger 2: compression breakout (15m)
def compress(ctx: Context, sl_usd=10.0, tp_mult=2.0, squeeze=0.8, cap=None) -> list[Setup]:
    if cap and sl_usd + COST > cap:
        return []
    d = _daily(ctx)
    df = ctx.df
    m15 = df.resample("15min", label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    day15 = (m15.index + timedelta(hours=6)).date
    pos = df.index.get_indexer(m15.index + timedelta(minutes=10))   # last 5m bar inside each 15m candle
    out, done = [], set()
    c15 = m15["close"].values
    for q in range(1, len(m15)):
        dy = day15[q]
        if dy in done or dy not in d.index or pos[q] < 0 or not _uk_ok(m15.index[q] + timedelta(minutes=15), 7, 20):
            continue
        r = d.loc[dy]
        if np.isnan(r["atr20"]) or np.isnan(r["wk_avg"]):
            continue
        if not (r["prev_range"] < squeeze * r["atr20"] and r["wk_range"] < squeeze * r["wk_avg"]):
            continue
        side = "BUY" if c15[q] > r["pdh"] and c15[q - 1] <= r["pdh"] else "SELL" if c15[q] < r["pdl"] and c15[q - 1] >= r["pdl"] else None
        if not side:
            continue
        i = pos[q]
        stop, tgt = _bracket(side, c15[q], sl_usd, tp_mult)
        close_t = pd.Timestamp.combine(pd.Timestamp(dy).date(), time(16, 50)).tz_localize(ET)
        why = (f"daily + weekly volatility squeeze, then 15m close {'above' if side == 'BUY' else 'below'} "
               f"previous-day {'high' if side == 'BUY' else 'low'}")
        out.append(_mk(ctx, i, side, c15[q], stop, tgt, "compress", why, close_t))
        done.add(dy)
    return out


# ------------------------------------------------------------------ Unger 3: 5m channel breakout
def channel(ctx: Context, n=96, sl_atr=2.0, tp_mult=2.0, max_per_day=2, cap=None) -> list[Setup]:
    df = ctx.df
    h, l, c, o = (df[k].values for k in ("high", "low", "close", "open"))
    hh = pd.Series(h).rolling(n).max().shift(1).values
    ll = pd.Series(l).rolling(n).min().shift(1).values
    trend = ctx.bias("ema")                    # 1H EMA50 side, closed candles only
    a, idx, day = ctx.atr, df.index, ctx.day
    out, per_day, busy_until = [], {}, None
    for i in range(n + 1, len(c)):
        if busy_until is not None and idx[i] < busy_until:
            continue
        if np.isnan(hh[i]) or np.isnan(a[i]) or not _uk_ok(idx[i], 7, 20):
            continue
        if per_day.get(day[i], 0) >= max_per_day:
            continue
        side = None
        if c[i] > hh[i] and trend[i] == "bull" and (c[i] - o[i]) > 0.5 * a[i]:
            side = "BUY"
        elif c[i] < ll[i] and trend[i] == "bear" and (o[i] - c[i]) > 0.5 * a[i]:
            side = "SELL"
        if not side:
            continue
        sl = sl_atr * a[i]
        if cap and sl + COST > cap:
            continue
        stop, tgt = _bracket(side, c[i], sl, tp_mult)
        why = f"5m close through the {n * 5 // 60}h price channel {'high' if side == 'BUY' else 'low'}, with the 1H trend, strong candle"
        s = _mk(ctx, i, side, c[i], stop, tgt, "channel", why, None)
        out.append(s)
        per_day[day[i]] = per_day.get(day[i], 0) + 1
        busy_until = idx[i] + timedelta(hours=2)   # one idea at a time
    return out


# ------------------------------------------------------------------ Unger 4: CCI +/-300 (backtest only)
def cci(ctx: Context, level=300, sl_usd=15.0, tp_mult=None, cap=None) -> list[Setup]:
    if cap and sl_usd + COST > cap:
        return []
    h1 = ctx.df.resample("1h", label="right", closed="left").agg(
        {"high": "max", "low": "min", "close": "last"}).dropna()
    tp = (h1["high"] + h1["low"] + h1["close"]) / 3
    ma = tp.rolling(20).mean()
    md = tp.rolling(20).apply(lambda x: np.mean(np.abs(x - x.mean())), raw=True)
    cc = ((tp - ma) / (0.015 * md)).values
    out = []
    t1 = h1.index
    i5 = ctx.df.index.get_indexer(t1 - timedelta(minutes=5))
    k = 21
    while k < len(cc):
        side = "BUY" if cc[k] > level and cc[k - 1] <= level else "SELL" if cc[k] < -level and cc[k - 1] >= -level else None
        if not side or i5[k] < 0 or not _uk_ok(t1[k], 7, 20):
            k += 1; continue
        e = k + 1
        while e < len(cc) and ((side == "BUY" and cc[e] > 0) or (side == "SELL" and cc[e] < 0)):
            e += 1
        # momentum exit = first 1H close where CCI is back through 0. Not happened yet (live) -> open-ended.
        exit_t = t1[e] if e < len(cc) else t1[k] + timedelta(days=30)
        entry = h1["close"].values[k]
        stop, tgt = _bracket(side, entry, sl_usd, tp_mult or 50)
        why = (f"1H CCI(20) broke {'above +' if side == 'BUY' else 'below -'}{level}: explosive momentum, ride it")
        out.append(_mk(ctx, i5[k], side, entry, stop, tgt, "cci", why, exit_t))
        k = e
    return out


def tjr(ctx: Context, cap=None, **kw) -> list[Setup]:
    p = Params(**kw); p.max_stop_usd = cap
    return tjr_find(ctx.df, "XAUUSD", p, ctx)


STRATEGIES = dict(pdbreak=pdbreak, compress=compress, channel=channel, cci=cci, tjr=tjr)

GRIDS = dict(
    pdbreak=[dict(sl_usd=s, tp_mult=t, hold_days=h, window_end_uk=w)
             for s in (5, 8, 12, 20) for t in (1.5, 2.0, 3.0) for h in (1, 3) for w in (12, 17)],
    compress=[dict(sl_usd=s, tp_mult=t, squeeze=q) for s in (5, 8, 12, 20) for t in (1.5, 2.0, 3.0) for q in (0.7, 0.9)],
    channel=[dict(n=n, sl_atr=a, tp_mult=t) for n in (48, 96, 192) for a in (1.0, 2.0) for t in (1.5, 2.0, 3.0)],
    cci=[dict(level=lv, sl_usd=s, tp_mult=t) for lv in (250, 300, 350) for s in (8, 12, 15, 20, 25) for t in (None, 1.5, 2.0, 3.0)],
    tjr=[dict(entry=e, target=t, bias=b, m15=m, accept_atr=1.5, confirm_bars=24, zones="both")
         for e in ("fvg", "market") for t in ("1.5R", "2R") for b in ("htf", "none") for m in (True, False)],
)
