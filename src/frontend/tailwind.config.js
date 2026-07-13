import colors from 'tailwindcss/colors';

/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // `sky` previously aliased to indigo (confusing); dev showcase now uses
        // `indigo-*` directly. `brand` teal palette was never referenced — removed.
        indigo: colors.indigo,
        accent: 'rgb(var(--workspace-accent-color) / <alpha-value>)',
      },
      fontFamily: {
        // Match the fonts actually loaded in index.html (IBM Plex Sans + Space Grotesk).
        // Previously declared 'Public Sans' which was never loaded, causing silent
        // fallback to system fonts instead of the intended typography.
        sans: ['"IBM Plex Sans"', 'Inter', '"Segoe UI"', 'sans-serif'],
        display: ['"Space Grotesk"', '"IBM Plex Sans"', 'sans-serif'],
      },
      borderRadius: {
        '2xl': '1rem',      // 16px
        '3xl': '1.5rem',    // 24px
        '4xl': '2rem',      // 32px
        '5xl': '2.5rem',    // 40px
      }
    },
  },
  plugins: [],
}
