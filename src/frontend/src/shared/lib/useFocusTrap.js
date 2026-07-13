import { useEffect, useRef } from "react";

const FOCUSABLE_SELECTOR = [
  "a[href]",
  "button:not([disabled])",
  "textarea:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  '[tabindex]:not([tabindex="-1"])',
].join(",");

/**
 * Trap keyboard focus inside `containerRef` while `active` is true.
 *
 * Behavior:
 *  - On activate: remembers the currently-focused element (the trigger) and
 *    moves focus to the first focusable child of the container.
 *  - Tab / Shift+Tab cycle within the container (WCAG 2.4.3 Focus Order).
 *  - On deactivate: restores focus to the trigger (WCAG 2.4.11).
 *
 * The consumer is responsible for closing the dialog on Escape (e.g. via an
 * `onKeyDown` handler on the same container) — this hook only manages focus.
 *
 * @param {React.RefObject<HTMLElement>} containerRef - ref to the dialog container
 * @param {boolean} active - whether the trap should be engaged
 */
export function useFocusTrap(containerRef, active) {
  const previouslyFocused = useRef(null);

  useEffect(() => {
    if (!active) {
      return undefined;
    }

    const container = containerRef.current;
    if (!container) {
      return undefined;
    }

    previouslyFocused.current = document.activeElement;

    const getFocusables = () =>
      Array.from(container.querySelectorAll(FOCUSABLE_SELECTOR)).filter(
        (el) => el.offsetParent !== null || el === document.activeElement,
      );

    // Move focus into the dialog on open
    const initial = getFocusables();
    if (initial.length > 0) {
      initial[0].focus();
    } else {
      container.setAttribute("tabindex", "-1");
      container.focus();
    }

    function handleKeyDown(event) {
      if (event.key !== "Tab") {
        return;
      }
      const items = getFocusables();
      if (items.length === 0) {
        event.preventDefault();
        return;
      }
      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    container.addEventListener("keydown", handleKeyDown);
    return () => {
      container.removeEventListener("keydown", handleKeyDown);
      const trigger = previouslyFocused.current;
      if (trigger && typeof trigger.focus === "function") {
        trigger.focus();
      }
    };
  }, [active, containerRef]);
}
