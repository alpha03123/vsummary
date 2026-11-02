// Theme colours shared by every Tailwind config that compiles workspace UI classes.
// Values live in CSS variables (styles.css :root / .dark), so components never pick a
// dark-mode shade themselves: `bg-danger-subtle text-danger` is the whole badge.
// vsummary-cloud/frontend/tailwind.config.js keeps a copy of this object.
const semantic = (name) => ({
  DEFAULT: `rgb(var(--color-${name}) / <alpha-value>)`,
  subtle: `rgb(var(--color-${name}-bg) / <alpha-value>)`,
  border: `rgb(var(--color-${name}-border) / <alpha-value>)`,
  muted: `rgb(var(--color-${name}-muted) / <alpha-value>)`,
});

export default {
  accent: "rgb(var(--workspace-accent-color) / <alpha-value>)",
  danger: semantic("danger"),
  warning: semantic("warning"),
  success: semantic("success"),
  info: semantic("info"),
};
