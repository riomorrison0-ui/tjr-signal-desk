# Gold strategy shoot-out: Andrea Unger's gold systems vs TJR

Data: **binance_paxg** 5m, 2020-08-28 → 2026-11-05. Settings picked on data before 2025-01-01, judged on data after it. 0.01 lots, max 2% risk, spread $0.3 per trade, entries at signal-candle close, UK hours 07–20.

## £1000 account (stop ≤ $26.0)

| strategy | settings | IS trades | IS win % | IS avg R | **OOS trades** | **OOS win %** | **OOS avg R** | OOS PF | OOS £ | trades/mo | worst streak |
|---|---|---|---|---|---|---|---|---|---|---|---|
| cci_fast | `{"tf": "30min", "level": 300, "sl_usd": 0, "sl_atr": 2.0, "tp_mult": 1.5}` | 239 | 36.0 | -0.095 | 60 | 40.0 | -0.044 | 0.92 | £-105.99 | 4.2 | 9 |
| imom | `{"from_uk": 700, "to_uk": 1300, "thresh_atr": 1.5, "hold_to_uk": 2000, "sl_atr": 2.0, "tp_mult": null}` | 123 | 45.5 | -0.002 | 25 | 32.0 | -0.356 | 0.42 | £-131.78 | 2.1 | 9 |
| nr7 | `{"sl_mult": 1.0, "tp_mult": 1.0}` | 130 | 43.8 | -0.077 | 12 | 50.0 | -0.001 | 1.0 | £2.85 | 2.2 | 6 |

**Pick for £1000:** nothing profitable in-sample

## £2000 account (stop ≤ $52.0)

| strategy | settings | IS trades | IS win % | IS avg R | **OOS trades** | **OOS win %** | **OOS avg R** | OOS PF | OOS £ | trades/mo | worst streak |
|---|---|---|---|---|---|---|---|---|---|---|---|
| cci_fast | `{"tf": "30min", "level": 300, "sl_usd": 0, "sl_atr": 2.0, "tp_mult": 1.5}` | 245 | 36.3 | -0.084 | 84 | 40.5 | -0.006 | 0.99 | £-10.45 | 4.6 | 9 |
| imom | `{"from_uk": 700, "to_uk": 1300, "thresh_atr": 1.5, "hold_to_uk": 2000, "sl_atr": 2.0, "tp_mult": null}` | 135 | 46.7 | -0.011 | 59 | 49.2 | 0.023 | 1.05 | £116.93 | 2.7 | 10 |
| nr7 | `{"sl_mult": 1.0, "tp_mult": 1.0}` | 142 | 43.7 | -0.075 | 37 | 40.5 | -0.107 | 0.67 | £-117.76 | 2.5 | 10 |

**Pick for £2000:** nothing profitable in-sample
