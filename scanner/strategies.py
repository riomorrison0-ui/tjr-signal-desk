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


# ================================================================== DAILY SESSION STRATEGIES
# Independent tests (2026): most daily gold setups lose after costs. These three published ones held up:
#   london   London range breakout (MQL5 blog, Oct 2026: 715 trades, ~49% win, PF 1.38, DD 17%)
#   orb      15-minute opening-range breakout, target 3R (Aurum: 2,003 trades, PF 1.77, walk-forward)
#   ibretr   Initial Balance retracement (Trade That Swing: ~70% win rate)

def _uk(ctx):
    if not hasattr(ctx, "_ukt"):
        u = ctx.df.index.tz_convert(UK)
        ctx._ukt = (np.array(u.hour * 60 + u.minute), np.array(u.date))
    return ctx._ukt


def _day_slices(ctx):
    """start/end positions of each UK calendar day."""
    if not hasattr(ctx, "_ukdays"):
        mins, dates = _uk(ctx)
        cuts = np.flatnonzero(np.r_[True, dates[1:] != dates[:-1], True])
        ctx._ukdays = [(cuts[k], cuts[k + 1]) for k in range(len(cuts) - 1)]
    return ctx._ukdays


def _at(ctx, i, hhmm):
    """Timestamp of the same UK day at hh:mm."""
    t = ctx.df.index[i].tz_convert(UK)
    return pd.Timestamp.combine(t.date(), time(hhmm // 100, hhmm % 100)).tz_localize(UK).tz_convert(ET)


def london(ctx: Context, stop="range", tp_mult=1.0, lo=0.5, hi=1.5, end_uk=1100, cap=None) -> list[Setup]:
    """Asian range 00:00-07:00 UK. First 5m close outside it between 07:00 and end_uk -> trade the break.
    Stop: opposite side of the range ('range') or the range midpoint ('mid'). Out by 16:00 UK."""
    df = ctx.df
    h, l, c = df["high"].values, df["low"].values, df["close"].values
    mins, _ = _uk(ctx)
    out, widths = [], []
    for a, b in _day_slices(ctx):
        m = mins[a:b]
        asia = np.flatnonzero(m < 7 * 60)
        if len(asia) < 60:
            continue
        rh, rl = h[a + asia].max(), l[a + asia].min()
        w = rh - rl
        avg = np.mean(widths[-20:]) if len(widths) >= 10 else None
        widths.append(w)
        if avg is None or not (lo * avg <= w <= hi * avg):
            continue
        end = end_uk // 100 * 60 + end_uk % 100
        for q in range(a, b):
            if not (7 * 60 <= mins[q] < end):
                continue
            side = "BUY" if c[q] > rh else "SELL" if c[q] < rl else None
            if not side:
                continue
            e = c[q]
            st = (rl if side == "BUY" else rh) if stop == "range" else (rl + rh) / 2
            risk = abs(e - st)
            if risk <= 0 or (cap and risk + COST > cap):
                break
            tgt = e + tp_mult * risk if side == "BUY" else e - tp_mult * risk
            why = f"London broke the Asian range ({rl:,.2f}–{rh:,.2f}, ${w:.0f} wide) to the {'upside' if side == 'BUY' else 'downside'}"
            out.append(_mk(ctx, q, side, e, st, tgt, "london", why, _at(ctx, q, 1600)))
            break
    return out


def orb(ctx: Context, open_uk=1430, minutes=15, stop="range", tp_mult=3.0, cap=None) -> list[Setup]:
    """Opening range of the first `minutes` after open_uk (14:30 UK = NY stock open, 13:30 = US data).
    First 5m close outside it within 2h -> trade the break. Out by 20:00 UK."""
    df = ctx.df
    h, l, c = df["high"].values, df["low"].values, df["close"].values
    mins, _ = _uk(ctx)
    o = open_uk // 100 * 60 + open_uk % 100
    out = []
    for a, b in _day_slices(ctx):
        m = mins[a:b]
        rng = np.flatnonzero((m >= o) & (m < o + minutes))
        if len(rng) < minutes // 5:
            continue
        rh, rl = h[a + rng].max(), l[a + rng].min()
        for q in range(a + rng[-1] + 1, b):
            if mins[q] >= o + 120:
                break
            side = "BUY" if c[q] > rh else "SELL" if c[q] < rl else None
            if not side:
                continue
            e = c[q]
            st = (rl if side == "BUY" else rh) if stop == "range" else (rl + rh) / 2
            risk = abs(e - st)
            if risk <= 0 or (cap and risk + COST > cap):
                break
            tgt = e + tp_mult * risk if side == "BUY" else e - tp_mult * risk
            why = f"5m close {'above' if side == 'BUY' else 'below'} the {minutes}-min opening range ({rl:,.2f}–{rh:,.2f}) from {open_uk // 100:02d}:{open_uk % 100:02d} UK"
            out.append(_mk(ctx, q, side, e, st, tgt, "orb", why, _at(ctx, q, 2000)))
            break
    return out


def ibretr(ctx: Context, open_uk=1430, entry_in=0.25, tgt_out=0.5, stop_in=0.6, cap=None) -> list[Setup]:
    """Initial Balance = first hour after open_uk. After a 5m close beyond it, LIMIT entry entry_in x IB back
    inside, target tgt_out x IB beyond the IB edge, stop stop_in x IB inside. Out by 20:00 UK."""
    df = ctx.df
    h, l, c = df["high"].values, df["low"].values, df["close"].values
    mins, _ = _uk(ctx)
    o = open_uk // 100 * 60 + open_uk % 100
    out = []
    for a, b in _day_slices(ctx):
        m = mins[a:b]
        ib = np.flatnonzero((m >= o) & (m < o + 60))
        if len(ib) < 10:
            continue
        hi_, lo_ = h[a + ib].max(), l[a + ib].min()
        w = hi_ - lo_
        if w <= 0:
            continue
        for q in range(a + ib[-1] + 1, b):
            if mins[q] >= o + 240:
                break
            side = "BUY" if c[q] > hi_ else "SELL" if c[q] < lo_ else None
            if not side:
                continue
            if side == "BUY":
                e, st, tgt = hi_ - entry_in * w, hi_ - stop_in * w, hi_ + tgt_out * w
            else:
                e, st, tgt = lo_ + entry_in * w, lo_ + stop_in * w, lo_ - tgt_out * w
            risk = abs(e - st)
            if cap and risk + COST > cap:
                break
            s = _mk(ctx, q, side, e, st, tgt, "ibretr",
                    f"New York broke its first-hour range ({lo_:,.2f}–{hi_:,.2f}); buying the pullback into it" if side == "BUY"
                    else f"New York broke its first-hour range ({lo_:,.2f}–{hi_:,.2f}); selling the pullback into it",
                    _at(ctx, q, 2000))
            s.entry_type, s.status, s.fill_time = "limit", "pending", None
            s.valid_until = _at(ctx, q, 1900).isoformat()
            out.append(s)
            break
    return out


STRATEGIES.update(london=london, orb=orb, ibretr=ibretr)
GRIDS.update(
    london=[dict(stop=s, tp_mult=t, lo=lo, hi=hi, end_uk=e) for s in ("range", "mid") for t in (0.75, 1.0, 1.5, 2.0)
            for lo, hi in ((0.5, 1.5), (0.0, 9.0)) for e in (1100, 1300)],
    orb=[dict(open_uk=o, minutes=mn, stop=s, tp_mult=t) for o in (1330, 1430, 800) for mn in (15, 30)
         for s in ("range", "mid") for t in (1.0, 2.0, 3.0)],
    ibretr=[dict(open_uk=o, entry_in=e, tgt_out=g, stop_in=s) for o in (1430, 800) for e in (0.1, 0.25)
            for g in (0.3, 0.5) for s in (0.6, 1.0)],
)
