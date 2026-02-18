import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import tailwindcss from '@tailwindcss/vite';
import commonjs from 'vite-plugin-commonjs';
import { resolve } from 'path';

// https://vitejs.dev/config/
const usePolling =
  process.env.VITE_USE_POLLING === 'true' || process.env.CHOKIDAR_USEPOLLING === 'true';
const pollingInterval = process.env.VITE_POLLING_INTERVAL
  ? Number(process.env.VITE_POLLING_INTERVAL)
  : 100;

const hmrHost = process.env.VITE_HMR_HOST;
const hmrPort = process.env.VITE_HMR_PORT ? Number(process.env.VITE_HMR_PORT) : undefined;
const hmrProtocol = process.env.VITE_HMR_PROTOCOL as 'ws' | 'wss' | undefined;
const hmrClientPort = process.env.VITE_HMR_CLIENT_PORT
  ? Number(process.env.VITE_HMR_CLIENT_PORT)
  : undefined;

export default defineConfig({
  plugins: [
    tailwindcss(),
    vue(),
    commonjs(),
  ],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src')
    }
  },
  optimizeDeps: {
    include: ['monaco-editor', 'lottie-web', 'konva'],
    esbuildOptions: {
      target: 'esnext',
      supported: {
        'top-level-await': true
      }
    }
  },
  server: {
    host: process.env.VITE_HOST === 'true' ? true : 'localhost',
    port: 5174,
    ...(usePolling && {
      watch: {
        usePolling: true,
        interval: pollingInterval,
      },
    }),
    ...((hmrHost || hmrPort || hmrProtocol || hmrClientPort) && {
      hmr: {
        host: hmrHost,
        port: hmrPort,
        protocol: hmrProtocol,
        clientPort: hmrClientPort,
      },
    }),
    ...(process.env.BACKEND_URL && {
      proxy: {
        '/api': {
          target: process.env.BACKEND_URL,
          changeOrigin: true,
          ws: true,
          // Prevent hanging connections during backend hot-reload
          timeout: 30_000,
          configure: (proxy) => {
            // Error codes expected during uvicorn --reload (1-2s restart window).
            // docker-compose depends_on service_healthy gates initial startup;
            // these only appear transiently during code-change restarts.
            const TRANSIENT = new Set(['ECONNREFUSED', 'ENOTFOUND', 'ECONNRESET', 'EPIPE', 'ETIMEDOUT']);
            let suppressedCount = 0;

            proxy.on('error', (err: NodeJS.ErrnoException, _req, res) => {
              const isTransient = TRANSIENT.has(err.code ?? '');

              if (isTransient) {
                // Batch-log transient errors to avoid flooding the console during rapid reloads
                suppressedCount++;
                if (suppressedCount === 1 || suppressedCount % 10 === 0) {
                  console.warn(`[proxy] Backend temporarily unavailable (${err.code}) — ${suppressedCount} transient error(s)`);
                }
              } else {
                console.error(`[proxy] Unexpected proxy error: ${err.code} ${err.message}`);
              }

              // HTTP response → return 504 so frontend client sees a clean status code
              if (res && 'writeHead' in res && !(res as import('http').ServerResponse).headersSent) {
                const httpRes = res as import('http').ServerResponse;
                httpRes.writeHead(504, { 'Content-Type': 'application/json' });
                httpRes.end(JSON.stringify({
                  code: 504,
                  message: isTransient
                    ? 'Backend temporarily unavailable (restarting)'
                    : `Backend unavailable: ${err.message}`,
                }));
                return;
              }

              // WebSocket upgrade → close the underlying socket cleanly
              if (res && 'destroy' in res && typeof (res as import('net').Socket).destroy === 'function') {
                (res as import('net').Socket).destroy();
              }
            });
          },
        },
      },
    }),
  },
  build: {
    target: 'esnext',
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('node_modules/monaco-editor')) {
            return 'monaco-editor';
          }
          if (id.includes('node_modules/shiki')) {
            return 'shiki';
          }
          if (id.includes('node_modules/plotly.js-dist-min')) {
            return 'plotly';
          }
          if (id.includes('node_modules/konva') || id.includes('node_modules/vue-konva')) {
            return 'konva';
          }
          if (id.includes('node_modules/lottie-web')) {
            return 'lottie';
          }
          return undefined;
        },
      },
    },
  },
});
