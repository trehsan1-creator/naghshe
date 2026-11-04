import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// The workspace is served from an Arena preview host (*.e2b.app), so the dev server
// must accept any host header and proxy /api to the FastAPI backend on :8000.
export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 5173,
    strictPort: true,
    allowedHosts: true,
    proxy: {
      "/api": {
        target: process.env.VITE_API_TARGET ?? "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
    chunkSizeWarningLimit: 1600,
    rollupOptions: {
      output: {
        manualChunks: {
          three: ["three", "@react-three/fiber", "@react-three/drei"],
          deck: ["@deck.gl/core", "@deck.gl/layers", "@deck.gl/react"],
          maps: ["maplibre-gl"],
        },
      },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    env: { VITE_API_BASE: "http://127.0.0.1:8000/api/v1" },
    include: ["src/**/*.test.{ts,tsx}"],
    testTimeout: 30_000,
  },
});
