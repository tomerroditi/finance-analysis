# Capital gains after 60 — there is no exemption

## The claim this corrects

notes/03 concluded that "from the month after the 60th birthday, portfolio
withdrawals are **completely untaxed**", and called it "the calculator's choice,
not Israeli law". The observation was right; the interpretation was wrong, and
the wrong version does not generalise.

`fixtures/cf_rise` breaks it outright. That plan retires at 60.08 — already past
60 — and the reference charges capital-gains tax anyway, for another seven
years:

| age | gross withdrawal | tax charged |
|---|---|---|
| 60.08 | 12,841.4 | 62.8 |
| 60.17 | 12,874.3 | 64.3 |
| 61.67 | 13,482.8 | 92.0 |
| 65.83 | 15,329.4 | 183.5 |
| 67.08 | — | **0.0**, and zero from then on |

## The actual rule

From age 60 the reference stops applying the flat 25% and instead taxes the
realised gain as **ordinary income** on the Israeli brackets, less credit
points — capped at 25%. This is real Israeli law: over 60, capital gains are
taxed at the taxpayer's marginal rate when that is lower than the flat rate.

Using the same 2025 brackets and 2.25 credit points the pension agent recovered
(notes/05), the fit is exact:

| scenario | monthly gain | predicted tax | observed |
|---|---|---|---|
| `cf_rise` at 60.08 | 6,072.7 | **62.8** | **62.8** |
| `cf_rise` at 65.83 | 7,204.8 | **183.8** | **183.5** |
| `tax_profit_50` at 60.08 | 3,425.0 | **0.0** | **0.0** |

And that last row is why it *looked* like an exemption: a 5,000/month
withdrawal produces a gain small enough that the brackets and credit points
wipe the tax out entirely. Retire early on a modest income and the tax vanishes
at 60; retire at 60 on a large one and it does not.

From the statutory pension age the extra ~6,110/month exemption (notes/05)
applies on top, which is what finally zeroes `cf_rise` at 67.08.

## Why it matters

Under the "blanket exemption" reading, `cf_rise` missed the reference by
**3,227**. Under the correct reading it misses by **1.53** over 533 months.
The distinction is not cosmetic for anyone retiring at 60+ with a large
portfolio — exactly the audience this calculator serves.

Implemented in `backend/services/fire/israeli_tax.py`. Because the bracket tax
is progressive, the gross-up (sell enough to net X) is no longer closed form
and is solved by bisection; the tax is monotone in the gross, so this is safe.
