import React from "react";
import { Archive, ArchiveRestore, Pencil, Trash2 } from "lucide-react";

const ACTION_ICON = {
  edit: Pencil,
  delete: Trash2,
  close: Archive,
  reopen: ArchiveRestore,
} as const;

interface RuleRowActionProps {
  kind: keyof typeof ACTION_ICON;
  label: string;
  /** Omit to render the action disabled — the rule does not allow it. */
  onClick?: () => void;
  testId?: string;
}

/**
 * One action in an expanded rule row's panel.
 *
 * Icon *and* label, unlike the Budget page's icon-only `LedgerRowAction`: the
 * panel only exists because it was tapped open, so it is read on a phone as
 * often as with a mouse, and an unlabelled icon there is a guess. Destructive
 * red stays reserved for delete — closing a rule is reversible
 * bookkeeping, so it takes the same neutral hover as edit.
 */
export const RuleRowAction: React.FC<RuleRowActionProps> = ({
  kind,
  label,
  onClick,
  testId,
}) => {
  const Icon = ACTION_ICON[kind];
  const enabled =
    kind === "delete"
      ? "hover:text-red-500 hover:bg-red-500/10"
      : "hover:text-blue-500 hover:bg-blue-500/10";
  return (
    <button
      type="button"
      data-testid={testId}
      disabled={!onClick}
      onClick={onClick}
      title={label}
      aria-label={label}
      className={`inline-flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-[11px] font-medium transition-all ${
        onClick
          ? `text-[var(--text-muted)] ${enabled}`
          : "cursor-not-allowed text-[var(--text-muted)]/25"
      }`}
    >
      <Icon size={13} className="shrink-0" />
      {label}
    </button>
  );
};
