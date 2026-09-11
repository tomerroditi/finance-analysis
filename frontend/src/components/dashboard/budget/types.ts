/**
 * The single shape the dashboard's rule grid renders. Monthly, yearly and
 * project analyses each return a different rule payload; every tab normalizes
 * to this before handing rows to the grid.
 */
export interface BudgetRule {
  id: number;
  name: string;
  category: string;
  budget_amount: number;
  spent_amount: number;
}
