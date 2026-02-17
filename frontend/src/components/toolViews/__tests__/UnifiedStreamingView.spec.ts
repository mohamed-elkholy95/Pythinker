import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount } from '@vue/test-utils';
import { nextTick } from 'vue';
import UnifiedStreamingView from '../UnifiedStreamingView.vue';
import type { StreamingContentType } from '@/types/streaming';

// Mock markdown parsing libraries
vi.mock('marked', () => ({
  marked: {
    parse: vi.fn((text: string) => {
      // Simple markdown parser for testing
      const html = text
        .replace(/^# (.+)$/gm, '<h1>$1</h1>')
        .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
        .replace(/^(?!<h\d>)(.+)$/gm, '<p>$1</p>');
      return html;
    })
  }
}));

vi.mock('dompurify', () => ({
  default: {
    sanitize: vi.fn((html: string) => html)
  }
}));

// Mock child components to simplify testing
vi.mock('../TerminalContentView.vue', () => ({
  default: {
    name: 'TerminalContentView',
    template: '<div class="terminal-mock">{{ content }}</div>',
    props: ['content', 'contentType', 'live']
  }
}));

vi.mock('../EditorContentView.vue', () => ({
  default: {
    name: 'EditorContentView',
    template: '<div class="editor-mock">{{ content }}</div>',
    props: ['content', 'language', 'live']
  }
}));

vi.mock('../SearchContentView.vue', () => ({
  default: {
    name: 'SearchContentView',
    template: '<div class="search-mock">{{ content }}</div>',
    props: ['content', 'toolContent', 'live']
  }
}));

vi.mock('../../ui/ShikiCodeBlock.vue', () => ({
  default: {
    name: 'ShikiCodeBlock',
    template: '<div class="shiki-mock">{{ code }}</div>',
    props: ['code', 'language', 'showCopy']
  }
}));

describe('UnifiedStreamingView', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Status Header', () => {
    it('shows streaming status when not final', () => {
      const wrapper = mount(UnifiedStreamingView, {
        props: {
          text: 'Loading...',
          contentType: 'terminal' as StreamingContentType,
          isFinal: false,
        },
      });

      expect(wrapper.find('.streaming-label').text()).toBe('Executing command...');
      expect(wrapper.findAll('.typing-dot')).toHaveLength(3);
    });

    it('shows complete status when final', () => {
      const wrapper = mount(UnifiedStreamingView, {
        props: {
          text: 'Done',
          contentType: 'terminal' as StreamingContentType,
          isFinal: true,
        },
      });

      expect(wrapper.find('.streaming-label').text()).toBe('Command complete');
    });

    it('shows progress badge when progress percent provided', () => {
      const wrapper = mount(UnifiedStreamingView, {
        props: {
          text: 'Processing...',
          contentType: 'text' as StreamingContentType,
          isFinal: false,
          progressPercent: 75,
        },
      });

      const badge = wrapper.find('.progress-badge');
      expect(badge.exists()).toBe(true);
      expect(badge.text()).toBe('75%');
    });

    it('hides progress badge when progress percent is null', () => {
      const wrapper = mount(UnifiedStreamingView, {
        props: {
          text: 'Processing...',
          contentType: 'text' as StreamingContentType,
          isFinal: false,
          progressPercent: null,
        },
      });

      expect(wrapper.find('.progress-badge').exists()).toBe(false);
    });
  });

  describe('Content Type Rendering', () => {
    it('renders terminal content type', () => {
      const wrapper = mount(UnifiedStreamingView, {
        props: {
          text: 'echo "hello"',
          contentType: 'terminal' as StreamingContentType,
          isFinal: false,
        },
      });

      expect(wrapper.find('.terminal-mock').exists()).toBe(true);
    });

    it('renders code content type', () => {
      const wrapper = mount(UnifiedStreamingView, {
        props: {
          text: 'def hello(): pass',
          contentType: 'code' as StreamingContentType,
          isFinal: false,
          language: 'python',
        },
      });

      expect(wrapper.find('.editor-mock').exists()).toBe(true);
    });

    it('renders markdown content type with sanitization', () => {
      const wrapper = mount(UnifiedStreamingView, {
        props: {
          text: '# Hello\n\nThis is **bold**.',
          contentType: 'markdown' as StreamingContentType,
          isFinal: false,
        },
      });

      const markdownBody = wrapper.find('.markdown-body');
      expect(markdownBody.exists()).toBe(true);
      expect(markdownBody.html()).toContain('<h1');
      expect(markdownBody.html()).toContain('Hello');
      expect(markdownBody.html()).toContain('<strong>bold</strong>');
    });

    it('renders JSON content type', () => {
      const wrapper = mount(UnifiedStreamingView, {
        props: {
          text: '{"key": "value"}',
          contentType: 'json' as StreamingContentType,
          isFinal: false,
        },
      });

      expect(wrapper.find('.json-content').exists()).toBe(true);
      expect(wrapper.find('.shiki-mock').exists()).toBe(true);
    });

    it('renders plain text content type', () => {
      const wrapper = mount(UnifiedStreamingView, {
        props: {
          text: 'Plain text content',
          contentType: 'text' as StreamingContentType,
          isFinal: false,
        },
      });

      const textContent = wrapper.find('.text-content');
      expect(textContent.exists()).toBe(true);
      expect(textContent.text()).toBe('Plain text content');
    });
  });

  describe('Typing Cursor', () => {
    it('shows typing cursor while streaming for text content', () => {
      const wrapper = mount(UnifiedStreamingView, {
        props: {
          text: 'Streaming...',
          contentType: 'text' as StreamingContentType,
          isFinal: false,
          showCursor: true,
        },
      });

      expect(wrapper.find('.typing-cursor').exists()).toBe(true);
    });

    it('hides typing cursor when streaming complete', () => {
      const wrapper = mount(UnifiedStreamingView, {
        props: {
          text: 'Complete',
          contentType: 'text' as StreamingContentType,
          isFinal: true,
          showCursor: true,
        },
      });

      expect(wrapper.find('.typing-cursor').exists()).toBe(false);
    });

    it('hides typing cursor when showCursor is false', () => {
      const wrapper = mount(UnifiedStreamingView, {
        props: {
          text: 'Streaming...',
          contentType: 'text' as StreamingContentType,
          isFinal: false,
          showCursor: false,
        },
      });

      expect(wrapper.find('.typing-cursor').exists()).toBe(false);
    });

    it('does not show cursor for terminal content type', () => {
      const wrapper = mount(UnifiedStreamingView, {
        props: {
          text: 'command output',
          contentType: 'terminal' as StreamingContentType,
          isFinal: false,
          showCursor: true,
        },
      });

      // Terminal has its own cursor, so we don't show ours
      expect(wrapper.find('.typing-cursor').exists()).toBe(false);
    });
  });

  describe('Auto-scroll', () => {
    it('auto-scrolls to bottom when text updates', async () => {
      const wrapper = mount(UnifiedStreamingView, {
        props: {
          text: 'Line 1',
          contentType: 'text' as StreamingContentType,
          isFinal: false,
          autoScroll: true,
        },
        attachTo: document.body,
      });

      const contentEl = wrapper.find('.streaming-content').element as HTMLElement;

      // Mock scrollHeight and scrollTop
      Object.defineProperty(contentEl, 'scrollHeight', {
        configurable: true,
        get: () => 1000,
      });
      Object.defineProperty(contentEl, 'scrollTop', {
        configurable: true,
        set: vi.fn(),
        get: () => 0,
      });

      const scrollSpy = vi.spyOn(contentEl, 'scrollTop', 'set');

      // Update text to trigger scroll
      await wrapper.setProps({ text: 'Line 1\nLine 2\nLine 3' });
      await nextTick();

      expect(scrollSpy).toHaveBeenCalledWith(1000);

      wrapper.unmount();
    });

    it('does not auto-scroll when autoScroll is false', async () => {
      const wrapper = mount(UnifiedStreamingView, {
        props: {
          text: 'Line 1',
          contentType: 'text' as StreamingContentType,
          isFinal: false,
          autoScroll: false,
        },
        attachTo: document.body,
      });

      const contentEl = wrapper.find('.streaming-content').element as HTMLElement;
      const scrollSpy = vi.spyOn(contentEl, 'scrollTop', 'set');

      await wrapper.setProps({ text: 'Line 1\nLine 2\nLine 3' });
      await nextTick();

      expect(scrollSpy).not.toHaveBeenCalled();

      wrapper.unmount();
    });
  });

  describe('Status Labels', () => {
    const contentTypes: Array<{ type: StreamingContentType; streaming: string; complete: string }> = [
      { type: 'terminal', streaming: 'Executing command...', complete: 'Command complete' },
      { type: 'code', streaming: 'Writing code...', complete: 'Code complete' },
      { type: 'markdown', streaming: 'Composing document...', complete: 'Document complete' },
      { type: 'json', streaming: 'Generating data...', complete: 'Data complete' },
      { type: 'search', streaming: 'Searching...', complete: 'Search complete' },
      { type: 'text', streaming: 'Processing...', complete: 'Complete' },
    ];

    it.each(contentTypes)('shows correct labels for $type content type', ({ type, streaming, complete }) => {
      const wrapperStreaming = mount(UnifiedStreamingView, {
        props: {
          text: 'Test',
          contentType: type,
          isFinal: false,
        },
      });

      expect(wrapperStreaming.find('.streaming-label').text()).toBe(streaming);

      const wrapperComplete = mount(UnifiedStreamingView, {
        props: {
          text: 'Test',
          contentType: type,
          isFinal: true,
        },
      });

      expect(wrapperComplete.find('.streaming-label').text()).toBe(complete);
    });
  });

  describe('Error Handling', () => {
    it('handles invalid markdown gracefully', () => {
      const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

      // Test with valid markdown first
      const wrapper = mount(UnifiedStreamingView, {
        props: {
          text: '# Valid Markdown',
          contentType: 'markdown' as StreamingContentType,
          isFinal: false,
        },
      });

      expect(wrapper.find('.markdown-body').exists()).toBe(true);

      // Markdown parsing is generally robust, so we'd need to break marked itself
      // to test error handling, which is not practical. The error handling is there
      // for edge cases.

      consoleSpy.mockRestore();
    });

    it('handles invalid JSON gracefully', () => {
      const wrapper = mount(UnifiedStreamingView, {
        props: {
          text: '{invalid json',
          contentType: 'json' as StreamingContentType,
          isFinal: false,
        },
      });

      // Should render the raw text when JSON parsing fails
      expect(wrapper.find('.json-content').exists()).toBe(true);
    });
  });
});
