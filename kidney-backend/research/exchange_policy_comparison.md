# Exchange matching policy comparison

Simulated pool: 40 incompatible donor/recipient pairs (seed 20260809). Graph: 40 nodes, 150 compatible directed edges.

## Summary

| Policy | Cycles selected | Pairs transplanted | Total mismatch quality | Total equity score |
|---|---|---|---|---|
| max_transplants | 4 | 8 | 17.0 | 15.2 |
| max_quality | 4 | 8 | 23.0 | 15.2 |
| equity_weighted | 4 | 8 | 19.0 | 16.5 |

## cPRA of matched vs. unmatched patients

| Policy | Avg cPRA (matched) | Avg cPRA (unmatched) |
|---|---|---|
| max_transplants | 27.0% | 22.2% |
| max_quality | 28.3% | 21.9% |
| equity_weighted | 33.1% | 20.7% |

## Which patients each policy transplants

### max_transplants

- Pair 08 (A recipient / B donor, waiting 1287d, moderate sensitization)
- Pair 10 (A recipient / B donor, waiting 53d, low sensitization)
- Pair 13 (B recipient / A donor, waiting 190d, low sensitization)
- Pair 14 (A recipient / B donor, waiting 1077d, low sensitization)
- Pair 15 (B recipient / A donor, waiting 877d, moderate sensitization)
- Pair 20 (A recipient / B donor, waiting 980d, low sensitization)
- Pair 30 (B recipient / A donor, waiting 549d, low sensitization)
- Pair 38 (B recipient / A donor, waiting 681d, moderate sensitization)

### max_quality

- Pair 07 (A recipient / B donor, waiting 985d, high sensitization)
- Pair 10 (A recipient / B donor, waiting 53d, low sensitization)
- Pair 13 (B recipient / A donor, waiting 190d, low sensitization)
- Pair 14 (A recipient / B donor, waiting 1077d, low sensitization)
- Pair 15 (B recipient / A donor, waiting 877d, moderate sensitization)
- Pair 20 (A recipient / B donor, waiting 980d, low sensitization)
- Pair 30 (B recipient / A donor, waiting 549d, low sensitization)
- Pair 38 (B recipient / A donor, waiting 681d, moderate sensitization)

### equity_weighted

- Pair 07 (A recipient / B donor, waiting 985d, high sensitization)
- Pair 08 (A recipient / B donor, waiting 1287d, moderate sensitization)
- Pair 13 (B recipient / A donor, waiting 190d, low sensitization)
- Pair 14 (A recipient / B donor, waiting 1077d, low sensitization)
- Pair 15 (B recipient / A donor, waiting 877d, moderate sensitization)
- Pair 20 (A recipient / B donor, waiting 980d, low sensitization)
- Pair 30 (B recipient / A donor, waiting 549d, low sensitization)
- Pair 38 (B recipient / A donor, waiting 681d, moderate sensitization)

## Patients only max transplants misses

### Matched by max_quality but not max_transplants

- Pair 07 (A recipient / B donor, waiting 985d, high sensitization)

### Matched by equity_weighted but not max_transplants

- Pair 07 (A recipient / B donor, waiting 985d, high sensitization)

