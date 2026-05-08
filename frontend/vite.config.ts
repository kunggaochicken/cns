/// <reference types="vitest" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@": path.resolve(__dirname, "./src") } },
  server: {
    proxy: {
      "/capture": "http://localhost:8000",
      "/graph": "http://localhost:8000",
      "/nodes": "http://localhost:8000",
      "/gate-items": "http://localhost:8000",
      "/hotspots": "http://localhost:8000",
      "/search": "http://localhost:8000",
      "/agents": "http://localhost:8000",
      "/stream": "http://localhost:8000",
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./tests/setup.ts"],
  },
});
