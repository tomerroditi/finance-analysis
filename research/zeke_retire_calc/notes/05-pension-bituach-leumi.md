# Pension, Keren Hishtalmut, Bituach Leumi, severance

All claims below cite the fixture that proves them. 27 probes, all prefixed `pn_`.
"Verified" = predicted from a formula and matched the engine's own number to the
displayed precision (charts round to 0.1 ₪). "Consistent with" = fits, not proven.

Reference scenario is `probe.BASE` (male, DOB 1990-01-01, income 10,000, expenses
5,000, one 5%/0.1% withdraw-portfolio of 100,000 with `portfolio_goal1=0`).

---

## 1. Bituach Leumi old-age pension (auto-generated)

**Amount is a constant 2,757.0 ₪/month. Start age = statutory retirement age.**

| fixture | change from BASE | BL row |
|---|---|---|
| `baseline` | — | `מגיל 67 בגובה 2,757.0` |
| `female` | `gender=female` | `מגיל 65 בגובה 2,757.0` |
| `dob_1980` | `dateOfBirth=1980-01-01` | `מגיל 67 בגובה 2,757.0` |
| `pn_bl_income_work` | `incomeSum1=40000`, `work_start_year=2026` | `מגיל 67 בגובה 2,757.0` |
| `pn_bl_partner` | partner P, DOB 1992, female | T: `מגיל 67 … 2,757.0`; P: `מגיל 65 … 2,757.0` |

So the amount is invariant to **gender, date of birth, income level,
`work_start_year`, and the presence of a partner**. Each person gets their own
full 2,757.0 — there is **no spouse increment** and no seniority/deferral
modelling (`pn_bl_partner`).

Start age: **67 for men, 65 for women** born 1990 / 1992 (`baseline`,
`female`, `pn_bl_partner`). This matches Israeli law for women born 1970+.
Payment begins the month *after* the birthday: in `baseline` the
`קיצבת זיקנה` series is 0.0 at age 67.00 and 2,757.0 from age 67.08.

The BL pension is **paid net** — it carries no income-tax and no BL-contribution
row. In `baseline` at age 67.08: `קיצבת זיקנה` 2,757.0 + checking withdrawal
2,243.0 = exactly the 5,000 expense.

### Open questions
- Where 2,757.0 comes from. It is *consistent with* `1,838 × 1.5` (a base
  old-age pension plus the statutory 50 % maximum seniority increment), but
  nothing in the input surface moves it, so the decomposition is **unproven**.
- Female statutory age for cohorts 1960–1969 (the law's 62→65 ramp) was not
  probed — only DOB 1990/1992, both of which give 65.
- Deferral bonus (5 %/yr past statutory age) — never observed; the pension
  always starts exactly at statutory age.

---

## 2. Pension fund accumulation — exact formula

```
factor       = ((1 + pensionInterest) * (1 - pensionFee1)) ** (1/12)
balance[t+1] = (balance[t] + pensionDeposit * (1 - pensionFee2)) * factor
```

Same multiplicative fee convention as portfolios (notes/01). The **deposit fee
`pensionFee2` is taken off the deposit before it lands**, and the net deposit
grows in that same month.

**Verified over 366 monthly steps, max absolute error 0.097 ₪** (pure chart
rounding) — `pn_accum`: balance 100,000, deposit 10,000, interest 7 %,
`pensionFee1=0.5`, `pensionFee2=3.0`, deposits to 2036-09-01.
factor = `(1.07*0.995)**(1/12)` = 1.0052341594.
First month: `(100,000 + 9,700) * 1.0052342 = 110,274.19` vs engine 110,274.2.

### How to read the pension balance out of the charts
It is not plotted directly, but

```
pension_balance[t] = netval_plot[t] - sum(asset_plot series[t])
```

is exact: in `pn_annuity_67` this residual is a flat 1,200,000.00 for every
month up to annuitisation, and drops to exactly 0.0 in the single month the
annuity starts (age 67.08).

`pensionEndType1='to_date'` + `pensionEndDate` gives a deterministic deposit
window: `pn_accum` made 121 deposits (2026-09 … 2036-09 inclusive).

---

## 3. The annuity factor (מקדם קצבה)

The engine prints it, e.g. `(מקדם 197.8 )`. It is **a function of gender and of
the age at which the annuity is claimed** — not a constant.

| gender | claim age | displayed | recovered = balance / total annuity | fixture |
|---|---|---|---|---|
| male | 60 | 224.4 | 1,200,000 / 5,347.2 = **224.413** | `pn_annuity_60` |
| male | 67 | 197.8 | 1,200,000 / 6,066.0 = **197.824** | `pn_annuity_67` |
| female | 60 | 227.3 | 1,200,000 / 5,278.4 = **227.342** | `pn_annuity_60_f` |
| female | 65 | 209.7 | 1,200,000 / 5,721.9 = **209.721** | `pn_annuity_67_f` |

Second, independent recovery of male@67 from `pn_accum` (different balance,
non-zero return and fees): pension balance at age 67.00 = 6,537,171.7, total
annuity 33,045.5 → **197.8233**. Agrees with `pn_annuity_67` to 6 significant
figures.

**Gender matters**: at the same claim age 60, male 224.413 vs female 227.342
(+1.3 %), i.e. women get a *larger* divisor (longer life expectancy).

The factor does **not** depend on the balance (1.2 M and 6.0 M both give 224.4
at 60 — `pn_annuity_60` vs `pn_muk0`) nor on `percentage_mukeret`
(`pn_muk0` and `pn_muk100` both 224.4).

**Open question:** only the endpoints of each gender's curve are known
(male 60 & 67, female 60 & 65) because `pension_tactics` offers only "60" and
"statutory". The shape in between (and whether it is a table lookup or a
formula) is unknown. Linear interpolation of the male curve (3.80 /yr) does not
explain the female value at 65, so the two genders use different tables.

### Component split of the balance
The balance is always split into **four** annuity rows:

```
מוכרת  תגמולים  = balance * (mukeret/100)       * 0.6
מוכרת  פיצויים  = balance * (mukeret/100)       * 0.4
מזכה   תגמולים  = balance * (1 - mukeret/100)   * 0.6
מזכה   פיצויים (מעסיק נוכחי) = balance * (1 - mukeret/100) * 0.4
```

Verified in `pn_annuity_67` (`percentage_mukeret=30`, total annuity 6,066.0):
1,091.9 / 727.9 / 2,547.7 / 1,698.5 = 0.18 / 0.12 / 0.42 / 0.28 × 6,066.0.
The 60/40 tagmulim/severance split is **hard-coded** — it did not move with
`percentage_mukeret` (`pn_muk0`: 16,041.6 / 10,694.4 = 0.6 / 0.4 of 26,735.9).

---

## 4. `pension_tactics`

| value | behaviour | FIRE age (1.2 M pension, `pension_tactics` the only change) |
|---|---|---|
| `60` | **entire** balance annuitised at 60, factor@60 | 47.1 (`pn_annuity_60`) |
| `60-67` | *mukeret* share at 60 @factor60, *mezake* share at statutory age @factor67 | 49.0 (`pn_annuity_6067`) |
| `67` | **entire** balance annuitised at statutory age, factor@statutory | 50.0 (`pn_annuity_67`) |

`60-67` is exactly the union of the other two, row for row:
its mukeret rows are 962.5 / 641.7 @ 224.4 — identical to `pn_annuity_60`;
its mezake rows are 2,547.7 / 1,698.5 @ 197.8 — identical to `pn_annuity_67`.
Verified to the shekel.

Earlier annuity ⇒ earlier FIRE (shorter bridge to fund), at the cost of a
larger divisor.

---

## 5. Tax treatment of the annuity — `percentage_mukeret`

Charts distinguish two income series `מוכרת` (recognised) and `מזכה`
(entitling), and expense series `מס הכנסה` and `ביטוח לאומי`.

### 5a. The recognised annuity (`מוכרת`) is 100 % income-tax-free, at every age
`pn_muk100` (6 M balance, `percentage_mukeret=100`, annuity 26,735.9 from age
60) has **no `מס הכנסה` expense series at all** — before or after 67.
`pn_muk0` (same balance, mukeret 0) does.

### 5b. The entitling annuity (`מזכה`) is ordinary income — 2025 brackets, 2.25 credit points

`pn_muk0`, ages 60–67, annuity 26,735.9, observed income tax **5,255.0/month**.

Monthly 2025 brackets (10 % ≤7,010; 14 % ≤10,060; 20 % ≤16,150; 31 % ≤22,440;
35 % ≤46,690):
`701.0 + 427.0 + 1,218.0 + 1,949.9 + 1,503.565 = 5,799.465`
minus credit `2.25 × 242 = 544.5` → **5,254.965 → 5,255.0**. Verified.

(The **2026** brackets do *not* fit — they would give 5,379.565 gross and a
residual of 124.6, not a whole number of credit points. The engine is on the
2025 table.)

### 5c. From statutory age a flat monthly exemption of ≈ 6,110 ₪ applies to `מזכה`

Two independent fits:

| fixture | mezake annuity from 67 | observed tax | implied exemption |
|---|---|---|---|
| `pn_muk0` | 26,735.9 | 3,189.0 | 6,110.2 |
| `pn_accum` | 23,131.8 | 2,071.8 | 6,110.0 |

Using **6,110.0** flat reproduces both to 0.1 ₪:
`tax(26,735.9−6,110) − 544.5 = 3,189.03` and
`tax(23,131.8−6,110) − 544.5 = 2,071.76`.

The exemption is a **fixed shekel amount, not a percentage** (6,110/26,735.9 =
22.9 % vs 6,110/23,131.8 = 26.4 %). It is *consistent with* 67 % × 9,120 =
6,110.4 (the post-2025 exemption rate on the 2023 קצבה מזכה ceiling), but
6,110.4 is ~0.3 ₪ outside the tightest fit — call it **6,110 ± 0.4**.

The recognised annuity does **not** consume this exemption: `pn_accum` has a
9,913.6 mukeret annuity alongside, and the mezake part still receives the full
6,110.

Cross-check on small annuities: `pn_annuity_67` (mezake 4,246.2 from 67) and
`pn_annuity_60` (mezake 3,743.0 from 60) both emit **no** `מס הכנסה` row —
4,246.2 < 6,110 exemption, and `tax(3,743.0) = 374.3 < 544.5` credit.

### 5d. Bituach Leumi *contributions* on the annuity — two-tier, verified

Charged on the **whole** annuity (mukeret included — `pn_muk0` and `pn_muk100`
both pay 2,592.3), and **only before statutory retirement age** (the row
disappears at 67 in every fixture; `pn_annuity_67` never has one).

```
contribution = 4.25 %  on the first 7,703.4 ₪/month
             + 11.90 % on the excess
```

| fixture | annuity | predicted | observed |
|---|---|---|---|
| `pn_annuity_6067` | 1,604.2 | 68.18 | 68.2 |
| `pn_annuity_60` | 5,347.2 | 227.26 | 227.3 |
| `pn_bl_contrib_mid` | 11,999.8 | 838.67 | 838.7 |
| `pn_muk0` / `pn_muk100` | 26,735.9 | 2,592.26 | 2,592.3 |

The two rates were solved from the last two rows (`r2 = 1,753.6/14,736.1 =
11.8999 %`), the threshold then from the third (`7,703.6`, ±1.3 given chart
rounding). 7,703.4 = 60 % × 12,839 — i.e. 60 % of an average wage of ~12,839 ₪,
the usual Israeli reduced-rate cut-off. **All four points verified.**

Portfolio and Keren-Hishtalmut withdrawals attract **no** BL contribution
(`pn_annuity_67` ages 50–67 has no `ביטוח לאומי` series at all).

---

## 6. `retireRule` — it is a return haircut on the *decumulation* phase

`retireRule < 80` is rejected server-side: `pn_rule_70` returns
`calc_success=false` with `הזן אחוז ביטחון לא נמוך מ-80%`.

**Mechanism (established).** The accumulation phase always uses the user's full
return; the **post-FIRE withdrawal phase uses a lower, confidence-derived
return**. Fitted month-over-month from `asset_plot` and the withdrawal series
(`b[t] = (b[t-1] - withdrawal[t]) * f`):

`pn_rule80_pf` and `pn_rule100_pf` (5 % / 0.1 % portfolio, all surplus routed
into it via `portfolio_goal1=99000000`, 1.2 M pension at 67):

- accumulation factor, **both** runs: 1.00399047 = `((1.05)(0.999))**(1/12)` — the user's 5 %.
- decumulation factor: rule 80 → 1.00166550, rule 100 → 1.00018763.

Recovered table (portfolioInterest = 5 %, fee 0.1 %, bridge = FIRE → 67):

| `retireRule` | FIRE age | bridge yrs | decum. monthly factor | implied gross annual return | fixture |
|---|---|---|---|---|---|
| 80 | 47.6 | 19.42 | 1.00166550 | **2.119 %** | `pn_rule80_pf` |
| 85 | 47.8 | 19.17 | 1.00126984 | **1.636 %** | `pn_rule85_pf` |
| 90 | 48.1 | 18.92 | 1.00088937 | **1.174 %** | `pn_rule90_pf` |
| 95 | 48.3 | 18.67 | 1.00052330 | **0.731 %** | `pn_rule95_pf` |
| 100 | 48.5 | 18.50 | 1.00018763 | **0.326 %** | `pn_rule100_pf` |

(implied return `r` from `f**12 = (1+r)(1-0.001)`.)

Three structural facts:

1. **It is proportional to nothing — it vanishes at zero return.** With
   `portfolioInterest1=0`, `retireRule=80` and `retireRule=100` produce
   *bit-identical* results (`pn_rule80_flat` / `pn_rule100_flat`: both FIRE
   01/2041, age 51.0, identical netval series).
2. **It is not a fixed fraction of the return either.** At
   `portfolioInterest1=10 %`, rule 80 gives 2.419 % (`pn_rule80_i10`) — ratio
   0.242, versus 0.424 at 5 %. Concave in the input return.
3. **It depends on the horizon.** At the same `retireRule=85`:
   `baseline` (FIRE 53.2, bridge to BL at 67 = 13.8 y) → 0.025 %;
   `pn_annuity_67` (FIRE 50.0, bridge 17.0 y) → 1.07 %;
   `pn_rule85_pf` (bridge 19.2 y) → 1.636 %. Longer horizon → higher supported
   return, as a Trinity-style table would give.

**Correction to notes/01.** `retireRule` was not inert in the pension-free
baseline — it *did* change the decumulation factor there (0.99993722 at rule 85
vs 0.99991933 at rule 100). It simply failed to move the retirement date,
because with `portfolio_goal1=0` the whole bridge was funded by 0 %-return cash
and only the last 7.8 years touched the portfolio.

**Open question:** the exact table. Confidence, horizon and the input return all
enter, and a constant-σ lognormal-percentile model does **not** fit (implied σ
would be 11.1 % / 12.2 % / 13.9 % for the three rule-85 points above). It is
most likely a lookup table interpolated on (confidence, years).

---

## 7. Severance (`withdraw_pizuim` + `work_start_year`)

**What is redeemed:** only the `פיצויים מזכה מעסיק נוכחי` component, i.e.
`balance × (1 − mukeret/100) × 0.4`. With balance 1.2 M and mukeret 30 that is
**336,000.0** — and the annuity list loses exactly that row (total annuity
drops 6,066.0 → 4,367.5 = 1,091.9 + 727.9 + 2,547.7). The *recognised*
severance component (727.9) is **not** redeemed. Redemption happens one month
after FIRE.

**Exempt ceiling = 13,300 ₪ × (redemption year − `work_start_year`).**

| fixture | `work_start_year` | redeemed | exempt | taxable |
|---|---|---|---|---|
| `pn_pizuim_2010` | 2010 | 04/2037, 336,000.0 | 336,000.0 (cap 27 × 13,300 = 359,100) | 0 |
| `pn_pizuim_2026` | 2026 | 05/2037, 336,000.0 | **146,300.0** = 11 × 13,300 | 189,700.0 |

**Cost of the exempt part — the offset formula (נוסחת הקיזוז), verified:**
the engine prints `תיקרת הפטור החודשי קטנה אחרי גיל פרישה ב-X`, with

```
X = exempt_severance * 1.35 / 180
```

336,000 × 1.35/180 = **2,520.0** (engine: 2,520.0);
146,300 × 1.35/180 = **1,097.25** (engine: 1,097.2). Verified.

**Tax on the taxable part — spread (פריסה) over 2 years, verified to the agora.**
`pn_pizuim_2026`: 189,700 / 24 = 7,904.167 ₪/month treated as ordinary income;
2025 brackets `701.0 + 0.14 × 894.167 = 826.183`, minus 544.5 credit =
**281.68**. The `מס הכנסה` expense series is exactly **281.7 for 24 consecutive
months** (ages 47.33 → 49.25) and 0 before and after.

Both lump sums arrive in the checking account at **face value** (the summary
says `נטו פידיון אחרי מס 189,700.0 ₪ נפדו 189,700.0 ₪`); the tax is billed
separately as the monthly expense row above.

**Open question:** the 2-year spread. Israeli law allows one tax year per 4
years of service (max 6); `floor(11/4) = 2` fits, but there is only one data
point. Also untested: whether the 13,300 ₪/yr ceiling is additionally capped by
the last salary (the real-world rule is `min(last salary, ceiling)`), and
whether `work_start_year` has any effect at all when `withdraw_pizuim` is off
(`pn_bl_income_work` set it to 2026 with no visible effect anywhere).

---

## 8. Keren Hishtalmut

**Adding a row needs no `add_line` call** — sending `num_keren_fields=1` plus
`kerenBalance1` / `kerenDeposit1` / `kerenInterest1` / `kerenType1` /
`kerenFee1` / `kerenEndType1` as plain form fields is enough
(`pn_keren_maslulit`). The row shows up as its own `שווי קרן השתלמות` asset
series and its own `משיכה מקרן השתלמות` income series.

**Growth law — same multiplicative convention, but `maslulit` pays 0.6 pp extra.**

```
effective_fee = kerenFee1                 if kerenType1 == 'ira'
              = kerenFee1 + 0.6           if kerenType1 == 'maslulit'
monthly factor = ((1 + kerenInterest) * (1 - effective_fee)) ** (1/12)
```

| fixture | type | `kerenFee1` | fitted monthly factor | implied annual | implied total fee |
|---|---|---|---|---|---|
| `pn_keren_masl_fee0` | maslulit | 0.0 | 1.00357069 | 1.043700 | **0.6 %** |
| `pn_keren_maslulit` | maslulit | 0.6 | 1.00306451 | 1.037400 | **1.2 %** |
| `pn_keren_masl_fee12` | maslulit | 1.2 | 1.00255546 | 1.031100 | **1.8 %** |
| `pn_keren_ira` | ira | 0.6 | 1.00357069 | 1.043700 | **0.6 %** |

(interest 5 % in all four; `1.0437 = 1.05 × 0.994`, `1.0374 = 1.05 × 0.988`,
`1.0311 = 1.05 × 0.982`.) So it is an **additive 0.6 pp**, not a doubling —
`kerenFee1=0` under `maslulit` still costs 0.6 %.

Effect on FIRE (500,000 KH, no portfolio, otherwise BASE): maslulit@0.6 → 47.2;
IRA@0.6 → 46.8; maslulit@0.0 → 45.9; maslulit@1.2 → 48.7.

The engine itself surfaces `המלצות מערכת שנבחנות: העברת קרנות השתלמות ל-IRA`
whenever the type is `maslulit` (`pn_keren_maslulit`, `pn_keren_masl_fee0`) and
not for `ira` — consistent with the 0.6 pp being the only difference found.

**Withdrawals are entirely tax-free.** In `pn_keren_maslulit` the KH is drawn
from age 58.0 to 81.0 after growing from 500,000 (so it is nearly all
unrealised gain), and the expense chart has only two series —
`['הוצאות שוטפות', 'הוצאה לא מתוכננת']`. No tax row of any kind. Contrast a
taxable portfolio, which always emits `מס על רווחי תיק …` while being drawn
(e.g. `pn_rule80_pf`: 363.5 ₪/month of capital-gains tax on a 5,000 ₪ expense).
Nothing in the model represents the 6-year seasoning rule.

**Open question:** `maslulit` vs `ira` showed **no** difference other than the
0.6 pp fee — no tax difference, no deposit cap, no liquidity rule.

---

## 9. Reading the charts (mechanics learned here)

- `netval_plot − Σ asset_plot` = the pension-fund balance (exact).
- The income chart carries the **gross** annuity, split into `מוכרת` / `מזכה`
  series plus `קיצבת זיקנה` for Bituach Leumi.
- The expense chart gains series on demand: `מס הכנסה`, `ביטוח לאומי`,
  `מס על רווחי תיק …`, `הפקדה לתיק …`. A series is absent when it is zero
  for the whole run — its absence is itself evidence.
- `הוצאה לא מתוכננת` is **not** an expense: it is the residual plug that makes
  `Σ income = Σ expense` each month, i.e. the money that was *not* spent.
  In `pn_keren_maslulit` at age 36.83 it is 5,000 while cash rises 5,000/month.
