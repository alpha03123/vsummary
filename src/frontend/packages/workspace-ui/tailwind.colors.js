// Theme colours shared by every Tailwind config that compiles workspace UI classes.
// Values live in CSS variables (styles.css :root / .dark), so components never pick a
// dark-mode shade themselves: `bg-danger-subtle text-danger` is the whole badge, and
// `bg-surface text-strong border-line` the whole card.
// vsummary-cloud/frontend/tailwind.config.js keeps a copy (its release build has no main checkout).
const rgb = (name) => `rgb(var(--${name}) / <alpha-value>)`;
const roles = (...names) => Object.fromEntries(names.map((name) => [name, rgb(name)]));
const semantic = (name) => ({
  DEFAULT: rgb(`color-${name}`),
  subtle: rgb(`color-${name}-bg`),
  border: rgb(`color-${name}-border`),
  muted: rgb(`color-${name}-muted`),
});

const colors = {
  accent: rgb("workspace-accent-color"),
  danger: semantic("danger"),
  warning: semantic("warning"),
  success: semantic("success"),
  info: semantic("info"),
};

export default {
  colors,
  backgroundColor: roles("canvas", "surface", "muted", "raised", "sunken", "soft", "softer", "inverse"),
  textColor: roles("strong", "body", "subtle", "faint", "ghost", "on-inverse", "on-accent"),
  borderColor: roles("line-soft", "line", "line-strong"),
  ringColor: roles("line", "line-strong"),
  gradientColorStops: roles("surface", "muted", "soft", "canvas"),
};
