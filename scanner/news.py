"""
News layer (free, no keys).

  - Economic calendar: ForexFactory weekly feed (faireconomy mirror). High-impact USD events
    block NEW gold signals from 30 min before to 30 min after the release.
  - Headlines: Google News RSS for gold, the Fed/dollar, and geopolitics (war, strikes, sanctions...).
    Headline risk is flagged on every call; a spike in conflict headlines in the last 2h raises a caution.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET_xml
from datetime import timedelta
from email.utils import parsedate_to_datetime

import pandas as pd
import requests

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) gold-desk/1.0"}
CAL_URLS = ["https://nfs.faireconomy.media/ff_calendar_thisweek.json",
            "https://cdn-nfs.faireconomy.media/ff_calendar_thisweek.json"]
BLACKOUT = timedelta(minutes=30)

QUERIES = {
    "gold": "gold price OR XAUUSD when:1d",
    "fed": "Federal Reserve OR Powell OR US inflation OR Treasury yields when:1d",
    "world": "war OR missile OR airstrike OR invasion OR sanctions OR escalation OR ceasefire when:1d",
}
RISK_WORDS = re.compile(r"\b(war|attack|missile|airstrike|strike[s]?|invasion|invade|escalat\w*|sanction\w*|nuclear|"
                        r"ceasefire|tariff\w*|emergency|crisis|default|shutdown|explosion|conflict|troops)\b", re.I)


def calendar() -> list[dict]:
    last = None
    for url in CAL_URLS:
        try:
            r = requests.get(url, headers=UA, timeout=20)
            r.raise_for_status()
            out = []
            for e in r.json():
                try:
                    t = pd.Timestamp(e["date"]).tz_convert("UTC")
                except Exception:  # noqa: BLE001
                    continue
                out.append(dict(title=e.get("title", ""), country=e.get("country", ""), impact=e.get("impact", ""),
                                time=t.isoformat(), forecast=e.get("forecast", ""), previous=e.get("previous", "")))
            return out
        except Exception as e:  # noqa: BLE001
            last = e
    raise RuntimeError(f"calendar unavailable: {last}")


def gold_events(events: list[dict], impacts=("High",)) -> list[dict]:
    return [e for e in events if e["country"] == "USD" and e["impact"] in impacts]


def blackout(events: list[dict], now: pd.Timestamp) -> dict | None:
    """The high-impact USD event that blocks trading right now, if any."""
    now = now.tz_convert("UTC")
    for e in gold_events(events):
        t = pd.Timestamp(e["time"])
        if t - BLACKOUT <= now <= t + BLACKOUT:
            return e
    return None


def next_events(events: list[dict], now: pd.Timestamp, n: int = 3, impacts=("High",)) -> list[dict]:
    now = now.tz_convert("UTC")
    ev = [e for e in gold_events(events, impacts) if pd.Timestamp(e["time"]) >= now - BLACKOUT]
    return sorted(ev, key=lambda e: e["time"])[:n]


def headlines(per_query: int = 6) -> dict:
    out = {}
    for key, q in QUERIES.items():
        try:
            r = requests.get("https://news.google.com/rss/search", params=dict(q=q, hl="en-GB", gl="GB", ceid="GB:en"),
                             headers=UA, timeout=20)
            r.raise_for_status()
            root = ET_xml.fromstring(r.content)
            items = []
            for it in root.iter("item"):
                title = (it.findtext("title") or "").strip()
                src = (it.findtext("source") or "").strip()
                try:
                    t = parsedate_to_datetime(it.findtext("pubDate")).astimezone(tz=None)
                    t = pd.Timestamp(t).tz_convert("UTC")
                except Exception:  # noqa: BLE001
                    t = None
                items.append(dict(title=title, source=src, time=t.isoformat() if t is not None else None,
                                  risk=bool(RISK_WORDS.search(title))))
            items.sort(key=lambda x: x["time"] or "", reverse=True)
            out[key] = items[:per_query]
        except Exception as e:  # noqa: BLE001
            out[key] = []
            out.setdefault("_errors", []).append(f"{key}: {e}")
    return out


def headline_risk(h: dict, now: pd.Timestamp) -> dict:
    """Count conflict/shock headlines in the last 2 hours."""
    now = now.tz_convert("UTC")
    recent = []
    for key in ("world", "gold", "fed"):
        for it in h.get(key, []):
            if it["risk"] and it["time"] and now - pd.Timestamp(it["time"]) <= timedelta(hours=2):
                recent.append(it)
    level = "high" if len(recent) >= 3 else "elevated" if recent else "normal"
    return dict(level=level, count=len(recent), examples=[r["title"] for r in recent[:3]])


def snapshot(now: pd.Timestamp) -> dict:
    """Everything the scanner needs from the news, never raising."""
    snap = dict(ok_calendar=False, ok_headlines=False, blackout=None, next=[], headlines={}, risk=dict(level="unknown"))
    try:
        ev = calendar()
        snap.update(ok_calendar=True, blackout=blackout(ev, now), next=next_events(ev, now),
                    week_high_usd=len(gold_events(ev)))
    except Exception as e:  # noqa: BLE001
        snap["calendar_error"] = str(e)
    h = headlines()
    snap["headlines"] = {k: v for k, v in h.items() if not k.startswith("_")}
    snap["ok_headlines"] = any(snap["headlines"].values())
    if h.get("_errors"):
        snap["headline_errors"] = h["_errors"]
    snap["risk"] = headline_risk(h, now)
    return snap
