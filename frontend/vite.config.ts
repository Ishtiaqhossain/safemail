import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "path";

// Port + API proxy target are env-overridable so an isolated E2E stack can run on
// alternate ports (e.g. PORT=3001 VITE_API_TARGET=http://localhost:8001) without
// colliding with a normal dev server. Defaults match the standard dev setup.
const port = Number(process.env.PORT) || 3000;
const apiTarget = process.env.VITE_API_TARGET || "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": resolve(__dirname, "src") },
  },
  server: {
    port,
    strictPort: true, // fail loudly on a port collision instead of moving to 3001
    proxy: {
      "/v1": { target: apiTarget, changeOrigin: true },
    },
  },
});
