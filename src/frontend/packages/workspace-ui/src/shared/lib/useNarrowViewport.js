import { useEffect, useState } from "react";

const NARROW_QUERY = "(max-width: 767px)";

// jsdom (tests) has no matchMedia; treat that as a wide screen.
export function matchesNarrowViewport() {
  return typeof window !== "undefined" && typeof window.matchMedia === "function" && window.matchMedia(NARROW_QUERY).matches;
}

/** True below Tailwind's `md` breakpoint, where the workspace shows one pane at a time. */
export function useNarrowViewport() {
  const [narrow, setNarrow] = useState(matchesNarrowViewport);
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return undefined;
    const query = window.matchMedia(NARROW_QUERY);
    const update = () => setNarrow(query.matches);
    update();
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);
  return narrow;
}
