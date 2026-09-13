# The two-phase model — the most important structural finding

> **CORRECTED 2026-09-06.** This note originally concluded that a withdrawal
> portfolio's return is "switched off" at retirement. That is wrong as a
> *mechanism*, though close in effect for the scenarios first measured. The
> return is not zeroed — it is **replaced by a much lower, confidence-derived
> return** (`retireRule`, a Trinity-style haircut). See the corrected section at
> the bottom and notes/05 §6.

The reference does **not** run one continuous simulation. Early retirement is a
regime change, and it changes how portfolios behave.

## Withdrawal portfolios stop compounding at retirement

Two runs, identical in every field except `portfolioDesignation`, same fixed
retirement age (55), same idle portfolio (`goal=0`, so it never receives
deposits; living costs are funded from the cash pile in both):

| fixture | designation | accumulation monthly factor | post-retirement monthly factor | balance at 55 | +5 years | at 81 |
|---|---|---|---|---|---|---|
| `eng_idle_i5` | `withdraw` | 1.003990 | **0.999919** | 241,120.4 | 239,953.1 | — |
| `eng_idle_goaldesig` | `goal` | 1.003990 | **1.003990** | 241,120.4 | 306,201.9 | 835,330.8 |

A `goal` portfolio compounds at the full rate forever. A `withdraw` portfolio
switches at the retirement date to a **decumulation return** that is far lower
than the user's — low enough that the management fee outweighs it and the
balance shrinks.

The decumulation return does not depend on the user's own return, proven by
holding the retirement age fixed and varying only the expected return:

| fixture | return | accumulation factor | post-retirement factor |
|---|---|---|---|
| `eng_idle_i5`  | 5%  | 1.003990 | 0.9999191 |
| `eng_idle_i20` | 20% | 1.015224 | 0.9999191 |

A 20% portfolio and a 5% portfolio decay at **exactly the same rate** after
retirement. The declared return only affects accumulation.

## Consequence

This is the single biggest driver of the calculator's conservatism, and the
biggest structural difference from `backend/services/retirement_service.py`,
which compounds the portfolio through retirement at the real rate. Reproducing
the reference means reproducing this. It is the #1 **deviation candidate** to
raise with the user: modelling a 30-year drawdown at 0% real return is a very
strong assumption, and it is probably what the site's Trinity-study note is
gesturing at (return decides how long the pot lasts, not how it grows).

## RESOLVED: the drain is the `retireRule` haircut

The residual return recovered from the decay is the reference's
**decumulation return**, set by `retireRule` (the confidence level) and the
length of the bridge from retirement to the state pension. The pension agent
established the mechanism independently (notes/05 §6); the numbers below are
the same phenomenon seen from the asset side.

Analysing only **idle** portfolios — ones never withdrawn from, so the decay is
pure growth and not confounded by withdrawals:

| fixture | rule | input return | fee | FIRE | bridge to 67 | decumulation return |
|---|---|---|---|---|---|---|
| `eng_idle_i5` | 85 | 5% | 0.1% | 55.08 | 11.92 y | 0.0030% |
| `eng_idle_i20` | 85 | **20%** | 0.1% | 55.08 | 11.92 y | **0.0030%** |
| `eng_idle_fee1` | 85 | 5% | **1.0%** | 55.08 | 11.92 y | **0.0030%** |
| `baseline` | 85 | 5% | 0.1% | 53.25 | 13.75 y | 0.0246% |

This is a cleaner control than was available to the pension agent, and it
sharpens their conclusion: **the decumulation return is a function of
`(confidence, bridge length)` only.** A 4× change in the input return and a 10×
change in the fee leave it bit-identical; only moving the retirement date moves
it. Their apparent input-return dependence came from runs where the FIRE age —
and therefore the bridge — moved too.

Note this analysis is only valid on idle portfolios. Applying it to a portfolio
that is being drawn (`eng_fixedage_*`) yields nonsense negative returns, because
the withdrawal is then mixed into the observed factor.

### Back-solving the implied withdrawal rate

Treating the decumulation return as "the return at which the pot is exactly
exhausted over the bridge", the implied sustainable withdrawal rate
`w = r / (1 - (1+r)^-N)` comes out as a clean Trinity-shaped surface —
decreasing in confidence and decreasing in horizon:

| confidence | bridge | implied SWR |
|---|---|---|
| 80 | 19.42 y | 6.34% |
| 85 | 19.17 y | 6.12% |
| 90 | 18.92 y | 5.93% |
| 95 | 18.67 y | 5.75% |
| 100 | 18.50 y | 5.58% |
| 85 | 17.00 y | 6.47% |
| 85 | 13.75 y | 7.29% |
| 85 | 11.92 y | 8.39% |

That is almost certainly the actual lookup table the reference interpolates —
a Trinity success-rate table for a 75% equity portfolio, exactly as the site's
own assumptions text claims. Mapping it precisely is the remaining work.

## The old (superseded) reading: the drain is not simply the management fee

Post-retirement decay for a `withdraw` portfolio, all with the fee shown:

| fixture | fee | observed annual factor | `1 - fee` would be |
|---|---|---|---|
| `eng_idle_i5` / `eng_idle_i20` | 0.1% | 0.9990300 (−0.0970%) | 0.9990 (−0.1%) |
| `eng_idle_fee1` | 1.0% | 0.9900284 (−0.9972%) | 0.9900 (−1.0%) |
| `baseline` | 0.1% | 0.9992455 (−0.0755%) | 0.9990 (−0.1%) |

Two things to note. First, the decay tracks the fee closely but is consistently
a hair *less* negative — equivalent to a constant residual return of about
+0.003%/yr, immaterial and most likely a day-count artifact. Second, and more
importantly, **`baseline` decays at a different rate (−0.0755%) than
`eng_idle_i5` (−0.0970%) despite an identical 0.1% fee**. The two differ in
retirement age (53.2 vs 55.0) and in solver mode (`retire_asap` vs
`retire_at_age`).

**Open question.** The likeliest explanation is that at retirement the engine
converts each withdrawal portfolio into a *drawdown schedule* — the reference's
own output describes exactly this ("withdrawal from cash from age 53.2 to 73.2,
then from the portfolio from 73.2 to 81.0") — so what looks like a decay rate is
really a scheduled amortization whose shape depends on the reserve's assigned
window. Not yet proven; needs a probe that varies the reserve window while
holding fee and balance fixed.
