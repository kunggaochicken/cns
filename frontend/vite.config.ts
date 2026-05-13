/// <reference types="vitest" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/graph": { target: "http://localhost:8000", changeOrigin: true },
      "/capture": { target: "http://localhost:8000", changeOrigin: true },
      "/stream": { target: "http://localhost:8000", changeOrigin: true },
      "/gate": { target: "http://localhost:8000", changeOrigin: true },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: "./tests/setup.ts",
    css: false,
  },
});
