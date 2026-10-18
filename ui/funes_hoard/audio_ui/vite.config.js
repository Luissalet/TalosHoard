import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
  base: "/audio/",
  root: 'client',
  
  plugins: [react(), tailwindcss()],
  build: {
    outDir: "../../../../funes_hoard/audio_memory/static",
    emptyOutDir: true,
  },
  server: {
    host: '127.0.0.1',
    port: Number(process.env.VITE_PORT || 5173),
    proxy: {
      '/audio/api': `http://127.0.0.1:${process.env.FUNES_PORT || process.env.PORT || 8813}`,
    },
  },
});
