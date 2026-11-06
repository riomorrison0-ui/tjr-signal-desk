# Gold strategy shoot-out: Andrea Unger's gold systems vs TJR

Data: **binance_paxg** 5m, 2020-08-28 → 2026-11-05. Settings picked on data before 2025-01-01, judged on data after it. 0.01 lots, max 2% risk, spread $0.3 per trade, entries at signal-candle close, UK hours 07–20.

## £200 account (stop ≤ $5.2)

| strategy | settings | IS trades | IS win % | IS avg R | **OOS trades** | **OOS win %** | **OOS avg R** | OOS PF | OOS £ | trades/mo | worst streak |
|---|---|---|---|---|---|---|---|---|---|---|---|
| london | `{"stop": "mid", "tp_mult": 1.0, "lo": 0.5, "hi": 1.5, "end_uk": 1100}` | 78 | 51.3 | -0.053 | 1 | 0.0 | -1.065 | 0.0 | £-3.79 | 1.4 | 10 |
| orb | `{"open_uk": 1430, "minutes": 30, "stop": "range", "tp_mult": 1.0}` | 157 | 52.9 | -0.035 | 9 | 22.2 | -0.652 | 0.23 | £-17.25 | 2.4 | 7 |
| ibretr | `{"open_uk": 1430, "entry_in": 0.25, "tgt_out": 0.5, "stop_in": 1.0}` | 106 | 50.0 | -0.048 | 7 | 42.9 | -0.196 | 0.57 | £-5.25 | 1.8 | 5 |
| cci | — not enough trades within this risk limit | | | | | | | | | | |

**Pick for £200:** nothing profitable in-sample

## £1000 account (stop ≤ $26.0)

| strategy | settings | IS trades | IS win % | IS avg R | **OOS trades** | **OOS win %** | **OOS avg R** | OOS PF | OOS £ | trades/mo | worst streak |
|---|---|---|---|---|---|---|---|---|---|---|---|
| london | `{"stop": "range", "tp_mult": 0.75, "lo": 0.0, "hi": 9.0, "end_uk": 1300}` | 726 | 48.3 | -0.089 | 101 | 58.4 | 0.047 | 1.14 | £61.95 | 11.3 | 8 |
| orb | `{"open_uk": 1430, "minutes": 30, "stop": "range", "tp_mult": 1.0}` | 922 | 46.2 | -0.105 | 319 | 48.9 | -0.027 | 0.94 | £-85.65 | 16.7 | 12 |
| ibretr | `{"open_uk": 1430, "entry_in": 0.25, "tgt_out": 0.5, "stop_in": 1.0}` | 411 | 54.0 | 0.033 | 135 | 50.4 | 0.019 | 1.05 | £25.48 | 7.4 | 8 |
| cci | `{"level": 300, "sl_usd": 8, "tp_mult": 3.0}` | 121 | 37.2 | 0.211 | 39 | 25.6 | -0.087 | 0.89 | £-20.87 | 2.2 | 8 |

**Pick for £1000:** cci `{"level": 300, "sl_usd": 8, "tp_mult": 3.0}`

## £2000 account (stop ≤ $52.0)

| strategy | settings | IS trades | IS win % | IS avg R | **OOS trades** | **OOS win %** | **OOS avg R** | OOS PF | OOS £ | trades/mo | worst streak |
|---|---|---|---|---|---|---|---|---|---|---|---|
| london | `{"stop": "range", "tp_mult": 1.0, "lo": 0.0, "hi": 9.0, "end_uk": 1100}` | 663 | 44.6 | -0.076 | 230 | 55.7 | 0.093 | 1.31 | £610.15 | 12.1 | 11 |
| orb | `{"open_uk": 1430, "minutes": 30, "stop": "range", "tp_mult": 1.0}` | 931 | 46.1 | -0.105 | 410 | 46.8 | -0.035 | 0.91 | £-215.24 | 18.0 | 12 |
| ibretr | `{"open_uk": 1430, "entry_in": 0.25, "tgt_out": 0.5, "stop_in": 1.0}` | 416 | 53.8 | 0.03 | 161 | 52.8 | 0.055 | 1.16 | £182.43 | 7.8 | 8 |
| cci | `{"level": 300, "sl_usd": 8, "tp_mult": 3.0}` | 121 | 37.2 | 0.211 | 39 | 25.6 | -0.087 | 0.89 | £-20.87 | 2.2 | 8 |

**Pick for £2000:** cci `{"level": 300, "sl_usd": 8, "tp_mult": 3.0}`

## Portfolio £1000: ibretr + cci

- 706 trades, 0.44 per trading day, a trade on 41.3% of days
- win 48.9% · PF 1.13 · avg 0.054R · £335.88 · max DD £122.96 · worst streak 9 · green months 55.3%
- in-sample avg 0.074R (532) · out-of-sample avg -0.005R (174), win 44.8%, PF 0.99, £4.61
- years: 2020 -0.08R/61 · 2021 +0.03R/135 · 2022 +0.26R/106 · 2023 -0.03R/104 · 2024 +0.12R/126 · 2025 +0.00R/107 · 2026 -0.01R/67

## Portfolio £2000: ibretr + cci

- 737 trades, 0.46 per trading day, a trade on 43.2% of days
- win 49.4% · PF 1.14 · avg 0.059R · £464.89 · max DD £117.91 · worst streak 7 · green months 55.3%
- in-sample avg 0.071R (537) · out-of-sample avg 0.027R (200), win 47.5%, PF 1.06, £161.56
- years: 2020 -0.08R/61 · 2021 +0.03R/137 · 2022 +0.25R/107 · 2023 -0.03R/104 · 2024 +0.12R/128 · 2025 +0.01R/109 · 2026 +0.05R/91
