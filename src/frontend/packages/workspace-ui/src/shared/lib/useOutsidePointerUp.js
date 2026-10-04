import { useEffect, useRef } from "react";

/** Close a floating surface only when a pointer gesture starts and ends outside it. */
export function useOutsidePointerUp(active, refs, onOutside) {
  const pointerStartedOutsideRef = useRef(false);

  useEffect(() => {
    if (!active) return undefined;

    const isInside = (target) => refs.some((ref) => ref.current?.contains(target));
    const onPointerDown = (event) => {
      pointerStartedOutsideRef.current = !isInside(event.target);
    };
    const onPointerUp = (event) => {
      if (pointerStartedOutsideRef.current && !isInside(event.target)) onOutside();
      pointerStartedOutsideRef.current = false;
    };

    window.addEventListener("pointerdown", onPointerDown);
    window.addEventListener("pointerup", onPointerUp);
    return () => {
      window.removeEventListener("pointerdown", onPointerDown);
      window.removeEventListener("pointerup", onPointerUp);
    };
  }, [active, onOutside, refs]);
}
