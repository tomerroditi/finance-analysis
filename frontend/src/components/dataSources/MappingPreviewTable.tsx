import { useTranslation } from "react-i18next";
import { formatCurrency } from "../../utils/numberFormatting";

interface PreviewRow {
  date: string;
  description: string;
  amount: number;
  category?: string;
  tag?: string;
}

interface Props {
  rows: PreviewRow[];
}

/**
 * Read-only table showing how the first few rows of an uploaded file
 * will look after the column mapping is applied.
 */
export function MappingPreviewTable({ rows }: Props) {
  const { t } = useTranslation();
  if (rows.length === 0) {
    return (
      <div className="text-xs text-[var(--text-muted)] italic">
        {t("dataSources.import.mappingMappedPreview")}…
      </div>
    );
  }
  return (
    <div className="overflow-x-auto rounded-xl border border-[var(--surface-light)]">
      <table className="w-full min-w-[480px] text-xs">
        <thead>
          <tr className="text-[10px] uppercase tracking-widest text-[var(--text-muted)] border-b border-[var(--surface-light)] bg-[var(--surface-light)]/40">
            <th className="text-start px-3 py-2 font-bold whitespace-nowrap">
              {t("common.date")}
            </th>
            <th className="text-start px-3 py-2 font-bold whitespace-nowrap">
              {t("common.description")}
            </th>
            <th className="text-center px-3 py-2 font-bold whitespace-nowrap">
              {t("common.amount")}
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, idx) => (
            <tr
              key={`${row.date}-${idx}`}
              className="border-b border-[var(--surface-light)]/40"
            >
              <td className="text-start px-3 py-2 whitespace-nowrap font-mono">
                {row.date}
              </td>
              <td
                className="text-start px-3 py-2 whitespace-nowrap truncate max-w-[240px]"
                dir="auto"
              >
                {row.description}
              </td>
              <td className="text-center px-3 py-2 whitespace-nowrap">
                <span dir="ltr">{formatCurrency(row.amount)}</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
