"""Telegram message builders: price, market map (4H/1H/15m/5m), news, status, test trade."""
from __future__ import annotations

import html

import numpy as np
import pandas as pd

from tjr import Context, KILLZONES, hourly_bias

UK = "Europe/London"


def uk(t) -> str:
    return pd.Timestamp(t).tz_convert(UK).strftime("%a %H:%M")


def esc(x) -> str:
    return html.escape(str(x))


def market_map(df: pd.DataFrame) -> dict:
    ctx = Context(df, "XAUUSD")
    i = len(ctx.df) - 1
    lv = {k: (None if np.isnan(v[i]) else round(float(v[i]), 2)) for k, v in ctx.lv.items()}
    b = {m: ctx.bias(m)[i] for m in ("structure4h", "structure", "htf")}
    b["15m"] = hourly_bias(ctx.df, "structure15m").values[i]
    last = ctx.df.iloc[-1]
    return dict(price=round(float(last["close"]), 2), time=ctx.df.index[-1], levels=lv, bias=b,
                atr5=round(float(ctx.atr[i]), 2))


def price_msg(m: dict, feed: str) -> str:
    return (f"💰 <b>XAUUSD {m['price']:,.2f}</b>\n"
            f"Last 5m close {uk(m['time'])} UK · {esc(feed)}\n"
            f"5m ATR ${m['atr5']:.2f}")


def map_msg(m: dict) -> str:
    L, p = m["levels"], m["price"]
    def row(name, key):
        v = L.get(key)
        if v is None:
            return f"{name}: —"
        d = v - p
        broken = (key.endswith("_L") or key == "PDL") and v > p or (key.endswith("_H") or key == "PDH") and v < p
        return f"{name}: <b>{v:,.2f}</b>  ({'+' if d >= 0 else ''}{d:,.2f}){' · taken' if broken else ''}"
    em = {"bull": "🟢 bullish", "bear": "🔴 bearish", "neutral": "⚪ neutral"}
    return ("🗺 <b>Market map</b> (price {:,.2f})\n".format(p) +
            "\n<b>4H</b>  bias " + em.get(m["bias"]["structure4h"], "?") + "\n" + row("Swing high", "H4_H") + "\n" + row("Swing low", "H4_L") +
            "\n\n<b>1H</b>  bias " + em.get(m["bias"]["structure"], "?") + "\n" + row("Swing high", "H1_H") + "\n" + row("Swing low", "H1_L") +
            "\n\n<b>Daily / sessions</b>\n" + row("Prev day high", "PDH") + "\n" + row("Prev day low", "PDL") + "\n" +
            row("Asia high", "Asia_H") + "\n" + row("Asia low", "Asia_L") + "\n" + row("London high", "London_H") + "\n" + row("London low", "London_L") +
            f"\n\n<b>15m</b> structure {em.get(m['bias']['15m'], '?')}\n"
            f"<b>4H + 1H together:</b> {'bullish' if m['bias']['htf'] == 'bull' else 'bearish' if m['bias']['htf'] == 'bear' else 'not aligned (choppy)'}")


def news_msg(n: dict, now: pd.Timestamp) -> str:
    out = ["📰 <b>News check</b>"]
    if n.get("ok_calendar"):
        if n.get("blackout"):
            e = n["blackout"]
            out.append(f"⛔ <b>NEWS BLACKOUT</b>: {esc(e['title'])} at {uk(e['time'])} UK. No new trades ±30 min.")
        else:
            out.append("✅ No high-impact USD news in the next 30 min.")
        if n.get("next"):
            out.append("\n<b>Next red-folder USD events</b>")
            for e in n["next"]:
                fc = f" (f'cast {esc(e['forecast'])})" if e.get("forecast") else ""
                out.append(f"• {uk(e['time'])} UK — {esc(e['title'])}{fc}")
        else:
            out.append("No more high-impact USD events this week.")
    else:
        out.append("⚠️ Calendar feed unreachable this run (" + esc(n.get("calendar_error", "?"))[:80] + ")")
    r = n.get("risk", {})
    lvl = {"normal": "🟢 normal", "elevated": "🟠 elevated", "high": "🔴 HIGH", "unknown": "⚪ unknown"}.get(r.get("level"), "?")
    out.append(f"\n<b>Headline risk (wars, strikes, sanctions, shocks):</b> {lvl}")
    for t in r.get("examples", []):
        out.append(f"• {esc(t)[:140]}")
    for key, title in (("gold", "Gold"), ("fed", "Fed / dollar"), ("world", "World")):
        items = n.get("headlines", {}).get(key, [])[:2]
        if items:
            out.append(f"\n<b>{title}</b>")
            for it in items:
                out.append(f"• {esc(it['title'])[:140]}")
    return "\n".join(out)


def test_trade_msg(m: dict, account: float, fx: float, cost: float, stop_cap: float) -> str:
    p = m["price"]
    sl = min(round(stop_cap - cost - 0.5, 2), 12.0)
    entry, stop, tp = p, round(p - sl, 2), round(p + 2 * sl, 2)
    risk_gbp = (sl + cost) / fx
    rew_gbp = (2 * sl - cost) / fx
    now = pd.Timestamp.now(tz=UK)
    return ("🧪 <b>TEST — NOT A TRADE. DO NOT TAKE.</b>\nThis is exactly how a real call will look:\n\n"
            "<b>🟢 BUY XAUUSD</b>  (Gold) · Unger previous-day breakout\n"
            f"MARKET entry <b>{entry:,.2f}</b>  — now (last price {p:,.2f})\n"
            f"Stop loss <b>{stop:,.2f}</b>  (${sl:.2f})\n"
            f"Take profit <b>{tp:,.2f}</b>  (${2 * sl:.2f}, 2.0R)\n\n"
            f"<b>0.01 lots</b> · risk ≈ £{risk_gbp:.2f} ({risk_gbp / account * 100:.1f}% of £{account:.0f}) · profit ≈ £{rew_gbp:.2f}\n\n"
            "Why: 5m close above previous-day high\n"
            "News: ✅ no red folder within 30 min · next red folder: CPI Wed 13:30 UK\n"
            "Headline risk: 🟢 normal\n"
            f"Signal {now:%H:%M} UK (candle close) · Hold up to 3 days if neither is hit\n"
            f"\nEvery call has one entry, one stop loss, one take profit. Anything needing a stop wider than ${stop_cap:.2f} (2% of £{account:.0f}) is skipped.\n#test")


def status_msg(account, max_risk, stop_cap, params_label, last_scan, open_n, closed_stats, strategy="") -> str:
    wr = closed_stats.get("win_rate")
    return ("✅ <b>Gold Desk — running on its own</b>\n"
            f"• Strategy: <b>{esc(strategy)}</b>\n"
            "• Checks gold at <b>every 5-minute candle close</b> (about 20 seconds after it closes), 24 hours a day, Sunday 23:00 → Friday 22:00 UK. Gold is shut at weekends.\n"
            "• Price: real-time feed matched to live spot gold, so levels line up with MT5.\n"
            "• Charts: 4H and 1H swing highs and lows, previous-day high and low, Asia and London ranges, 15m and 5m candles.\n"
            "• News: USD red-folder calendar (no new trades ±30 min around 🔴) plus gold, Fed and war/world headlines, refreshed every 15 min.\n"
            "• Calls only between 07:00 and 20:00 UK so you can act on them.\n"
            f"• Risk: 0.01 lots, max {max_risk:g}% of £{account:.0f}, so the stop must be ≤ ${stop_cap:.2f}, otherwise the setup is skipped.\n"
            "• Every day, Mon–Fri: 06:45 London brief · 08:30 news folders · 13:15 New York brief\n"
            "• <b>You never need to prompt it.</b> It restarts itself every few hours, and a backup timer restarts it if anything breaks.\n"
            "• Optional commands: /price /levels /folders /news /status\n"
            f"\nLast check {uk(last_scan)} UK · open calls {open_n} · closed {closed_stats.get('trades', 0)}"
            + (f" · win rate {wr}%" if wr is not None else "") + f"\n<code>{esc(params_label)}</code>")
