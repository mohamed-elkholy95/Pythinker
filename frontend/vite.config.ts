import { defineConfig, type Plugin } from 'vite';
import vue from '@vitejs/plugin-vue';
import tailwindcss from '@tailwindcss/vite';
import commonjs from 'vite-plugin-commonjs';
import { resolve } from 'path';
import { readFileSync } from 'fs';

// ---------------------------------------------------------------------------
// noVNC TLA patch — https://github.com/novnc/noVNC/issues/1943
//
// noVNC v1.6 ships Babel-converted CJS on npm.  lib/util/browser.js contains
// a top-level `await` (valid ESM, invalid CJS).  Every `require()` of that
// file fails in esbuild because require() is synchronous.
//
// Fix: replace the blocking TLA with a deferred `.then()`.  The H.264 codec
// check runs asynchronously and resolves well before VNC negotiates codecs.
// ---------------------------------------------------------------------------
const NOVNC_TLA_RE =
  /exports\.supportsWebCodecsH264Decode\s*=\s*supportsWebCodecsH264Decode\s*=\s*await\s+_checkWebCodecsH264DecodeSupport\(\)\s*;/;

const NOVNC_TLA_FIX = [
  'exports.supportsWebCodecsH264Decode = supportsWebCodecsH264Decode = false;',
  '_checkWebCodecsH264DecodeSupport().then(function(v) {',
  '  exports.supportsWebCodecsH264Decode = supportsWebCodecsH264Decode = v;',
  '});',
].join('\n');

/** Vite transform plugin — patches noVNC when served outside dep optimization. */
function patchNoVncTLA(): Plugin {
  return {
    name: 'patch-novnc-tla',
    enforce: 'pre',
    transform(code, id) {
      if (id.includes('novnc') && id.endsWith('browser.js') && NOVNC_TLA_RE.test(code)) {
        return { code: code.replace(NOVNC_TLA_RE, NOVNC_TLA_FIX), map: null };
      }
    },
  };
}

/** Chroma → final colors for web overlay; must match `macOS.colors` in chroma-render.json. */
function loadAppleCursorChromaRules(): Array<{ match: string; replace: string }> {
  const p = resolve(__dirname, 'src/assets/cursors/apple_cursor-main/chroma-render.json');
  try {
    const j = JSON.parse(readFileSync(p, 'utf-8')) as {
      macOS?: { colors?: Array<{ match: string; replace: string }> };
    };
    const colors = j.macOS?.colors;
    if (Array.isArray(colors) && colors.length > 0) return colors;
  } catch {
    /* use defaults below */
  }
  return [
    { match: '#00FF00', replace: '#000000' },
    { match: '#0000FF', replace: '#FFFFFF' },
  ];
}

const APPLE_CURSOR_CHROMA = loadAppleCursorChromaRules();

/**
 * Apple cursor SVGs under `apple_cursor-main/svg` use chroma key colors; see chroma-render.json.
 * The Konva overlay imports them as URLs — without recolor they show lime/blue in the browser.
 */
function recolorAppleCursorSvgForWeb(): Plugin {
  const isAppleCursorSvg = (pathOnly: string) =>
    /apple_cursor-main[/\\]svg[/\\].+\.svg$/i.test(pathOnly);

  const applyChromaToFinalColors = (svg: string) => {
    let out = svg;
    for (const { match, replace } of APPLE_CURSOR_CHROMA) {
      const escaped = match.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      out = out.replace(new RegExp(escaped, 'gi'), replace);
    }
    return out;
  };

  return {
    name: 'recolor-apple-cursor-svg-web',
    enforce: 'pre',
    load(id) {
      const pathOnly = id.split('?')[0];
      if (!pathOnly.endsWith('.svg') || !isAppleCursorSvg(pathOnly)) {
        return null;
      }
      try {
        const raw = readFileSync(pathOnly, 'utf-8');
        const recolored = applyChromaToFinalColors(raw);
        const dataUrl = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(recolored)}`;
        return `export default ${JSON.stringify(dataUrl)}`;
      } catch {
        return null;
      }
    },
  };
}

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
    patchNoVncTLA(),
    recolorAppleCursorSvgForWeb(),
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
        'top-level-await': true,
      },
      plugins: [
        {
          // esbuild plugin — patches noVNC's browser.js during dep optimization
          name: 'patch-novnc-tla',
          setup(build) {
            build.onLoad(
              { filter: /novnc[\\/]lib[\\/]util[\\/]browser\.js$/ },
              (args) => {
                let contents = readFileSync(args.path, 'utf-8');
                if (NOVNC_TLA_RE.test(contents)) {
                  contents = contents.replace(NOVNC_TLA_RE, NOVNC_TLA_FIX);
                }
                return { contents, loader: 'js' };
              },
            );
          },
        },
      ],
    },
  },
  server: {
    host: process.env.VITE_HOST === 'true' ? true : 'localhost',
    port: 5174,
    allowedHosts: ['pythinker.com', 'frontend.pythinker.orb.local'],
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
          // Increase proxy timeout for long-lived WebSocket connections
          proxyTimeout: 0,
          configure: (proxy) => {
            // Error codes expected during uvicorn --reload (1-2s restart window).
            // docker-compose depends_on service_healthy gates initial startup;
            // these only appear transiently during code-change restarts.
            const TRANSIENT = new Set(['ECONNREFUSED', 'ENOTFOUND', 'ECONNRESET', 'EPIPE', 'ETIMEDOUT']);
            let suppressedCount = 0;
            let suppressResetTimer: ReturnType<typeof setTimeout> | null = null;

            const isTransientProxyError = (err: NodeJS.ErrnoException): boolean => {
              if (TRANSIENT.has(err.code ?? '')) return true;
              const msg = (err.message || '').toLowerCase();
              // Backend reload / SSE upgrade teardown — not actionable in dev.
              if (
                msg.includes('ended by the other party') ||
                msg.includes('socket hang up') ||
                msg.includes('write after end')
              ) {
                return true;
              }
              return false;
            };

            proxy.on('error', (err: NodeJS.ErrnoException, _req, res) => {
              const isTransient = isTransientProxyError(err);

              if (isTransient) {
                // Batch-log transient errors to avoid flooding the console during rapid reloads
                suppressedCount++;
                if (suppressedCount === 1 || suppressedCount % 10 === 0) {
                  console.warn(`[proxy] Backend temporarily unavailable (${err.code}) — ${suppressedCount} transient error(s)`);
                }
                // Reset suppressed counter after 30s of quiet (backend fully restarted)
                if (suppressResetTimer) clearTimeout(suppressResetTimer);
                suppressResetTimer = setTimeout(() => { suppressedCount = 0; }, 30_000);
              } else {
                console.error(`[proxy] Unexpected proxy error: ${err.code} ${err.message}`);
              }

              // HTTP response → return 504 so frontend client sees a clean status code
              if (res && 'writeHead' in res && !(res as import('http').ServerResponse).headersSent) {
                const httpRes = res as import('http').ServerResponse;
                httpRes.writeHead(504, {
                  'Content-Type': 'application/json',
                  'Retry-After': '2',
                });
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
