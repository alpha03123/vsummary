import colors from 'tailwindcss/colors';
import containerQueries from '@tailwindcss/container-queries';

/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
    "./packages/workspace-ui/src/**/*.{js,jsx}",
    "./node_modules/@alpha03123/vsummary-workspace-ui/dist/**/*.js",
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
        // Latin glyphs from IBM Plex Sans; Chinese falls through to each platform's best UI font.
        // `display` is kept as an alias so headings share the body face instead of a second family.
        sans: ['"IBM Plex Sans"', '"PingFang SC"', '"Hiragino Sans GB"', '"Microsoft YaHei UI"', '"Microsoft YaHei"', '"Noto Sans SC"', '"Segoe UI"', 'sans-serif'],
        display: ['"IBM Plex Sans"', '"PingFang SC"', '"Hiragino Sans GB"', '"Microsoft YaHei UI"', '"Microsoft YaHei"', '"Noto Sans SC"', '"Segoe UI"', 'sans-serif'],
      },
      borderRadius: {
        // Three radii: controls 12px (xl), cards 16px (2xl/3xl), outer panels 20px (4xl/5xl).
        '2xl': '1rem',      // 16px
        '3xl': '1rem',      // 16px
        '4xl': '1.25rem',   // 20px
        '5xl': '1.25rem',   // 20px
      }
    },
  },
  plugins: [
    // 面板宽度是拖拽出来的（workspaceLayout.js panelMinWidth 320），视口媒体查询
    // 完全测不到它。工具页头部需要 ~460px，容器查询是唯一能按「面板宽度」降级的方案。
    containerQueries,
  ],
}
