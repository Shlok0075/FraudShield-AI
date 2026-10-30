# Dataset Card - PaySim (offline benchmark)

- **Source file:** `PS_20174392719_1491204439457_log.csv` (SHA-256 `16910f90577b0d981bf8ff289714510bb89bc71bff7d3f220f024e287e4eea6b`)
- **Intended use:** offline model comparison for an academic prototype. NOT evidence of production banking performance.
- **Not the live-demo data:** the live demo uses a separate simulated stream (see simulator docs).
- **Seed:** 42 | **Built:** 2026-09-29T13:28:51.218997+00:00 | Python 3.13.14, pandas 2.3.3

## Size and class balance
- Rows: 6,362,620; fraud rows: 8,213 (0.1291%)
- Duplicate rows: 0; missing values: 0
- Time span: 742 simulated hours

| Type | Rows | Fraud |
|---|---|---|
| CASH_IN | 1,399,284 | 0 |
| CASH_OUT | 2,237,500 | 4,116 |
| DEBIT | 41,432 | 0 |
| PAYMENT | 2,151,495 | 0 |
| TRANSFER | 532,909 | 4,097 |

## Split (chronological on timestamp)
| Split | Rows | Fraud | Fraud rate |
|---|---|---|---|
| train | 3,792,821 | 3,175 | 0.0837% |
| val | 1,276,276 | 780 | 0.0611% |
| test | 1,293,523 | 4,258 | 0.3292% |

Cut-offs (epoch s): train < 1705078800, val < 1705345200, test after. Preprocessing is fitted on train only.

## Entity structure (matters for behavioral features)
- Unique users (`nameOrig`): 6,353,307; share with more than 1 txn: 0.15%; max txns/user: 3
- Unique counterparties (`nameDest`): 2,722,362; share with more than 1 txn: 16.88%

## Leakage handling
- Dropped columns: oldbalanceOrg, newbalanceOrig, oldbalanceDest, newbalanceDest, isFlaggedFraud (post-transaction balances are generated from the fraud outcome; `isFlaggedFraud` is the output of a rule system).
- Fraud labels enter history features only after a 24 h delay.

## Known limitations
- Synthetic (simulator-generated) data derived from one country's mobile-money logs; fraud patterns are simulated.
- No device or location fields, so the `device_geo` feature group cannot be trained on this dataset.
- `step` is a simulated hour; hour-of-day / day-of-week assume an arbitrary calendar alignment.
- Origin accounts rarely repeat, so per-user behavioral features carry little signal here (see entity structure above).
