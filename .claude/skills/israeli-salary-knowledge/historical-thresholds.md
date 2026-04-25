# Historical Israeli Tax & Contribution Thresholds (2000 → 2026)

Companion reference to the main `SKILL.md`. Tracks how the key **numbers** — tax brackets, KH cap, Makifa cap, Bituach Leumi ceilings, credit-point value, average wage, minimum wage — moved year over year. Useful when the demo data or a calculator needs to reason about a transaction from 2015, or when you want to sanity-check a current number against history.

> **Confidence & caveats**
> - Data for **2022 onwards** is high-confidence, cross-referenced against multiple live sources.
> - Data for **2010–2021** is good for year-end snapshots; finer intra-year detail may be approximate.
> - Data for **2000–2009** is broadly accurate but individual bracket thresholds may be off by a few percent; this era also saw major structural tax reforms (Rabinovich 2003, Trajtenberg 2011) so the bracket *structure* itself shifted.
> - Where a number is marked "~" it's a rough figure cross-referenced from secondary sources rather than verified against the Israeli Tax Authority gazette.
> - The ultimate authoritative sources are listed in the **Useful Reference Sources** section at the bottom.

---

## Sections
1. Income-tax brackets (2000 → 2026)
2. Credit-point value — נקודת זיכוי (2000 → 2026)
3. Pension Makifa deposit & salary cap (compulsory pension era: 2008 → 2026)
4. Keren Hishtalmut tax-exempt ceiling (2000 → 2026)
5. Bituach Leumi + Health Tax ceilings (employee side, 2000 → 2026)
6. Average wage — שכר ממוצע (2000 → 2026)
7. Minimum wage (2000 → 2026)
8. How to use this document
9. Useful reference sources (for finer-grained searches)

---
## 1. Income-tax brackets

Israel's income tax is progressive with 7 brackets. The bracket **structure** changed in several waves over the past 25 years:

- **Pre-2003:** Top marginal rate was ~60%; base brackets were narrower.
- **2003–2009:** Rabinovich reform gradually cut the top rate from ~60% → 46%. Rates fell every year as the reform phased in.
- **2010–2012:** Post-GFC adjustments. Top rate bottomed around 45%.
- **2011–2013:** Trajtenberg reform (after 2011 social protests) reintroduced progression at the top; surtax (מס יסף) of 2% then 3% on annual income > ~640k added.
- **2014–2021:** Brackets widened slightly each year via indexation. Top marginal 47% + 3% surtax = **effective 50% top**.
- **2022–2024:** Indexation continued; bracket structure stable at 7 brackets.
- **2025–2027:** Brackets **frozen** at 2024 values.
- **2026:** Mid-freeze override — 20% and 31% brackets widened as a one-off.

### Current-era brackets (monthly gross, NIS) — 2022 → 2026

| Rate | 2022 | 2023 | 2024 | 2025 (frozen) | 2026 |
|---:|---:|---:|---:|---:|---:|
| **10%** ≤ | 6,450 | 6,790 | 7,010 | 7,010 | 7,010 |
| **14%** ≤ | 9,240 | 9,730 | 10,060 | 10,060 | 10,060 |
| **20%** ≤ | 14,840 | 15,620 | 16,150 | 16,150 | **19,000** (widened) |
| **31%** ≤ | 20,620 | 21,710 | 22,440 | 22,440 | **25,100** (widened) |
| **35%** ≤ | 42,910 | 45,180 | 46,690 | 46,690 | 46,690 |
| **47%** ≤ | 55,270 | 58,190 | 60,130 | 60,130 | 60,130 |
| **50%** (+3% surtax) > | 60,130 | 60,130 | 60,130 | 60,130 | 60,130 |

### Historical snapshots — 2000 → 2021 (10% bracket threshold + top marginal rate)

Full 7-bracket tables for every year in this range are impractical to keep in sync here; consult the Tax Authority archives (see Useful sources). What matters for demo-data realism is the ballpark:

| Year | 10% bracket ≤ (NIS/mo, approx) | Top marginal rate | Notes |
|---:|---:|---:|---|
| 2000 | ~3,900 | ~50% | Pre-reform. |
| 2003 | ~4,100 | 49% | Rabinovich reform kicks in. |
| 2005 | ~4,220 | 49% | |
| 2007 | ~4,790 | 47% | |
| 2010 | ~5,070 | 45% | Post-GFC trough in top rate. |
| 2012 | ~5,150 | 48% | Trajtenberg raised top rate + added surtax. |
| 2013 | ~5,280 | 50% (47% + 3% surtax) | Surtax permanent. |
| 2015 | ~5,550 | 50% | VAT cut from 18% to 17% this year (unrelated to income tax but often confused). |
| 2017 | ~6,220 | 50% | |
| 2019 | ~6,310 | 50% | |
| 2020 | ~6,330 | 50% | |
| 2021 | ~6,331 | 50% | |

---

## 2. Credit-point value — נקודת זיכוי

A tax credit point **reduces the month's income-tax bill by a fixed NIS amount** (not a percentage). Indexed annually — the monthly value moves roughly with CPI. Used to calculate the after-credit tax: `tax_owed = bracket_tax − points × point_value`.

| Year | Monthly value (NIS) | Annual value (NIS) | Notes |
|---:|---:|---:|---|
| 2000 | ~170 | ~2,040 | |
| 2003 | ~181 | ~2,172 | |
| 2005 | ~185 | ~2,220 | |
| 2008 | ~193 | ~2,316 | |
| 2010 | ~205 | ~2,460 | |
| 2012 | ~211 | ~2,532 | |
| 2014 | ~216 | ~2,592 | |
| 2016 | ~215 | ~2,580 | CPI was flat/deflationary. |
| 2018 | ~216 | ~2,592 | |
| 2020 | ~219 | ~2,628 | |
| 2021 | ~218 | ~2,616 | |
| 2022 | **223** | **2,676** | |
| 2023 | ~235 | ~2,820 | |
| 2024 | **242** | **2,904** | |
| 2025 | 242 (frozen) | 2,904 (frozen) | |
| 2026 | 242 (frozen) | 2,904 (frozen) | |

### Typical point allocations (unchanged across the era)

- Resident male: 2.25 points
- Resident female: 2.75 points (+0.5 female bonus)
- Each child under 18 (to mother): +1 to +1.5 points depending on age
- Each child under 3: +1 point split between parents
- New olim: 3 extra points in year 1, declining
- Single parent: extra allocation

At 2026 values, a typical married male gets 2.25 × 242 = 545 NIS/mo tax credit; a mother of two young children at 4.75 points gets ~1,150 NIS/mo tax credit.

---

## 3. Pension Makifa deposit & salary cap

**Compulsory pension did not exist before 2008.** Until then, pension deposits were driven by collective agreements (e.g. Histadrut sector agreements) — widespread but not universal. The compulsory-pension law passed in 2008 and the mandatory percentages were phased in gradually, reaching their current **18.5% total (6% employee / 6.5% employer / 6% severance)** only in 2017.

| Era | Compulsory? | Minimum total rate | Notes |
|---|---|---:|---|
| pre-2008 | No | 0% legal minimum | Deposits depended on employer's collective agreement. |
| 2008-2013 | Yes (phased in) | 2.5% → 15% (phased) | Both employee and employer percentages rose 0.5 pp/year. |
| 2014-2016 | Yes | ~17.5% | Nearly at current minimum. |
| 2017+ | Yes | **18.5%** | Current minimum: 6% / 6.5% / 6%. |

### Makifa deposit cap (= salary cap × ~16.4%)

Since 2016 the Makifa salary cap = **2.5 × average wage** (before 2016 it was 4× average wage, so the cap was much less binding and virtually no one hit it).

| Year | Avg wage (NIS/mo) | Makifa salary cap ≈ | Makifa **deposit** cap (NIS/mo) | Notes |
|---:|---:|---:|---:|---|
| 2000 | ~7,050 | 4× → ~28,200 | n/a (voluntary era) | Pre-compulsory. |
| 2005 | ~7,700 | 4× → ~30,800 | n/a (voluntary era) | |
| 2008 | ~8,200 | 4× → ~32,800 | ~4,100 | Compulsory law year. |
| 2010 | ~8,700 | 4× → ~34,800 | ~4,350 | |
| 2012 | ~9,100 | 4× → ~36,400 | ~4,550 | |
| 2014 | ~9,250 | 4× → ~37,000 | ~4,625 | Last year under 4× rule. |
| 2016 | ~9,600 | **2.5× → ~24,000** | ~3,900 | **Rule changed to 2.5×** — much more binding. |
| 2018 | ~10,070 | 2.5× → ~25,175 | ~4,130 | |
| 2020 | ~10,460 | 2.5× → ~26,150 | ~4,290 | |
| 2021 | 10,551 (COVID freeze) | 2.5× → 26,378 | 4,326 | |
| 2022 | 10,551 (still frozen) | 2.5× → 26,378 | **4,326** | |
| 2023 | ~11,870 | 2.5× → ~29,675 | ~4,870 | |
| 2024 | ~12,500 | 2.5× → ~31,250 | **5,139** | |
| 2025 | ~12,536 | 2.5× → ~31,340 | ~5,140 | |
| 2026 | ~12,536 | 2.5× → ~25,000–31,340 (sources vary) | **5,140** | |

### Consequences

- Gross ≤ salary cap → all pension goes to **Makifa**; no Mashlima account.
- Gross > salary cap → deposits on the first `salary_cap` shekels to **Makifa**; deposits on the remainder to **Mashlima** (same 18.5% in both). Same percentages; different instrument.
- Applied **per individual** — never combined across spouses.
- For the current demo (2026 reference) we use `makifa_salary_cap = 25,000 ILS/month`. The 2015-and-earlier cap is effectively non-binding for all but very high earners.

---

## 4. Keren Hishtalmut tax-exempt ceiling

Expressed as a **gross monthly salary cap**: KH deposits at 10% on gross **up to this ceiling** are tax-advantaged. Deposits above the ceiling are still legal but taxable for the employee — most payrolls cap at this base.

| Year | Gross salary cap (NIS/mo) | 10% deposit at cap | Notes |
|---:|---:|---:|---|
| 2000 | ~6,500 | ~650 | Era of lower caps; roughly tied to avg wage. |
| 2005 | ~7,000 | ~700 | |
| 2008 | ~8,500 | ~850 | |
| 2010 | ~11,000 | ~1,100 | Cap raised significantly. |
| 2012 | ~14,000 | ~1,400 | |
| 2014 | 15,712 | 1,571 | **Cap stabilised at 15,712** — unchanged since. |
| 2016 | 15,712 | 1,571 | |
| 2018 | 15,712 | 1,571 | |
| 2020 | 15,712 | 1,571 | |
| 2022 | 15,712 | 1,571 | |
| 2024 | 15,712 | 1,571 | |
| 2026 | **15,712** (frozen) | 1,571 | Frozen through 2027 alongside tax brackets. |

**The KH salary cap has been unusually stable since ~2014.** It was not indexed meaningfully for the last decade and is now explicitly frozen through 2027. Virtually every Israeli payroll system caps KH deposits at this exact base.

### Self-employed parallel figures (for completeness)

| Year | Deductible (yr) | Capital-gains exempt (yr) |
|---:|---:|---:|
| 2020 | ~12,900 | ~18,600 |
| 2021 | 11,835 | 18,480 |
| 2022 | 12,150 | 18,960 |
| 2024 | **13,202** | 18,854 |
| 2026 | 13,203 | 20,566 |

---

## 5. Bituach Leumi + Health Tax ceilings (employee side)

Two tiers of combined National-Insurance + health-tax contributions apply to salaried employees up to a monthly ceiling. **Rates have been very stable for 25 years — it's the ceilings that move.**

**Rate structure (broadly stable since ~1995):**

| Bracket | Bituach Leumi | Health tax | Combined |
|---|---:|---:|---:|
| Low | 0.4% | 3.1% | **3.5%** |
| High (above low threshold, up to ceiling) | 7.0% | 5.0% | **12.0%** |
| Above ceiling | 0% | 0% | **0%** |

Rates have been adjusted minimally across the era — the 3.5% / 12% combination has held since approximately 2006, with only brief wartime surcharges (e.g. +0.8% in 2024).

### Thresholds (monthly gross NIS)

| Year | Low-bracket upper bound | Ceiling (max contribution base) |
|---:|---:|---:|
| 2000 | ~3,870 | ~34,680 |
| 2005 | ~4,300 | ~36,090 |
| 2008 | ~4,800 | ~38,520 |
| 2010 | ~4,810 | ~38,415 |
| 2012 | ~5,050 | ~41,850 |
| 2015 | ~5,556 | ~43,370 |
| 2018 | ~6,164 | ~43,890 |
| 2020 | ~6,331 | 44,020 |
| 2021 | 6,331 | 44,020 |
| 2022 | 6,331 | 45,075 |
| 2023 | 7,122 | 47,465 |
| 2024 | 7,522 (April raise) | 49,030 |
| 2025 | 7,122 | 50,695 |
| 2026 | 7,122 | 50,695 |

**Note on 2024:** A temporary +0.8% BTL surcharge was added on employee wages above ~7,522 NIS/mo as part of the war-era budget (employers paid the same). Rolled back for 2025.

---

## 6. Average wage — שכר ממוצע במשק

Published annually by the CBS / Bituach Leumi. Many of the thresholds above (Makifa cap, BTL ceiling, minimum pension benefit) are tied to this figure.

| Year | Average wage (NIS/mo) | Notes |
|---:|---:|---|
| 2000 | ~7,050 | |
| 2003 | ~7,250 | |
| 2005 | ~7,700 | |
| 2008 | ~8,200 | |
| 2010 | ~8,700 | |
| 2012 | ~9,100 | |
| 2014 | ~9,250 | |
| 2016 | ~9,600 | |
| 2018 | ~10,070 | |
| 2019 | 10,273 | |
| 2020 | ~10,460 | |
| 2021 | 10,551 | Frozen due to COVID. |
| 2022 | 10,551 | Still frozen. |
| 2023 | ~11,870 | Catch-up. |
| 2024 | ~12,500 | |
| 2025 | ~12,536 | |
| 2026 | ~12,536 | |

---

## 7. Minimum wage

Floor set by law, raised periodically by the Knesset (not indexed automatically).

| Year | Minimum wage (NIS/mo) | Notes |
|---:|---:|---|
| 2000 | ~2,800 | |
| 2002 | ~3,335 | |
| 2005 | ~3,585 | |
| 2008 | ~3,710 | |
| 2011 | 4,100 | |
| 2013 | ~4,300 | |
| 2015 | 4,650 | |
| 2017 | 5,000 | |
| 2022 | 5,300 | |
| 2023 | 5,571.75 | Apr-2023 raise. |
| 2024 | 5,880.02 | Apr-2024 raise (5.6% bump). |
| 2025 | 5,880.02 | Held. |
| 2026 | 6,443.85 | Significant raise. |

---

## 8. How to use this document

- When a demo-data generator references a salary or pension in year Y, check the **KH cap row**, **Makifa cap row**, and **income-tax bracket row** for Y — all three are needed for a realistic net-salary calculation.
- For the current demo (`REFERENCE_DATE = 2026-02-25`), the generator uses 2026 values. If asked to make the demo support multiple years, pick the row for each year and make the constants in `generate_insurance_data` date-aware.
- **Do not hard-code numbers from old years as if they were current** — always check against the latest row.
- When quoting a bracket to a user, include the year you're quoting from. "The 31% bracket" without a year is ambiguous.
- For transactions before 2008, remember: **no compulsory pension**. For transactions before 2016, the Makifa cap was 4× average wage — effectively non-binding.
- If precision matters (e.g. writing a calculator that will be used for real money), verify the figure against the official sources in Section 9 below. Secondary sources including this document can be off by a few hundred shekels in early-era rows.

---

## 9. Useful reference sources (for finer-grained searches)

When you need more precision than this document provides — especially for pre-2015 figures, or exact bracket thresholds for a specific year — go straight to these.

### Authoritative Israeli-government sources

- **Israel Tax Authority (רשות המסים)** — [gov.il/he/departments/israel_tax_authority](https://www.gov.il/he/departments/israel_tax_authority). Authoritative on income tax brackets, credit points, allowances.
- **Ministry of Finance Monthly Deductions Booklet** — [gov.il/en/pages/income-tax-monthly-deductions-booklet](https://www.gov.il/en/pages/income-tax-monthly-deductions-booklet). Reference tables payroll systems use for actual deductions.
- **Bituach Leumi — rates for salaried workers** — [btl.gov.il (official rates page)](https://www.btl.gov.il/English%20Homepage/Insurance/Ratesandamount/Pages/forSalaried.aspx). Authoritative on BTL + health-tax tiers and ceilings.
- **Bank of Israel** — [boi.org.il/en/economic-roles/statistics/](https://www.boi.org.il/en/economic-roles/statistics/). For the official interest rate series.
- **Israeli Central Bureau of Statistics (CBS)** — [cbs.gov.il](https://www.cbs.gov.il/en/Pages/default.aspx). Source for average and minimum wage data.
- **Capital Market, Insurance & Savings Authority (רשות שוק ההון)** — [gov.il/he/departments/units/capital_market](https://www.gov.il/he/departments/units/capital_market). Authoritative on pension/KH regulations and deposit ceilings.

### Plain-language explainers (use as starting point)

- **[Kol Zchut (כל זכות)](https://www.kolzchut.org.il/)** — ~6,000-article wiki on Israeli rights/entitlements. Use as a bridge: read the summary, then click through to the official source. Covers employment, pension, KH, BTL, income tax, mortgage, consumer rights.
- **[Pensuni (פנסוני)](https://pensuni.com/)** — Hebrew pension/payroll reference; usually publishes a "תקרות ומדדים לשנה" page each year with all the indexed figures in one place.
- **[Meitav (מיטב) Guide](https://www.meitav.co.il/)** — Investment house with clear Hebrew explainers on pension, KH, and tax caps.
- **[Clalbit תקרות עדכון PDF](https://www.clalbit.co.il/)** — Insurance co. publishes an annual PDF with all thresholds; useful for cross-referencing a single year.
- **Globes (Hebrew + English)** — [en.globes.co.il](https://en.globes.co.il/en/) — financial news; often covers bracket revisions and budget changes in detail.
- **Jerusalem Post Business** — [jpost.com/business-and-innovation](https://www.jpost.com/business-and-innovation/) — English coverage of tax / payroll changes.
- **CWS Israel payroll updates** — [cwsisrael.com](https://www.cwsisrael.com/) — concise English summaries of annual payroll changes (targeted at EoR clients).
- **Dray & Dray tax blog** — [cpa-dray.com/en/blog](https://cpa-dray.com/en/blog/) — practitioner-level English explainers of Israeli taxation (good for historical context on credit points, KH, tax rates).
- **PwC Worldwide Tax Summaries — Israel** — [taxsummaries.pwc.com/israel](https://taxsummaries.pwc.com/israel/individual/taxes-on-personal-income) — professional-grade summary of current Israeli personal income tax.
- **KPMG TIES Israel** — [assets.kpmg.com](https://assets.kpmg.com/content/dam/kpmgsites/xx/pdf/2023/01/TIES-Israel.pdf.coredownload.inline.pdf) — detailed PDF on taxation of international executives; has historical bracket tables.
- **Nefesh B'Nefesh — Understanding Israeli Salary Stubs** — [nbn.org.il](https://www.nbn.org.il/life-in-israel/employment/employee-rights-and-benefits/understanding-israeli-salary-stubs/) — plain-English walkthrough of a payslip.

### Interest-rate / macro data

- **Global-Rates — Israeli Key Interest Rate** — [global-rates.com](https://www.global-rates.com/en/interest-rates/central-banks/18/israeli-key-interest-rate/). Clean historical decision table.
- **FRED (St. Louis Fed)** — [fred.stlouisfed.org](https://fred.stlouisfed.org/tags/series?t=interbank%3Binterest+rate%3Bisrael). Free CSV-downloadable monthly series.
- **Trading Economics — Israel Interest Rate** — [tradingeconomics.com/israel/interest-rate](https://tradingeconomics.com/israel/interest-rate).
- **Jewish Virtual Library — Interest Rate** — [jewishvirtuallibrary.org/israel-interest-rate](https://jewishvirtuallibrary.org/israel-interest-rate). Annual table since 1995.

### Search strategy tips

- Hebrew searches return better results for historical Israeli tax data than English. Try `תקרת הפקדה לקרן פנסיה 2015` instead of "Israeli pension cap 2015".
- When a secondary source gives a suspicious number, search for its Hebrew term on the relevant **.gov.il** subdomain (e.g. `site:btl.gov.il תקרת הכנסה 2018`).
- For any figure going into code that affects real money, double-check against two independent sources before committing.

