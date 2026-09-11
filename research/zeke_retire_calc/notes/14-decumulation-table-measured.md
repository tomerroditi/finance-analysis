# The decumulation table — measured

notes/10 harvested this surface by fitting one scalar per fixture. It is now
**measured directly**, so the engine has no fitted parameters left.

## Method

Pin the retirement age (`base_problem=retire_at_age`), give the plan a 20M cash
pile so living costs never touch the portfolio, and read the idle portfolio's
post-retirement growth straight off the asset chart. Confidence and retirement
age are then the only free variables. 47 cells, `probe_trinity.py`.

The design is validated by agreement with rates fitted independently on
scenarios where the portfolio *is* drawn: rule 85 at FIRE 45.08 measures
2.1292%, and 2.1292% is exactly what `sol_at_age_45` and the three
`lot_*_known` fixtures fit to.

## The surface (confidence 85)

| FIRE age | 37 | 40 | 45 | 50 | 51 | 52 | 53 | 54–60 | 61 | 62 | 63 | 64 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| return | 2.76 | 2.61 | 2.13 | 1.07 | 0.72 | 0.32 | 0.04 | ~0.00 | 2.74 | 2.69 | 2.63 | 2.57 |

Two things stand out.

**It collapses to zero approaching 60.** Retire at 54 or later and the
reference assumes the portfolio earns *nothing* for the rest of your life. That
is the single harshest assumption in the model, and it is what makes late-ish
early retirement look so much worse than a naive projection would.

**It jumps back at 61.** There is a genuine discontinuity at 60: retire after
60 and the rate returns to ~2.7%. The natural reading is that before 60 the
portfolio has to bridge to the age when pension money becomes reachable, and
that bridge is what is being stress-tested; retire past 60 and there is no
bridge left, so the constraint changes. Interpolation must never cross this
boundary — `decumulation.py` splits the table into two branches.

Confidence moves it as expected — more certainty, less assumed growth:

| confidence | 80 | 85 | 90 | 95 | 100 |
|---|---|---|---|---|---|
| return at FIRE 45 | 2.52 | 2.13 | 1.77 | 1.44 | 1.12 |

## Two rules found while validating it

**The haircut can never raise a return.** With `portfolioInterest = 0`,
confidence 80 and confidence 100 give bit-identical output (`pn_rule80_flat` /
`pn_rule100_flat`). The decumulation return is `min(table, the user's return)`.

**A study fund's hidden fee is accumulation-only.** A `maslulit` fund carries an
extra 0.6 pp beyond the stated management fee while accumulating (notes/05), but
in decumulation only the **stated** fee is charged. Solving each of the four
study-fund fixtures for the implied return recovers the table to within 0.09 pp
under this rule, versus 0.7 pp if the hidden fee is kept — and it takes those
fixtures from the worst in the corpus (16% relative error) to inside 2%.

## Accuracy with no fitted input

Replaying all 63 recorded runs using the table alone:

- median relative error **0.083%**
- 46 of 63 inside 0.5%
- **62 of 63 inside 2%**

The residual is interpolation error: the table is sampled at five confidence
levels and a dozen ages, and real scenarios land between grid points. Denser
sampling would shrink it further; the shape is settled.
