<template>
  <div
    v-bind="$attrs"
    ref="contentRef"
    :class="[
      'tiptap-report-editor bg-[var(--background-white-main)]',
      embedded ? 'overflow-visible' : compact ? 'overflow-hidden' : 'h-full overflow-y-auto px-8 py-6'
    ]"
    @scroll="$emit('scroll', $event)"
  >
    <EditorContent
      :editor="editor"
      :class="[
        'prose prose-gray',
        compact
          ? ['prose-compact', hideMainTitleInCompact ?? true ? 'hide-main-title' : '']
          : 'max-w-4xl mx-auto'
      ]"
    />
  </div>

  <!-- Citation reference card — teleported to body so it escapes overflow clipping -->
  <Teleport to="body">
    <Transition name="cit-pop">
      <a
        v-if="citCard.visible"
        class="cit-card"
        :href="citCard.url || undefined"
        target="_blank"
        rel="noopener noreferrer"
        :style="{ left: citCard.x + 'px', top: citCard.y + 'px' }"
        @mouseenter="keepCard"
        @mouseleave="scheduleHideCard"
        @click="openCitCardUrl"
      >
        <p class="cit-card-title">{{ citCard.title }}</p>
        <div class="cit-card-footer">
          <img
            v-if="citCard.faviconUrl"
            :src="citCard.faviconUrl"
            class="cit-card-favicon"
            @error="(e) => { (e.target as HTMLImageElement).style.display = 'none' }"
          />
          <span class="cit-card-domain">{{ citCard.domain }}</span>
          <svg class="cit-card-arrow" viewBox="0 0 12 12" fill="none">
            <path d="M2.5 9.5L9.5 2.5M9.5 2.5H5M9.5 2.5V7" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </div>
      </a>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, onBeforeUnmount, computed, nextTick, reactive } from 'vue';
import { useEditor, EditorContent } from '@tiptap/vue-3';
import { marked } from 'marked';
import DOMPurify from 'dompurify';
import { normalizeVerificationMarkers, linkifyInlineCitations } from './reportContentNormalizer';
import { createTiptapDocumentExtensions } from './tiptapDocumentExtensions';
import { getFaviconUrl } from '@/utils/toolDisplay';
import type { SourceCitation } from '@/types/message';

// Fragment root (div + Teleport) — disable auto attr-inheritance so $attrs go to the real div
defineOptions({ inheritAttrs: false });

const props = defineProps<{
  content: string;
  editable?: boolean;
  compact?: boolean;
  hideMainTitleInCompact?: boolean;
  embedded?: boolean;
  /** Structured sources from backend — used as authoritative data for citation popups */
  sources?: SourceCitation[];
}>();

const _emit = defineEmits<{
  (e: 'scroll', event: Event): void;
}>();

const contentRef = ref<HTMLElement | null>(null);

// ── Citation reference card state (declared early — template accesses this on first render) ──
const citCard = reactive({ visible: false, title: '', domain: '', faviconUrl: '', url: '', x: 0, y: 0 });
let _hideCardTimer: ReturnType<typeof setTimeout> | null = null;

// Convert markdown to HTML, applying citation linkification before marked.parse()
const htmlContent = computed(() => {
  if (!props.content) return '';
  const normalizedMarkdown = normalizeVerificationMarkers(props.content);
  const linkedMarkdown = linkifyInlineCitations(normalizedMarkdown);
  const rawHtml = marked.parse(linkedMarkdown, { async: false, breaks: true, gfm: true }) as string;
  return DOMPurify.sanitize(rawHtml);
});

// After TipTap renders, stamp id="ref-N" onto list items inside the
// References / Sources / Bibliography section. TipTap strips unknown id attrs
// from its schema nodes, so we must do this via direct DOM mutation.
// Also injects data-{title,domain,url} into inline citation badges for the popup,
// and stamps the same data onto reference-section anchors for hover popups.
const addReferenceAnchors = () => {
  const proseMirror = contentRef.value?.querySelector('.ProseMirror');
  if (!proseMirror) return;

  const refHeadingRe = /^(references?|sources?|bibliography|citations?)$/i;
  const headings = Array.from(proseMirror.querySelectorAll('h1, h2, h3, h4'));
  const refMap = new Map<string, { title: string; domain: string; url: string }>();

  // Seed refMap from structured backend sources (authoritative, index-based).
  // The backend assigns citation numbers sequentially (1-based), matching [N] in content.
  if (props.sources?.length) {
    for (let i = 0; i < props.sources.length; i++) {
      const src = props.sources[i];
      try {
        const domain = new URL(src.url).hostname.replace(/^www\./, '');
        const title = (src.title || domain).slice(0, 80);
        refMap.set(String(i + 1), { title, domain, url: src.url });
      } catch { /* malformed URL — skip, DOM scraping will fill the gap */ }
    }
  }

  // Helper: find the first anchor whose raw href is external (not a fragment)
  const findExternalAnchor = (el: Element): HTMLAnchorElement | null => {
    const anchors = Array.from(el.querySelectorAll('a[href]')) as HTMLAnchorElement[];
    return anchors.find((a) => {
      const raw = a.getAttribute('href') ?? '';
      return raw && !raw.startsWith('#');
    }) ?? null;
  };

  // Helper: extract a URL from plain text when no <a> tag is present
  const extractUrlFromText = (text: string): string | null => {
    const m = text.match(/https?:\/\/[^\s)<>]+/);
    return m ? m[0] : null;
  };

  // Helper: build refMap entry from an anchor or bare-text URL.
  // Skips if refMap already has an entry from structured sources (authoritative).
  const extractRefMeta = (el: Element, num: string) => {
    if (refMap.has(num)) {
      // Already populated from props.sources — still stamp the DOM anchor for styling
      const anchor = findExternalAnchor(el);
      if (anchor) {
        const meta = refMap.get(num)!;
        anchor.dataset.title = meta.title;
        anchor.dataset.domain = meta.domain;
        anchor.dataset.url = meta.url;
        anchor.classList.add('ref-list-anchor');
        anchor.setAttribute('target', '_blank');
        anchor.setAttribute('rel', 'noopener noreferrer');
      }
      return;
    }
    const anchor = findExternalAnchor(el);
    if (anchor) {
      try {
        const domain = new URL(anchor.href).hostname.replace(/^www\./, '');
        const title = (anchor.textContent?.trim() || domain).slice(0, 64);
        refMap.set(num, { title, domain, url: anchor.href });
        // Stamp data on the reference-section anchor for hover popup
        anchor.dataset.title = title;
        anchor.dataset.domain = domain;
        anchor.dataset.url = anchor.href;
        anchor.classList.add('ref-list-anchor');
        anchor.setAttribute('target', '_blank');
        anchor.setAttribute('rel', 'noopener noreferrer');
      } catch { /* ignore malformed URLs */ }
      return;
    }
    // Fallback: bare URL in text content (LLM didn't use markdown link syntax)
    const bareUrl = extractUrlFromText(el.textContent ?? '');
    if (bareUrl) {
      try {
        const domain = new URL(bareUrl).hostname.replace(/^www\./, '');
        const title = domain.slice(0, 64);
        refMap.set(num, { title, domain, url: bareUrl });
      } catch { /* ignore */ }
    }
  };

  const refMapSizeBeforeHeadingScan = refMap.size;

  for (const heading of headings) {
    if (!refHeadingRe.test(heading.textContent?.trim() ?? '')) continue;

    let sibling = heading.nextElementSibling;
    let nextNum = 1; // running counter for list items across split lists
    while (sibling) {
      if (/^H[1-4]$/.test(sibling.tagName)) break;

      // Ordered or unordered list — process all items
      if (sibling.tagName === 'OL' || sibling.tagName === 'UL') {
        const startAttr = sibling.getAttribute('start');
        const startNum = startAttr ? parseInt(startAttr, 10) : nextNum;
        sibling.querySelectorAll(':scope > li').forEach((item, index) => {
          const num = String(startNum + index);
          item.setAttribute('id', `ref-${num}`);
          extractRefMeta(item, num);
        });
        nextNum = startNum + sibling.querySelectorAll(':scope > li').length;
        // Continue scanning — references may span multiple lists
        sibling = sibling.nextElementSibling;
        continue;
      }

      // Bracket-style: "[N] [Link Title](URL)" — rendered as a <p> by marked
      if (sibling.tagName === 'P' || sibling.tagName === 'DIV') {
        const text = sibling.textContent?.trimStart() ?? '';
        const m = text.match(/^\[(\d{1,3})\]/);
        if (m) {
          const num = m[1];
          sibling.setAttribute('id', `ref-${num}`);
          extractRefMeta(sibling, num);
          nextNum = Math.max(nextNum, parseInt(num, 10) + 1);
        }
      }

      sibling = sibling.nextElementSibling;
    }
  }

  // Fallback: scan for bold-text reference headers (e.g., "**Sources:**" or "**References:**").
  // LLMs often use bold text instead of proper markdown headings for reference sections.
  // Only run this scan if the heading-based scan above found nothing new.
  const headingScanFound = refMap.size > refMapSizeBeforeHeadingScan;
  if (!headingScanFound) {
    const paragraphs = Array.from(proseMirror.querySelectorAll('p'));
    for (const p of paragraphs) {
      const strong = p.querySelector('strong');
      if (!strong) continue;
      const strongText = strong.textContent?.trim().replace(/:$/, '') ?? '';
      if (!refHeadingRe.test(strongText)) continue;

      // Found a bold reference header — process siblings just like heading scan
      let sibling = p.nextElementSibling;
      let nextNum = 1;
      while (sibling) {
        if (/^H[1-4]$/.test(sibling.tagName)) break;
        // Stop if we hit another paragraph with bold text (likely a new section)
        if (sibling.tagName === 'P' && sibling.querySelector('strong') && sibling !== p) {
          const sibStrong = sibling.querySelector('strong')?.textContent?.trim().replace(/:$/, '') ?? '';
          if (sibStrong.length > 2 && !sibStrong.match(/^\d/)) break;
        }

        if (sibling.tagName === 'OL' || sibling.tagName === 'UL') {
          const startAttr = sibling.getAttribute('start');
          const startNum = startAttr ? parseInt(startAttr, 10) : nextNum;
          sibling.querySelectorAll(':scope > li').forEach((item, index) => {
            const num = String(startNum + index);
            item.setAttribute('id', `ref-${num}`);
            extractRefMeta(item, num);
          });
          nextNum = startNum + sibling.querySelectorAll(':scope > li').length;
          sibling = sibling.nextElementSibling;
          continue;
        }

        if (sibling.tagName === 'P' || sibling.tagName === 'DIV') {
          const text = sibling.textContent?.trimStart() ?? '';
          const m = text.match(/^\[(\d{1,3})\]/);
          if (m) {
            const num = m[1];
            sibling.setAttribute('id', `ref-${num}`);
            extractRefMeta(sibling, num);
            nextNum = Math.max(nextNum, parseInt(num, 10) + 1);
          }
        }

        sibling = sibling.nextElementSibling;
      }
      break; // Only process the first bold reference header
    }
  }

  // Stamp data attributes onto inline citation badge anchors for popup card.
  // Also remove target/_blank / rel added by the Link extension — citation
  // badges are internal fragment links and must scroll within the page.
  proseMirror.querySelectorAll('a[href^="#ref-"]').forEach((badge) => {
    const el = badge as HTMLAnchorElement;
    el.removeAttribute('target');
    el.removeAttribute('rel');
    // Strip TipTap Link extension classes — citation badges have their own styling
    el.classList.remove('report-link', 'hover:underline', 'cursor-pointer');
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
  editable: props.editable ?? false,
  extensions: createTiptapDocumentExtensions(),
  editorProps: {
    attributes: {
      class: 'focus:outline-none min-h-full',
    },
  },
  onCreate: () => { nextTick(addReferenceAnchors); },
  onUpdate: () => { nextTick(addReferenceAnchors); },
});

// Watch for content changes - convert markdown to HTML
watch(() => props.content, () => {
  if (editor.value && htmlContent.value !== editor.value.getHTML()) {
    // emitUpdate: false avoids infinite loops, but onUpdate won't fire —
    // so re-run addReferenceAnchors manually after the DOM settles.
    editor.value.commands.setContent(htmlContent.value, { emitUpdate: false });
    nextTick(addReferenceAnchors);
  }
});

// Watch for sources changes — sources may arrive after initial content render.
// Re-stamp citation data attributes so all badges get popup data.
watch(() => props.sources, () => {
  nextTick(addReferenceAnchors);
}, { deep: true });

// Watch for editable changes
watch(() => props.editable, (newEditable) => {
  if (editor.value) {
    editor.value.setEditable(newEditable ?? false);
  }
});

// ── Citation reference card handlers ──────────────────────────────────────
const openCitCardUrl = () => { if (citCard.url) window.open(citCard.url, '_blank', 'noopener,noreferrer'); };
const keepCard = () => { if (_hideCardTimer) { clearTimeout(_hideCardTimer); _hideCardTimer = null; } };
const scheduleHideCard = () => { _hideCardTimer = setTimeout(() => { citCard.visible = false; }, 120); };

const _onBadgeOver = (e: MouseEvent) => {
  const badge = (e.target as HTMLElement).closest(
    'a[href^="#ref-"], .ref-list-anchor',
  ) as HTMLElement | null;
  if (!badge) return;

  // Fast path: pre-stamped by addReferenceAnchors
  let title = badge.dataset.title ?? '';
  let domain = badge.dataset.domain ?? '';
  let url = badge.dataset.url ?? '';

  const rawHref = (badge as HTMLAnchorElement).getAttribute?.('href') ?? '';
  const num = rawHref.replace('#ref-', '');

  // Fallback 1: resolve from props.sources (authoritative, index-based).
  // Runs when title/domain/url are missing — sources carry the full metadata.
  if (!title || !url) {
    const srcIdx = parseInt(num, 10) - 1;
    if (srcIdx >= 0 && props.sources?.[srcIdx]) {
      const src = props.sources[srcIdx];
      try {
        const d = new URL(src.url).hostname.replace(/^www\./, '');
        if (!title) title = (src.title || d).slice(0, 80);
        if (!domain) domain = d;
        if (!url) url = src.url;
        badge.dataset.title = title;
        badge.dataset.domain = domain;
        badge.dataset.url = url;
      } catch { /* malformed URL — try DOM fallback */ }
    }
  }

  // Fallback 2: resolve from the reference element in the DOM.
  // Runs when url is still missing after sources lookup.
  if (!url) {
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
            const d = new URL(ext.href).hostname.replace(/^www\./, '');
            if (!title) title = (ext.textContent?.trim() || d).slice(0, 64);
            if (!domain) domain = d;
            url = ext.href;
            badge.dataset.title = title;
            badge.dataset.domain = domain;
            badge.dataset.url = url;
          } catch { /* ignore malformed URLs */ }
        } else {
          // Last resort: extract bare URL from text content
          const bareMatch = refEl.textContent?.match(/https?:\/\/[^\s)<>]+/);
          if (bareMatch) {
            try {
              const d = new URL(bareMatch[0]).hostname.replace(/^www\./, '');
              if (!title) title = d.slice(0, 64);
              if (!domain) domain = d;
              url = bareMatch[0];
              badge.dataset.title = title;
              badge.dataset.domain = domain;
              badge.dataset.url = url;
            } catch { /* ignore */ }
          }
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
  // Centre the card below the badge, clamped to viewport width
  const cardWidth = 260;
  citCard.x = Math.min(Math.max(rect.left + rect.width / 2 - cardWidth / 2, 8), window.innerWidth - cardWidth - 8);
  citCard.y = rect.bottom + 8;
  citCard.visible = true;
};

const _onBadgeOut = (e: MouseEvent) => {
  if ((e.target as HTMLElement).closest('a[href^="#ref-"], .ref-list-anchor')) scheduleHideCard();
};

// Intercept clicks on citation badges (href="#ref-N").
// If the badge has a resolved external URL, open it in a new tab.
// Otherwise fall back to scrolling to the reference element.
const _onBadgeClick = (e: MouseEvent) => {
  const anchor = (e.target as HTMLElement).closest('a[href^="#ref-"]') as HTMLAnchorElement | null;
  if (!anchor) return;
  e.preventDefault();
  const externalUrl = anchor.dataset.url;
  if (externalUrl) {
    window.open(externalUrl, '_blank', 'noopener,noreferrer');
    return;
  }
  const refId = anchor.getAttribute('href')!.slice(1);
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

// Expose content ref for parent component
defineExpose({
  contentRef,
});
</script>

<style scoped>
/* Prose styling for report content */
:deep(.prose) {
  --tw-prose-body: var(--text-primary);
  --tw-prose-headings: var(--text-primary);
  --tw-prose-links: #1a73e8;
  --tw-prose-bold: var(--text-primary);
  --tw-prose-counters: var(--text-secondary);
  --tw-prose-bullets: var(--text-tertiary);
  --tw-prose-hr: var(--border-main);
  --tw-prose-quotes: var(--text-secondary);
  --tw-prose-quote-borders: var(--border-main);
  --tw-prose-captions: var(--text-tertiary);
  --tw-prose-code: var(--text-primary);
  --tw-prose-pre-code: var(--text-primary);
  --tw-prose-pre-bg: var(--fill-tsp-gray-main);
  --tw-prose-th-borders: var(--border-main);
  --tw-prose-td-borders: var(--border-light);
}

/* Dark mode prose + report-link overrides in unscoped <style> block below */

/* Link styling */
:deep(.report-link) {
  color: #1a73e8;
  transition: color 0.15s ease;
}

:deep(.prose h1) {
  font-size: 1.875rem;
  font-weight: 700;
  margin-top: 2rem;
  margin-bottom: 1rem;
  line-height: 1.3;
}

:deep(.prose h2) {
  font-size: 1.5rem;
  font-weight: 600;
  margin-top: 1.75rem;
  margin-bottom: 0.75rem;
  line-height: 1.35;
  border-bottom: 1px solid var(--border-light);
  padding-bottom: 0.5rem;
}

:deep(.prose h3) {
  font-size: 1.25rem;
  font-weight: 600;
  margin-top: 1.5rem;
  margin-bottom: 0.5rem;
  line-height: 1.4;
}

:deep(.prose h4) {
  font-size: 1.1rem;
  font-weight: 600;
  margin-top: 1.25rem;
  margin-bottom: 0.5rem;
  line-height: 1.4;
}

:deep(.prose p) {
  margin-top: 0.75rem;
  margin-bottom: 0.75rem;
  line-height: 1.7;
}

:deep(.prose ul),
:deep(.prose ol) {
  margin-top: 0.75rem;
  margin-bottom: 0.75rem;
  padding-left: 1.5rem;
}

:deep(.prose li) {
  margin-top: 0.25rem;
  margin-bottom: 0.25rem;
}

:deep(.prose blockquote) {
  border-left: 4px solid var(--border-main);
  padding-left: 1rem;
  margin-top: 1rem;
  margin-bottom: 1rem;
  font-style: italic;
  color: var(--text-secondary);
}

:deep(.prose table) {
  width: 100%;
  border-collapse: collapse;
  margin-top: 1rem;
  margin-bottom: 1rem;
  font-size: 0.875rem;
  table-layout: fixed;
}

:deep(.prose th) {
  background-color: var(--fill-tsp-gray-main);
  border: 1px solid var(--border-main);
  padding: 0.75rem;
  text-align: left;
  font-weight: 600;
}

:deep(.prose td) {
  border: 1px solid var(--border-light);
  padding: 0.75rem;
  vertical-align: top;
}

:deep(.prose th p),
:deep(.prose td p) {
  margin: 0;
}

:deep(.prose code) {
  background-color: var(--fill-tsp-gray-main);
  padding: 0.125rem 0.375rem;
  border-radius: 0.25rem;
  font-size: 0.875em;
}

:deep(.prose pre) {
  margin-top: 1rem;
  margin-bottom: 1rem;
}

:deep(.prose pre code) {
  background-color: transparent;
  padding: 0;
}

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

/* ===== INLINE CITATION BADGE ===== */
/* Default: outlined. Hover: fills solid black + popup card appears. */
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
  transition: background 0.15s ease, border-color 0.15s ease, color 0.15s ease;
  user-select: none;
}

:deep(a[href^="#ref-"]:hover) {
  background: #1c1c1e;
  border-color: #1c1c1e;
  color: #ffffff;
  text-decoration: none !important;
}

/* Dark mode badge + report-link safety overrides live in the unscoped <style> block below
   to avoid Vue scoped CSS compilation issues with :global() + :deep() */

/* Safety: override report-link styles if class persists on citation badges
   (TipTap Link extension re-applies classes on every render cycle) */
:deep(a.report-link[href^="#ref-"]) {
  color: rgba(0, 0, 0, 0.45);
  text-decoration: none !important;
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

/* Dark mode .ref-list-anchor:hover in unscoped <style> block below */

/* no pseudo-element tooltip — handled by .cit-card teleported to body */

:deep(.prose hr) {
  border-color: var(--border-main);
  margin-top: 2rem;
  margin-bottom: 2rem;
}

:deep(.prose img) {
  max-width: 100%;
  height: auto;
  border-radius: 0.5rem;
  margin-top: 1rem;
  margin-bottom: 1rem;
}

/* Task list styling */
:deep(.prose ul[data-type="taskList"]) {
  list-style: none;
  padding-left: 0;
}

:deep(.prose ul[data-type="taskList"] li) {
  display: flex;
  align-items: flex-start;
  gap: 0.5rem;
}

:deep(.prose ul[data-type="taskList"] li input[type="checkbox"]) {
  margin-top: 0.25rem;
}

/* Compact mode styling for card preview */
:deep(.prose-compact) {
  --tw-prose-body: var(--text-secondary);
  --tw-prose-headings: var(--text-primary);
  --tw-prose-links: var(--tw-prose-links, #1a73e8);
  --tw-prose-bold: var(--text-primary);
  --tw-prose-counters: var(--text-secondary);
  --tw-prose-bullets: var(--text-tertiary);
  --tw-prose-hr: var(--border-main);
  --tw-prose-quotes: var(--text-secondary);
  --tw-prose-quote-borders: var(--border-main);
  --tw-prose-captions: var(--text-tertiary);
  --tw-prose-code: var(--text-primary);
  --tw-prose-pre-code: var(--text-primary);
  --tw-prose-pre-bg: var(--fill-tsp-gray-main);
  --tw-prose-th-borders: var(--border-main);
  --tw-prose-td-borders: var(--border-light);
}

:deep(.prose-compact.hide-main-title h1) {
  display: none; /* Hide h1 in compact mode - shown separately */
}

:deep(.prose-compact h2) {
  font-size: 1rem;
  font-weight: 600;
  margin-top: 1rem;
  margin-bottom: 0.5rem;
  line-height: 1.35;
  border-bottom: none;
  padding-bottom: 0;
  color: var(--text-primary);
}

:deep(.prose-compact h3) {
  font-size: 0.875rem;
  font-weight: 600;
  margin-top: 0.75rem;
  margin-bottom: 0.375rem;
  line-height: 1.4;
  color: var(--text-primary);
}

:deep(.prose-compact h4) {
  font-size: 0.8125rem;
  font-weight: 600;
  margin-top: 0.625rem;
  margin-bottom: 0.25rem;
  line-height: 1.4;
  color: var(--text-primary);
}

:deep(.prose-compact p) {
  margin-top: 0.5rem;
  margin-bottom: 0.5rem;
  line-height: 1.6;
  font-size: 0.875rem;
  color: var(--text-secondary);
}

:deep(.prose-compact ul),
:deep(.prose-compact ol) {
  margin-top: 0.5rem;
  margin-bottom: 0.5rem;
  padding-left: 1.25rem;
  font-size: 0.875rem;
}

:deep(.prose-compact li) {
  margin-top: 0.125rem;
  margin-bottom: 0.125rem;
}

:deep(.prose-compact blockquote) {
  border-left: 3px solid var(--border-main);
  padding-left: 0.75rem;
  margin-top: 0.75rem;
  margin-bottom: 0.75rem;
  font-style: italic;
  color: var(--text-secondary);
  font-size: 0.875rem;
}

:deep(.prose-compact table) {
  width: 100%;
  border-collapse: collapse;
  margin-top: 0.75rem;
  margin-bottom: 0.75rem;
  font-size: 0.75rem;
}

:deep(.prose-compact th) {
  background-color: var(--fill-tsp-gray-main);
  border: 1px solid var(--border-main);
  padding: 0.5rem;
  text-align: left;
  font-weight: 600;
}

:deep(.prose-compact td) {
  border: 1px solid var(--border-light);
  padding: 0.5rem;
}

:deep(.prose-compact code) {
  background-color: var(--fill-tsp-gray-main);
  padding: 0.0625rem 0.25rem;
  border-radius: 0.1875rem;
  font-size: 0.8125em;
}

:deep(.prose-compact pre) {
  margin-top: 0.75rem;
  margin-bottom: 0.75rem;
  padding: 0.75rem;
  font-size: 0.75rem;
}

:deep(.prose-compact hr) {
  border-color: var(--border-main);
  margin-top: 1rem;
  margin-bottom: 1rem;
}

:deep(.prose-compact img) {
  max-width: 100%;
  height: auto;
  border-radius: 0.375rem;
  margin-top: 0.75rem;
  margin-bottom: 0.75rem;
}

:deep(.prose-compact strong) {
  color: var(--text-primary);
  font-weight: 600;
}
</style>

<!-- Global styles for the teleported citation card (no scoping — lives on <body>) -->
<style>
.cit-card {
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
    0 12px 28px rgba(0, 0, 0, 0.10);
  pointer-events: auto;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
  text-decoration: none;
  display: block;
  cursor: pointer;
}

.cit-card-title {
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

.cit-card-footer {
  display: flex;
  align-items: center;
  gap: 6px;
}

.cit-card-favicon {
  width: 14px;
  height: 14px;
  border-radius: 3px;
  flex-shrink: 0;
  object-fit: contain;
}

.cit-card-domain {
  font-size: 12px;
  color: #666666;
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cit-card-arrow {
  width: 11px;
  height: 11px;
  color: #999999;
  flex-shrink: 0;
}

/* ── Transition ── */
.cit-pop-enter-active {
  transition: opacity 0.16s ease, transform 0.2s cubic-bezier(0.34, 1.56, 0.64, 1);
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
.dark .cit-card {
  background: #222222;
  border-color: rgba(255, 255, 255, 0.09);
  box-shadow:
    0 0 0 1px rgba(255, 255, 255, 0.04),
    0 4px 6px rgba(0, 0, 0, 0.2),
    0 12px 28px rgba(0, 0, 0, 0.4);
}

.dark .cit-card-title {
  color: #f0f0f0;
}

.dark .cit-card-domain {
  color: rgba(240, 240, 240, 0.45);
}

.dark .cit-card-arrow {
  color: rgba(240, 240, 240, 0.35);
}

/* ── Dark mode: prose link variable ──────────────────────────────────── */
.dark .tiptap-report-editor .prose {
  --tw-prose-links: #7cb3e0;
}

/* ── Dark mode: report-link color ────────────────────────────────────── */
.dark .tiptap-report-editor .report-link {
  color: #7cb3e0;
}

/* ── Dark mode: inline citation badges ───────────────────────────────
   Uses .tiptap-report-editor class for specificity (beats scoped [data-v] attrs).
   Placed here (unscoped) because .dark in <style scoped> can be
   unreliable across Vue SFC compiler versions. */
.dark .tiptap-report-editor a[href^="#ref-"] {
  background: transparent;
  border-color: rgba(255, 255, 255, 0.22);
  color: rgba(255, 255, 255, 0.5);
  text-decoration: none !important;
}

.dark .tiptap-report-editor a[href^="#ref-"]:hover {
  background: #e5e5e7;
  border-color: #e5e5e7;
  color: #1c1c1e;
  text-decoration: none !important;
}

/* ── Dark mode: report-link safety override for citation badges ────── */
.dark .tiptap-report-editor a.report-link[href^="#ref-"] {
  color: rgba(255, 255, 255, 0.5);
}

/* ── Dark mode: reference list anchor hover ──────────────────────────── */
.dark .tiptap-report-editor .ref-list-anchor:hover {
  text-decoration-color: #7cb3e0;
  color: #7cb3e0;
}
</style>
