# Gold strategy shoot-out: Andrea Unger's gold systems vs TJR

Data: **binance_paxg** 5m, 2020-08-28 → 2026-11-05. Settings picked on data before 2025-01-01, judged on data after it. 0.01 lots, max 2% risk, spread $0.3 per trade, entries at signal-candle close, UK hours 07–20.

## £200 account (stop ≤ $5.2)

| strategy | settings | IS trades | IS win % | IS avg R | **OOS trades** | **OOS win %** | **OOS avg R** | OOS PF | OOS £ | trades/mo | worst streak |
|---|---|---|---|---|---|---|---|---|---|---|---|
| cci | — not enough trades within this risk limit | | | | | | | | | | |

**Pick for £200:** nothing profitable in-sample

## £500 account (stop ≤ $13.0)

| strategy | settings | IS trades | IS win % | IS avg R | **OOS trades** | **OOS win %** | **OOS avg R** | OOS PF | OOS £ | trades/mo | worst streak |
|---|---|---|---|---|---|---|---|---|---|---|---|
| cci | `{"level": 300, "sl_usd": 8, "tp_mult": 3.0}` | 121 | 37.2 | 0.211 | 39 | 25.6 | -0.087 | 0.89 | £-20.87 | 2.2 | 8 |

**Pick for £500:** cci `{"level": 300, "sl_usd": 8, "tp_mult": 3.0}`

## £1000 account (stop ≤ $26.0)

| strategy | settings | IS trades | IS win % | IS avg R | **OOS trades** | **OOS win %** | **OOS avg R** | OOS PF | OOS £ | trades/mo | worst streak |
|---|---|---|---|---|---|---|---|---|---|---|---|
| cci | `{"level": 300, "sl_usd": 8, "tp_mult": 3.0}` | 121 | 37.2 | 0.211 | 39 | 25.6 | -0.087 | 0.89 | £-20.87 | 2.2 | 8 |

**Pick for £1000:** cci `{"level": 300, "sl_usd": 8, "tp_mult": 3.0}`
