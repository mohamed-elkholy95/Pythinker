import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import tailwindcss from '@tailwindcss/vite';
import { resolve } from 'path';

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [
    tailwindcss(),
    vue(),
  ],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src')
    }
  },
  optimizeDeps: {
    include: ['monaco-editor'],
    exclude: ['@novnc/novnc'],
    esbuildOptions: {
      target: 'esnext'
    }
  },
  server: {
    host: true,
    port: 5173,
    ...(process.env.BACKEND_URL && {
      proxy: {
        '/api': {
          target: process.env.BACKEND_URL,
          changeOrigin: true,
          ws: true,
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
        },
      },
    },
  },
});
