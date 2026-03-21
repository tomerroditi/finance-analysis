import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  startOfMonth,
  endOfMonth,
  startOfYear,
  endOfYear,
  subMonths,
  format,
} from "date-fns";
import { he } from "date-fns/locale/he";
import i18n from "../i18n";
import { Calendar as CalendarIcon, ChevronDown } from "lucide-react";

export type DateRange = {
  start: Date | null;
  end: Date | null;
};

interface DateRangePickerProps {
  value: DateRange;
  onChange: (range: DateRange) => void;
}

export function DateRangePicker({ value, onChange }: DateRangePickerProps) {
  const { t } = useTranslation();
  const [isOpen, setIsOpen] = useState(false);

  const presets = [
    {
      label: t("dateRange.allTime"),
      getValue: () => ({ start: null, end: null }),
    },
    {
      label: t("dateRange.currentMonth"),
      getValue: () => ({
        start: startOfMonth(new Date()),
        end: endOfMonth(new Date()),
      }),
    },
    {
      label: t("dateRange.lastMonth"),
      getValue: () => {
        const lastMonth = subMonths(new Date(), 1);
        return { start: startOfMonth(lastMonth), end: endOfMonth(lastMonth) };
      },
    },
    {
      label: t("dateRange.currentYear"),
      getValue: () => ({
        start: startOfYear(new Date()),
        end: endOfMonth(new Date()),
      }), // End of update is usually today or end of year
    },
    {
      label: t("dateRange.lastYear"),
      getValue: () => {
        const d = new Date();
        d.setFullYear(d.getFullYear() - 1);
        return { start: startOfYear(d), end: endOfYear(d) };
      },
    },
    {
      label: t("dateRange.last12Months"),
      getValue: () => ({ start: subMonths(new Date(), 12), end: new Date() }),
    },
  ];

  const formatDate = (d: Date | null) => (d ? format(d, "dd/MM/yyyy", i18n.language === "he" ? { locale: he } : undefined) : "...");

  return (
    <div className="relative">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 px-4 py-2 bg-[var(--surface)] border border-[var(--surface-light)] rounded-lg hover:border-[var(--primary)] transition-colors"
      >
        <CalendarIcon size={16} className="text-[var(--text-muted)]" />
        <span className="text-sm font-medium">
          {value.start && value.end
            ? `${formatDate(value.start)} - ${formatDate(value.end)}`
            : value.start === null && value.end === null
              ? t("dateRange.allTime")
              : t("dateRange.selectDateRange")}
        </span>
        <ChevronDown
          size={14}
          className={`text-[var(--text-muted)] transition-transform ${isOpen ? "rotate-180" : ""}`}
        />
      </button>

      {isOpen && (
        <>
          <div
            className="fixed inset-0 z-10"
            onClick={() => setIsOpen(false)}
          />
          <div className="absolute end-0 top-full mt-2 w-64 bg-[var(--surface)] border border-[var(--surface-light)] rounded-xl shadow-xl z-20 p-2">
            <div className="space-y-1">
              {presets.map((preset) => (
                <button
                  key={preset.label}
                  onClick={() => {
                    onChange(preset.getValue());
                    setIsOpen(false);
                  }}
                  className="w-full text-start px-3 py-2 text-sm rounded-lg hover:bg-[var(--surface-light)] transition-colors"
                >
                  {preset.label}
                </button>
              ))}
            </div>

            <div className="border-t border-[var(--surface-light)] my-2 pt-2">
              <p className="text-xs text-[var(--text-muted)] px-3 mb-2">
                {t("dateRange.customRange")}
              </p>
              <div className="grid grid-cols-2 gap-2 px-2">
                <input
                  type="date"
                  className="w-full bg-[var(--background)] border border-[var(--surface-light)] rounded px-2 py-1 text-xs"
                  value={value.start ? format(value.start, "yyyy-MM-dd") : ""}
                  onChange={(e) =>
                    onChange({ ...value, start: e.target.valueAsDate })
                  }
                />
                <input
                  type="date"
                  className="w-full bg-[var(--background)] border border-[var(--surface-light)] rounded px-2 py-1 text-xs"
                  value={value.end ? format(value.end, "yyyy-MM-dd") : ""}
                  onChange={(e) =>
                    onChange({ ...value, end: e.target.valueAsDate })
                  }
                />
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
