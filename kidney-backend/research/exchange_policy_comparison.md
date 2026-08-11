# Exchange matching policy comparison

Simulated pool: 40 incompatible donor/recipient pairs (seed 20260809). Graph: 40 nodes, 212 compatible directed edges.

## Summary

| Policy | Cycles selected | Pairs transplanted | Total mismatch quality | Total equity score | Total LKDPI quality |
|---|---|---|---|---|---|
| max_transplants | 6 | 12 | 24.0 | 23.1 | 791.4 |
| max_quality | 6 | 12 | 34.0 | 22.5 | 876.1 |
| equity_weighted | 6 | 12 | 23.0 | 25.5 | 868.8 |
| max_lkdpi_quality | 6 | 12 | 32.0 | 24.3 | 951.3 |

## cPRA of matched vs. unmatched patients

| Policy | Avg cPRA (matched) | Avg cPRA (unmatched) |
|---|---|---|
| max_transplants | 29.3% | 27.6% |
| max_quality | 26.9% | 28.6% |
| equity_weighted | 34.2% | 25.5% |
| max_lkdpi_quality | 31.0% | 26.8% |

## Which patients each policy transplants

### max_transplants

- Pair 02 (B recipient / A donor, waiting 51d, low sensitization)
- Pair 09 (B recipient / A donor, waiting 910d, moderate sensitization)
- Pair 12 (B recipient / A donor, waiting 803d, high sensitization)
- Pair 18 (A recipient / B donor, waiting 477d, low sensitization)
- Pair 19 (B recipient / A donor, waiting 1365d, high sensitization)
- Pair 23 (A recipient / B donor, waiting 56d, low sensitization)
- Pair 25 (A recipient / B donor, waiting 1155d, low sensitization)
- Pair 28 (A recipient / B donor, waiting 138d, low sensitization)
- Pair 30 (B recipient / A donor, waiting 1103d, low sensitization)
- Pair 31 (A recipient / B donor, waiting 967d, low sensitization)
- Pair 36 (B recipient / A donor, waiting 1103d, low sensitization)
- Pair 39 (A recipient / B donor, waiting 510d, high sensitization)

### max_quality

- Pair 02 (B recipient / A donor, waiting 51d, low sensitization)
- Pair 08 (A recipient / B donor, waiting 214d, low sensitization)
- Pair 09 (B recipient / A donor, waiting 910d, moderate sensitization)
- Pair 12 (B recipient / A donor, waiting 803d, high sensitization)
- Pair 18 (A recipient / B donor, waiting 477d, low sensitization)
- Pair 19 (B recipient / A donor, waiting 1365d, high sensitization)
- Pair 23 (A recipient / B donor, waiting 56d, low sensitization)
- Pair 26 (A recipient / B donor, waiting 1152d, moderate sensitization)
- Pair 28 (A recipient / B donor, waiting 138d, low sensitization)
- Pair 30 (B recipient / A donor, waiting 1103d, low sensitization)
- Pair 31 (A recipient / B donor, waiting 967d, low sensitization)
- Pair 36 (B recipient / A donor, waiting 1103d, low sensitization)

### equity_weighted

- Pair 02 (B recipient / A donor, waiting 51d, low sensitization)
- Pair 09 (B recipient / A donor, waiting 910d, moderate sensitization)
- Pair 11 (A recipient / B donor, waiting 1354d, low sensitization)
- Pair 12 (B recipient / A donor, waiting 803d, high sensitization)
- Pair 18 (A recipient / B donor, waiting 477d, low sensitization)
- Pair 19 (B recipient / A donor, waiting 1365d, high sensitization)
- Pair 25 (A recipient / B donor, waiting 1155d, low sensitization)
- Pair 26 (A recipient / B donor, waiting 1152d, moderate sensitization)
- Pair 30 (B recipient / A donor, waiting 1103d, low sensitization)
- Pair 31 (A recipient / B donor, waiting 967d, low sensitization)
- Pair 36 (B recipient / A donor, waiting 1103d, low sensitization)
- Pair 39 (A recipient / B donor, waiting 510d, high sensitization)

### max_lkdpi_quality

- Pair 02 (B recipient / A donor, waiting 51d, low sensitization)
- Pair 08 (A recipient / B donor, waiting 214d, low sensitization)
- Pair 09 (B recipient / A donor, waiting 910d, moderate sensitization)
- Pair 12 (B recipient / A donor, waiting 803d, high sensitization)
- Pair 18 (A recipient / B donor, waiting 477d, low sensitization)
- Pair 19 (B recipient / A donor, waiting 1365d, high sensitization)
- Pair 25 (A recipient / B donor, waiting 1155d, low sensitization)
- Pair 26 (A recipient / B donor, waiting 1152d, moderate sensitization)
- Pair 30 (B recipient / A donor, waiting 1103d, low sensitization)
- Pair 31 (A recipient / B donor, waiting 967d, low sensitization)
- Pair 36 (B recipient / A donor, waiting 1103d, low sensitization)
- Pair 39 (A recipient / B donor, waiting 510d, high sensitization)

## Patients only max transplants misses

### Matched by max_quality but not max_transplants

- Pair 08 (A recipient / B donor, waiting 214d, low sensitization)
- Pair 26 (A recipient / B donor, waiting 1152d, moderate sensitization)

### Matched by equity_weighted but not max_transplants

- Pair 11 (A recipient / B donor, waiting 1354d, low sensitization)
- Pair 26 (A recipient / B donor, waiting 1152d, moderate sensitization)

### Matched by max_lkdpi_quality but not max_transplants

- Pair 08 (A recipient / B donor, waiting 214d, low sensitization)
- Pair 26 (A recipient / B donor, waiting 1152d, moderate sensitization)

