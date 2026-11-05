import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev server: binds 0.0.0.0 and proxies /api to the FastAPI backend so the
// browser only ever talks to this origin (works behind the Arena preview).
export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 5173,
    allowedHosts: true,
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: true },
    },
  },
  preview: { host: "0.0.0.0", port: 5173, allowedHosts: true },
  build: { outDir: "dist", chunkSizeWarningLimit: 900 },
});
