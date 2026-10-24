import i18n from "../i18n";
import type { Transaction } from "../types/transaction";
import { humanizeProvider, humanizeService } from "./textFormatting";

/**
 * A source filter value: `""` for every source, `service:<table>` for every
 * account of one kind (all credit cards, all bank accounts), or
 * `account:<id>` for a single account.
 */
export type SourceFilter = string;

export interface SourceOption {
  label: string;
  value: SourceFilter;
  /** The table the option's rows come from; absent on "all sources". */
  source?: string;
}

const SERVICE_PREFIX = "service:";
const ACCOUNT_PREFIX = "account:";

const SERVICE_ORDER = [
  "credit_card_transactions",
  "bank_transactions",
  "cash_transactions",
  "manual_investment_transactions",
  "insurance_transactions",
];

const SERVICE_LABEL_KEYS: Record<string, string> = {
  credit_card_transactions: "dashboard.sourceFilter.creditCards",
  bank_transactions: "dashboard.sourceFilter.banks",
  cash_transactions: "dashboard.sourceFilter.cash",
  manual_investment_transactions: "dashboard.sourceFilter.investments",
  insurance_transactions: "dashboard.sourceFilter.insurance",
};

/** An account is its table plus provider, name and number — `unique_id` is per-table. */
function accountId(tx: Transaction): string {
  return JSON.stringify([
    tx.source ?? "",
    tx.provider ?? "",
    tx.account_name ?? "",
    tx.account_number ?? "",
  ]);
}

function accountLabel(tx: Transaction): string {
  const parts = [
    tx.provider ? humanizeProvider(tx.provider) : "",
    tx.account_name ?? "",
  ].filter(Boolean);
  const name = parts.join(" · ") || humanizeService(tx.source ?? "");
  return tx.source === "credit_card_transactions" && tx.account_number
    ? `${name} ••${tx.account_number.slice(-4)}`
    : name;
}

function serviceRank(source: string): number {
  const rank = SERVICE_ORDER.indexOf(source);
  return rank === -1 ? SERVICE_ORDER.length : rank;
}

/**
 * The options a source picker offers for these transactions: "all sources",
 * then every kind of source present (credit cards and bank accounts first —
 * the two most picked), then the accounts of each kind that has more than one.
 */
export function sourceOptions(transactions: Transaction[]): SourceOption[] {
  const accountsBySource = new Map<string, Map<string, string>>();
  for (const tx of transactions) {
    if (!tx.source) continue;
    let accounts = accountsBySource.get(tx.source);
    if (!accounts) {
      accounts = new Map();
      accountsBySource.set(tx.source, accounts);
    }
    const id = accountId(tx);
    if (!accounts.has(id)) accounts.set(id, accountLabel(tx));
  }

  const options: SourceOption[] = [
    { label: i18n.t("dashboard.sourceFilter.all"), value: "" },
  ];
  const sources = [...accountsBySource.keys()].sort(
    (a, b) => serviceRank(a) - serviceRank(b) || a.localeCompare(b),
  );
  for (const source of sources) {
    const labelKey = SERVICE_LABEL_KEYS[source];
    options.push({
      label: labelKey ? i18n.t(labelKey) : humanizeService(source),
      value: `${SERVICE_PREFIX}${source}`,
      source,
    });
  }
  for (const source of sources) {
    const accounts = accountsBySource.get(source)!;
    if (accounts.size < 2) continue;
    const sorted = [...accounts.entries()].sort(([, a], [, b]) => a.localeCompare(b));
    for (const [id, label] of sorted) {
      options.push({ label, value: `${ACCOUNT_PREFIX}${id}`, source });
    }
  }
  return options;
}

/** Whether `tx` came from the source `filter` names. */
export function matchesSource(tx: Transaction, filter: SourceFilter): boolean {
  if (!filter) return true;
  if (filter.startsWith(SERVICE_PREFIX)) {
    return tx.source === filter.slice(SERVICE_PREFIX.length);
  }
  if (filter.startsWith(ACCOUNT_PREFIX)) {
    return accountId(tx) === filter.slice(ACCOUNT_PREFIX.length);
  }
  return true;
}
