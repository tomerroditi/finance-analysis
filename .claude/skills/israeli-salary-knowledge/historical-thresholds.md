# Historical Israeli Tax & Contribution Thresholds

Companion reference to the main `SKILL.md`. The main doc spells out the rules; this one tracks how the **numbers** (tax brackets, KH cap, Makifa cap, Bituach Leumi ceilings, credit-point value, average wage) have moved year over year. Useful when the demo data or a calculator needs to reason about a transaction from 2023, or when you want to sanity-check a current number against recent history.

> **Caveats**
> - All thresholds are set by the Israeli government (משרד האוצר / בנק ישראל / ביטוח לאומי) and indexed annually based on the CPI and average wage. Exact figures are authoritative only from the official sources (linked at the bottom).
> - The tax code received multiple mid-year adjustments in the 2022–2026 window because of inflation / war-era fiscal policy; several brackets were explicitly **frozen** for 2025–2027, then the 2026 budget widened the 20% and 31% brackets as a one-off change. Both facts are noted where relevant.
> - Where a number is marked "~" it is a rough figure cross-referenced from secondary sources rather than verified against the official gazette.

---

## 1. Income-tax brackets (monthly gross, NIS)

Each row is the **upper bound** of the bracket named on the far left. The top bracket has no upper bound; income above it is taxed at the final rate plus a **3% surtax (מס יסף)** when annual taxable income exceeds ~721,560 NIS (monthly ~60,130).

| Rate | 2022 | 2023 | 2024 | 2025 (frozen) | 2026 |
|---:|---:|---:|---:|---:|---:|
| **10%** ≤ | 6,450 | 6,790 | 7,010 | 7,010 | 7,010 |
| **14%** ≤ | 9,240 | 9,730 | 10,060 | 10,060 | 10,060 |
| **20%** ≤ | 14,840 | 15,620 | 16,150 | 16,150 | **19,000** (widened) |
| **31%** ≤ | 20,620 | 21,710 | 22,440 | 22,440 | **25,100** (widened) |
| **35%** ≤ | 42,910 | 45,180 | 46,690 | 46,690 | 46,690 |
| **47%** ≤ | 55,270 | 58,190 | 60,130 | 60,130 | 60,130 |
| **50%** (+3% surtax) > | 60,130 | 60,130 | 60,130 | 60,130 | 60,130 |

**Notes:**
- **2025 freeze**: Brackets and other indexed thresholds were frozen at their 2024 values for 2025–2027 as part of the 2025 budget. Scheduled indexation resumes in 2028 based on 2027 CPI/wage data.
- **2026 widening**: The 2026 budget overrode the freeze for two brackets only — the 20% bracket extended from 16,150 → 19,000 and the 31% bracket from 22,440 → 25,100, giving middle-income earners more room in the lower brackets.
- Earlier years (pre-2022) follow the same 7-bracket structure; each threshold was a few percent lower than the 2022 values due to indexation.

**Annual equivalents** (multiply monthly × 12):

| Rate | 2024 Annual | 2026 Annual (widened brackets shown) |
|---:|---:|---:|
| 10% ≤ | 84,120 | 84,120 |
| 14% ≤ | 120,720 | 120,720 |
| 20% ≤ | 193,800 | 228,000 |
| 31% ≤ | 269,280 | 301,200 |
| 35% ≤ | 560,280 | 560,280 |
| 47% ≤ | 721,560 | 721,560 |
| 50% + 3% > | 721,560 | 721,560 |

---

## 2. Credit point value — נקודת זיכוי

A tax credit point **reduces the month's income-tax bill by a fixed NIS amount** (not a percentage). Indexed annually — the value moves roughly with CPI.

| Year | Monthly value (NIS) | Annual value (NIS) |
|---:|---:|---:|
| 2020 | ~215 | ~2,580 |
| 2021 | ~218 | ~2,616 |
| 2022 | **223** | **2,676** |
| 2023 | ~235 | ~2,820 |
| 2024 | **242** | **2,904** |
| 2025 | 242 (frozen) | 2,904 (frozen) |
| 2026 | 242 (frozen) | 2,904 (frozen) |

A typical married man resident claims 2.25 points (→ 545 NIS/mo tax credit at 2026 value). A resident woman claims 2.75 points. Mother of children adds ~1 point per child under 18 (scales by child age); single parents add more.

---

## 3. Pension — Makifa deposit & salary cap

The Makifa deposit ceiling is derived from the average wage (שכר ממוצע במשק). Since 2016 the ceiling has been set at **2.5 × average wage** (before 2016 it was 4× average wage, so the cap was much less binding). The deposit cap is the salary cap × ~16.4%.

| Year | Average wage (NIS/mo) | Makifa salary cap ≈ 2.5 × avg | Makifa deposit cap (NIS/mo) |
|---:|---:|---:|---:|
| 2020 | ~10,460 | ~26,150 | ~4,290 |
| 2021 | 10,551 (COVID freeze) | 26,378 | 4,326 |
| 2022 | 10,551 (still frozen) | 26,378 | **4,326** |
| 2023 | ~11,870 | ~29,675 | ~4,870 |
| 2024 | ~12,500 | ~31,250 | **5,139** |
| 2025 | ~12,536 | ~31,340 | ~5,140 |
| 2026 | ~12,536 | ~25,000–31,340 (sources vary on exact 2026 number) | **5,140** |

**Consequences:**
- Gross ≤ salary cap → all pension deposits go to **Makifa**; no Mashlima account exists.
- Gross > salary cap → Makifa gets deposits on the first `salary_cap` shekels of gross; **Mashlima** gets deposits on the remainder. Same 18.5% percentages in both.
- The cap is applied independently to each individual's own salary — spouses are never combined.

**Cap formula reminder** (use this when writing calculators — the precise cap moves each year):
```
makifa_deposit_cap ≈ 2.5 × average_wage × 0.164   # informal
makifa_salary_cap  ≈ 2.5 × average_wage
```

For the 2026 demo data we use `makifa_salary_cap = 25,000 ILS/month` — this sits in the middle of the range the sources quote and is easy to reason about. The real-world figure indexes upwards with the average wage.

---

## 4. Keren Hishtalmut tax-exempt ceiling

Expressed as a **gross monthly salary cap**: KH deposits at 10% on gross **up to this ceiling** are tax-advantaged (no income tax on employer share, no capital-gains tax on withdrawal after 6 years). Deposits on gross above the ceiling are still legal but taxable for the employee.

| Year | Gross salary cap (NIS/mo) | 10% deposit at cap (NIS/mo) | Annual deposit at cap |
|---:|---:|---:|---:|
| 2020 | 15,712 | 1,571 | 18,854 |
| 2021 | 15,712 | 1,571 | 18,854 |
| 2022 | 15,712 | 1,571 | 18,854 |
| 2023 | 15,712 | 1,571 | 18,854 |
| 2024 | 15,712 | 1,571 | 18,854 |
| 2025 | 15,712 (frozen) | 1,571 | 18,854 |
| 2026 | **15,712** (frozen) | 1,571 | 18,854 |

**The KH salary cap has been unusually stable** — it was set at 15,712 NIS/mo years ago and has not been indexed since (it's explicitly frozen through 2027 alongside the tax brackets). This is why virtually every payroll system in Israel caps KH deposits at this exact base.

**Self-employed parallel rules** (for completeness — salaried KH doesn't use these):
- 2021: deductible 11,835/yr; capital-gains exempt 18,480/yr
- 2022: deductible 12,150/yr; capital-gains exempt 18,960/yr
- 2024: deductible **13,202/yr**; capital-gains exempt 18,854/yr
- 2026: deductible **13,203/yr**; capital-gains exempt 20,566/yr

---

## 5. Bituach Leumi + Health Tax ceilings (employee side)

Two tiers of combined National-Insurance + health-tax contributions apply to salaried employees up to an annual ceiling. Employer-side rates are separate (approx. 3.55% low / 7.6% above) and paid on top of gross.

| Year | Low-bracket upper bound (NIS/mo) | High-bracket upper bound / max ceiling (NIS/mo) | Low rate | High rate |
|---:|---:|---:|---:|---:|
| 2021 | 6,331 | 44,020 | 3.5% | 12.0% |
| 2022 | 6,331 | 45,075 | 3.5% | 12.0% |
| 2023 | 7,122 | 47,465 | 3.5% | 12.0% |
| 2024 | 7,522 (apr.) | 49,030 | 3.5% | 12.0% |
| 2025 | 7,122 | 50,695 | 3.5% | 12.0% |
| 2026 | 7,122 | 50,695 | 3.5% | 12.0% |

**Rate-tier breakdown** (combined = Bituach Leumi + health tax):
- Low bracket: 0.4% BTL + 3.1% health = 3.5%
- High bracket: 7.0% BTL + 5.0% health = 12.0%
- Above the ceiling: nothing withheld.

**Notes:**
- 2024 saw a temporary +0.8% war-related employee BTL surcharge on gross above ~7,522 NIS/mo. That surcharge was rolled back for 2025.
- The low-bracket threshold and the ceiling are both indexed (roughly to the average wage). Numbers here are ballpark; for authoritative calculations consult the Bituach Leumi website.

---

## 6. Average wage (שכר ממוצע במשק) — reference for indexed thresholds

Many of the thresholds above (Makifa cap, BTL ceiling, minimum wage, minimum pension benefit) are tied to this figure. Published annually by the CBS / Bituach Leumi.

| Year | Average wage (NIS/mo) |
|---:|---:|
| 2019 | 10,273 |
| 2020 | ~10,460 |
| 2021 | 10,551 (frozen due to COVID) |
| 2022 | 10,551 (still frozen) |
| 2023 | ~11,870 |
| 2024 | ~12,500 |
| 2025 | ~12,536 |
| 2026 | ~12,536 |

---

## 7. Minimum wage

Not directly needed for net-salary calculation but often referenced alongside the thresholds above.

| Year | Minimum wage (NIS/mo) |
|---:|---:|
| 2015 | 4,650 |
| 2017 | 5,000 |
| 2022 | 5,300 |
| 2023 | 5,571.75 |
| 2024 (Apr) | 5,880.02 |
| 2025 | 5,880.02 |
| 2026 | 5,880.02 |

---

## 8. How to use this document

- When a demo data generator references a salary or pension in year Y, check the **KH cap row for year Y**, the **Makifa cap row for year Y**, and the **income tax bracket row for year Y** — all three are needed for a realistic net-salary calculation.
- For the current demo (`REFERENCE_DATE = 2026-02-25`), the generator uses 2026 values. If you're asked to make the demo support multiple years, pick the row for each year and make the constants in `generate_insurance_data` date-aware.
- **Do not hard-code numbers from old years as if they were current** — always check against the latest row.
- When quoting a bracket to a user, include the year you're quoting from. "The 31% bracket" without a year is ambiguous.

## Sources

- [PwC — Israel Individual Taxes on Personal Income](https://taxsummaries.pwc.com/israel/individual/taxes-on-personal-income)
- [Jerusalem Post — 2026 tax bracket revision (widening)](https://www.jpost.com/business-and-innovation/banking-and-finance/article-892194)
- [CWS Israel — 2025 Israeli Payroll Updates](https://www.cwsisrael.com/2025-israeli-payroll-updates/)
- [CWS Israel — Israeli Tax Changes 2026: Complete Guide](https://www.cwsisrael.com/israeli-tax-changes-2026-complete-guide/)
- [CWS Israel — National Insurance (Bituach Leumi) & Health Tax 2025](https://www.cwsisrael.com/national-insurance-bituach-leumi-and-health-tax-in-2025/)
- [ביטוח לאומי — Rates for Salaried Workers (official)](https://www.btl.gov.il/English%20Homepage/Insurance/Ratesandamount/Pages/forSalaried.aspx)
- [Dray & Dray — Tax rates in Israel (credit points, history)](https://cpa-dray.com/en/blog/tax-rates-in-israel/)
- [Dray & Dray — Keren Hishtalmut tax benefits](https://cpa-dray.com/en/blog/keren-hishtalmut/)
- [Pensuni — תקרות מס וסכומים עיקרים לשנת 2026](https://pensuni.com/?p=827)
- [Pensuni — תקרת הפקדה לקרן פנסיה בשנת 2026](https://pensuni.com/?p=1281)
- [Blue & White Finance — The ultimate guide to Keren Hishtalmut](https://bluewhitefinance.com/the-ultimate-guide-to-keren-hishtalmut/)
- [Globes — income tax brackets revised due to inflation (2023)](https://en.globes.co.il/en/article-israels-income-tax-brackets-revised-due-to-inflation-1001435217)
