/**
 * Canonical Transaction type used across the frontend.
 * All fields are optional except `amount` and `date` which are always present.
 */
export interface Transaction {
  id?: number;
  unique_id?: string;
  source?: string;
  desc?: string;
  description?: string;
  amount: number;
  date: string;
  category?: string;
  tag?: string;
  provider?: string;
  account_name?: string;
  account_number?: string;
  pending_refund_id?: number;
  split_id?: number | null;
  /** `"split_child"` on a part of a split transaction. */
  type?: string | null;
  /** On a split part: the transaction it was carved from, and its tag then. */
  parent_unique_id?: number | null;
  parent_category?: string | null;
  parent_tag?: string | null;
  parent_amount?: number | null;
}
