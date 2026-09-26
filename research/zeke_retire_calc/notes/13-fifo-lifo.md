# FIFO / LIFO — solved

> **This note previously claimed the synthetic-lot hypothesis was disproved.
> That claim was wrong, and the error was mine.** The disproof grew the lots at
> the *accumulation* rate for the whole horizon, but a withdrawal portfolio
> switches to the decumulation rate at retirement (notes/07). With the correct
> two-phase growth the hypothesis fits. The old reasoning is kept at the bottom
> as a caution.

## The model

The reference has no real purchase history — the user types a balance and a
profit fraction — so it manufactures one: the opening balance is a run of
**equal-basis monthly purchases**, the newest bought *last* month and the
oldest `N` months ago, each grown at the portfolio's own rate since. `N` solves

```
sum(f**a for a in range(1, N + 1)) == N / (1 - profit_fraction)
```

giving 315 lots at 50% profit and 907 at 90% (5% portfolio). Deposits append
lots bought at par. FIFO sells from the front, LIFO from the back, and the
realised gain is taxed by the same age-aware rules as everything else
(notes/11).

## Where the ladder starts is unobservable; how long it is, is not

The lots are rescaled to the stated opening balance, and shifting every age by
a constant is exactly undone by that rescale — so no observable distinguishes
"newest bought today" from "newest bought a year ago". Sweeping a constant
offset confirms it: the replay does not move by an agora.

`N` is a different matter, and the corpus reads it directly. Sweeping the
ladder length against the reference's own monthly tax rows:

| ladder | `pf_fifo` | `pf_fifo_nodep` | `pf_fifo_p90` | `pf_lifo` | `lot_lifo_nodep` |
|---|---|---|---|---|---|
| `N − 2` | 1.26 | 1.21 | 0.11 | 1.68 | 1.87 |
| **`N − 1` (`a` from 1)** | **1.50** | **1.83** | **0.06** | **1.32** | **1.72** |
| `N` (`a` from 0) | 2.15 | 2.58 | 0.14 | 3.32 | 3.77 |
| `N + 1` | 2.82 | 3.31 | 0.22 | 5.83 | 6.60 |

Summing the ladder from `a = 1` rather than `a = 0` is one lot shorter at 50%
profit and one shorter at 90%, and it halves the worst tax disagreement on
every fixture with a synthetic history — while leaving the two `*_known`
fixtures, which have none, at the reference's display precision either way.
`N − 2` splits the difference and has no derivation behind it, so the sum from
1 is what ships. Over the full horizon the change takes the four worst asset
residuals from 63/53/80/113 shekels down to 36/39/49/54.

## Evidence

The decisive experiment was a portfolio starting at **zero** balance, so there
is no synthetic history at all and every lot is a deposit we know exactly
(`lot_fifo_known`, `lot_lifo_known`). LIFO's first withdrawal there is taxed on
`1 − 1/f = 0.00397` — precisely one month of growth on the newest deposit.

Replaying the reference's own gross withdrawals through the model, with one
fitted decumulation rate per scenario:

| fixture | method | lots | worst monthly Δtax |
|---|---|---|---|
| `lot_fifo_known` | FIFO | known deposits only | **0.05** |
| `lot_lifo_known` | LIFO | known deposits only | **0.05** |
| `pf_fifo_p90` | FIFO | 908 synthetic | 0.08 |
| `pf_fifo` | FIFO | 316 synthetic + deposits | 1.72 |
| `pf_fifo_nodep` | FIFO | 316 synthetic | 1.95 |
| `pf_lifo` | LIFO | 316 synthetic + deposits | 2.19 |
| `lot_lifo_nodep` | LIFO | 316 synthetic | 3.09 |

Seven scenarios across both methods, with and without deposits, at 50% and 90%
profit. The two `*_known` fixtures match to 5 agorot — the reference's own
display precision — and they are the ones with no synthetic history to guess
at, which is what makes them decisive about the *mechanics* rather than the
manufactured history.

## The mistake, kept as a caution

The earlier disproof measured "the age of the lot being consumed" from each
withdrawal's taxable fraction, using `p = 1 − f^-age` with `f` the accumulation
factor. Post-retirement the portfolio grows far more slowly, so that inversion
attributed far too much age to every lot, made the pool look like it rotated at
0.74 lots a month instead of ~1.2, and produced an "impossible" lot size of
~5,050 against a model floor of ~8,100. Every number in that argument was
arithmetically right and the conclusion was still wrong, because the growth
rate fed into it was wrong.

The lesson worth keeping: when inverting an observable to recover a hidden
parameter, the inversion inherits every assumption of the forward model. Here
the forward model had a regime change in it that the inversion did not.
