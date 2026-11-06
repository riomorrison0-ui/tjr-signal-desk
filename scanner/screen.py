"""Pass/fail screen for daily strategies, fixed BEFORE looking at results.
PASS = >=8 trades/month, avg R > 0 in-sample AND out-of-sample, PF >= 1.2 overall,
>=5 of 7 years profitable, max drawdown <= 15% of the account."""
import json
import sys

files = sys.argv[1:]
rows = []
for f in files:
    rows += json.load(open(f))
print(f"{len(rows)} results screened")
passed, near = [], []
for r in rows:
    a, i, o = r["all"], r["ins"], r["oos"]
    if not a["n"]:
        continue
    yrs = [v["avg_r"] for v in r["years"].values() if v["n"] >= 5]
    green = sum(1 for y in yrs if y > 0)
    checks = dict(freq=a["per_month"] >= 8, ins=(i["avg_r"] or -9) > 0, oos=(o["avg_r"] or -9) > 0,
                  pf=(a["pf"] or 0) >= 1.2, years=green >= 5, dd=a["max_dd_gbp"] <= 0.15 * r["account"])
    score = sum(checks.values())
    line = (f"{r['strategy']:9s} £{r['account']:<5} {json.dumps(r['params'])[:85]:85s} /mo {a['per_month']:5} wr {a['win_rate']} "
            f"pf {a['pf']} avgR {a['avg_r']:+.3f} IS {i['avg_r']} OOS {o['avg_r']} green {green}/{len(yrs)} dd£{a['max_dd_gbp']:.0f} "
            f"£{a['pnl_gbp']:.0f}  fails: {[k for k, v in checks.items() if not v]}")
    (passed if score == 6 else near if score >= 5 else []).append((a["avg_r"], line))
print("== PASS"); [print(l) for _, l in sorted(passed, reverse=True)]
print("== 5/6 (one check failed)"); [print(l) for _, l in sorted(near, reverse=True)[:25]]
