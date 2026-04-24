# Bank of Israel — Key Interest Rate History

Companion reference to the main `SKILL.md`. Use this when reasoning about anything tied to the Bank of Israel's benchmark rate: mortgage-prime loans, savings-plan yields, Keren Hishtalmut's bond tracks, fixed-rate investment comparisons, or the realism of demo data covering a given year.

> **Caveats**
> - Figures are pulled from reputable secondary sources (see links at the bottom). For authoritative or legal use, verify against the Bank of Israel website.
> - "Prime" in everyday Israeli banking conversations is **`BoI rate + 1.5%`**. A lot of consumer lending (mortgages, credit lines, overdrafts) is quoted as "prime − X" or "prime + X". Keep track of whether you mean the **BoI rate** or the **prime rate** — the 1.5% spread is constant but the absolute numbers aren't the same.
> - Rate decisions happen 6–8 times per year, usually on Monday evenings. The list below shows the **decision date** and the **new rate**; between decisions the rate is unchanged.

---

## 1. BoI key rate — annotated timeline (2020 → present)

| Decision date | New rate | Delta | Context |
|---|---:|---:|---|
| **Apr 2020** | **0.10%** | −0.15 | COVID emergency cut from 0.25% → 0.1% (record low). |
| (held) | 0.10% | 0.00 | Unchanged for ~2 years — 8 "no-change" decisions in 2021 alone. |
| **Apr 11, 2022** | **0.35%** | +0.25 | First hike of the cycle, in response to inflation above 5%. |
| **May 23, 2022** | **0.75%** | +0.40 | |
| **Jul 4, 2022** | **1.25%** | +0.50 | |
| **Aug 22, 2022** | **2.00%** | +0.75 | Biggest single hike in two decades. |
| **Oct 3, 2022** | **2.75%** | +0.75 | |
| **Nov 21, 2022** | **3.25%** | +0.50 | End of 2022 at 3.25%. |
| **Jan 2, 2023** | **3.75%** | +0.50 | |
| **Feb 20, 2023** | **4.25%** | +0.50 | |
| **Apr 3, 2023** | **4.50%** | +0.25 | |
| **May 22, 2023** | **4.75%** | +0.25 | **Peak of the cycle.** |
| (held) | 4.75% | 0.00 | Held through Oct, Nov, Dec 2023 despite the war outbreak. |
| **Jan 1, 2024** | **4.50%** | −0.25 | First cut in nearly 2 years; flagged as cautious. |
| (held) | 4.50% | 0.00 | Held through all of 2024 and most of 2025. |
| **Nov 24, 2025** | **4.25%** | −0.25 | Cut after Hamas ceasefire, first move since Jan 2024. |
| **Jan 5, 2026** | **4.00%** | −0.25 | Surprise cut, second straight. |
| **Mar 2026** | 4.00% (held) | 0.00 | Inflation picked up; committee paused further cuts. |

## 2. Year-end snapshots

| Year end | BoI rate | "Prime" rate (BoI + 1.5%) | Notes |
|---:|---:|---:|---|
| 2019 | 0.25% | 1.75% | Pre-COVID low. |
| 2020 | 0.10% | 1.60% | COVID emergency cut in April. |
| 2021 | 0.10% | 1.60% | Unchanged all year. |
| 2022 | 3.25% | 4.75% | Rapid tightening from April onward. |
| 2023 | 4.75% | 6.25% | Peak; held from May through year-end. |
| 2024 | 4.50% | 6.00% | One cut in January, held the rest of the year. |
| 2025 | 4.25% | 5.75% | One cut in November (post-ceasefire). |
| 2026 (current) | 4.00% | 5.50% | January cut; held at March meeting. |

## 3. Rates BoI forecasts / consensus

Per BoI's current (early-2026) macroeconomic forecast, the rate is projected to fall by a cumulative ~0.5% to roughly **3.5% by end-2026**, assuming a stable geopolitical environment. This is a projection, not a commitment — committee votes move with inflation prints and FX pressure.

## 4. How the BoI rate feeds into products seen in this project

- **Mortgage prime-linked tracks**: the "Prime" column above is what banks charge on prime-linked mortgage portions (usually 33% of the loan). A user with a prime − 0.5% loan is currently paying 5.00%.
- **Mortgage fixed tracks** (קבוע צמוד / קבוע לא צמוד): set at origination and don't follow BoI changes afterwards. But the **origination** rate is sensitive to where BoI sits at the time the loan closed — a mortgage originated in 2020 has a much lower fixed rate than one originated in 2023.
- **Savings plans (פק"ם, פיקדון)**: bank deposits often track BoI with a spread. When demo data models a savings plan with a fixed yield, the yield should be realistic for the year the deposit was made (e.g. a 2021-era savings plan at 4.2% would be implausibly high — it would more likely be 0.5% — whereas in 2023 that yield is conservative).
- **Keren Hishtalmut / Pension bond tracks**: these follow government-bond yields (slightly above BoI rate). When setting demo yield_pct on "Bonds Track", use something close to the year-end BoI rate + a small spread.
- **Consumer credit / overdrafts**: usually prime + X%, so tracked rates are higher than mortgage prime figures.
- **Car loans**: typically fixed at origination at something in the range `prime + 2% ... prime + 5%` depending on credit profile.

## 5. Sanity-check table for demo investments

When writing demo data for a savings plan or investment that spans multiple years, the yield should follow the rate regime of its period. Rough ranges that feel realistic:

| Investment type | 2020-2021 | 2022 | 2023 | 2024-2026 |
|---|---:|---:|---:|---:|
| Bank savings plan (פק"ם, fixed-rate) | 0.3–1.5% | 1–3% | 3.5–5% | 3.5–5% |
| Israeli government bonds (medium duration) | 0.5–1.5% | 2–4% | 4–5% | 4–4.5% |
| Corporate bond (investment grade) | 2–3% | 3–5% | 5–7% | 5–7% |
| Pension bonds track | 1–3% | 2–4% | 3–5% | 3.5–5% |
| Pension equity / S&P 500 track | 8–15% (bull market) | −15% to 0% | +20% | 6–12% (long-term avg) |
| Mortgage prime track (borrower pays) | 1.5–2% | 1.5→5% (rising) | 5–6% | 5–6% |

If a demo sets a 2020 savings plan at 4.2%, it looks implausible — BoI was 0.1% and no consumer fixed-rate product was paying 4%+. Align yields to the **decade of origination**, not the current rate.

## Sources

- [Bank of Israel — BOI Interest Rate and Monetary Tools (official)](https://www.boi.org.il/en/economic-roles/statistics/boi-interest-rate-and-the-monetary-tools/boi-interest-rate-and-the-monetary-tools/)
- [Bank of Israel — Monetary Policy (official)](https://www.boi.org.il/en/economic-roles/monetary-policy/)
- [Global-Rates — Israeli Key Interest Rate history](https://www.global-rates.com/en/interest-rates/central-banks/18/israeli-key-interest-rate/)
- [Trading Economics — Israel Interest Rate](https://tradingeconomics.com/israel/interest-rate)
- [Statista — Israel monthly central bank interest rate 1994-2024](https://www.statista.com/statistics/1475575/israel-monthly-central-bank-interest-rate/)
- [Times of Israel — Rate decisions timeline (2022–2026)](https://www.timesofisrael.com/bank-of-israel-hikes-key-lending-rate-for-sixth-time-in-2022-to-tame-inflation/)
- [Times of Israel — Jan 2026 second consecutive cut](https://www.timesofisrael.com/in-bold-move-central-bank-cuts-interest-rates-for-2nd-straight-time-after-ceasefire/)
- [Haaretz — BoI surprise 4% cut Jan 2026](https://www.haaretz.com/israel-news/2026-01-05/ty-article/.premium/bank-of-israel-lowers-benchmark-interest-rate-by-0-25-to-4-percent-in-surprise-move/0000019b-8fd1-d4fc-a3bb-fff1a5f90000)
- [FocusEconomics — Israel BoI interest rate](https://www.focus-economics.com/country-indicator/israel/interest-rate/)
