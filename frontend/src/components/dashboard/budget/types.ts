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
  /**
   * Whether this envelope has been settled, for the tabs that can close one.
   * Monthly rules have no such state and leave it undefined; the grid only
   * draws the closed treatment where a tab also passes `onToggleClosed`.
   */
  closed?: boolean;
}
