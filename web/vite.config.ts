import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // In Docker Compose the API is reached by its service name.
      '/api': process.env.API_PROXY_TARGET ?? 'http://localhost:8000',
    },
    watch: {
      // File change events do not cross a Windows bind mount, so poll instead.
      usePolling: process.env.VITE_USE_POLLING === 'true',
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test-setup.ts'],
  },
});
