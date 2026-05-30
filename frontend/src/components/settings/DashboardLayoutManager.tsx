import { useState } from "react";
import { useTranslation } from "react-i18next";
import { GripVertical, Eye, EyeOff, RotateCcw } from "lucide-react";
import {
  useDashboardLayout,
  DASHBOARD_CARDS,
  type DashboardCardId,
} from "../../hooks/useDashboardLayout";

const LABEL_KEYS: Record<DashboardCardId, string> = Object.fromEntries(
  DASHBOARD_CARDS.map((c) => [c.id, c.labelKey]),
) as Record<DashboardCardId, string>;

/**
 * Dashboard layout editor for the Settings "Dashboard" tab.
 *
 * - Visible cards: a vertically draggable list (native HTML5 DnD) whose order
 *   maps directly to the dashboard's top-to-bottom card order.
 * - Hidden cards: a separate, non-draggable list. Hiding a card removes it from
 *   the draggable area; showing it appends it back to the bottom of the order.
 *
 * The top KPI header is pinned and intentionally absent from both lists.
 */
export function DashboardLayoutManager() {
  const { t } = useTranslation();
  const { layout, setOrder, toggleHidden, reset } = useDashboardLayout();
  const [dragId, setDragId] = useState<DashboardCardId | null>(null);
  const [overId, setOverId] = useState<DashboardCardId | null>(null);

  const handleDrop = (targetId: DashboardCardId) => {
    if (!dragId || dragId === targetId) {
      setDragId(null);
      setOverId(null);
      return;
    }
    const next = [...layout.order];
    const from = next.indexOf(dragId);
    const to = next.indexOf(targetId);
    if (from === -1 || to === -1) return;
    next.splice(from, 1);
    next.splice(to, 0, dragId);
    setOrder(next);
    setDragId(null);
    setOverId(null);
  };

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between gap-2">
        <p className="text-[11px] text-[var(--text-muted)]">
          {t("settings.dashboardLayoutHelp")}
        </p>
        <button
          onClick={reset}
          className="shrink-0 flex items-center gap-1 text-xs font-medium text-[var(--text-muted)] hover:text-[var(--text-default)] transition-colors"
        >
          <RotateCcw size={13} />
          {t("settings.dashboardLayoutReset")}
        </button>
      </div>

      {/* Visible / draggable */}
      <div>
        <p className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-2">
          {t("settings.dashboardVisibleCards")}
        </p>
        <div className="space-y-1.5">
          {layout.order.length === 0 && (
            <p className="text-xs text-[var(--text-muted)] text-center py-3">
              {t("settings.dashboardNoVisibleCards")}
            </p>
          )}
          {layout.order.map((id) => (
            <div
              key={id}
              draggable
              onDragStart={() => setDragId(id)}
              onDragEnd={() => {
                setDragId(null);
                setOverId(null);
              }}
              onDragOver={(e) => {
                e.preventDefault();
                if (overId !== id) setOverId(id);
              }}
              onDrop={() => handleDrop(id)}
              className={`flex items-center gap-2 rounded-lg border px-3 py-2.5 bg-[var(--surface-light)] cursor-grab active:cursor-grabbing transition-colors ${
                overId === id && dragId && dragId !== id
                  ? "border-[var(--primary)]"
                  : "border-[var(--surface-light)]"
              } ${dragId === id ? "opacity-50" : ""}`}
            >
              <GripVertical size={16} className="text-[var(--text-muted)] shrink-0" />
              <span className="flex-1 text-sm text-[var(--text-default)] truncate">
                {t(LABEL_KEYS[id])}
              </span>
              <button
                onClick={() => toggleHidden(id)}
                aria-label={t("settings.dashboardHideCard")}
                className="p-1.5 rounded-md text-[var(--text-muted)] hover:text-[var(--text-default)] hover:bg-[var(--surface)] transition-colors"
              >
                <Eye size={15} />
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* Hidden */}
      {layout.hidden.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-2">
            {t("settings.dashboardHiddenCards")}
          </p>
          <div className="space-y-1.5">
            {layout.hidden.map((id) => (
              <div
                key={id}
                className="flex items-center gap-2 rounded-lg border border-dashed border-[var(--surface-light)] px-3 py-2.5 opacity-70"
              >
                <EyeOff size={16} className="text-[var(--text-muted)] shrink-0" />
                <span className="flex-1 text-sm text-[var(--text-muted)] truncate">
                  {t(LABEL_KEYS[id])}
                </span>
                <button
                  onClick={() => toggleHidden(id)}
                  aria-label={t("settings.dashboardShowCard")}
                  className="p-1.5 rounded-md text-[var(--text-muted)] hover:text-[var(--primary)] hover:bg-[var(--surface)] transition-colors"
                >
                  <Eye size={15} />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
