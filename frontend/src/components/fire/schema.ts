/**
 * The reference calculator's input surface, declared once.
 *
 * Field names are the reference's own, so a scenario can be posted straight to
 * `/api/fire/calculate` and compared against a recorded run. Documented in
 * `research/zeke_retire_calc/notes/02-input-surface.md`.
 */

export type FieldKind = "number" | "text" | "date" | "select" | "checkbox";

export interface FieldSpec {
  /** Reference field name, minus the row index for repeatable rows. */
  name: string;
  kind: FieldKind;
  labelKey: string;
  default: string;
  options?: { value: string; labelKey: string }[];
  min?: number;
  max?: number;
  step?: string;
  /** Shown only when this other field has one of these values. */
  visibleWhen?: { field: string; values: string[] };
}

export interface SectionSpec {
  key: string;
  titleKey: string;
  hintKey?: string;
  fields: FieldSpec[];
  /** Repeatable sections are backed by a `num_<countKey>_fields` counter. */
  repeatable?: { countKey: string; addLabelKey: string; max: number };
}

const startTypeOptions = [
  { value: "now", labelKey: "fire.opt.start.now" },
  { value: "fire", labelKey: "fire.opt.start.fire" },
  { value: "from_date", labelKey: "fire.opt.start.fromDate" },
  { value: "one_time", labelKey: "fire.opt.start.oneTime" },
];

const endTypeOptions = [
  { value: "forever", labelKey: "fire.opt.end.forever" },
  { value: "fire", labelKey: "fire.opt.end.fire" },
  { value: "to_date", labelKey: "fire.opt.end.toDate" },
  { value: "60", labelKey: "fire.opt.end.age60" },
];

function flowFields(prefix: string, defaultEnd: string, defaultSum: string): FieldSpec[] {
  return [
    { name: `${prefix}StartType`, kind: "select", labelKey: "fire.field.start",
      default: "now", options: startTypeOptions },
    { name: `${prefix}StartDate`, kind: "date", labelKey: "fire.field.startDate", default: "",
      visibleWhen: { field: `${prefix}StartType`, values: ["from_date", "one_time"] } },
    { name: `${prefix}EndType`, kind: "select", labelKey: "fire.field.end",
      default: defaultEnd, options: endTypeOptions },
    { name: `${prefix}EndDate`, kind: "date", labelKey: "fire.field.endDate", default: "",
      visibleWhen: { field: `${prefix}EndType`, values: ["to_date"] } },
    { name: `${prefix}Sum`, kind: "number", labelKey: "fire.field.amount", default: defaultSum, min: 0 },
    { name: `${prefix}Rise`, kind: "number", labelKey: "fire.field.annualRise", default: "0.0", step: "any" },
    { name: `${prefix}Description`, kind: "text", labelKey: "fire.field.description", default: "" },
  ];
}

function personFields(suffix: string): FieldSpec[] {
  return [
    { name: `pensionName${suffix}`, kind: "text", labelKey: "fire.field.name", default: "" },
    { name: `gender${suffix}`, kind: "select", labelKey: "fire.field.gender", default: "male",
      options: [
        { value: "male", labelKey: "fire.opt.gender.male" },
        { value: "female", labelKey: "fire.opt.gender.female" },
      ] },
    { name: `dateOfBirth${suffix}`, kind: "date", labelKey: "fire.field.dateOfBirth", default: "" },
    { name: `is_american${suffix}`, kind: "select", labelKey: "fire.field.isAmerican", default: "no",
      options: [
        { value: "no", labelKey: "common.no" },
        { value: "yes", labelKey: "common.yes" },
      ] },
  ];
}

function pensionFields(suffix: string, tacticKey: string, endKey: string): FieldSpec[] {
  return [
    { name: `pensionBalance${suffix}`, kind: "number", labelKey: "fire.field.pensionBalance", default: "0", min: 0 },
    { name: `pensionDeposit${suffix}`, kind: "number", labelKey: "fire.field.pensionDeposit", default: "0", min: 0 },
    { name: `pensionFee1${suffix}`, kind: "number", labelKey: "fire.field.feeOnBalance", default: "0.05", min: 0, step: "any" },
    { name: `pensionFee2${suffix}`, kind: "number", labelKey: "fire.field.feeOnDeposit", default: "1.5", min: 0, step: "any" },
    { name: `pensionInterest${suffix}`, kind: "number", labelKey: "fire.field.expectedReturn", default: "7.0", step: "any" },
    { name: tacticKey, kind: "select", labelKey: "fire.field.pensionTactic", default: "60",
      options: [
        { value: "60", labelKey: "fire.opt.tactic.all60" },
        { value: "67", labelKey: "fire.opt.tactic.allStatutory" },
        { value: "60-67", labelKey: "fire.opt.tactic.split" },
      ] },
    { name: `percentage_mukeret${suffix}`, kind: "number", labelKey: "fire.field.mukeretPct", default: "30", min: 0, max: 100 },
    { name: endKey, kind: "select", labelKey: "fire.field.depositsEnd", default: "fire", options: endTypeOptions },
    { name: `pensionEndDate${suffix}`, kind: "date", labelKey: "fire.field.endDate", default: "",
      visibleWhen: { field: endKey, values: ["to_date"] } },
    { name: `withdraw_pizuim${suffix}`, kind: "checkbox", labelKey: "fire.field.withdrawSeverance", default: "" },
    { name: `work_start_year${suffix}`, kind: "number", labelKey: "fire.field.workStartYear", default: "", min: 1986,
      visibleWhen: { field: `withdraw_pizuim${suffix}`, values: ["on"] } },
  ];
}

export const SECTIONS: SectionSpec[] = [
  {
    key: "problem",
    titleKey: "fire.section.problem",
    hintKey: "fire.hint.problem",
    fields: [
      { name: "base_problem", kind: "select", labelKey: "fire.field.baseProblem", default: "retire_asap",
        options: [
          { value: "retire_asap", labelKey: "fire.opt.problem.asap" },
          { value: "retire_at_age", labelKey: "fire.opt.problem.checkup" },
          { value: "improve_cash_to_reach_retire_at_age", labelKey: "fire.opt.problem.improveCash" },
          { value: "increase_risk_to_reach_retire_at_age", labelKey: "fire.opt.problem.increaseRisk" },
        ] },
      { name: "wanted_retire_age", kind: "number", labelKey: "fire.field.targetAge", default: "", min: 18, max: 100,
        visibleWhen: { field: "base_problem", values: [
          "retire_at_age", "improve_cash_to_reach_retire_at_age", "increase_risk_to_reach_retire_at_age"] } },
      { name: "base_problem_max_age", kind: "number", labelKey: "fire.field.maxAge", default: "60", min: 18, max: 100 },
      { name: "base_problem_cash_improve", kind: "number", labelKey: "fire.field.maxCashImprovement", default: "0", min: 0,
        visibleWhen: { field: "base_problem", values: ["improve_cash_to_reach_retire_at_age"] } },
      { name: "base_problem_risk_increase", kind: "number", labelKey: "fire.field.maxRiskIncrease", default: "0", min: 0, step: "any",
        visibleWhen: { field: "base_problem", values: ["increase_risk_to_reach_retire_at_age"] } },
    ],
  },
  { key: "person", titleKey: "fire.section.person", fields: personFields("") },
  {
    key: "partner",
    titleKey: "fire.section.partner",
    fields: [
      { name: "pensionTake_2", kind: "checkbox", labelKey: "fire.field.includePartner", default: "" },
      ...personFields("_2").map((f) => ({
        ...f,
        visibleWhen: { field: "pensionTake_2", values: ["on"] },
      })),
    ],
  },
  {
    key: "withdrawal",
    titleKey: "fire.section.withdrawal",
    hintKey: "fire.hint.withdrawal",
    fields: [
      { name: "retireRule", kind: "number", labelKey: "fire.field.confidence", default: "85", min: 80, max: 100, step: "any" },
      { name: "prati_hishtalmut_order", kind: "select", labelKey: "fire.field.drawOrder", default: "prati",
        options: [
          { value: "prati", labelKey: "fire.opt.order.portfolioFirst" },
          { value: "hishtalmut", labelKey: "fire.opt.order.kerenFirst" },
        ] },
    ],
  },
  {
    key: "cash",
    titleKey: "fire.section.cash",
    fields: [
      { name: "cashBuffer", kind: "number", labelKey: "fire.field.desiredBuffer", default: "0", min: 0 },
      { name: "balance", kind: "number", labelKey: "fire.field.currentBalance", default: "0", step: "any" },
      { name: "creditLimit", kind: "number", labelKey: "fire.field.creditLimit", default: "0", min: 0 },
    ],
  },
  {
    key: "expense",
    titleKey: "fire.section.expenses",
    hintKey: "fire.hint.expenses",
    repeatable: { countKey: "expense", addLabelKey: "fire.action.addExpense", max: 20 },
    fields: flowFields("expense", "forever", "5000"),
  },
  {
    key: "income",
    titleKey: "fire.section.incomes",
    hintKey: "fire.hint.incomes",
    repeatable: { countKey: "income", addLabelKey: "fire.action.addIncome", max: 20 },
    fields: flowFields("income", "fire", "10000"),
  },
  {
    key: "portfolio",
    titleKey: "fire.section.portfolios",
    hintKey: "fire.hint.portfolios",
    repeatable: { countKey: "portfolio", addLabelKey: "fire.action.addPortfolio", max: 20 },
    fields: [
      { name: "portfolioDesignation", kind: "select", labelKey: "fire.field.designation", default: "withdraw",
        options: [
          { value: "withdraw", labelKey: "fire.opt.designation.withdraw" },
          { value: "goal", labelKey: "fire.opt.designation.goal" },
          { value: "mukeret_main", labelKey: "fire.opt.designation.mukeretMain" },
          { value: "mukeret_partner", labelKey: "fire.opt.designation.mukeretPartner" },
        ] },
      { name: "portfolio_type", kind: "select", labelKey: "fire.field.instrument", default: "portfolio",
        options: [
          { value: "portfolio", labelKey: "fire.opt.instrument.broker" },
          { value: "ibkr", labelKey: "fire.opt.instrument.ibkr" },
          { value: "gemel", labelKey: "fire.opt.instrument.gemel" },
          { value: "polisa", labelKey: "fire.opt.instrument.polisa" },
          { value: "kaspit", labelKey: "fire.opt.instrument.kaspit" },
          { value: "pikadon", labelKey: "fire.opt.instrument.pikadon" },
        ] },
      { name: "portfolioBalance", kind: "number", labelKey: "fire.field.balance", default: "0", min: 0 },
      { name: "portfolio_deposit", kind: "number", labelKey: "fire.field.monthlyDepositCap", default: "", min: 0 },
      { name: "portfolio_goal", kind: "number", labelKey: "fire.field.goal", default: "0", min: 0 },
      { name: "portfolioInterest", kind: "number", labelKey: "fire.field.expectedReturn", default: "5.0", step: "any" },
      { name: "portfolioFee", kind: "number", labelKey: "fire.field.fee", default: "0.1", min: 0, step: "any" },
      { name: "portfolioProfitFraction", kind: "number", labelKey: "fire.field.profitFraction", default: "0.0", min: 0, max: 100, step: "any" },
      { name: "portfolio_fifo_lifo", kind: "select", labelKey: "fire.field.lotMethod", default: "flat",
        options: [
          { value: "flat", labelKey: "fire.opt.lot.flat" },
          { value: "fifo", labelKey: "fire.opt.lot.fifo" },
          { value: "lifo", labelKey: "fire.opt.lot.lifo" },
        ] },
      { name: "portfolioDescription", kind: "text", labelKey: "fire.field.description", default: "" },
    ],
  },
  { key: "pension", titleKey: "fire.section.pension", fields: pensionFields("", "pension_tactics", "pensionEndType1") },
  {
    key: "partnerPension",
    titleKey: "fire.section.partnerPension",
    fields: pensionFields("_2", "pension_tactics_2", "pensionEndType2").map((f) => ({
      ...f,
      visibleWhen: f.visibleWhen ?? { field: "pensionTake_2", values: ["on"] },
    })),
  },
  {
    key: "keren",
    titleKey: "fire.section.keren",
    hintKey: "fire.hint.keren",
    repeatable: { countKey: "keren", addLabelKey: "fire.action.addKeren", max: 20 },
    fields: [
      { name: "kerenBalance", kind: "number", labelKey: "fire.field.balance", default: "0", min: 0 },
      { name: "kerenDeposit", kind: "number", labelKey: "fire.field.monthlyDeposit", default: "0", min: 0 },
      { name: "kerenInterest", kind: "number", labelKey: "fire.field.expectedReturn", default: "5.0", step: "any" },
      { name: "kerenType", kind: "select", labelKey: "fire.field.kerenType", default: "maslulit",
        options: [
          { value: "maslulit", labelKey: "fire.opt.keren.maslulit" },
          { value: "ira", labelKey: "fire.opt.keren.ira" },
        ] },
      { name: "kerenFee", kind: "number", labelKey: "fire.field.fee", default: "0.6", min: 0, step: "any" },
      { name: "kerenEndType", kind: "select", labelKey: "fire.field.depositsEnd", default: "fire", options: endTypeOptions },
      { name: "kerenEndDate", kind: "date", labelKey: "fire.field.endDate", default: "",
        visibleWhen: { field: "kerenEndType", values: ["to_date"] } },
    ],
  },
  {
    key: "loan",
    titleKey: "fire.section.loans",
    repeatable: { countKey: "loan", addLabelKey: "fire.action.addLoan", max: 20 },
    fields: [
      { name: "debtStartDate", kind: "date", labelKey: "fire.field.loanStart", default: "" },
      { name: "debtInterest", kind: "number", labelKey: "fire.field.interestRate", default: "3", step: "any" },
      { name: "debtInitialSum", kind: "number", labelKey: "fire.field.originalPrincipal", default: "0", min: 0 },
      { name: "debtTotalPeriod", kind: "number", labelKey: "fire.field.termYears", default: "0", min: 0, max: 80 },
      { name: "debtType", kind: "select", labelKey: "fire.field.loanType", default: "spitzer",
        options: [
          { value: "spitzer", labelKey: "fire.opt.loan.spitzer" },
          { value: "baloon", labelKey: "fire.opt.loan.balloon" },
          { value: "grace", labelKey: "fire.opt.loan.grace" },
        ] },
    ],
  },
  {
    key: "realestate",
    titleKey: "fire.section.realEstate",
    repeatable: { countKey: "realestate", addLabelKey: "fire.action.addProperty", max: 20 },
    fields: [
      { name: "realestateValue", kind: "number", labelKey: "fire.field.currentValue", default: "0", min: 0 },
      { name: "realestateRise", kind: "number", labelKey: "fire.field.annualAppreciation", default: "0.0", step: "any" },
    ],
  },
];

/** Initial flat payload: every non-repeatable default, plus one row each where the reference starts with one. */
export function initialScenario(): Record<string, string> {
  const fields: Record<string, string> = {};
  const counts: Record<string, number> = {
    expense: 1, income: 1, portfolio: 1, keren: 0, loan: 0, realestate: 0,
  };
  for (const section of SECTIONS) {
    if (section.repeatable) {
      const count = counts[section.repeatable.countKey] ?? 0;
      fields[`num_${section.repeatable.countKey}_fields`] = String(count);
      for (let row = 1; row <= count; row += 1) {
        for (const field of section.fields) fields[`${field.name}${row}`] = field.default;
      }
    } else {
      for (const field of section.fields) fields[field.name] = field.default;
    }
  }
  return fields;
}
