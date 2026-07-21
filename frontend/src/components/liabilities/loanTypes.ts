import type { LoanType } from "../../services/api";

export const LOAN_TYPES: LoanType[] = [
  "fixed_unlinked",
  "prime_linked",
  "variable_unlinked",
];

export const AMORTIZATION_METHODS = [
  "shpitzer",
  "equal_principal",
  "balloon",
] as const;

/** Prime-based types price off the BoI prime series instead of a flat rate. */
export const isPrimeBased = (loanType: string) =>
  loanType === "prime_linked" || loanType === "variable_unlinked";
