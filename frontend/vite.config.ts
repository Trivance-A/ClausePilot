import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { '@': path.resolve(__dirname, 'src') } },
  server: {
    port: 3000,
    proxy: {
      // 백엔드(FastAPI :8000)로 프록시. 목 모드(VITE_USE_MOCK=true)에서는 MSW가 먼저 가로챈다.
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
  build: { sourcemap: false, chunkSizeWarningLimit: 1500 },
});
