import { type ReactNode, useEffect, useRef, useState } from "react";

interface DeferUntilVisibleProps {
  /** The card content to mount once the placeholder scrolls near the viewport. */
  children: ReactNode;
  /**
   * Render immediately, skipping the observer. Used for the first few cards
   * (above the fold on any realistic viewport) so they never flash a skeleton
   * and their data is requested on the very first paint.
   */
  eager?: boolean;
  /**
   * Tailwind class reserving the placeholder's height so cards further down
   * stay genuinely below the fold (otherwise every zero-height placeholder
   * stacks at the top and the observer mounts them all at once).
   */
  reserveClassName?: string;
}

/**
 * Defers mounting `children` — and therefore any data queries they fire — until
 * the card is scrolled to within a short margin of the viewport.
 *
 * On first open the dashboard mounts ~a dozen cards, each firing its own
 * analytics request. Letting the below-the-fold chart cards wait until they're
 * about to be seen keeps the initial request burst focused on the content the
 * user is actually looking at — the pinned KPI header and the top cards — so
 * the dashboard becomes interactive sooner.
 *
 * Once a card becomes visible it stays mounted: the observer disconnects and
 * the card never unmounts on scroll-away, so its queries don't refetch.
 */
export function DeferUntilVisible({
  children,
  eager = false,
  reserveClassName = "min-h-[20rem]",
}: DeferUntilVisibleProps) {
  // Environments without IntersectionObserver (jsdom, SSR) render eagerly —
  // decided at init so the effect never has to call setState synchronously.
  const [visible, setVisible] = useState(
    () => eager || typeof IntersectionObserver === "undefined",
  );
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (visible) return;
    const el = ref.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setVisible(true);
          observer.disconnect();
        }
      },
      { rootMargin: "300px" },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [visible]);

  if (visible) return <>{children}</>;

  return (
    <div
      ref={ref}
      aria-hidden="true"
      className={`${reserveClassName} rounded-xl bg-[var(--surface)]/40 animate-pulse`}
    />
  );
}
