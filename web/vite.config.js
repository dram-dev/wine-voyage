import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // `npm run dev` proxies /api to the local FastAPI server so the sommelier
    // endpoints work without setting VITE_API_BASE.
    proxy: {
      "/api": {
        target: process.env.VITE_DEV_API || "http://localhost:8420",
        changeOrigin: true,
      },
    },
  },
});
