import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Loader2 } from "lucide-react";

interface PendingButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  /** The write this button fired is out: the button turns busy until it settles. */
  pending: boolean;
  /** The button's leading icon, which the spinner takes the place of while pending. */
  icon?: ReactNode;
  /** Spinner size in px; match the icon it replaces. */
  spinnerSize?: number;
  /**
   * The button draws {@link SavingSpinner} itself, where its own layout wants
   * it (a row whose right-hand badge it replaces): only disabled and busy here.
   */
  ownSpinner?: boolean;
}

/** The spinner a busy control shows; for a control that is not a button. */
export function SavingSpinner({ size = 14 }: { size?: number }) {
  return <Loader2 size={size} className="animate-spin shrink-0" aria-hidden="true" />;
}

/**
 * A button that fires a write the screen cannot answer from the cache, and so
 * waits for the server: while the write is out it is disabled, busy for
 * assistive tech, and spins — in place of its icon when it has one, ahead of
 * its label otherwise. The label stays, so the button keeps its size.
 *
 * A disabled button alone reads as broken: nothing says the click was taken.
 * See `.claude/rules/frontend_writes.md` → "Writes that wait".
 */
export function PendingButton({
  pending,
  icon,
  spinnerSize = 14,
  ownSpinner = false,
  disabled,
  children,
  type = "button",
  ...rest
}: PendingButtonProps) {
  const lead = pending && !ownSpinner ? <SavingSpinner size={spinnerSize} /> : icon;
  return (
    <button
      {...rest}
      type={type}
      disabled={disabled || pending}
      aria-busy={pending || undefined}
      data-pending={pending || undefined}
    >
      {lead !== undefined && children !== undefined && children !== null ? (
        <span className="inline-flex items-center justify-center gap-1.5">
          {lead}
          {children}
        </span>
      ) : (
        (lead ?? children)
      )}
    </button>
  );
}
