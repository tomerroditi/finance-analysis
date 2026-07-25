import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Info } from "lucide-react";

interface ScrapeErrorTooltipProps {
  /**
   * Technical detail recorded by the backend — the provider's own message, HTTP
   * body or exception text. Shown as secondary copy, never as the headline.
   */
  message?: string;
  /**
   * Failure category from the backend (`INVALID_PASSWORD`, `TIMEOUT`, …). Picks
   * the translated explanation. Undefined for scrapes recorded before the
   * backend tracked it — those fall back to showing `message` alone.
   */
  errorType?: string;
}

/**
 * Categories with their own translated explanation under
 * `dataSources.scrapeError.*`. Anything else falls back to the generic copy, so
 * a category the backend adds later degrades to "something went wrong" plus the
 * technical detail rather than rendering a raw `dataSources.scrapeError.FOO`
 * key path at the user.
 */
const KNOWN_ERROR_TYPES = [
  "INVALID_PASSWORD",
  "CHANGE_PASSWORD",
  "ACCOUNT_BLOCKED",
  "TWO_FACTOR_RETRIEVER_MISSING",
  "TIMEOUT",
  "NO_ACCOUNTS",
  "INIT_ERROR",
] as const;

/**
 * Info badge that explains why a scrape failed.
 *
 * Separates the two audiences that used to share one string: the headline is
 * friendly translated copy chosen by `errorType`, and the provider's raw text
 * sits underneath as opt-in technical detail. Before this the raw text *was*
 * the message, so it had to be either debuggable or readable — never both.
 *
 * Shows on hover (desktop) and on tap (mobile) — touch devices have no hover,
 * so the icon is a real button that toggles the tooltip, with a full-screen
 * backdrop to dismiss it on an outside tap.
 */
export function ScrapeErrorTooltip({ message, errorType }: ScrapeErrorTooltipProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);

  const known = errorType
    ? (KNOWN_ERROR_TYPES as readonly string[]).includes(errorType)
    : false;
  const headline = known
    ? t(`dataSources.scrapeError.${errorType}`)
    : t("dataSources.scrapeError.GENERAL_ERROR");
  const detail = (message || "").trim();

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
        <div className="max-w-[240px] rounded border border-gray-700 bg-gray-900 p-2 text-[10px] shadow-lg">
          <p className="whitespace-normal break-words font-semibold text-white">
            {headline}
          </p>
          {!!detail && (
            <>
              <p className="mt-1.5 text-[9px] font-bold uppercase tracking-wider text-gray-500">
                {t("dataSources.errorTechnicalDetails")}
              </p>
              {/* dir="auto" — provider text may be Hebrew, and it must not be
                  forced into the surrounding UI direction. */}
              <p
                dir="auto"
                className="whitespace-normal break-words font-mono text-[9px] leading-snug text-gray-400"
              >
                {detail}
              </p>
            </>
          )}
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
