# The drawdown phase

## Withdrawal order — verified exactly

Reading `fixtures/baseline.json` month by month, the funding order is:

1. **Free cash** — the checking account down to `cashBuffer`.
2. **Withdrawal portfolios**, in list order.
3. **The buffer itself**, once the portfolios are gone.

Our engine reproduces the entire pre-pension drawdown of `baseline`
(ages 53.25 → 67.08, 167 months) with a **maximum cash deviation of 0.00**.

The transitions in `baseline` show every rule at once:

| age | cash Δ/mo | portfolio Δ/mo | what is happening |
|---|---|---|---|
| 53.25 | −5,000 | −13.9 | retirement: cash funds the whole 5,000 expense |
| 67.08 | −2,243 | −13.7 | Bituach Leumi (2,757) starts; cash covers only the residual |
| 73.17 | −1,261 | −995.6 | cash runs dry mid-month; the portfolio covers the remaining 982 |
| 73.25 | 0 | −2,256.5 | portfolio funds the full 2,243 residual |
| 80.08 | 0 | −2,090.4 | BL steps up 2,757 → 2,912, so the portfolio draws less |

That last row is a real Israeli rule surfacing: the old-age pension increases at
age 80. Corroborates the pension agent's area.

## Retirement index convention

The reported retirement age is the age of the **last working month**, not the
first retired one. In `baseline` the reference prints "גיל פרישה: 53.2"; work
income is still 10,000 at index 198 (age 53.17) and drops to 0 at index 199
(age 53.25). So `retire_index` — the first fully-retired month — is the index
*after* the one matching the printed age. Detect it from the work-income
series, never from the rounded age.

## RESOLVED: the "frozen" portfolio's decay rate

A frozen (withdrawal, post-retirement) portfolio decays at a **perfectly
constant rate** — measured across three separate 40-month windows in each
scenario, the monthly factor is stable to nine decimal places. But the rate is
not a clean function of the management fee:

| fixture | fee | retirement age | observed annual decay | implied residual return |
|---|---|---|---|---|
| `baseline` | 0.1% | 53.25 | −0.07543% | +0.0246%/yr |
| `eng_idle_i5` | 0.1% | 55.08 | −0.09702% | +0.0030%/yr |
| `eng_idle_i20` | 0.1% | 55.08 | −0.09702% | +0.0030%/yr |
| `eng_idle_fee1` | 1.0% | 55.08 | −0.99705% | +0.0029%/yr |

Reading the decay as `((1 + r) * (1 - fee)) ** (1/12)` recovers a residual
return `r` that is consistent at ~0.003%/yr across the three `eng_idle` runs —
including across a 10× fee change and a 5% vs 20% return change — but is
~0.0246%/yr in `baseline`. The two groups differ in only two respects:
`base_problem` (`retire_asap` vs `retire_at_age`) and retirement age
(53.25 vs 55.08).

**Answer:** the residual return is the reference's **decumulation return**, set
by `retireRule` and the length of the bridge from retirement to the state
pension — not a day-count artifact. `baseline` retires 1.83 years earlier than
the `eng_idle` runs, so its bridge is longer, so its supported return is higher
(0.0246% vs 0.0030%), so it decays more slowly. Full treatment in notes/07 and
notes/05 §6.

## Capital-gains tax — SOLVED, verified to 0.1

`fixtures/cf_credit_0` exposes the mechanism directly: its expense chart carries
a dedicated `מס על רווחי תיק` ("tax on portfolio gains") series alongside the
gross withdrawal, so both sides of the equation are observable.

For the default `flat` lot method the rule is a straight gross-up at **25%**
(Israeli CGT) on the *proportional* unrealised gain:

```
g     = (balance - basis) / balance
gross = need / (1 - 0.25 * g)      # capped at the balance
tax   = gross * 0.25 * g
basis -= gross * (1 - g)           # basis consumed proportionally
balance -= gross
```

The opening basis comes from the input: `basis = balance * (1 - profitFraction)`.

Fitted on the first attempt and matching **every** month of `cf_credit_0`:

| month | gross (ref / ours) | tax (ref / ours) | balance (ref / ours) |
|---|---|---|---|
| 5  | 5,024.8 / 5,024.8 | 24.8 / 24.8 | 97,373.4 / 97,373.4 |
| 10 | 5,049.3 / 5,049.3 | 49.3 / 49.3 | 73,831.3 / 73,831.3 |
| 20 | 5,097.6 / 5,097.6 | 97.6 / 97.6 | 24,945.8 / 24,945.8 |
| 24 | 5,116.6 / 5,116.6 | 116.6 / 116.6 | 4,703.9 / 4,703.9 |
| 25 | 4,703.9 / 4,703.9 | 111.4 / 111.4 | 0.0 / 0.0 |

Month 25 is the partial final withdrawal: the gross is capped at the remaining
balance, so the net falls 407.5 short of the 5,000 need — and the reference
reports exactly that as `החתיכה החסרה = 408` ("the missing piece"), the same
phrase the smart-advice token uses for a shortfall.

`fifo` and `lifo` are not this rule and are left unimplemented rather than
guessed at.
