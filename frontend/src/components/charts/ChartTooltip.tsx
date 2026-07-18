import { formatCurrency } from "../../utils/numberFormatting";

interface TooltipEntry {
  name?: string | number;
  value?: number | [number, number];
  color?: string;
  fill?: string;
  stroke?: string;
  dataKey?: string | number;
  hide?: boolean;
}

interface ChartTooltipProps {
  active?: boolean;
  payload?: TooltipEntry[];
  label?: string | number;
  /** Format the header label (e.g. month key → localized month). */
  labelFormatter?: (label: string | number) => string;
  /** Format a value; defaults to formatCurrency. */
  valueFormatter?: (value: number, entry: TooltipEntry) => string;
  /** Skip entries (e.g. helper series that shouldn't show). */
  filter?: (entry: TooltipEntry) => boolean;
}

/**
 * Shared tooltip content for all Recharts charts — dark surface panel with a
 * colour dot + name + currency-formatted value per series. Pass to
 * `<Tooltip content={<ChartTooltip />} />`.
 */
export function ChartTooltip({
  active,
  payload,
  label,
  labelFormatter,
  valueFormatter,
  filter,
}: ChartTooltipProps) {
  if (!active || !payload || payload.length === 0) return null;
  const entries = payload.filter(
    (e) => !e.hide && e.value !== undefined && (!filter || filter(e)),
  );
  if (entries.length === 0) return null;

  return (
    <div className="rounded-lg border border-[rgba(148,163,184,0.2)] bg-[#1e293b] px-3 py-2 text-xs text-[#e2e8f0] shadow-lg">
      {label !== undefined && label !== "" && (
        <p className="mb-1 font-bold">
          {labelFormatter ? labelFormatter(label) : label}
        </p>
      )}
      {entries.map((entry, i) => {
        const color = entry.color ?? entry.stroke ?? entry.fill;
        const value = entry.value as number | [number, number];
        const text = Array.isArray(value)
          ? `${format(value[0], entry, valueFormatter)} – ${format(value[1], entry, valueFormatter)}`
          : format(value, entry, valueFormatter);
        return (
          <p key={`${entry.dataKey ?? entry.name ?? i}`} className="flex items-center gap-1.5">
            {color && (
              <span
                className="inline-block h-2 w-2 shrink-0 rounded-full"
                style={{ backgroundColor: color }}
              />
            )}
            {entry.name !== undefined && (
              <span className="text-[#94a3b8]">{entry.name}:</span>
            )}
            <span className="font-semibold">{text}</span>
          </p>
        );
      })}
    </div>
  );
}

function format(
  value: number,
  entry: TooltipEntry,
  valueFormatter?: (value: number, entry: TooltipEntry) => string,
): string {
  return valueFormatter ? valueFormatter(value, entry) : formatCurrency(value);
}
