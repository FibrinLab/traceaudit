/// <reference types="vitest/config" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { readFileSync } from 'node:fs';

const pkg = JSON.parse(readFileSync(new URL('./package.json', import.meta.url), 'utf8')) as { version: string };

// Relative base so the built site works from file:// and from any sub-path (GitHub Pages).
export default defineConfig({
  base: './',
  plugins: [react()],
  define: {
    __VIEWER_VERSION__: JSON.stringify(pkg.version),
  },
  server: {
    // In development, same-origin `/api/*` calls (the default API base) are proxied to the service:
    // the mock (`npm run mock`, port 8787) or a real `traceaudit serve` via VITE_API_PROXY.
    proxy: {
      '/api': { target: process.env.VITE_API_PROXY ?? 'http://127.0.0.1:8787', changeOrigin: true },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    target: 'es2020',
  },
  test: {
    environment: 'jsdom',
    globals: true,
    include: ['src/**/*.test.ts', 'src/**/*.test.tsx'],
  },
});
