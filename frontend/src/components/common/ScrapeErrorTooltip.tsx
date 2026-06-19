import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Info } from "lucide-react";

interface ScrapeErrorTooltipProps {
  message: string;
}

/**
 * Info badge that reveals a scrape's failure reason.
 *
 * Shows the message on hover (desktop) and on tap (mobile) — touch devices have
 * no hover, so the icon is a real button that toggles the tooltip, with a
 * full-screen backdrop to dismiss it on an outside tap.
 */
export function ScrapeErrorTooltip({ message }: ScrapeErrorTooltipProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);

  return (
    <span className="group/err relative inline-flex">
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          setOpen((v) => !v);
        }}
        className="-m-1 p-1 text-red-400"
        aria-label={t("dataSources.showErrorDetails")}
        aria-expanded={open}
      >
        <Info size={12} />
      </button>
      <div
        className={`absolute bottom-full end-0 z-50 mb-1 ${
          open ? "block" : "hidden group-hover/err:block"
        }`}
      >
        <div
          dir="auto"
          className="max-w-[240px] whitespace-normal break-words rounded border border-gray-700 bg-gray-900 p-2 text-[10px] text-white shadow-lg"
        >
          {message}
        </div>
      </div>
      {open && (
        <div
          className="fixed inset-0 z-40"
          aria-hidden="true"
          onClick={() => setOpen(false)}
        />
      )}
    </span>
  );
}
