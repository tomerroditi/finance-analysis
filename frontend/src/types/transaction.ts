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
}
