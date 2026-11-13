import path from "node:path";

import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

const backend = process.env.DRIFTWATCH_API ?? "http://localhost:8000";

// Vendor libraries that change rarely get their own long-cached chunks.
const vendorChunks: Record<string, string[]> = {
  react: ["react", "react-dom", "react-router-dom", "react-router", "scheduler"],
  data: ["@tanstack/react-query", "@tanstack/query-core"],
  ui: [
    "@radix-ui/react-dialog",
    "@radix-ui/react-label",
    "@radix-ui/react-slot",
    "@radix-ui/react-switch",
    "@radix-ui/react-tabs",
  ],
  icons: ["lucide-react"],
  charts: ["recharts"],
  motion: ["motion", "framer-motion", "motion-dom", "motion-utils"],
};

function vendorChunk(id: string): string | undefined {
  const modulePath = id.replace(/\\/g, "/");
  for (const [chunk, packages] of Object.entries(vendorChunks)) {
    if (packages.some((name) => modulePath.includes(`/node_modules/${name}/`))) return chunk;
  }
  return undefined;
}

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "src") },
  },
  server: {
    proxy: {
      "/api": { target: backend, changeOrigin: true },
      "/healthz": { target: backend, changeOrigin: true },
    },
  },
  build: {
    rollupOptions: {
      output: { manualChunks: vendorChunk },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
  },
});
