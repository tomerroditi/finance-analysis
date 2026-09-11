# Complete input surface of the reference calculator

90 controls. Repeatable sections cap at 20 rows each. `num_*_fields`
hidden counters tell the server how many rows to read.

## Main form

| field | type | default | options / range | meaning |
|---|---|---|---|---|
| `base_problem` | select | `retire_asap` | retire_asap/retire_at_age/improve_cash_to_reach_retire_at_age/increase_risk_to_reach_retire_at_age | Which problem to solve (retire ASAP / check-up at age / reach age via cashflow / via return) |
| `wanted_retire_age` | number | `` |  | Target retirement age |
| `base_problem_max_age` | number | `60` |  | Max acceptable retirement age (search upper bound) |
| `base_problem_cash_improve` | number | `0` |  | Max monthly cash-flow improvement the solver may assume |
| `base_problem_risk_increase` | number | `0` |  | Max return increase [%] the solver may assume |
| `pensionName` | text | `` |  | Name (retiree 1) |
| `gender` | select | `male` | male/female | Gender |
| `dateOfBirth` | date | `` |  | Date of birth |
| `is_american` | select | `no` | no/yes | US citizen (PFIC/US tax) |
| `pensionTake_2` | checkbox | `` |  |  |
| `pensionName_2` | text | `` |  | Name (partner) |
| `gender_2` | select | `male` | male/female | Gender (partner) |
| `dateOfBirth_2` | date | `` |  | Date of birth (partner) |
| `is_american_2` | select | `no` | no/yes | US citizen (PFIC/US tax) |
| `retireRule` | number | `85` | min 0 | Confidence % the portfolio does not deplete before the pension (Trinity, 75% equities); 80-100 |
| `prati_hishtalmut_order` | select | `prati` | prati/hishtalmut | Which bucket to draw first: taxed portfolio vs Keren Hishtalmut |
| `cashBuffer` | number | `0` | min 0 | Desired checking balance |
| `balance` | number | `0` |  | Current checking balance |
| `creditLimit` | number | `0` | min 0 | Credit line |
| `expenseStartType1` | select | `now` | now/fire/from_date/one_time |  |
| `expenseStartDate1` | date | `` |  |  |
| `expenseEndType1` | select | `forever` | forever/fire/to_date/60 |  |
| `expenseEndDate1` | date | `` |  |  |
| `expenseSum1` | number | `5000` | min 0 | Monthly amount |
| `expenseRise1` | number | `0.0` |  | Annual real rise [%] |
| `expenseDescription1` | text | `הוצאות חודשיות` |  | Free text |
| `incomeStartType1` | select | `now` | now/fire/from_date/one_time |  |
| `incomeStartDate1` | date | `` |  |  |
| `incomeEndType1` | select | `fire` | forever/fire/to_date/60 |  |
| `incomeEndDate1` | date | `` |  |  |
| `incomeSum1` | number | `10000` | min 0 |  |
| `incomeRise1` | number | `0.0` |  |  |
| `incomeDescription1` | text | `הכנסות חודשיות` |  |  |
| `portfolioDesignation1` | select | `goal` | withdraw/goal/mukeret_main/mukeret_partner | withdraw (funds living) | goal | mukeret_main | mukeret_partner |
| `portfolio_type1` | select | `kaspit` | portfolio/ibkr/gemel/polisa/kaspit/pikadon | portfolio | ibkr | gemel | polisa | kaspit | pikadon (instrument, drives tax/limits) |
| `portfolioBalance1` | number | `0` | min 0 | Current balance |
| `portfolio_deposit1` | number | `` | min 0 | Monthly deposit cap (blank = unlimited) |
| `portfolio_goal1` | number | `0` | min 0 | Target balance — deposits stop on reaching it (0 = never deposit) |
| `portfolioInterest1` | number | `5.0` |  | Expected real return [%] |
| `portfolioFee1` | number | `0.1` | min 0 | Management fee [%] |
| `portfolioProfitFraction1` | number | `0.0` | min 0 | Share of balance that is unrealised profit [%] |
| `portfolio_fifo_lifo1` | select | `flat` | flat/fifo/lifo | Lot accounting: flat | FIFO | LIFO |
| `portfolioDescription1` | text | `` |  |  |
| `pensionBalance` | number | `0` | min 0 | Accrued pension |
| `pensionDeposit` | number | `0` | min 0 | Monthly pension deposit |
| `pensionFee1` | number | `0.05` | min 0 | Fee on balance [%] |
| `pensionFee2` | number | `1.5` | min 0 | Fee on deposit [%] |
| `pensionInterest` | number | `7.0` |  | Expected return [%] |
| `pension_tactics` | select | `60` | 60/67/60-67 | Draw all from 60 | all from statutory age | recognised from 60 + entitling from statutory |
| `percentage_mukeret` | number | `30` | min 0 | % of the annuity that is "recognised" (קצבה מוכרת, tax-free) |
| `pensionEndType1` | select | `fire` | forever/fire/to_date/60 | When deposits stop |
| `pensionEndDate` | date | `` |  |  |
| `pensionBalance_2` | number | `0` | min 0 | Accrued pension |
| `pensionDeposit_2` | number | `0` | min 0 | Monthly pension deposit |
| `pensionFee1_2` | number | `0.05` | min 0 | Fee on balance [%] |
| `pensionFee2_2` | number | `1.5` | min 0 | Fee on deposit [%] |
| `pensionInterest_2` | number | `7.0` |  | Expected return [%] |
| `pension_tactics_2` | select | `60` | 60/67/60-67 | Draw all from 60 | all from statutory age | recognised from 60 + entitling from statutory |
| `percentage_mukeret_2` | number | `30` | min 0 | % of the annuity that is "recognised" (קצבה מוכרת, tax-free) |
| `pensionEndType2` | select | `fire` | forever/fire/to_date/60 |  |
| `pensionEndDate_2` | date | `` |  |  |
| `withdraw_pizuim` | checkbox | `` |  | Redeem severance (pizuim) at retirement |
| `work_start_year` | number | `` | min 1986 max 2026 | First year of work (severance/pizuim seniority) |
| `withdraw_pizuim_2` | checkbox | `` |  | Redeem severance (pizuim) at retirement |
| `work_start_year_2` | number | `` | min 1986 max 2026 | First year of work (severance/pizuim seniority) |
| `num_loan_fields` | hidden | `0` |  |  |
| `num_keren_fields` | hidden | `0` |  |  |
| `num_income_fields` | hidden | `1` |  |  |
| `num_expense_fields` | hidden | `1` |  |  |
| `num_portfolio_fields` | hidden | `1` |  |  |
| `num_realestate_fields` | hidden | `0` |  |  |

## Keren Hishtalmut row (repeatable)

| field | type | default | options | meaning |
|---|---|---|---|---|
| `kerenBalance1` | number | `0` |  | Keren Hishtalmut balance |
| `kerenDeposit1` | number | `0` |  | Monthly KH deposit |
| `kerenInterest1` | number | `5.0` |  | Expected return [%] |
| `kerenType1` | select | `maslulit` | maslulit/ira | maslulit | IRA |
| `kerenFee1` | number | `0.6` |  | Fee [%] |
| `kerenEndType1` | select | `fire` | forever/fire/to_date/60 | When deposits stop |
| `kerenEndDate1` | date | `` |  |  |

## Loan row (repeatable)

| field | type | default | options | meaning |
|---|---|---|---|---|
| `debtStartDate1` | date | `` |  | Loan start |
| `debtInterest1` | number | `3` |  | Rate [%] |
| `debtInitialSum1` | number | `0` |  | Original principal |
| `debtTotalPeriod1` | number | `0` |  | Original term (years) |
| `debtType1` | select | `spitzer` | spitzer/baloon/grace | spitzer | balloon | grace |

## Real-estate row (repeatable)

| field | type | default | options | meaning |
|---|---|---|---|---|
| `realestateValue1` | number | `0` |  | Current value |
| `realestateRise1` | number | `0.0` |  | Annual appreciation [%] |
