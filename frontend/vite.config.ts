import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  // 백엔드 FastAPI 주소. docker compose 기본 매핑이 8080 (backend/README 참고). .env 의 VITE_PROXY_TARGET 으로 변경 가능.
  const target = env.VITE_PROXY_TARGET || 'http://localhost:8080';
  return {
    plugins: [react()],
    resolve: { alias: { '@': path.resolve(__dirname, 'src') } },
    server: {
      port: 3000,
      proxy: {
        // 목 모드(VITE_USE_MOCK=true)에서는 MSW가 브라우저에서 먼저 가로채므로 프록시까지 오지 않는다.
        '/api': { target, changeOrigin: true },
      },
    },
    build: { sourcemap: false, chunkSizeWarningLimit: 1500 },
  };
});

