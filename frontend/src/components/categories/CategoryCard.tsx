import { Wallet } from "lucide-react";

interface CategoryCardProps {
  /** Category name, shown as the card title. */
  category: string;
  /** Emoji icon, or undefined to fall back to the wallet glyph. */
  icon: string | undefined;
  /** Secondary line: tag count for active cards, last-used for unused ones. */
  subtitle: string;
  onClick: () => void;
  /** Dim the card, marking it as unused. */
  muted?: boolean;
}

/**
 * One category tile in the categories grid. Shared by the active grid and the
 * unused section so the two stay visually identical apart from the muting.
 */
export function CategoryCard({
  category,
  icon,
  subtitle,
  onClick,
  muted = false,
}: CategoryCardProps) {
  return (
    <button
      data-testid={`category-card-${category}`}
      onClick={onClick}
      className={`flex flex-col items-center gap-1.5 sm:gap-2 p-2 sm:p-4 bg-[var(--surface)] rounded-xl sm:rounded-2xl border border-[var(--surface-light)] hover:border-[var(--primary)]/50 hover:bg-[var(--surface-light)]/30 transition-all text-center group ${
        muted ? "opacity-60 hover:opacity-100" : ""
      }`}
    >
      <div className="w-9 h-9 sm:w-12 sm:h-12 flex items-center justify-center rounded-lg sm:rounded-xl bg-blue-500/10 border border-blue-500/20 text-lg sm:text-2xl shrink-0">
        {icon ? (
          <span>{icon}</span>
        ) : (
          <Wallet className="text-blue-400 w-[18px] h-[18px] sm:w-[22px] sm:h-[22px]" />
        )}
      </div>
      <h3 className="font-bold text-xs sm:text-sm truncate w-full" dir="auto">
        {category}
      </h3>
      <span className="text-[10px] sm:text-xs text-[var(--text-muted)]" dir="ltr">
        {subtitle}
      </span>
    </button>
  );
}
