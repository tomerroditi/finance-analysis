// Type definitions for the file-import data-source feature.
// Mirrors backend/services/file_import_parser.py + backend/routes/imported_accounts.py.

export type ImportService = "banks" | "credit_cards" | "cash";

export type AmountMode = "single" | "split";
export type SignConvention = "positive_is_income" | "positive_is_expense";

export type DateFormat =
  | "auto"
  | "iso"
  | "dd/mm/yyyy"
  | "mm/dd/yyyy"
  | "dd-mm-yyyy"
  | "dd.mm.yyyy"
  | "excel_serial";

export interface FieldRef {
  column: string | null;
  format?: DateFormat;
}

export type AmountMapping =
  | {
      mode: "single";
      column: string;
      sign_convention: SignConvention;
    }
  | {
      mode: "split";
      debit_column: string;
      credit_column: string;
    };

export interface ColumnMapping {
  skip_rows: number;
  date: { column: string; format: DateFormat };
  description: { column: string };
  amount: AmountMapping;
  category: FieldRef;
  tag: FieldRef;
  account_number: FieldRef;
}

export interface ImportedAccount {
  id: number;
  service: ImportService;
  provider: string;
  account_name: string;
  mapping: ColumnMapping;
}

export interface PreviewResponse {
  rows: Array<{
    date: string;
    description: string;
    amount: number;
    category?: string;
    tag?: string;
    account_number?: string;
  }>;
  dropped_invalid: number;
  raw_headers: string[];
}

export interface ImportSummary {
  inserted: number;
  skipped_duplicates: number;
  dropped_invalid: number;
}
