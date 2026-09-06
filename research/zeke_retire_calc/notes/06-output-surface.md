# Output surface — what our UI has to reproduce

Derived from the result HTML of `fixtures/baseline.json` (73 KB of rendered
markup returned by the job). The reference renders everything server-side into
three tabs: **results**, **graphs**, and a **smart advice** tab that only
appears when the optimizer finds an improvement.

## 1. Headline verdict
Success: `אתה צפוי לפרוש ב-03/2043!!` + `גיל פרישה: 53.2` (month/year and age
to one decimal). Failure: `לא הצלחת להגיע ליעדיך בפחות מ 280 חודשים.`
("you did not reach your goals within N months") — see `fixtures/desig_goal.json`.
A third state exists: `אין תוצאות להצגה` when the request is degenerate, e.g. a
person already older than the max retirement age (`fixtures/old_66.json`).

## 2. Goal attainment checklist (עמידה ביעדים)
One row per goal, each ✓/✗:
- `יעד כיסוי של הוצאות מחיה` — living expenses covered to the horizon
- `יעד הורשה` — bequest goal. **There is no bequest input field**, so this is
  presumably "net worth ≥ 0 at age 81". Needs confirmation.
- `קרן פנסיה של <name>` — one row per person with a pension fund.

## 3. Asset snapshot cards — two of them
"מצב נכסים בנקודת זמן נוכחית (08/2026)" and "מצב נכסים בפרישה מוקדמת (03/2043)".
Each shows a net-worth figure plus a **doughnut chart** breaking assets into
categories (`assetspie0` = today, `assetspie1` = at retirement). In the baseline
these are `{תיקים: 100,000}` and `{תיקים: 220,893.8, עובר ושב: 995,000}`.

## 4. Annuity list (קצבאות לאורך השנים)
Per person, each stream as: source, start age, monthly amount — e.g.
`ביטוח לאומי של T - זיקנה, קצבה מגיל 67 בגובה 2,757.0 ₪`, with a marker for
which component is "converted" (מרכיב שמומר).

## 5. Withdrawal plan (תוכנית המשיכה מהתיקים)
An ordered list of drawdown segments: source bucket, age range, average monthly
amount. Baseline: `עובר ושב` from 53.2 to 73.2 averaging 4,145.8, then
`תיק בברוקר בארץ` from 73.2 to 81.0 averaging 2,210.2.
Note 995,000 / 240 months = 4,145.83 exactly — cash is drawn flat with no return.

## 6. Narrative (סיפור המסע שלך)
Prose summary: the retirement age, and the total pension income at age 60.

## 7. Charts — five monthly time series, all stacked area/line over age
| canvas | series |
|---|---|
| `income_plot` | one per income source: work, withdrawal from cash, withdrawal per portfolio, old-age pension |
| `expense_plot` | `הוצאות שוטפות` + `הוצאה לא מתוכננת` (unplanned — origin unknown, being investigated) |
| `netval_plot` | single net-worth series |
| `asset_plot` | one per asset: cash, each portfolio, (pension, KH, real estate when present) |
| `buffer_plot` | checking-account balance |

All share the same monthly age axis, so a single simulation result feeds all
five — our engine should return one tidy per-month record and let the UI pivot.
