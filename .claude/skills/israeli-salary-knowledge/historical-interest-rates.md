# Bank of Israel — Key Interest Rate History (2000 → present)

Companion reference to the main `SKILL.md`. Use this when reasoning about anything tied to the Bank of Israel's benchmark rate: mortgage-prime loans, savings-plan yields, Keren Hishtalmut's bond tracks, fixed-rate investment comparisons, or the realism of demo data covering a given year.

> **Confidence & caveats**
> - Data for **2000–2012** is stitched together from secondary sources and BoI narrative mentions; individual month-by-month resolution in that era is lower. Year-end / peak figures are reliable to ~0.25 pp.
> - Data for **2013–present** is high-confidence (covered by multiple live data providers and BoI press releases).
> - For authoritative values go straight to the BoI — the "Useful reference sources" section at the bottom lists their live page plus the FRED and global-rates mirrors.
> - "Prime" in everyday Israeli banking is **`BoI rate + 1.5%`**. Consumer lending (mortgages, overdrafts) is quoted as "prime − X" / "prime + X". The 1.5% spread is constant; the absolute numbers move with BoI.
> - Rate decisions happen ~8 times a year (typically Monday evenings). Between decisions the rate is unchanged.

---

## 1. Year-end BoI key rate + governor context (2000 → present)

Approximate year-end rate. Where a year had a major within-year swing (2002, 2008, 2009, 2022), the swing is noted.

| Year | Governor | Rate (year-end) | Prime (+1.5%) | Context |
|---:|---|---:|---:|---|
| 2000 | David Klein | 8.2% | 9.7% | Gradual easing from the high-rate 1990s. |
| 2001 | Klein | 5.6% (Dec) | 7.1% | Aggressive cuts. Dropped sharply that December. |
| 2002 | Klein | 9.1% | 10.6% | Klein cut to 3.8% in Jan, but inflation & ILS depreciation forced a reversal: hiked to 9% by year-end. |
| 2003 | Klein | 5.25% | 6.75% | Rabinovich tax reform + rate easing as situation stabilised. |
| 2004 | Klein | 3.7% | 5.2% | Continued disinflation → cuts. |
| 2005 | Klein → Stanley Fischer (May) | 4.5% | 6.0% | Fischer inherited rising-rate phase. |
| 2006 | Fischer | 4.5% | 6.0% | |
| 2007 | Fischer | 4.0% | 5.5% | |
| 2008 | Fischer | 2.5% | 4.0% | Global Financial Crisis — aggressive cuts starting Oct 2008. |
| 2009 | Fischer | 1.25% | 2.75% | Hit record low 0.5% in April; Fischer began hiking in Sept (first major central bank to hike post-GFC). |
| 2010 | Fischer | 2.0% | 3.5% | Gradual normalisation. |
| 2011 | Fischer | 2.75% | 4.25% | Peaked at ~3.25% mid-year, then cut. |
| 2012 | Fischer | 2.0% | 3.5% | |
| 2013 | Fischer → Karnit Flug (Nov) | 1.0% | 2.5% | Cuts resumed mid-year. Flug took over. |
| 2014 | Flug | 0.25% | 1.75% | Rapid cuts to fight deflation. |
| 2015 | Flug | 0.1% | 1.6% | Hit effective zero. |
| 2016 | Flug | 0.1% | 1.6% | Unchanged all year. |
| 2017 | Flug | 0.1% | 1.6% | Unchanged. |
| 2018 | Flug → Amir Yaron (Dec) | 0.25% | 1.75% | Single 0.15 pp hike at year-end under Yaron. |
| 2019 | Yaron | 0.25% | 1.75% | Held. |
| 2020 | Yaron | 0.1% | 1.6% | COVID emergency cut April 2020. |
| 2021 | Yaron | 0.1% | 1.6% | Unchanged — 8 "no-change" decisions that year. |
| 2022 | Yaron | 3.25% | 4.75% | 6 hikes between Apr and Nov. |
| 2023 | Yaron | 4.75% | 6.25% | Peak of the cycle. Held through the war year. |
| 2024 | Yaron | 4.5% | 6.0% | Single Jan-2024 cut, then held. |
| 2025 | Yaron | 4.25% | 5.75% | Cut once in Nov (post-ceasefire). |
| 2026 | Yaron | 4.00% (current) | 5.50% | Jan-2026 cut; March meeting held. |

## 2. Recent-era decision timeline (2020 → present)

The granular list (kept from the previous version of this doc) for anyone reasoning about changes inside the last rate cycle:

| Decision date | New rate | Delta | Context |
|---|---:|---:|---|
| **Apr 2020** | **0.10%** | −0.15 | COVID emergency cut from 0.25% → 0.1% (record low). |
| (held) | 0.10% | 0.00 | Unchanged for ~2 years. |
| **Apr 11, 2022** | **0.35%** | +0.25 | First hike of the cycle. |
| **May 23, 2022** | **0.75%** | +0.40 | |
| **Jul 4, 2022** | **1.25%** | +0.50 | |
| **Aug 22, 2022** | **2.00%** | +0.75 | Biggest single hike in two decades. |
| **Oct 3, 2022** | **2.75%** | +0.75 | |
| **Nov 21, 2022** | **3.25%** | +0.50 | End of 2022. |
| **Jan 2, 2023** | **3.75%** | +0.50 | |
| **Feb 20, 2023** | **4.25%** | +0.50 | |
| **Apr 3, 2023** | **4.50%** | +0.25 | |
| **May 22, 2023** | **4.75%** | +0.25 | **Peak of the cycle.** |
| (held) | 4.75% | 0.00 | Held through Oct-Dec 2023 despite war. |
| **Jan 1, 2024** | **4.50%** | −0.25 | First cut in ~2 years. |
| (held) | 4.50% | 0.00 | Held through 2024 and most of 2025. |
| **Nov 24, 2025** | **4.25%** | −0.25 | Post-ceasefire cut. |
| **Jan 5, 2026** | **4.00%** | −0.25 | Second consecutive cut. |
| **Mar 2026** | 4.00% (held) | 0.00 | Committee paused as inflation ticked up. |

For dated decision-by-decision history pre-2020, see the BoI's own page (linked below) or the global-rates.com archive, both of which have decision-level granularity going back to the 1990s.

## 3. How the BoI rate feeds into products in this project

- **Mortgage prime-linked tracks** — the "Prime" column is what banks charge on prime-linked portions (typically 33% of the loan). A "prime − 0.5%" loan is currently paying ~5.0%.
- **Mortgage fixed tracks** (קבוע צמוד / קבוע לא צמוד) — set at origination; they **don't follow** BoI changes afterwards. Origination rate depends heavily on where BoI sat when the loan closed: a 2020 fixed mortgage has a dramatically lower rate than a 2023 one.
- **Savings plans** (פיקדון / פק״ם) — usually track BoI + a spread.
- **Keren Hishtalmut / Pension bond tracks** — follow government-bond yields (slightly above BoI).
- **Corporate bonds / consumer credit** — higher spreads; typically `prime + 2..5%`.

## 4. Sanity-check table for demo investments

When writing demo data spanning multiple years, yields should match the era they were locked in.

| Product | 2003-2007 | 2008-2011 | 2012-2015 | 2016-2021 | 2022 | 2023 | 2024-2026 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Bank savings plan (fixed) | 2-4% | 1-3% | 0.5-2% | 0.1-1% | 1-3% | 3.5-5% | 3.5-5% |
| Israeli govt bonds (mid-dur.) | 3-5% | 2-4% | 1-3% | 0.5-2% | 2-4% | 4-5% | 4-4.5% |
| Corporate bond (IG) | 4-7% | 3-6% | 2-5% | 1-4% | 3-5% | 5-7% | 5-7% |
| Pension bond track | 3-5% | 2-4% | 1-3% | 1-3% | 2-4% | 3-5% | 3.5-5% |
| Pension equity / S&P | 5-15% (mixed) | −35% → +30% (volatile) | 5-15% | 6-20% | −15% to 0% | +20% | 6-12% (avg) |
| Mortgage prime (paid) | 5-7% | 3-4% | 2-4% | 1.6-2% | 1.5→5% | 5-6% | 5.5-6% |

A 2015 savings plan at 4% is implausible (BoI was 0.1%); 2023 at 4% is conservative; 2007 at 4% is reasonable; 2002 at 4% is low (BoI was 5-9% that year).

## Useful reference sources — for finer-grained searches

For the rate history specifically, these are the most useful places to go when you need more precision than this doc provides:

- **Bank of Israel — [official rate page](https://www.boi.org.il/en/economic-roles/statistics/boi-interest-rate-and-the-monetary-tools/boi-interest-rate-and-the-monetary-tools/)**. Authoritative; has a downloadable historical series.
- **Bank of Israel — [statistics portal](https://www.boi.org.il/en/economic-roles/statistics/)**. Gateway to the new series database (all BoI time series: rates, FX, money-supply, balance-of-payments, etc.).
- **FRED (St. Louis Fed) — [Israel Interest Rate tag](https://fred.stlouisfed.org/tags/series?t=interbank%3Binterest+rate%3Bisrael)** — Federal Reserve's free data warehouse. CSV-downloadable monthly series.
- **global-rates.com — [Israeli Key Interest Rate history](https://www.global-rates.com/en/interest-rates/central-banks/18/israeli-key-interest-rate/)** — clean table of every BoI decision with date + new rate, from the 1990s onward.
- **Trading Economics — [Israel Interest Rate](https://tradingeconomics.com/israel/interest-rate)** — similar, with charts.
- **Jewish Virtual Library — [Israel Economic Indicators: Interest Rate](https://jewishvirtuallibrary.org/israel-interest-rate)** — clean annual-rate table since 1995.
- **Statista — [Israel monthly central bank interest rate 1994–2024](https://www.statista.com/statistics/1475575/israel-monthly-central-bank-interest-rate/)** — monthly granularity (paywalled).
- **FocusEconomics — [Israel BoI Interest Rate (eop)](https://www.focus-economics.com/country-indicator/israel/interest-rate/)** — concise year-end table.
- **Bank of Jerusalem — [Interest Rates Fluctuations](https://www.bankjerusalem.co.il/en/mortgages/rates_history)** — useful specifically for mortgage-linked rate history.
- **[Kol Zchut — הלוואת משכנתא](https://www.kolzchut.org.il/he/הלוואת_משכנתא)** — plain-language summary of how prime-linked mortgages work, with links to BoI regulations.
