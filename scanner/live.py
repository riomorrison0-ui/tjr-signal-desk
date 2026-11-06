"""
Live scanner. Runs every 5 minutes on GitHub Actions.

- fetches the latest closed 5m candles for every instrument
- runs the TJR model; any setup confirmed in the last 45 min that we haven't sent -> NEW SIGNAL
- re-checks every pending/open signal -> FILLED / TP HIT / STOPPED / EXPIRED updates
- keeps the paper account (data/state.json) and the dashboard feed (docs/signals.json)
"""
from __future__ import annotations

import json
import os
import sys
from datetime import timedelta
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, os.path.dirname(__file__))
from tjr import ET, INSTRUMENTS, Params, Setup, find_setups, simulate  # noqa: E402
from data import gold_live  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "data" / "state.json"
FEED = ROOT / "docs" / "signals.json"
CONFIG = ROOT / "config.json"

LOT = 0.01                 # fixed lot size
LOT_OZ = 1.0               # 0.01 lot XAUUSD = 1 oz -> $1 per $1 move


def load_json(p: Path, default):
    try:
        return json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        return default


_CHAT = {}


def chat_id(state) -> str | None:
    """Use TELEGRAM_CHAT_ID if set, else learn it from whoever pressed Start on the bot."""
    if os.getenv("TELEGRAM_CHAT_ID"):
        return os.getenv("TELEGRAM_CHAT_ID")
    if state.get("tg_chat"):
        return state["tg_chat"]
    tok = os.getenv("TELEGRAM_BOT_TOKEN")
    if not tok:
        return None
    try:
        ups = requests.get(f"https://api.telegram.org/bot{tok}/getUpdates", timeout=15).json().get("result", [])
        for u in reversed(ups):
            m = u.get("message") or u.get("my_chat_member") or {}
            cid = (m.get("chat") or {}).get("id")
            if cid:
                state["tg_chat"] = str(cid)
                return state["tg_chat"]
    except Exception as e:  # noqa: BLE001
        print("getUpdates failed", e)
    return None


def tg(text: str):
    tok, chat = os.getenv("TELEGRAM_BOT_TOKEN"), _CHAT.get("id")
    print("TG>", text.replace("\n", " | "))
    if not tok or not chat:
        return
    try:
        requests.post(f"https://api.telegram.org/bot{tok}/sendMessage",
                      json={"chat_id": chat, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True},
                      timeout=15)
    except Exception as e:  # noqa: BLE001
        print("telegram failed", e)


def fmt(x, dp):
    return f"{x:,.{dp}f}"


def unit(inst, d):
    if inst in ("EURUSD", "GBPUSD"):
        return f"{d * 10000:.1f} pips"
    if inst == "XAUUSD":
        return f"${d:.2f}"
    return f"{d:.1f} pts"


def signal_msg(s: dict, last: float) -> str:
    cfg = INSTRUMENTS[s["instrument"]]
    dp = cfg["dp"]
    arrow = "🟢 BUY" if s["side"] == "BUY" else "🔴 SELL"
    risk = abs(s["entry"] - s["stop"])
    rew = abs(s["target"] - s["entry"])
    t = pd.Timestamp(s["confirm_time"]).tz_convert("Europe/London").strftime("%H:%M")
    vu = pd.Timestamp(s["valid_until"]).tz_convert("Europe/London").strftime("%H:%M")
    gap = s["entry"] - last
    where = "at market" if abs(gap) < 1e-9 else (f"{unit(s['instrument'], abs(gap))} {'below' if gap < 0 else 'above'} current price")
    kind = "LIMIT" if s["status"] == "pending" else "MARKET"
    fx = s.get("gbpusd", 1.30)
    risk_gbp = (risk + cfg["cost"]) * LOT_OZ / fx
    rew_gbp = (rew - cfg["cost"]) * LOT_OZ / fx
    acct = s.get("account_gbp", 200)
    money = f"\n<b>0.01 lots</b> · risk ≈ £{risk_gbp:.2f} ({risk_gbp / acct * 100:.1f}% of £{acct:.0f}) · profit ≈ £{rew_gbp:.2f}\n"
    return (
        f"<b>{arrow} {s['instrument']}</b>  ({cfg['name']})\n"
        f"{kind} entry <b>{fmt(s['entry'], dp)}</b>  — {where}\n"
        f"Stop <b>{fmt(s['stop'], dp)}</b>  ({unit(s['instrument'], risk)} risk)\n"
        f"Take profit <b>{fmt(s['target'], dp)}</b>  ({unit(s['instrument'], rew)}, {s['rr']}R)\n"
        + money +
        f"\nWhy: {s['level_name'].replace('_', ' ')} swept → 5m break of structure"
        f"{' → FVG retrace' if kind == 'LIMIT' else ''}. 1H bias {s['bias']}. {s['killzone'].upper()} killzone.\n"
        f"Signal {t} UK" + (f" · limit valid until {vu} UK" if kind == "LIMIT" else "") +
        ("\n<i>Levels are on COMEX futures (a few $ above spot) — on MT5 place it using the distances.</i>" if "futures" in s.get("feed", "") else "")
        + "\n#paper"
    )


def update_msg(s: dict) -> str:
    dp = INSTRUMENTS[s["instrument"]]["dp"]
    head = f"{s['side']} {s['instrument']} @ {fmt(s['entry'], dp)}"
    if s["status"] == "open":
        return f"✅ FILLED — {head}. Stop {fmt(s['stop'], dp)}, target {fmt(s['target'], dp)}."
    if s["status"] == "win":
        g = pnl_gbp(s)
        return f"💰 TAKE PROFIT HIT — {head} → {fmt(s['exit_price'], dp)}  (+£{g:.2f}, +{s['r']}R)" if s["r"] > 0 else f"➖ CLOSED AT END OF DAY — {head} (£{g:.2f})"
    if s["status"] == "loss":
        g = pnl_gbp(s)
        closed_eod = any("end of day" in n for n in s.get("notes", []))
        return f"{'➖ CLOSED AT END OF DAY' if closed_eod else '❌ STOPPED'} — {head} → {fmt(s['exit_price'], dp)}  (£{g:.2f}, {s['r']}R)"
    if s["status"] == "expired":
        return f"⌛ CANCELLED — {head} never filled. Delete the limit order."
    return head


def pnl_gbp(c) -> float:
    cost = INSTRUMENTS[c["instrument"]]["cost"]
    move = (c["exit_price"] - c["entry"]) if c["side"] == "BUY" else (c["entry"] - c["exit_price"])
    return (move - cost) * LOT_OZ / c.get("gbpusd", 1.30)


def stats(closed, start):
    rs = [c["r"] for c in closed]
    wins = [r for r in rs if r > 0]
    bal, curve = start, []
    for c in closed:
        c["pnl_gbp"] = round(pnl_gbp(c), 2)
        bal += c["pnl_gbp"]
        curve.append(dict(t=c["exit_time"], balance=round(bal, 2)))
    return dict(trades=len(rs), wins=len(wins), win_rate=round(100 * len(wins) / len(rs), 1) if rs else None,
                total_r=round(sum(rs), 2), avg_r=round(sum(rs) / len(rs), 3) if rs else None,
                balance=round(bal, 2), start_balance=start, curve=curve)


def gbpusd() -> float:
    try:
        from data import yahoo
        return float(yahoo("GBPUSD=X", "5m", "1d")["close"].iloc[-1])
    except Exception:  # noqa: BLE001
        return 1.30


def main():
    cfg = load_json(CONFIG, {})
    p = Params(**cfg.get("params", {}))
    account = float(cfg.get("account_gbp", 200))
    max_risk_pct = float(cfg.get("max_risk_pct", 2.0))
    fx = gbpusd()
    # hard cap: stop + spread may never risk more than max_risk_pct of the account at 0.01 lots
    p.max_stop_usd = round(account * max_risk_pct / 100 * fx / LOT_OZ, 2)
    state = load_json(STATE, {"signals": {}, "created": pd.Timestamp.now(tz="UTC").isoformat()})
    now = pd.Timestamp.now(tz=ET)
    prices = {}
    _CHAT["id"] = chat_id(state)
    if _CHAT["id"] and not state.get("tg_hello"):
        tg("🟡 <b>Gold Desk is live.</b>\nI watch XAUUSD every 5 minutes and call TJR setups in the London (07:00–10:00 UK) and New York (13:30–16:00 UK) killzones. Every call, fill, target and stop lands here. Paper trading only.")
        state["tg_hello"] = now.isoformat()

    for inst, ic in INSTRUMENTS.items():
        if inst not in cfg.get("instruments", list(INSTRUMENTS)):
            continue
        try:
            df, feed = gold_live()
        except Exception as e:  # noqa: BLE001
            print("data error", inst, e)
            continue
        print("feed:", feed, len(df), "bars, last", df.index[-1])
        if df.empty:
            continue
        last = float(df["close"].iloc[-1])
        prices[inst] = dict(price=last, time=df.index[-1].isoformat(), feed=feed)

        # 1) new signals
        for s in find_setups(df, inst, p):
            if s.id in state["signals"]:
                continue
            if pd.Timestamp(s.confirm_time) < now - timedelta(minutes=45):
                continue  # too old to act on
            d = s.to_dict()
            d["sent_at"] = now.isoformat()
            d["initial_status"] = s.status
            d["feed"] = feed
            d["gbpusd"] = round(fx, 5)
            d["account_gbp"] = account
            state["signals"][s.id] = d
            tg(signal_msg(d, last))

        # 2) manage live signals
        for sid, d in state["signals"].items():
            if d["instrument"] != inst or d["status"] not in ("pending", "open"):
                continue
            if d.get("feed", feed).replace(" (stale)", "") != feed.replace(" (stale)", ""):
                continue  # only judge a trade on the same price feed it was signalled on
            base = {k: d[k] for k in Setup.__dataclass_fields__ if k in d}
            base.update(status=d["initial_status"], fill_time=None if d["initial_status"] == "pending" else d["confirm_time"],
                        exit_time=None, exit_price=None, r=None, notes=[])
            s = simulate(Setup(**base), df, ic["cost"])
            if s.status != d["status"]:
                prev = d["status"]
                d.update(status=s.status, fill_time=s.fill_time, exit_time=s.exit_time,
                         exit_price=s.exit_price, r=s.r, notes=s.notes)
                if not (prev == "pending" and s.status in ("win", "loss")):
                    tg(update_msg(d))
                else:  # filled and finished between two runs
                    d2 = dict(d, status="open"); tg(update_msg(d2)); tg(update_msg(d))

    sigs = sorted(state["signals"].values(), key=lambda d: d["confirm_time"], reverse=True)
    closed = sorted([d for d in sigs if d["status"] in ("win", "loss")], key=lambda d: d["exit_time"])
    state["updated"] = now.isoformat()
    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(state, indent=1, default=str))
    FEED.parent.mkdir(exist_ok=True)
    FEED.write_text(json.dumps(dict(
        updated=now.isoformat(), params=p.label(), prices=prices, stats=stats(closed, account),
        account=dict(gbp=account, max_risk_pct=max_risk_pct, lot=LOT, stop_cap_usd=p.max_stop_usd, gbpusd=round(fx, 5)),
        backtest=load_json(ROOT / "reports" / "summary.json", None),
        signals=sigs[:200]), indent=1, default=str))
    print("ok", len(sigs), "signals tracked")


if __name__ == "__main__":
    main()
