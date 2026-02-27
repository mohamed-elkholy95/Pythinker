import { Node, mergeAttributes } from '@tiptap/core';
import { VueNodeViewRenderer } from '@tiptap/vue-3';
import type { Component } from 'vue';
import MermaidChartView from './MermaidChartView.vue';

const MERMAID_LANGUAGES = new Set(['mermaid']);

/**
 * Custom TipTap node for Mermaid diagrams.
 *
 * Activated by fenced code blocks with language `mermaid`:
 *
 *   ```mermaid
 *   graph LR
 *     A --> B --> C
 *   ```
 *
 * The node is `atom: true` (no editable content) and is parsed BEFORE
 * CodeBlockLowlight so its parseHTML rule takes precedence for matching languages.
 */
export const MermaidBlock = Node.create({
    name: 'mermaidBlock',
    group: 'block',
    atom: true,

    addAttributes() {
        return {
            language: { default: 'mermaid' },
            chartCode: { default: '' },
        };
    },

    parseHTML() {
        return [
            {
                tag: 'pre',
                preserveWhitespace: 'full',
                getAttrs: (element) => {
                    const el = element as HTMLElement;
                    const code = el.querySelector('code');
                    if (!code) return false;

                    const langClass = Array.from(code.classList).find((c) => c.startsWith('language-'));
                    const lang = langClass?.slice('language-'.length) ?? '';
                    if (!MERMAID_LANGUAGES.has(lang)) return false;

                    return { language: lang, chartCode: code.textContent ?? '' };
                },
            },
        ];
    },

    renderHTML({ node, HTMLAttributes }) {
        return [
            'pre',
            mergeAttributes(HTMLAttributes, { 'data-mermaid-chart': '' }),
            ['code', { class: `language-${node.attrs.language as string}` }, node.attrs.chartCode as string],
        ];
    },

    addNodeView() {
        return VueNodeViewRenderer(MermaidChartView as unknown as Component);
    },
});
