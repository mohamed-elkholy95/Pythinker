<template>
  <div
    ref="contentRef"
    v-bind="$attrs"
    :class="['tiptap-message-viewer', compact ? 'tiptap-message-viewer--compact' : '']"
  >
    <EditorContent
      :editor="editor"
      :class="[
        'tiptap-message-prose',
        compact ? 'tiptap-message-prose--compact' : '',
      ]"
    />
  </div>

  <!-- Citation reference card — teleported to body so it escapes overflow clipping -->
  <Teleport to="body">
    <Transition name="cit-pop">
      <a
        v-if="citCard.visible"
        class="msg-cit-card"
        :href="citCard.url || undefined"
        target="_blank"
        rel="noopener noreferrer"
        :style="{ left: citCard.x + 'px', top: citCard.y + 'px' }"
        @mouseenter="keepCard"
        @mouseleave="scheduleHideCard"
      >
        <p class="msg-cit-card-title">{{ citCard.title }}</p>
        <div class="msg-cit-card-footer">
          <img
            v-if="citCard.faviconUrl"
            :src="citCard.faviconUrl"
            class="msg-cit-card-favicon"
            @error="(e) => { (e.target as HTMLImageElement).style.display = 'none' }"
          />
          <span class="msg-cit-card-domain">{{ citCard.domain }}</span>
          <svg class="msg-cit-card-arrow" viewBox="0 0 12 12" fill="none">
            <path
              d="M2.5 9.5L9.5 2.5M9.5 2.5H5M9.5 2.5V7"
              stroke="currentColor"
              stroke-width="1.5"
              stroke-linecap="round"
              stroke-linejoin="round"
            />
          </svg>
        </div>
      </a>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, onBeforeUnmount, computed, nextTick, reactive } from 'vue';
import { useEditor, EditorContent } from '@tiptap/vue-3';
import StarterKit from '@tiptap/starter-kit';
import Link from '@tiptap/extension-link';
import Image from '@tiptap/extension-image';
import Highlight from '@tiptap/extension-highlight';
import TaskList from '@tiptap/extension-task-list';
import TaskItem from '@tiptap/extension-task-item';
import TextAlign from '@tiptap/extension-text-align';
import Typography from '@tiptap/extension-typography';
import CodeBlockLowlight from '@tiptap/extension-code-block-lowlight';
import { common, createLowlight } from 'lowlight';
import { marked } from 'marked';
import DOMPurify from 'dompurify';
import { normalizeVerificationMarkers, linkifyInlineCitations } from './report/reportContentNormalizer';
import { getFaviconUrl } from '@/utils/toolDisplay';

// Fragment root (div + Teleport) — disable auto attr-inheritance so $attrs go to the real div
defineOptions({ inheritAttrs: false });

const props = withDefaults(
  defineProps<{
    content: string;
    /** Render as compact (summary cards, etc.) */
    compact?: boolean;
  }>(),
  { compact: false }
);

const contentRef = ref<HTMLElement | null>(null);
const lowlight = createLowlight(common);

// ── Citation popup card state ──────────────────────────────────────────────
const citCard = reactive({
  visible: false,
  title: '',
  domain: '',
  faviconUrl: '',
  url: '',
  x: 0,
  y: 0,
});
let _hideCardTimer: ReturnType<typeof setTimeout> | null = null;

// Apply same normalizers as TiptapReportEditor: verification markers + inline citations
const htmlContent = computed(() => {
  if (!props.content) return '<p></p>';
  const normalizedMarkdown = normalizeVerificationMarkers(props.content);
  const linkedMarkdown = linkifyInlineCitations(normalizedMarkdown);
  const rawHtml = marked.parse(linkedMarkdown, { async: false, breaks: true, gfm: true }) as string;
  return DOMPurify.sanitize(rawHtml);
});

// After TipTap renders, stamp id="ref-N" onto reference list items,
// inject data-title/data-domain into inline citation badges for the popup,
// and stamp the same data onto reference-section anchors for hover popups.
// (TipTap strips unknown id attrs from schema nodes — DOM mutation bypasses this.)
const addReferenceAnchors = () => {
  const proseMirror = contentRef.value?.querySelector('.ProseMirror');
  if (!proseMirror) return;

  const refHeadingRe = /^(references?|sources?|bibliography|citations?)$/i;
  const headings = Array.from(proseMirror.querySelectorAll('h1, h2, h3, h4'));
  const refMap = new Map<string, { title: string; domain: string; url: string }>();

  // Helper: find the first anchor inside an element whose raw href is external
  const findExternalAnchor = (el: Element): HTMLAnchorElement | null => {
    const anchors = Array.from(el.querySelectorAll('a[href]')) as HTMLAnchorElement[];
    return anchors.find((a) => {
      const raw = a.getAttribute('href') ?? '';
      return raw && !raw.startsWith('#');
    }) ?? null;
  };

  for (const heading of headings) {
    if (!refHeadingRe.test(heading.textContent?.trim() ?? '')) continue;

    let sibling = heading.nextElementSibling;
    while (sibling) {
      if (/^H[1-4]$/.test(sibling.tagName)) break;

      if (sibling.tagName === 'OL') {
        sibling.querySelectorAll('li').forEach((item, index) => {
          const num = String(index + 1);
          item.setAttribute('id', `ref-${num}`);
          const anchor = findExternalAnchor(item);
          if (anchor) {
            try {
              const domain = new URL(anchor.href).hostname.replace(/^www\./, '');
              const title = (anchor.textContent?.trim() || domain).slice(0, 64);
              refMap.set(num, { title, domain, url: anchor.href });
              // Stamp directly here — no secondary lookup needed
              anchor.dataset.title = title;
              anchor.dataset.domain = domain;
              anchor.dataset.url = anchor.href;
              anchor.classList.add('ref-list-anchor');
            } catch {
              // ignore malformed URLs
            }
          }
        });
        break;
      }

      // Bracket-style: "[N] [Title](URL)" rendered as a <p>
      if (sibling.tagName === 'P' || sibling.tagName === 'DIV') {
        const text = sibling.textContent?.trimStart() ?? '';
        const m = text.match(/^\[(\d{1,3})\]/);
        if (m) {
          const num = m[1];
          sibling.setAttribute('id', `ref-${num}`);
          const anchor = findExternalAnchor(sibling);
          if (anchor) {
            try {
              const domain = new URL(anchor.href).hostname.replace(/^www\./, '');
              const title = (anchor.textContent?.trim() || domain).slice(0, 64);
              refMap.set(num, { title, domain, url: anchor.href });
              anchor.dataset.title = title;
              anchor.dataset.domain = domain;
              anchor.dataset.url = anchor.href;
              anchor.classList.add('ref-list-anchor');
            } catch {
              // ignore malformed URLs
            }
          }
        }
      }

      sibling = sibling.nextElementSibling;
    }
  }

  // Stamp data attributes onto inline citation badge anchors for popup card.
  // Also remove target="_blank" / rel added by the Link extension — citation
  // badges are internal fragment links and must scroll within the page.
  proseMirror.querySelectorAll('a[href^="#ref-"]').forEach((badge) => {
    const el = badge as HTMLAnchorElement;
    el.removeAttribute('target');
    el.removeAttribute('rel');
    const raw = el.getAttribute('href');
    const num = raw?.replace('#ref-', '');
    if (num && refMap.has(num)) {
      const { title, domain, url } = refMap.get(num)!;
      el.dataset.title = title;
      el.dataset.domain = domain;
      el.dataset.url = url;
    }
  });
};

const editor = useEditor({
  content: htmlContent.value,
  editable: false,
  extensions: [
    StarterKit.configure({
      codeBlock: false,
      link: false,
    }),
    Link.configure({
      openOnClick: true,
      HTMLAttributes: {
        class: 'message-link',
        target: '_blank',
        rel: 'noopener noreferrer',
      },
    }),
    Image.configure({
      HTMLAttributes: {
        class: 'message-image',
      },
    }),
    Highlight.configure({ multicolor: true }),
    TaskList,
    TaskItem.configure({ nested: true }),
    TextAlign.configure({ types: ['heading', 'paragraph'] }),
    Typography,
    CodeBlockLowlight.configure({
      lowlight,
      HTMLAttributes: {
        class: 'message-code-block',
      },
    }),
  ],
  editorProps: {
    attributes: {
      class: 'focus:outline-none select-text',
    },
  },
  onCreate: () => { nextTick(addReferenceAnchors); },
  onUpdate: () => { nextTick(addReferenceAnchors); },
});

watch(
  () => props.content,
  () => {
    if (editor.value && htmlContent.value !== editor.value.getHTML()) {
      editor.value.commands.setContent(htmlContent.value, false);
    }
  }
);

// ── Citation popup card handlers ───────────────────────────────────────────
const keepCard = () => {
  if (_hideCardTimer) {
    clearTimeout(_hideCardTimer);
    _hideCardTimer = null;
  }
};

const scheduleHideCard = () => {
  _hideCardTimer = setTimeout(() => {
    citCard.visible = false;
  }, 120);
};

const _onBadgeOver = (e: MouseEvent) => {
  const badge = (e.target as HTMLElement).closest(
    'a[href^="#ref-"], .ref-list-anchor',
  ) as HTMLElement | null;
  if (!badge) return;

  // Fast path: pre-stamped by addReferenceAnchors
  let title = badge.dataset.title ?? '';
  let domain = badge.dataset.domain ?? '';
  let url = badge.dataset.url ?? '';

  // Fallback: resolve at hover time from the reference element in the DOM.
  // Covers cases where addReferenceAnchors ran before the References section
  // was rendered, or where no formal heading was detected.
  if (!title && !domain) {
    const rawHref = (badge as HTMLAnchorElement).getAttribute?.('href') ?? '';
    const refId = rawHref.startsWith('#') ? rawHref.slice(1) : '';
    if (refId) {
      const proseMirror = contentRef.value?.querySelector('.ProseMirror');
      const refEl = proseMirror?.querySelector(`#${refId}`);
      if (refEl) {
        const anchors = Array.from(refEl.querySelectorAll('a[href]')) as HTMLAnchorElement[];
        const ext = anchors.find((a) => {
          const h = a.getAttribute('href') ?? '';
          return h && !h.startsWith('#');
        });
        if (ext) {
          try {
            domain = new URL(ext.href).hostname.replace(/^www\./, '');
            title = (ext.textContent?.trim() || domain).slice(0, 64);
            url = ext.href;
            // Cache for future hovers
            badge.dataset.title = title;
            badge.dataset.domain = domain;
            badge.dataset.url = url;
          } catch { /* ignore malformed URLs */ }
        }
      }
    }
  }

  if (!title && !domain) return;

  keepCard();
  const rect = badge.getBoundingClientRect();
  citCard.title = title;
  citCard.domain = domain;
  citCard.faviconUrl = domain ? (getFaviconUrl(`https://${domain}`) ?? '') : '';
  citCard.url = url;
  const cardWidth = 260;
  citCard.x = Math.min(
    Math.max(rect.left + rect.width / 2 - cardWidth / 2, 8),
    window.innerWidth - cardWidth - 8,
  );
  citCard.y = rect.bottom + 8;
  citCard.visible = true;
};

const _onBadgeOut = (e: MouseEvent) => {
  if ((e.target as HTMLElement).closest('a[href^="#ref-"], .ref-list-anchor')) scheduleHideCard();
};

// Intercept clicks on citation badges (href="#ref-N") — scroll to the
// reference element instead of triggering browser anchor navigation,
// which doesn't work reliably inside the chat's custom scroll container.
const _onBadgeClick = (e: MouseEvent) => {
  const anchor = (e.target as HTMLElement).closest('a[href^="#ref-"]') as HTMLAnchorElement | null;
  if (!anchor) return;
  e.preventDefault();
  const refId = anchor.getAttribute('href')!.slice(1); // strip '#'
  const refEl = contentRef.value?.querySelector(`#${refId}`);
  if (refEl) {
    refEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }
};

onMounted(() => {
  contentRef.value?.addEventListener('mouseover', _onBadgeOver);
  contentRef.value?.addEventListener('mouseout', _onBadgeOut);
  contentRef.value?.addEventListener('click', _onBadgeClick);
});

onBeforeUnmount(() => {
  contentRef.value?.removeEventListener('mouseover', _onBadgeOver);
  contentRef.value?.removeEventListener('mouseout', _onBadgeOut);
  contentRef.value?.removeEventListener('click', _onBadgeClick);
  if (_hideCardTimer) clearTimeout(_hideCardTimer);
  editor.value?.destroy();
});

defineExpose({ contentRef });
</script>

<style scoped>
/* ── Container ───────────────────────────────────── */
.tiptap-message-viewer {
  width: 100%;
  min-height: 1em;
}

.tiptap-message-viewer--compact {
  font-size: 0.9375rem;
}

/* ── Prose base ──────────────────────────────────── */
.tiptap-message-prose {
  font-family: var(--font-sans);
  color: var(--text-primary);
  font-size: 15.5px;
  line-height: 1.7;
  letter-spacing: -0.003em;
  text-align: left;
  text-rendering: optimizeLegibility;
  -webkit-font-smoothing: antialiased;
  hyphens: auto;
  hyphenate-limit-chars: 6 3 2;
}

.tiptap-message-prose--compact {
  font-size: 14px;
  line-height: 1.55;
}

:deep(.tiptap) {
  outline: none;
  max-width: 72ch;
}

/* ── Paragraphs — matching report modal ──────────── */
:deep(.tiptap p) {
  margin: 16px 0;
  line-height: 1.75;
  text-align: inherit;
}

:deep(.tiptap p:first-child) {
  margin-top: 0;
}

:deep(.tiptap p:last-child) {
  margin-bottom: 0;
}

/* ── Inline text ─────────────────────────────────── */
:deep(.tiptap strong) {
  font-weight: 600;
  color: var(--text-primary);
}

:deep(.tiptap em) {
  font-style: italic;
  color: var(--text-secondary);
}

/* ── Links — matching report modal blue ──────────── */
:deep(.tiptap a),
:deep(.message-link) {
  color: #1a73e8;
  text-decoration: none;
  transition: color 0.15s ease, text-decoration-color 0.15s ease;
}

:deep(.tiptap a:hover),
:deep(.message-link:hover) {
  text-decoration: underline;
  text-decoration-color: rgba(26, 115, 232, 0.5);
}

:global(.dark) :deep(.tiptap a),
:global(.dark) :deep(.message-link),
:global([data-theme='dark']) :deep(.tiptap a),
:global([data-theme='dark']) :deep(.message-link) {
  color: #58a6ff;
}

/* ── Headings — matching report modal hierarchy ───── */
:deep(.tiptap h1) {
  font-size: 1.625rem;
  font-weight: 700;
  color: var(--text-primary);
  margin: 2rem 0 1rem;
  line-height: 1.3;
  letter-spacing: -0.02em;
  text-align: inherit;
}

:deep(.tiptap h2) {
  font-size: 1.375rem;
  font-weight: 700;
  color: var(--text-primary);
  margin: 2.25rem 0 1rem;
  line-height: 1.35;
  letter-spacing: -0.015em;
  padding-bottom: 0.5rem;
  border-bottom: 1px solid var(--border-light);
  text-align: inherit;
}

:deep(.tiptap h3) {
  font-size: 1.2rem;
  font-weight: 700;
  color: var(--text-primary);
  margin: 2rem 0 0.75rem;
  line-height: 1.4;
  letter-spacing: -0.01em;
  text-align: inherit;
}

:deep(.tiptap h4) {
  font-size: 1.05rem;
  font-weight: 700;
  color: var(--text-primary);
  margin: 1.5rem 0 0.5rem;
  line-height: 1.4;
  text-align: inherit;
}

:deep(.tiptap h1:first-child),
:deep(.tiptap h2:first-child),
:deep(.tiptap h3:first-child),
:deep(.tiptap h4:first-child) {
  margin-top: 0;
}

/* ── Lists — matching report modal spacing ───────── */
:deep(.tiptap ul),
:deep(.tiptap ol) {
  margin: 16px 0;
  padding-left: 24px;
  text-align: inherit;
}

:deep(.tiptap ul) {
  list-style-type: disc;
}

:deep(.tiptap ul ul) {
  list-style-type: circle;
}

:deep(.tiptap ul ul ul) {
  list-style-type: square;
}

:deep(.tiptap ol) {
  list-style-type: decimal;
}

:deep(.tiptap ol ol) {
  list-style-type: lower-alpha;
}

:deep(.tiptap li) {
  margin: 8px 0;
  padding-left: 4px;
  line-height: 1.7;
}

:deep(.tiptap li::marker) {
  color: var(--text-secondary);
  font-weight: 500;
}

:deep(.tiptap li > ul),
:deep(.tiptap li > ol) {
  margin: 4px 0 8px;
}

:deep(.tiptap li > p) {
  margin: 0;
}

/* ── Blockquotes — prominent with bg tint ─────────── */
:deep(.tiptap blockquote) {
  border-left: 3px solid var(--border-dark);
  background: var(--fill-tsp-gray-main);
  padding: 0.625rem 1rem;
  margin: 0.875rem 0;
  border-radius: 0 6px 6px 0;
  font-style: italic;
  color: var(--text-secondary);
  text-align: inherit;
}

:deep(.tiptap blockquote p) {
  margin: 0;
}

/* ── Horizontal rule — matching report modal ─────── */
:deep(.tiptap hr) {
  border: none;
  border-top: 1px solid var(--border-main);
  margin: 32px 0;
}

/* ── Inline code ─────────────────────────────────── */
:deep(.tiptap code) {
  background-color: var(--fill-tsp-gray-main);
  padding: 0.15em 0.4em;
  border-radius: 4px;
  font-size: 0.875em;
  font-family: ui-monospace, 'SF Mono', 'Cascadia Code', monospace;
  color: var(--text-primary);
  border: 1px solid var(--border-light);
}

/* ── Code blocks ─────────────────────────────────── */
:deep(.tiptap pre) {
  margin: 0.875em 0;
  border-radius: 8px;
  overflow-x: auto;
}

:deep(.tiptap pre code) {
  background: none;
  padding: 0;
  border: none;
  font-size: inherit;
}

:deep(.message-code-block) {
  background-color: var(--fill-tsp-gray-main) !important;
  padding: 0.875rem 1rem !important;
  border-radius: 8px !important;
  font-size: 0.875rem !important;
  line-height: 1.55 !important;
  border: 1px solid var(--border-light) !important;
}

/* ── Tables ──────────────────────────────────────── */
:deep(.tiptap table) {
  width: 100%;
  border-collapse: collapse;
  margin: 1rem 0;
  font-size: 0.9em;
  table-layout: auto;
  overflow-x: auto;
  display: block;
}

:deep(.tiptap th) {
  background-color: var(--fill-tsp-gray-main);
  border: 1px solid var(--border-main);
  padding: 0.6rem 0.75rem;
  text-align: left;
  font-weight: 600;
  color: var(--text-primary);
}

:deep(.tiptap td) {
  border: 1px solid var(--border-light);
  padding: 0.6rem 0.75rem;
  vertical-align: top;
  color: var(--text-primary);
}

:deep(.tiptap tr:nth-child(even) td) {
  background-color: var(--fill-tsp-gray-main);
}

:deep(.tiptap th p),
:deep(.tiptap td p) {
  margin: 0;
}

/* ── Images ──────────────────────────────────────── */
:deep(.tiptap img),
:deep(.message-image) {
  max-width: 100%;
  height: auto;
  border-radius: 8px;
  margin: 0.625em 0;
  border: 1px solid var(--border-light);
}

/* ── Task lists ──────────────────────────────────── */
:deep(.tiptap ul[data-type='taskList']) {
  list-style: none;
  padding-left: 0;
}

:deep(.tiptap ul[data-type='taskList'] li) {
  display: flex;
  align-items: flex-start;
  gap: 0.5rem;
  padding-left: 0;
}

:deep(.tiptap ul[data-type='taskList'] li::marker) {
  content: none;
}

:deep(.tiptap ul[data-type='taskList'] li input[type='checkbox']) {
  pointer-events: none;
  margin-top: 0.3em;
  width: 14px;
  height: 14px;
  flex-shrink: 0;
  accent-color: #1a73e8;
}

/* ── Reference list anchors — hover shows popup card ─ */
:deep(.ref-list-anchor) {
  cursor: pointer;
  text-decoration: underline;
  text-decoration-color: rgba(26, 115, 232, 0.35);
  text-underline-offset: 2px;
  transition: text-decoration-color 0.15s ease, color 0.15s ease;
}

:deep(.ref-list-anchor:hover) {
  text-decoration-color: #1a73e8;
  color: #1a73e8;
}

:global(.dark) :deep(.ref-list-anchor:hover),
:global([data-theme='dark']) :deep(.ref-list-anchor:hover) {
  text-decoration-color: #58a6ff;
  color: #58a6ff;
}

/* ── Verification markers ────────────────────────── */
:deep(.verification-marker) {
  color: var(--function-warning);
  font-size: 0.72em;
  line-height: 1;
  margin-left: 0.24rem;
  opacity: 0.8;
  cursor: help;
  user-select: none;
}

:deep(.verification-marker:hover) {
  opacity: 1;
}

/* ── Inline citation badges — identical to TiptapReportEditor ── */
:deep(a[href^="#ref-"]) {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 16px;
  height: 16px;
  padding: 0 3.5px;
  background: transparent;
  border: 1.5px solid rgba(0, 0, 0, 0.22);
  border-radius: 5px;
  color: rgba(0, 0, 0, 0.45);
  font-size: 9.5px;
  font-weight: 700;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
  letter-spacing: 0;
  text-decoration: none !important;
  cursor: pointer;
  position: relative;
  vertical-align: 0.25em;
  line-height: 1;
  margin: 0 1.5px;
  transition:
    background 0.15s ease,
    border-color 0.15s ease,
    color 0.15s ease;
  user-select: none;
}

:deep(a[href^="#ref-"]:hover) {
  background: #1c1c1e;
  border-color: #1c1c1e;
  color: #ffffff;
  text-decoration: none !important;
}

:global(.dark) :deep(a[href^="#ref-"]),
:global([data-theme='dark']) :deep(a[href^="#ref-"]) {
  border-color: rgba(255, 255, 255, 0.25);
  color: rgba(255, 255, 255, 0.45);
}

:global(.dark) :deep(a[href^="#ref-"]:hover),
:global([data-theme='dark']) :deep(a[href^="#ref-"]:hover) {
  background: #e5e5e7;
  border-color: #e5e5e7;
  color: #1c1c1e;
}
</style>

<!-- Global styles for the teleported citation card (no scoping — lives on <body>) -->
<style>
.msg-cit-card {
  position: fixed;
  z-index: 99999;
  width: 260px;
  background: #ffffff;
  border: 1px solid rgba(0, 0, 0, 0.08);
  border-radius: 12px;
  padding: 11px 14px 10px;
  box-shadow:
    0 0 0 1px rgba(0, 0, 0, 0.04),
    0 4px 6px rgba(0, 0, 0, 0.04),
    0 12px 28px rgba(0, 0, 0, 0.1);
  pointer-events: auto;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
  text-decoration: none;
  display: block;
  cursor: pointer;
}

.msg-cit-card-title {
  margin: 0 0 8px;
  font-size: 13.5px;
  font-weight: 600;
  color: #111111;
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.msg-cit-card-footer {
  display: flex;
  align-items: center;
  gap: 6px;
}

.msg-cit-card-favicon {
  width: 14px;
  height: 14px;
  border-radius: 3px;
  flex-shrink: 0;
  object-fit: contain;
}

.msg-cit-card-domain {
  font-size: 12px;
  color: #666666;
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.msg-cit-card-arrow {
  width: 11px;
  height: 11px;
  color: #999999;
  flex-shrink: 0;
}

/* ── Transition ── */
.cit-pop-enter-active {
  transition:
    opacity 0.16s ease,
    transform 0.2s cubic-bezier(0.34, 1.56, 0.64, 1);
}
.cit-pop-leave-active {
  transition: opacity 0.1s ease;
}
.cit-pop-enter-from {
  opacity: 0;
  transform: translateY(-6px) scale(0.96);
}
.cit-pop-leave-to {
  opacity: 0;
}

/* ── Dark mode ── */
.dark .msg-cit-card,
[data-theme='dark'] .msg-cit-card {
  background: #1e1e20;
  border-color: rgba(255, 255, 255, 0.09);
  box-shadow:
    0 0 0 1px rgba(255, 255, 255, 0.04),
    0 4px 6px rgba(0, 0, 0, 0.2),
    0 12px 28px rgba(0, 0, 0, 0.4);
}

.dark .msg-cit-card-title,
[data-theme='dark'] .msg-cit-card-title {
  color: #f0f0f0;
}

.dark .msg-cit-card-domain,
[data-theme='dark'] .msg-cit-card-domain {
  color: rgba(240, 240, 240, 0.45);
}

.dark .msg-cit-card-arrow,
[data-theme='dark'] .msg-cit-card-arrow {
  color: rgba(240, 240, 240, 0.35);
}
</style>
