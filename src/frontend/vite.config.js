import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
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
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8001",
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: "./src/test/setupTests.js",
  },
});
