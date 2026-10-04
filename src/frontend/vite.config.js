import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@src": path.resolve(__dirname, "src"),
      "@testing-library/react": path.resolve(__dirname, "node_modules/@testing-library/react"),
      react: path.resolve(__dirname, "node_modules/react"),
      "react-dom": path.resolve(__dirname, "node_modules/react-dom"),
      "markmap-view": path.resolve(__dirname, "node_modules/markmap-view"),
      d3: path.resolve(__dirname, "node_modules/d3"),
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes("node_modules")) {
            return undefined;
          }
          if (
            id.includes("react-markdown") ||
            id.includes("remark-gfm") ||
            id.includes("remark-") ||
            id.includes("rehype-") ||
            id.includes("unified") ||
            id.includes("micromark") ||
            id.includes("mdast") ||
            id.includes("hast") ||
            id.includes("unist") ||
            id.includes("vfile")
          ) {
            return "vendor-markdown";
          }
          if (id.includes("framer-motion")) {
            return "vendor-motion";
          }
          if (id.includes("lucide-react")) {
            return "vendor-icons";
          }
          return undefined;
        },
      },
    },
  },
  server: {
    host: "127.0.0.1",
    port: 4173,
    fs: {
      allow: [path.resolve(__dirname, "../..")],
    },
    proxy: {
      "/api": {
        target: process.env.VSUMMARY_API_URL ?? "http://127.0.0.1:8001",
        changeOrigin: true,
      },
      "/mcp": {
        target: process.env.VSUMMARY_API_URL ?? "http://127.0.0.1:8001",
        changeOrigin: true,
      },
    },
  },
  test: {
    alias: {
      "@workspace": path.resolve(__dirname, "packages/workspace-ui/src"),
      "@alpha03123/vsummary-workspace-ui": path.resolve(__dirname, "packages/workspace-ui/src/index.jsx"),
    },
    environment: "jsdom",
    globals: true,
    include: ["../../tests/frontend/**/*.{test,spec}.{js,jsx,ts,tsx}"],
    setupFiles: "./src/testing/setupTests.js",
  },
});
