import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  base: "/activity/",
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8813",
    },
  },
  build: {
    outDir: "../../../funes_hoard/static",
    sourcemap: false,
    emptyOutDir: true,
  },
});
