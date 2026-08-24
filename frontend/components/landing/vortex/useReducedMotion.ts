"use client";

import * as React from "react";

/** Whether the reader has asked for less movement. Read straight off the media
 *  query rather than through framer-motion: it is one boolean, and the import is
 *  a dependency this component otherwise has no use for. Starts false so the
 *  server and the first client render agree, then corrects on mount. */
export function useReducedMotion() {
  const [reduced, setReduced] = React.useState(false);
  React.useEffect(() => {
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    const sync = () => setReduced(query.matches);
    sync();
    query.addEventListener("change", sync);
    return () => query.removeEventListener("change", sync);
  }, []);
  return reduced;
}
