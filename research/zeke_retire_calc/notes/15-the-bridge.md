# The bridge — what the decumulation surface is actually read on

notes/14 measured the surface as a function of `(retireRule, retirement age)`.
That was the right shape but the wrong key. The surface is read on the
**bridge**: how long the withdrawal portfolio must last before pension money
starts arriving. Four facts, each from a decisive fixture.

## 1. The bridge ends at the statutory age, not at a fixed one

`female` — a woman retiring at 52.75 — is reproduced only if she reads the
curve at `65 - 52.75`, not `67 - 52.75`. Under the old age-keyed table it was
the fourth-worst fixture in the corpus (3.7% out); on the bridge it is exact.
Everything else in the corpus is male, which is why this went unnoticed: for a
man the two keys differ by a constant and the table absorbed it.

## 2. Retiring past 60 lands on the same curve, shifted

The rate collapses to zero by 54 and stays there to 60, then jumps back to
~2.7% at 61 (notes/14). Those post-60 points are not a second surface: invert
the pre-60 curve on them and they sit at `bridge + 23.45` years, with the shift
constant to ±0.035 across all four measured ages, and the same shift reproduces
the 62.08 point at every one of the five confidence levels. So the whole
surface is one curve per confidence, sampled twice.

The switch happens between 60.08 (still collapsed) and 61.08 (already back), a
gap the fixtures cannot narrow; `BRANCH_AGE` sits at the midpoint.

## 3. A pension claimed early shortens the bridge — weighted by what it pays

`pension_tactics` moves the claim age, and the surface follows:

| fixture | claim structure | measured rate | plain statutory bridge |
|---|---|---|---|
| `pn_annuity_60` | all at 60 | 0.0007 | would give 1.85 |
| `pn_annuity_6067` | 30% at 60, rest at 67 | 0.9776 | would give 1.356 |
| `pf_mukeret_ref` | couple, both all at 60 | 1.7239 | would give 2.60 |

The rule that fits all three is a **weighted average of the rate each stream's
own bridge implies**, weighted by the monthly annuity each pays:

```
rate = Σ pay_i · surface(start_i - retirement) / Σ pay_i
```

- `pn_annuity_60`: one wait, to 60 → 0.0006 against 0.0007 measured.
- `pf_mukeret_ref`: four streams, all at 60 → 1.7233 against 1.7239.
- `pn_annuity_6067`: 1,604.2/month from 60 and 4,246.2/month from 67 → 0.9841
  against 0.9776 — inside the surface's own interpolation error there.

Two variants are ruled out by the same three runs. Averaging the *ages* and
reading the surface once gives 0.748 for `pn_annuity_6067` against 0.9776 — the
curve is far too convex for that. Including the state pension in the weights
gives 0.61 for `pn_annuity_60` against 0.0007: Bituach Leumi does not count,
only the annuities the plan itself converts.

## 4. Bituach Leumi pays a spouse increment

Not a bridge fact, but it surfaced while chasing one. In `pf_mukeret_ref` the
wife's old-age pension is **4,143.0** from her 65th birthday and **2,757.0**
from his 67th — she is paid for two people for exactly the 24 months in
between. The increment is 1,386.0, and it is not means-tested: her husband is
drawing a 24,000/month pension throughout that window.

Missing it left a 33,314 shekel hole in that fixture — 1,386.2 a month for 24
months, riding along in the checking account to the end of the horizon. With it
the fixture replays to 50 shekels.

`pn_bl_partner` is the control: a man born 1990 and a woman born 1992 reach
their claim ages in the same month, so no window opens and no increment is
paid. It matched before this change and still does.

## What is still open: a gemel converted at 60

Three fixtures — `pf_mukeret2`, `pf_mukeret3_t60`, `pf_mukeret4_order` — miss by
93k–158k. All three, and only they, hold a **gemel portfolio earmarked
`mukeret_*`**, which converts to a recognised annuity at 60.

The rate each one needs, fitted against its own withdrawal portfolio to five
agorot, does not follow rule 3:

| fixture | streams | rate needed | rule 3 gives |
|---|---|---|---|
| `pf_mukeret2` | 5,153.9@60, 10,915.4@60 (gemel), 21,830.3@67 | 2.7182 | 2.5319 |
| `pf_mukeret3_t60` | 5,153.9@60, 12,025.8@60, 10,915.4@60 (gemel) | 2.5201 | 2.2104 |
| `pf_mukeret4_order` | couple, four at 60 (two gemel), 18,004.1@65, 21,830.3@67 | 2.5615 | 2.4831 |

`pf_mukeret3_t60` is the sharpest statement of the problem: **every** annuity in
it starts at 60, yet the rate it needs is the one a bridge of 25.7 years buys,
not the 22.7 years to its own 60th birthday. Something in the plan is still
being waited for. `pf_mukeret_ref` is the control — same couple, same
all-at-60 claim, no gemel — and it is exact.

Counting the gemel conversions at the statutory age instead of at 60 fits two
of the three much better (2.6830 and 2.4188, and the total absolute error over
the corpus drops from 0.58 to 0.23 points) but pushes `pf_mukeret4_order` past
the truth in the other direction, so it is not the rule either. It is recorded
here because it is the best lead: whoever probes the reference next should
sweep gemel balance against the implied rate at a fixed retirement age, which
separates "the gemel is weighted differently" from "the gemel is waited for".

Until then the engine uses rule 3 — the reading the annuity chart supports,
since those annuities really are paid from 60 — and the three fixtures carry
explicit bounds in `test_reference_parity.KNOWN_GAPS`.
