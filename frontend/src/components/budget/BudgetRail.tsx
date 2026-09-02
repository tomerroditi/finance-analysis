import React from "react";

/**
 * Secondary column beside the ledger.
 *
 * Everything on the page used to be `w-full`, so on a wide screen the rule
 * rows were ~1200px of mostly empty space while the trend chart and the
 * per-project summary sat far below the fold. Those move here instead.
 *
 * Below `lg:` the rail is just the bottom of the stack — a phone has no
 * horizontal room to give it.
 */
export const BudgetRail: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <aside className="w-full lg:w-[272px] lg:shrink-0 flex flex-col gap-3">{children}</aside>
);

interface RailCardProps {
  title: string;
  /** Figure or badge shown opposite the title. */
  value?: React.ReactNode;
  items?: { key: string; label: React.ReactNode; value: React.ReactNode }[];
  children?: React.ReactNode;
}

export const RailCard: React.FC<RailCardProps> = ({ title, value, items, children }) => (
  <div className="bg-[var(--surface)] rounded-2xl border border-[var(--surface-light)] shadow-sm p-3">
    <div className="flex items-center justify-between gap-2">
      <p className="text-[10px] sm:text-xs text-[var(--text-muted)] uppercase tracking-wide truncate">
        {title}
      </p>
      {value}
    </div>
    {items && items.length > 0 && (
      <ul className="mt-2 pt-2 border-t border-[var(--surface-light)] space-y-1.5">
        {items.map((item) => (
          <li key={item.key} className="flex items-center justify-between gap-2 text-xs">
            <span className="text-[var(--text-muted)] truncate" dir="auto">
              {item.label}
            </span>
            <span className="font-mono text-[var(--text-default)] shrink-0" dir="ltr">
              {item.value}
            </span>
          </li>
        ))}
      </ul>
    )}
    {children}
  </div>
);
