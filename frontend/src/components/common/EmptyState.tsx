import { Fragment, type ComponentType, type ReactNode } from "react";
import { type LucideProps } from "lucide-react";

interface EmptyStateProps {
  /** Lucide icon component shown above the title. Omit for icon-less variant. */
  icon?: ComponentType<LucideProps>;
  /** Headline — short, sentence case. Already-translated string. */
  title: string;
  /** Optional supporting copy. Already-translated string. */
  description?: string;
  /**
   * Optional 2–4 step cards rendered between the description and the CTA
   * buttons. Use for onboarding flows where the user needs a sequence of
   * actions to get data flowing (connect → scrape → analyse).
   */
  steps?: Array<{ title: string; description: string }>;
  /**
   * Primary call-to-action. Use a single CTA per empty state — the goal
   * is to give the user one obvious next step.
   */
  cta?: {
    label: string;
    onClick: () => void;
  };
  /**
   * Secondary supporting action (e.g. "Try demo mode"). Render only when
   * the primary CTA is present and a true alternative exists.
   */
  secondary?: {
    label: string;
    onClick: () => void;
  };
  /**
   * Optional fully-rendered footer slot for cases where the action isn't
   * a single button (e.g. inline confirmation dialogs).
   */
  footer?: ReactNode;
  /** Compact variant for inline / in-card usage. Default is page-level. */
  size?: "page" | "inline";
  className?: string;
}

/**
 * Per-page empty-state placeholder with an optional 3-step onboarding flow
 * and a single primary CTA.
 *
 * The component is presentational: callers are responsible for translating
 * all string props via i18next before passing them in.
 */
export function EmptyState({
  icon: Icon,
  title,
  description,
  steps,
  cta,
  secondary,
  footer,
  size = "page",
  className = "",
}: EmptyStateProps) {
  const isPage = size === "page";

  const containerClasses = isPage
    ? "bg-[var(--surface)] border border-dashed border-[var(--surface-light)] rounded-3xl p-8 md:p-16 text-center"
    : "bg-[var(--surface-light)]/40 border border-dashed border-[var(--surface-light)] rounded-2xl p-6 md:p-8 text-center";

  const iconClasses = isPage
    ? "p-4 bg-[var(--surface-light)] rounded-2xl w-fit mx-auto mb-6 text-[var(--text-muted)]"
    : "p-3 bg-[var(--surface-light)] rounded-xl w-fit mx-auto mb-4 text-[var(--text-muted)]";

  const titleClasses = isPage
    ? "text-xl md:text-2xl font-bold mb-2"
    : "text-lg font-bold mb-2";

  return (
    <div role="status" className={`${containerClasses} ${className}`}>
      {Icon && (
        <div className={iconClasses}>
          <Icon size={isPage ? 32 : 24} />
        </div>
      )}
      <h2 className={titleClasses}>{title}</h2>
      {description && (
        <p className="text-sm text-[var(--text-muted)] max-w-md mx-auto">
          {description}
        </p>
      )}
      {steps && steps.length > 0 && (
        <div className="flex items-start gap-2 justify-center mt-6 max-w-sm mx-auto">
          {steps.map((step, i) => (
            <Fragment key={i}>
              <div className="flex-1 min-w-0 bg-[var(--surface-light)] rounded-xl p-3 text-center">
                <p className="text-sm font-semibold text-[var(--text)]">
                  {step.title}
                </p>
                <p className="text-xs text-[var(--text-muted)] mt-1">
                  {step.description}
                </p>
              </div>
              {i < steps.length - 1 && (
                <span
                  className="text-[var(--primary)] text-base shrink-0 mt-3"
                  dir="ltr"
                  aria-hidden="true"
                >
                  →
                </span>
              )}
            </Fragment>
          ))}
        </div>
      )}
      {(cta || secondary) && (
        <div className="mt-6 flex flex-col sm:flex-row items-center justify-center gap-3">
          {cta && (
            <button
              type="button"
              onClick={cta.onClick}
              className="px-4 py-2 rounded-lg bg-[var(--primary)] text-white font-medium hover:bg-[var(--primary)]/90 transition-colors w-full sm:w-auto"
            >
              {cta.label}
            </button>
          )}
          {secondary && (
            <button
              type="button"
              onClick={secondary.onClick}
              className="px-4 py-2 rounded-lg bg-transparent text-[var(--text)] font-medium border border-[var(--surface-light)] hover:bg-[var(--surface-light)]/40 transition-colors w-full sm:w-auto"
            >
              {secondary.label}
            </button>
          )}
        </div>
      )}
      {footer && <div className="mt-4">{footer}</div>}
    </div>
  );
}
