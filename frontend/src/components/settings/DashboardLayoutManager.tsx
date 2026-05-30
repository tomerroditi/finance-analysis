import { useTranslation } from "react-i18next";
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  TouchSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
  arrayMove,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { GripVertical, Eye, EyeOff, RotateCcw } from "lucide-react";
import {
  useDashboardLayout,
  DASHBOARD_CARDS,
  type DashboardCardId,
} from "../../hooks/useDashboardLayout";

const LABEL_KEYS: Record<DashboardCardId, string> = Object.fromEntries(
  DASHBOARD_CARDS.map((c) => [c.id, c.labelKey]),
) as Record<DashboardCardId, string>;

/** One sortable row in the visible-cards list. */
function SortableCardRow({
  id,
  label,
  onHide,
  hideLabel,
}: {
  id: DashboardCardId;
  label: string;
  onHide: () => void;
  hideLabel: string;
}) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id });

  const style: React.CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition,
  };

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={`flex items-center gap-2 rounded-lg border px-3 py-2.5 bg-[var(--surface-light)] ${
        isDragging
          ? "border-[var(--primary)] shadow-lg z-10 relative opacity-95"
          : "border-[var(--surface-light)]"
      }`}
    >
      {/* Drag handle — only the handle starts a drag, so the hide button stays clickable */}
      <button
        type="button"
        {...attributes}
        {...listeners}
        className="touch-none cursor-grab active:cursor-grabbing text-[var(--text-muted)] hover:text-[var(--text-default)] shrink-0"
        aria-label={label}
      >
        <GripVertical size={16} />
      </button>
      <span className="flex-1 text-sm text-[var(--text-default)] truncate" dir="auto">
        {label}
      </span>
      <button
        type="button"
        onClick={onHide}
        aria-label={hideLabel}
        className="p-1.5 rounded-md text-[var(--text-muted)] hover:text-[var(--text-default)] hover:bg-[var(--surface)] transition-colors"
      >
        <Eye size={15} />
      </button>
    </div>
  );
}

/**
 * Dashboard layout editor for the Settings "Dashboard" tab.
 *
 * - Visible cards: a smooth, animated sortable list (@dnd-kit) whose order maps
 *   directly to the dashboard's top-to-bottom card order. Only the grip handle
 *   initiates a drag; neighbours slide out of the way with a spring transition.
 * - Hidden cards: a separate, non-sortable list. Hiding a card removes it from
 *   the sortable area; showing it appends it back to the bottom of the order.
 *
 * The top KPI header is pinned and intentionally absent from both lists.
 */
export function DashboardLayoutManager() {
  const { t } = useTranslation();
  const { layout, setOrder, toggleHidden, reset } = useDashboardLayout();

  const sensors = useSensors(
    // Small activation distance so a click on the handle isn't swallowed as a
    // drag, but a deliberate drag starts immediately and smoothly.
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(TouchSensor, {
      activationConstraint: { delay: 120, tolerance: 6 },
    }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const from = layout.order.indexOf(active.id as DashboardCardId);
    const to = layout.order.indexOf(over.id as DashboardCardId);
    if (from === -1 || to === -1) return;
    setOrder(arrayMove(layout.order, from, to));
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

      {/* Visible / sortable */}
      <div>
        <p className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-2">
          {t("settings.dashboardVisibleCards")}
        </p>
        {layout.order.length === 0 ? (
          <p className="text-xs text-[var(--text-muted)] text-center py-3">
            {t("settings.dashboardNoVisibleCards")}
          </p>
        ) : (
          <DndContext
            sensors={sensors}
            collisionDetection={closestCenter}
            onDragEnd={handleDragEnd}
          >
            <SortableContext items={layout.order} strategy={verticalListSortingStrategy}>
              <div className="space-y-1.5">
                {layout.order.map((id) => (
                  <SortableCardRow
                    key={id}
                    id={id}
                    label={t(LABEL_KEYS[id])}
                    hideLabel={t("settings.dashboardHideCard")}
                    onHide={() => toggleHidden(id)}
                  />
                ))}
              </div>
            </SortableContext>
          </DndContext>
        )}
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
                <span className="flex-1 text-sm text-[var(--text-muted)] truncate" dir="auto">
                  {t(LABEL_KEYS[id])}
                </span>
                <button
                  type="button"
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
