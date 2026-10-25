import { Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";

interface LoadingSpinnerProps {
  /** Already-translated caption; defaults to `common.loading`. */
  label?: string;
  /** Inline variant for a row or a card section. Default fills a panel. */
  size?: "panel" | "inline";
  className?: string;
}

/**
 * Centered spinner for a region whose data is still loading — shown in place
 * of its empty state, which would otherwise claim there is nothing to show.
 */
export function LoadingSpinner({
  label,
  size = "panel",
  className = "",
}: LoadingSpinnerProps) {
  const { t } = useTranslation();
  const sizing =
    size === "inline" ? "py-3 text-xs" : "py-8 md:py-12 text-sm";
  return (
    <div
      role="status"
      data-testid="loading-spinner"
      className={`flex items-center justify-center gap-2 text-[var(--text-muted)] ${sizing} ${className}`}
    >
      <Loader2 size={size === "inline" ? 14 : 20} className="animate-spin shrink-0" />
      {label ?? t("common.loading")}
    </div>
  );
}
