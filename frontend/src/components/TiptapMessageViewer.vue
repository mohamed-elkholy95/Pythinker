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
        @click="openCitCardUrl"
      >
        <p class="msg-cit-card-title">{{ citCard.title }}</p>
        <div class="msg-cit-card-footer">
          <img
            v-if="citCard.faviconUrl"
            :src="citCard.faviconUrl"
            class="msg-cit-card-favicon"
            @error="(e: Event) => { (e.target as HTMLImageElement).style.display = 'none'; if (citCard.domain) _failedFaviconDomains.add(citCard.domain); }"
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
import { Table } from '@tiptap/extension-table';
import TableRow from '@tiptap/extension-table-row';
import TableHeader from '@tiptap/extension-table-header';
import TableCell from '@tiptap/extension-table-cell';
import TaskList from '@tiptap/extension-task-list';
import TaskItem from '@tiptap/extension-task-item';
import TextAlign from '@tiptap/extension-text-align';
import Typography from '@tiptap/extension-typography';
import CodeBlockLowlight from '@tiptap/extension-code-block-lowlight';
import { common, createLowlight } from 'lowlight';
import { marked } from 'marked';
import DOMPurify from 'dompurify';
import { normalizeVerificationMarkers, linkifyInlineCitations } from './report/reportContentNormalizer';
import { MermaidBlock } from './report/tiptapMermaidExtension';
import { getFaviconUrl } from '@/utils/toolDisplay';
import type { SourceCitation } from '@/types/message';

// Fragment root (div + Teleport) — disable auto attr-inheritance so $attrs go to the real div
defineOptions({ inheritAttrs: false });

const props = withDefaults(
  defineProps<{
    content: string;
    /** Render as compact (summary cards, etc.) */
    compact?: boolean;
    /** Structured sources from backend — used as authoritative data for citation popups */
    sources?: SourceCitation[];
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
const _failedFaviconDomains = new Set<string>();

// Debug flag — enabled via ?debugCitations in URL or console: window.__citDebug = true
const _citDebug = typeof window !== 'undefined' && new URLSearchParams(window.location.search).has('debugCitations');

// Apply same normalizers as TiptapReportEditor: verification markers + inline citations
const htmlContent = computed(() => {
  if (!props.content) return '<p></p>';
  const normalizedMarkdown = normalizeVerificationMarkers(props.content);
  const linkedMarkdown = linkifyInlineCitations(normalizedMarkdown);
  // Collapse 3+ consecutive newlines to 2 — prevents excessive <br> gaps from `breaks: true`
  const collapsed = linkedMarkdown.replace(/\n{3,}/g, '\n\n');
  const rawHtml = marked.parse(collapsed, { async: false, breaks: true, gfm: true }) as string;
  const sanitized = DOMPurify.sanitize(rawHtml);
  if (_citDebug) {
    console.groupCollapsed('%c[CitDebug:Msg] htmlContent pipeline', 'color:#9b59b6;font-weight:bold');
    const refTail = (s: string) => {
      const idx = s.search(/(?:#{1,4}\s*(?:references?|sources?|bibliography|citations?)|\*{2}(?:references?|sources?|bibliography|citations?):?\*{2})/i);
      return idx >= 0 ? s.slice(idx, idx + 800) : '(no references section detected)';
    };
    console.log('after linkifyInlineCitations (ref tail):\n', refTail(linkedMarkdown));
    console.log('after marked.parse (ref tail):\n', refTail(rawHtml));
    console.log('after DOMPurify (ref tail):\n', refTail(sanitized));
    console.groupEnd();
  }
  return sanitized;
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

  if (_citDebug) {
    console.groupCollapsed('%c[CitDebug:Msg] addReferenceAnchors', 'color:#1a73e8;font-weight:bold');
    console.log('props.sources count:', props.sources?.length ?? 0);
    console.log('headings found:', headings.map(h => `${h.tagName}: "${h.textContent?.trim()}"`));
  }

  // Seed refMap from structured backend sources (authoritative, index-based).
  // The backend assigns citation numbers sequentially (1-based), matching [N] in content.
  if (props.sources?.length) {
    for (let i = 0; i < props.sources.length; i++) {
      const src = props.sources[i];
      try {
        const domain = new URL(src.url).hostname.replace(/^www\./, '');
        const title = (src.title || domain).slice(0, 80);
        refMap.set(String(i + 1), { title, domain, url: src.url });
      } catch {
        if (_citDebug) console.warn(`  source[${i}] malformed URL:`, src.url);
      }
    }
    if (_citDebug) console.log('refMap after sources seed:', Object.fromEntries(refMap));
  }

  // Helper: find the first anchor inside an element whose raw href is external
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

      // Bracket-style: "[N] [Title](URL)" rendered as a <p>.
      // Match ALL bracket refs in the element (multiple may land in one <p> via <br>).
      if (sibling.tagName === 'P' || sibling.tagName === 'DIV') {
        const text = sibling.textContent?.trimStart() ?? '';
        const bracketMatches = [...text.matchAll(/\[(\d{1,3})\]/g)];
        if (bracketMatches.length > 0) {
          sibling.setAttribute('id', `ref-${bracketMatches[0][1]}`);
          for (const bm of bracketMatches) {
            const num = bm[1];
            extractRefMeta(sibling, num);
            nextNum = Math.max(nextNum, parseInt(num, 10) + 1);
          }
        }
      }

      sibling = sibling.nextElementSibling;
    }
  }

  // Fallback: scan for bold-text reference headers (e.g., "**Sources:**" or "**References:**").
  // In chat messages, the LLM often uses bold text instead of proper markdown headings.
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
          const bracketMatches = [...text.matchAll(/\[(\d{1,3})\]/g)];
          if (bracketMatches.length > 0) {
            sibling.setAttribute('id', `ref-${bracketMatches[0][1]}`);
            for (const bm of bracketMatches) {
              const num = bm[1];
              extractRefMeta(sibling, num);
              nextNum = Math.max(nextNum, parseInt(num, 10) + 1);
            }
          }
        }

        sibling = sibling.nextElementSibling;
      }
      break; // Only process the first bold reference header
    }
  }

  // Stamp data attributes onto inline citation badge anchors for popup card.
  // Also strip Link extension attributes/classes — citation badges have their own styling.
  const badges = Array.from(proseMirror.querySelectorAll('a[href^="#ref-"]'));
  const unresolvedBadges: string[] = [];
  badges.forEach((badge) => {
    const el = badge as HTMLAnchorElement;
    el.removeAttribute('target');
    el.removeAttribute('rel');
    // Strip TipTap Link extension classes — citation badges have their own styling
    el.classList.remove('message-link', 'hover:underline', 'cursor-pointer');
    const raw = el.getAttribute('href');
    const num = raw?.replace('#ref-', '');
    if (num && refMap.has(num)) {
      const { title, domain, url } = refMap.get(num)!;
      el.dataset.title = title;
      el.dataset.domain = domain;
      el.dataset.url = url;
      el.dataset.citResolved = 'true';
      if (_citDebug) el.removeAttribute('data-cit-unresolved');
    } else {
      el.dataset.citResolved = 'false';
      if (_citDebug) {
        el.dataset.citUnresolved = 'true';
        if (num) unresolvedBadges.push(num);
      }
    }
  });

  if (_citDebug) {
    console.log('refMap final:', Object.fromEntries(refMap));
    console.log(`badges: ${badges.length} total, ${unresolvedBadges.length} unresolved:`, unresolvedBadges);
    const refEls = Array.from(proseMirror.querySelectorAll('[id^="ref-"]'));
    console.log('DOM ref-N elements:', refEls.map(el => `${el.id} (${el.tagName})`));
    console.groupEnd();
  }
};

// ── GitHub-style alert blockquote enhancement ──────────────────────────────
// Converts blockquotes starting with [!NOTE], [!TIP], [!IMPORTANT], [!WARNING], [!CAUTION]
// into styled alert cards with icons and color-coded classes.
const ALERT_TYPES: Record<string, { icon: string; label: string }> = {
  NOTE: { icon: 'ℹ️', label: 'Note' },
  TIP: { icon: '💡', label: 'Tip' },
  IMPORTANT: { icon: '❗', label: 'Important' },
  WARNING: { icon: '⚠️', label: 'Warning' },
  CAUTION: { icon: '🔴', label: 'Caution' },
};

/** Build a styled alert header element from alert metadata (safe — only static trusted strings). */
const _buildAlertHeader = (alertMeta: { icon: string; label: string }): HTMLDivElement => {
  const header = document.createElement('div');
  header.className = 'gh-alert-header';
  const iconSpan = document.createElement('span');
  iconSpan.className = 'gh-alert-icon';
  iconSpan.textContent = alertMeta.icon;
  header.appendChild(iconSpan);
  header.appendChild(document.createTextNode(alertMeta.label));
  return header;
};

const enhanceAlertBlockquotes = () => {
  const proseMirror = contentRef.value?.querySelector('.ProseMirror');
  if (!proseMirror) return;

  const blockquotes = Array.from(proseMirror.querySelectorAll('blockquote'));
  for (const bq of blockquotes) {
    if (bq.classList.contains('gh-alert')) continue; // Already processed

    const firstP = bq.querySelector('p');
    if (!firstP) continue;

    const text = firstP.textContent?.trim() ?? '';

    // Strategy 1: GitHub-flavored [!TYPE] syntax (e.g., "> [!WARNING]\n> content")
    const gfmMatch = text.match(/^\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]\s*/i);
    if (gfmMatch) {
      const type = gfmMatch[1].toUpperCase();
      const alertMeta = ALERT_TYPES[type];
      if (!alertMeta) continue;

      bq.classList.add('gh-alert', `gh-alert-${type.toLowerCase()}`);

      // Remove the [!TYPE] marker from the first paragraph text
      firstP.innerHTML = firstP.innerHTML.replace(/\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]\s*/i, '');
      if (!firstP.textContent?.trim()) {
        firstP.remove();
      }

      bq.insertBefore(_buildAlertHeader(alertMeta), bq.firstChild);
      continue;
    }

    // Strategy 2: Bold-label blockquotes from LLM output (e.g., "> **Note:** content")
    const boldLabel = firstP.querySelector('strong');
    if (boldLabel) {
      const labelText = boldLabel.textContent?.trim().replace(/:$/, '').toUpperCase() ?? '';
      const alertMeta = ALERT_TYPES[labelText];
      if (alertMeta) {
        bq.classList.add('gh-alert', `gh-alert-${labelText.toLowerCase()}`);

        // Remove the bold label and any trailing colon/space from the paragraph
        boldLabel.remove();
        firstP.innerHTML = firstP.innerHTML.replace(/^[\s:]+/, '');
        if (!firstP.textContent?.trim()) {
          firstP.remove();
        }

        bq.insertBefore(_buildAlertHeader(alertMeta), bq.firstChild);
      }
    }
  }
};

const postRenderEnhance = () => {
  addReferenceAnchors();
  enhanceAlertBlockquotes();
};

const editor = useEditor({
  content: htmlContent.value,
  editable: false,
  extensions: [
    // MermaidBlock must come before CodeBlockLowlight so its parseHTML rule
    // takes precedence for `language-mermaid` code fences.
    MermaidBlock,
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
    Table.configure({
      resizable: false,
      HTMLAttributes: { class: 'tiptap-table' },
    }),
    TableRow,
    TableHeader,
    TableCell,
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
  onCreate: () => { nextTick(postRenderEnhance); },
  onUpdate: () => { nextTick(postRenderEnhance); },
});

watch(
  () => props.content,
  () => {
    if (editor.value && htmlContent.value !== editor.value.getHTML()) {
      // emitUpdate: false avoids infinite loops, but onUpdate won't fire —
      // so re-run enhancements manually after the DOM settles.
      editor.value.commands.setContent(htmlContent.value, { emitUpdate: false });
      nextTick(postRenderEnhance);
    }
  }
);

// Re-run anchoring when structured sources arrive (may come after content)
watch(() => props.sources, () => {
  nextTick(postRenderEnhance);
}, { deep: true });

// ── Citation popup card handlers ───────────────────────────────────────────
const openCitCardUrl = () => { if (citCard.url) window.open(citCard.url, '_blank', 'noopener,noreferrer'); };
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

  const rawHref = (badge as HTMLAnchorElement).getAttribute?.('href') ?? '';
  const num = rawHref.replace('#ref-', '');

  // Fallback 1: resolve from props.sources — also runs when url is missing.
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

  // Fallback 2: DOM scraping — runs when url is still missing.
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

  if (!title && !domain) {
    if (_citDebug) {
      console.warn(`[CitDebug:Msg] hover on [${num}] — ALL resolution failed`, {
        'data-attrs': { title: badge.dataset.title, domain: badge.dataset.domain, url: badge.dataset.url },
        'sources[idx]': props.sources?.[parseInt(num, 10) - 1] ?? 'N/A',
        'DOM #ref-N': !!contentRef.value?.querySelector(`.ProseMirror #ref-${num}`),
      });
    }
    return;
  }

  keepCard();
  const rect = badge.getBoundingClientRect();
  citCard.title = title;
  citCard.domain = domain;
  citCard.faviconUrl = domain && !_failedFaviconDomains.has(domain)
    ? (getFaviconUrl(`https://${domain}`) ?? '')
    : '';
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
  const externalUrl = anchor.dataset.url;
  if (externalUrl) {
    window.open(externalUrl, '_blank', 'noopener,noreferrer');
    return;
  }
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

/* ── Links — matching report modal blue (exclude citation badges) ── */
:deep(.tiptap a:not([href^="#ref-"])),
:deep(.message-link:not([href^="#ref-"])) {
  color: #1a73e8;
  text-decoration: none;
  transition: color 0.15s ease, text-decoration-color 0.15s ease;
}

:deep(.tiptap a:not([href^="#ref-"]):hover),
:deep(.message-link:not([href^="#ref-"]):hover) {
  text-decoration: underline;
  text-decoration-color: rgba(26, 115, 232, 0.5);
}

:global(.dark) :deep(.tiptap a:not([href^="#ref-"])),
:global(.dark) :deep(.message-link:not([href^="#ref-"])) {
  color: #7cb3e0;
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

/* ── GitHub-style alert callouts ─────────────────── */
:deep(.tiptap blockquote.gh-alert) {
  font-style: normal;
  padding: 0.875rem 1rem 0.875rem 1rem;
  margin: 1rem 0;
  border-radius: 8px;
  border-left-width: 4px;
}

:deep(.tiptap blockquote.gh-alert .gh-alert-header) {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 700;
  font-size: 0.85em;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  margin-bottom: 6px;
}

:deep(.tiptap blockquote.gh-alert .gh-alert-icon) {
  font-size: 1em;
  line-height: 1;
}

:deep(.tiptap blockquote.gh-alert p) {
  color: var(--text-primary);
  font-size: 0.925em;
  line-height: 1.6;
}

:deep(.tiptap blockquote.gh-alert-note) {
  border-left-color: #3b82f6;
  background: rgba(59, 130, 246, 0.06);
}
:deep(.tiptap blockquote.gh-alert-note .gh-alert-header) {
  color: #3b82f6;
}

:deep(.tiptap blockquote.gh-alert-tip) {
  border-left-color: #10b981;
  background: rgba(16, 185, 129, 0.06);
}
:deep(.tiptap blockquote.gh-alert-tip .gh-alert-header) {
  color: #10b981;
}

:deep(.tiptap blockquote.gh-alert-important) {
  border-left-color: #8b5cf6;
  background: rgba(139, 92, 246, 0.06);
}
:deep(.tiptap blockquote.gh-alert-important .gh-alert-header) {
  color: #8b5cf6;
}

:deep(.tiptap blockquote.gh-alert-warning) {
  border-left-color: #f59e0b;
  background: rgba(245, 158, 11, 0.06);
}
:deep(.tiptap blockquote.gh-alert-warning .gh-alert-header) {
  color: #f59e0b;
}

:deep(.tiptap blockquote.gh-alert-caution) {
  border-left-color: #ef4444;
  background: rgba(239, 68, 68, 0.06);
}
:deep(.tiptap blockquote.gh-alert-caution .gh-alert-header) {
  color: #ef4444;
}

/* Dark mode alert callout backgrounds */
:global(.dark) :deep(.tiptap blockquote.gh-alert-note) { background: rgba(59, 130, 246, 0.1); }
:global(.dark) :deep(.tiptap blockquote.gh-alert-tip) { background: rgba(16, 185, 129, 0.1); }
:global(.dark) :deep(.tiptap blockquote.gh-alert-important) { background: rgba(139, 92, 246, 0.1); }
:global(.dark) :deep(.tiptap blockquote.gh-alert-warning) { background: rgba(245, 158, 11, 0.1); }
:global(.dark) :deep(.tiptap blockquote.gh-alert-caution) { background: rgba(239, 68, 68, 0.1); }

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

/* ── Tables — premium styling ────────────────────── */
:deep(.tiptap table) {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
  margin: 1.25rem 0;
  font-size: 0.9em;
  table-layout: auto;
  overflow: hidden;
  display: table;
  border-radius: 10px;
  border: 1px solid var(--border-main);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
}

:deep(.tiptap th) {
  background: linear-gradient(180deg, var(--fill-tsp-gray-main) 0%, rgba(0, 0, 0, 0.025) 100%);
  border-bottom: 2px solid var(--border-main);
  border-right: 1px solid var(--border-light);
  padding: 0.7rem 0.85rem;
  text-align: left;
  font-weight: 700;
  font-size: 0.8em;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text-secondary);
}

:deep(.tiptap th:last-child) {
  border-right: none;
}

:deep(.tiptap td) {
  border-bottom: 1px solid var(--border-light);
  border-right: 1px solid var(--border-light);
  padding: 0.65rem 0.85rem;
  vertical-align: top;
  color: var(--text-primary);
  transition: background-color 0.1s ease;
}

:deep(.tiptap td:last-child) {
  border-right: none;
}

:deep(.tiptap tr:last-child td) {
  border-bottom: none;
}

:deep(.tiptap tbody tr:nth-child(even) td) {
  background-color: rgba(0, 0, 0, 0.015);
}

:deep(.tiptap tbody tr:hover td) {
  background-color: rgba(26, 115, 232, 0.04);
}

:deep(.tiptap th p),
:deep(.tiptap td p) {
  margin: 0;
}

:global(.dark) :deep(.tiptap table) {
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.15);
}

:global(.dark) :deep(.tiptap th) {
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.06) 0%, rgba(255, 255, 255, 0.02) 100%);
}

:global(.dark) :deep(.tiptap tbody tr:nth-child(even) td) {
  background-color: rgba(255, 255, 255, 0.02);
}

:global(.dark) :deep(.tiptap tbody tr:hover td) {
  background-color: rgba(124, 179, 224, 0.06);
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

:global(.dark) :deep(.ref-list-anchor:hover) {
  text-decoration-color: #7cb3e0;
  color: #7cb3e0;
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

/* Dark mode badge styles live in the unscoped <style> block below
   to avoid Vue scoped CSS compilation issues with :global() + :deep() */
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
.dark .msg-cit-card {
  background: #222222;
  border-color: rgba(255, 255, 255, 0.09);
  box-shadow:
    0 0 0 1px rgba(255, 255, 255, 0.04),
    0 4px 6px rgba(0, 0, 0, 0.2),
    0 12px 28px rgba(0, 0, 0, 0.4);
}

.dark .msg-cit-card-title {
  color: #f0f0f0;
}

.dark .msg-cit-card-domain {
  color: rgba(240, 240, 240, 0.45);
}

.dark .msg-cit-card-arrow {
  color: rgba(240, 240, 240, 0.35);
}

/* ── Dark mode: inline citation badges ─────────────────────────────────
   Uses .tiptap-message-viewer class for specificity (beats scoped [data-v] attrs).
   Placed here (unscoped) because :global(.dark) :deep() in <style scoped> can be
   unreliable across Vue SFC compiler versions. */
.dark .tiptap-message-viewer a[href^="#ref-"] {
  background: transparent;
  border-color: rgba(255, 255, 255, 0.22);
  color: rgba(255, 255, 255, 0.5);
  text-decoration: none !important;
}

.dark .tiptap-message-viewer a[href^="#ref-"]:hover {
  background: #e5e5e7;
  border-color: #e5e5e7;
  color: #1c1c1e;
  text-decoration: none !important;
}

/* ── Debug: highlight unresolved citation badges ────────────────────── */
.tiptap-message-viewer a[data-cit-unresolved="true"] {
  border-color: #e53e3e !important;
  color: #e53e3e !important;
  position: relative;
}
.tiptap-message-viewer a[data-cit-unresolved="true"]::after {
  content: '?';
  position: absolute;
  top: -7px;
  right: -6px;
  width: 10px;
  height: 10px;
  background: #e53e3e;
  color: white;
  border-radius: 50%;
  font-size: 7px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  line-height: 1;
}
</style>
