import { useEffect, useState } from "react";

/**
 * Track a CSS media query from JavaScript.
 *
 * Used where a layout difference changes behaviour rather than just appearance — the
 * list sidebar is a column on a desktop and a scrolling row on a phone, and a drag
 * gesture has to follow whichever direction the items actually run in. CSS alone
 * cannot tell the drag code that.
 *
 * The query should match the breakpoint in the stylesheet. Two sources of truth for
 * one number is a real cost; the alternative is reading a custom property back out of
 * the computed style, which trades a duplicated number for a more obscure mechanism.
 * It is written once here and once in auth.css, and both say 768px.
 */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() => window.matchMedia(query).matches);

  useEffect(() => {
    const list = window.matchMedia(query);
    // Read again on mount: the viewport can change between the initial state and this
    // effect, and a rotated phone should not need a reload to be noticed.
    setMatches(list.matches);

    const onChange = (e: MediaQueryListEvent) => setMatches(e.matches);
    list.addEventListener("change", onChange);
    return () => list.removeEventListener("change", onChange);
  }, [query]);

  return matches;
}
