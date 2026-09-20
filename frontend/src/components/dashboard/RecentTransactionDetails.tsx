import { useTranslation } from "react-i18next";
import type { Transaction } from "../../types/transaction";
import { formatDate } from "../../utils/dateFormatting";
import { formatCurrency } from "../../utils/numberFormatting";
import { humanizeProvider, humanizeService } from "../../utils/textFormatting";

/**
 * Read-only detail sheet for one transaction in the dashboard's recent feed.
 *
 * The feed row only has room for the description, the category/tag and the
 * amount, so everything that identifies *where* the money moved — provider,
 * account, the credit card's last four digits — lives here, behind the row's
 * "Details" action.
 */
export function RecentTransactionDetails({ tx }: { tx: Transaction }) {
  const { t } = useTranslation();

  const isCreditCard = tx.source === "credit_card_transactions";
  const description = tx.description || tx.desc || "";

  const rows: { label: string; value: string; ltr?: boolean }[] = [
    { label: t("common.description"), value: description || t("transactions.noDescription") },
    { label: t("common.date"), value: formatDate(tx.date), ltr: true },
    { label: t("common.amount"), value: formatCurrency(tx.amount), ltr: true },
    {
      label: t("common.category"),
      value: tx.category || t("common.uncategorized"),
    },
    { label: t("common.tag"), value: tx.tag && tx.tag !== "-" ? tx.tag : "—" },
    {
      label: t("transactions.details.provider"),
      value: tx.provider ? humanizeProvider(tx.provider) : "—",
    },
    { label: t("common.account"), value: tx.account_name || "—" },
  ];

  if (tx.account_number) {
    rows.push({
      label: isCreditCard
        ? t("transactions.details.cardNumber")
        : t("transactions.details.accountNumber"),
      value: isCreditCard ? `•••• ${tx.account_number.slice(-4)}` : tx.account_number,
      ltr: true,
    });
  }

  if (tx.source) {
    rows.push({
      label: t("transactions.table.source"),
      value: humanizeService(tx.source),
    });
  }

  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5 px-3 py-2 text-xs">
      {rows.map((row) => (
        <div key={row.label} className="contents">
          <dt className="text-[var(--text-muted)] whitespace-nowrap">{row.label}</dt>
          <dd
            className="text-[var(--text-default)] break-words text-end"
            dir={row.ltr ? "ltr" : "auto"}
          >
            {row.value}
          </dd>
        </div>
      ))}
    </dl>
  );
}
