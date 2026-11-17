"""Compare free live gold price sources at the same moments."""
import time
import requests
import pandas as pd

UA = {"User-Agent": "Mozilla/5.0 gold-desk/1.0"}


def swissquote():
    j = requests.get("https://forex-data-feed.swissquote.com/public-quotes/bboquotes/instrument/XAU/USD", headers=UA, timeout=10).json()
    best = []
    for plat in j:
        for p in plat.get("spreadProfilePrices", []):
            best.append((p["bid"], p["ask"]))
    bid = sorted(b for b, _ in best)[len(best) // 2]; ask = sorted(a for _, a in best)[len(best) // 2]
    return (bid + ask) / 2, f"bid {bid} ask {ask} ts {j[0].get('ts')}"


def gold_api():
    j = requests.get("https://api.gold-api.com/price/XAU", headers=UA, timeout=10).json()
    return float(j["price"]), f"updatedAt {j.get('updatedAt')}"


def goldprice():
    j = requests.get("https://data-asg.goldprice.org/dbXRates/USD", headers=UA, timeout=10).json()
    return float(j["items"][0]["xauPrice"]), f"date {j.get('date')}"


def paxg():
    j = requests.get("https://data-api.binance.vision/api/v3/ticker/price", params={"symbol": "PAXGUSDT"}, headers=UA, timeout=10).json()
    return float(j["price"]), "binance PAXG last"


def yahoo(sym):
    r = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}", params={"interval": "1m", "range": "1d"}, headers=UA, timeout=10).json()
    m = r["chart"]["result"][0]["meta"]
    return float(m["regularMarketPrice"]), f"{sym} t={pd.Timestamp(m['regularMarketTime'], unit='s')}"


SRC = dict(swissquote=swissquote, gold_api=gold_api, goldprice=goldprice, paxg=paxg,
           yahoo_xau=lambda: yahoo("XAUUSD=X"), yahoo_gc=lambda: yahoo("GC=F"))
for rnd in range(6):
    now = pd.Timestamp.now(tz="UTC")
    vals = {}
    for k, f in SRC.items():
        try:
            v, info = f(); vals[k] = v
            print(f"{now:%H:%M:%S} {k:11s} {v:10.2f}  {info}")
        except Exception as e:  # noqa: BLE001
            print(f"{now:%H:%M:%S} {k:11s} ERROR {str(e)[:80]}")
    if "swissquote" in vals:
        print("   diff vs swissquote:", {k: round(v - vals["swissquote"], 2) for k, v in vals.items()})
    time.sleep(15)
