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
          configure: (proxy) => {
            proxy.on('error', (err, _req, res) => {
              // Intentional: ECONNREFUSED during backend restart windows returns 504.
              // docker-compose depends_on service_healthy already gates startup order;
              // these errors only appear transiently during container restarts.
              // The frontend client handles 504 as "backend unavailable" — no retry here.
              if (res && 'writeHead' in res && !res.headersSent) {
                (res as import('http').ServerResponse).writeHead(504, { 'Content-Type': 'application/json' });
                (res as import('http').ServerResponse).end(
                  JSON.stringify({ code: 504, message: `Backend unavailable: ${err.message}` }),
                );
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
        manualChunks: {
          'monaco-editor': ['monaco-editor'],
          'shiki': ['shiki'],
          'konva': ['konva', 'vue-konva'],
          'lottie': ['lottie-web'],
        },
      },
    },
  },
});
