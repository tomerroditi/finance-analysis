import { useEffect } from "react";

/**
 * Locks body scroll when a modal/overlay is open.
 * Preserves scroll position and restores it on close.
 */
export function useScrollLock(isOpen: boolean) {
  useEffect(() => {
    if (!isOpen) return;

    const scrollY = window.scrollY;
    document.body.style.setProperty("--scroll-y", `-${scrollY}px`);
    document.body.classList.add("modal-open");

    return () => {
      document.body.classList.remove("modal-open");
      document.body.style.removeProperty("--scroll-y");
      window.scrollTo(0, scrollY);
    };
  }, [isOpen]);
}
