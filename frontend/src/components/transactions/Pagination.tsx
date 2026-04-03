import {
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
} from "lucide-react";
import { useTranslation } from "react-i18next";

interface PaginationProps {
  currentPage: number;
  totalPages: number;
  totalItems: number;
  startRow: number;
  endRow: number;
  rowsPerPage: number;
  rowsPerPageOptions?: number[] | null;
  onPageChange: (page: number) => void;
  onRowsPerPageChange?: (rows: number) => void;
  compact?: boolean;
}

export function Pagination({
  currentPage,
  totalPages,
  totalItems,
  startRow,
  endRow,
  rowsPerPage,
  rowsPerPageOptions,
  onPageChange,
  onRowsPerPageChange,
  compact = false,
}: PaginationProps) {
  const { t } = useTranslation();

  if (totalPages <= 0) return null;

  return (
    <div
      className={`flex flex-col sm:flex-row items-center justify-between gap-2 ${compact ? "mt-3 px-2" : "mt-4 px-2 md:px-4 py-3 bg-[var(--surface-light)]/30 border-t border-[var(--surface-light)]"}`}
    >
      <div className="flex items-center gap-2 md:gap-4">
        <span className="text-xs md:text-sm text-[var(--text-muted)] whitespace-nowrap">
          {totalItems > 0 ? (
            <>
              {t("transactions.pagination.showing")}{" "}
              <span className="text-white font-medium">{startRow}</span> {t("transactions.pagination.to")}{" "}
              <span className="text-white font-medium">{endRow}</span> {t("transactions.pagination.of")}{" "}
              <span className="text-white font-medium">
                {totalItems}
              </span>
            </>
          ) : (
            t("transactions.noResults")
          )}
        </span>
        {rowsPerPageOptions && onRowsPerPageChange && (
          <div className="flex items-center gap-2">
            <span className="text-sm text-[var(--text-muted)] whitespace-nowrap">
              {t("transactions.pagination.rows")}:
            </span>
            <select
              value={rowsPerPage}
              onChange={(e) => {
                onRowsPerPageChange(Number(e.target.value));
                onPageChange(1);
              }}
              className="bg-[var(--surface)] border border-[var(--surface-light)] rounded px-2 py-1 text-sm outline-none"
            >
              {rowsPerPageOptions.map((opt) => (
                <option key={opt} value={opt}>
                  {opt}
                </option>
              ))}
            </select>
          </div>
        )}
      </div>
      <div className="flex items-center gap-1">
        <button
          onClick={() => onPageChange(1)}
          disabled={currentPage === 1}
          className="p-1 rounded hover:bg-[var(--surface-light)] text-[var(--text-muted)] disabled:opacity-30 transition-colors"
        >
          <ChevronsLeft size={compact ? 16 : 20} />
        </button>
        <button
          onClick={() => onPageChange(Math.max(1, currentPage - 1))}
          disabled={currentPage === 1}
          className="p-1 rounded hover:bg-[var(--surface-light)] text-[var(--text-muted)] disabled:opacity-30 transition-colors"
        >
          <ChevronLeft size={compact ? 16 : 20} />
        </button>
        <span className="px-4 text-sm whitespace-nowrap">
          {t("transactions.pagination.page")} <span className="text-white font-medium">{currentPage}</span>{" "}
          {t("transactions.pagination.of")}{" "}
          <span className="text-white font-medium">{totalPages || 1}</span>
        </span>
        <button
          onClick={() => onPageChange(Math.min(totalPages, currentPage + 1))}
          disabled={currentPage === totalPages || totalPages === 0}
          className="p-1 rounded hover:bg-[var(--surface-light)] text-[var(--text-muted)] disabled:opacity-30 transition-colors"
        >
          <ChevronRight size={compact ? 16 : 20} />
        </button>
        <button
          onClick={() => onPageChange(totalPages)}
          disabled={currentPage === totalPages || totalPages === 0}
          className="p-1 rounded hover:bg-[var(--surface-light)] text-[var(--text-muted)] disabled:opacity-30 transition-colors"
        >
          <ChevronsRight size={compact ? 16 : 20} />
        </button>
      </div>
    </div>
  );
}
