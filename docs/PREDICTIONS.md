# Your predictions (do this BEFORE the final run)

This is the one part of the project that has to be yours. Before seeing the final matrix, guess it.
Afterwards the report puts your guess in every cell next to the real answer, and tells you your average
miss. Being wrong in specific ways is how you'll actually understand the results, and "I predicted X,
the data said Y, and here's why" is a far better explanation than reciting a table.

## How

1. Run `.venv/Scripts/python.exe -m qrt predictions`. This creates `predictions.csv` in the project root.
2. Open it in Excel. There is one line per (researcher, audit) cell. Fill `predicted_percent` with a
   number from 0 to 100. You can leave cells blank; only the filled ones get scored.
   - For every researcher except `honest_trend`, the cell is the **catch rate**: of that researcher's
     fake claims, what % will this audit reject?
   - For `honest_trend` it is the **false-alarm rate**: its edge is real, so what % will this audit wrongly
     reject?
3. Don't look at `results/dev-*` first. Dev results use a different seed but would still spoil your
   guesses.
4. Tell Claude "run final". It runs once and locks.

## Cheat sheet (what everything means)

**Researchers**

| Researcher | What it does | True edge? |
|---|---|---|
| honest_null | One momentum rule, done properly, in a market with no edge | No: any claim is luck |
| honest_trend | The same rule in a market with a real hidden trend | **Yes** |
| miner_null | Tries 120 rules and keeps the best | No |
| miner_trend | Tries 120 rules in the trending market | Usually yes (104 of 120 rules have real edge there) |
| lookahead | Decides with today's close, trades at today's open | No |
| normaliser | Bets on returning to the whole-sample average price (future included) | No |
| cost_ignorer | Fast reversal rule with zero costs; real gross edge, loses after costs | No (after costs) |
| survivor | "Buy the dip", only on stocks still listed today | No |
| window_picker | Tries 11 start dates and reports the best period | No |
| asset_picker | Tries 20 assets and reports the best one | No |

**Audits**

| Audit | Tier | Rejects when... |
|---|---|---|
| psr | 1 | The Sharpe isn't significantly above 0 (allowing for fat tails) |
| dsr_assumed | 1 | The Sharpe doesn't beat the best of 100 imaginary worthless strategies |
| dsr | 2 | The same, with the real number of trials |
| pbo | 2 | The in-sample winner usually finishes in the bottom half out-of-sample |
| bonferroni | 2 | The p-value × the number of trials ≥ 5% |
| reality_check | 2 | The best trial doesn't beat zero by more than luck (bootstrap) |
| spa | 2 | The same, ignoring obviously bad trials |
| placebo | 3 | The whole process finds edges as good in sign-randomised (edge-free) data |
| delay | 3 | Trading one day later kills it |
| cost_stress | 3 | Double costs kill it |
| pit_universe | 3 | Putting the delisted stocks back kills it |
| holdout | 3 | The process's pick from the first 70% fails on the last 30% |
| forward_1y | 3 | One year of honest paper trading isn't significant |
| forward_3y | 3 | Three years of honest paper trading isn't significant |

Hints to think about, without answers:
- Can a test that only sees returns ever notice that the code peeked at the future?
- Which audits can't possibly know a stock was delisted?
- A real edge with a true Sharpe of 0.7: how significant is one year of it?
