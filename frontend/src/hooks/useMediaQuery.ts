import { useEffect, useState } from "react";

/**
 * Subscribe to a CSS media query and return whether it currently matches.
 *
 * Reads `matchMedia` synchronously on first render so there's no layout flash,
 * then updates whenever the match state changes.
 *
 * @param query A media query string, e.g. `"(min-width: 1024px)"`.
 */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() =>
    typeof window !== "undefined" ? window.matchMedia(query).matches : false,
  );

  useEffect(() => {
    const mql = window.matchMedia(query);
    const onChange = () => setMatches(mql.matches);
    onChange();
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, [query]);

  return matches;
}
