import { Node, mergeAttributes } from '@tiptap/core';
import { VueNodeViewRenderer } from '@tiptap/vue-3';
import type { Component } from 'vue';
import PlotlyChartView from './PlotlyChartView.vue';

const CHART_LANGUAGES = new Set(['chart', 'plotly']);

/**
 * Custom TipTap node for interactive Plotly charts.
 *
 * Activated by fenced code blocks with language `chart` or `plotly`:
 *
 *   ```chart
 *   {"data": [{"type": "bar", "x": ["A","B"], "y": [1,2]}], "layout": {"title": "My Chart"}}
 *   ```
 *
 * The node is `atom: true` (no editable content) and is parsed BEFORE
 * CodeBlockLowlight so its parseHTML rule takes precedence for matching languages.
 */
export const PlotlyChartBlock = Node.create({
  name: 'plotlyChartBlock',
  group: 'block',
  atom: true,

  addAttributes() {
    return {
      language: { default: 'chart' },
      chartData: { default: '' },
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
          if (!CHART_LANGUAGES.has(lang)) return false;

          return { language: lang, chartData: code.textContent ?? '' };
        },
      },
    ];
  },

  renderHTML({ node, HTMLAttributes }) {
    return [
      'pre',
      mergeAttributes(HTMLAttributes, { 'data-plotly-chart': '' }),
      ['code', { class: `language-${node.attrs.language as string}` }, node.attrs.chartData as string],
    ];
  },

  addNodeView() {
    // Cast needed: Vue's DefineComponent inference doesn't satisfy Component<NodeViewProps>
    // but the runtime behaviour is correct — VueNodeViewRenderer injects the right props.
    return VueNodeViewRenderer(PlotlyChartView as unknown as Component);
  },
});
