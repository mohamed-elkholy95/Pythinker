import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import type { ReportData } from '@/components/report/types';
import ReportModal from '@/components/report/ReportModal.vue';

const { downloadSessionReportPdfMock, saveAsMock } = vi.hoisted(() => {
  return {
    downloadSessionReportPdfMock: vi.fn(),
    saveAsMock: vi.fn(),
  };
});

vi.mock('@/api/agent', () => ({
  downloadSessionReportPdf: downloadSessionReportPdfMock,
}));

vi.mock('file-saver', () => ({
  saveAs: saveAsMock,
}));

const reportFixture: ReportData = {
  id: 'report-1',
  title: 'Reliability Report',
  content: '# Reliability Report\n\n## Findings\n\n- Item one',
  author: 'Pythinker',
  lastModified: Date.now(),
  sections: [],
};

const mountReportModal = () =>
  mount(ReportModal, {
    props: {
      open: true,
      report: reportFixture,
      sessionId: 'session-1',
      showToc: true,
    },
    global: {
      stubs: {
        Dialog: { template: '<div><slot /></div>' },
        DialogContent: { template: '<div><slot /></div>' },
        Popover: { template: '<div><slot /></div>' },
        PopoverTrigger: { template: '<div><slot /></div>' },
        PopoverContent: { template: '<div><slot /></div>' },
        TiptapReportEditor: { template: '<div class="ProseMirror"><h2>Findings</h2></div>' },
      },
    },
  });

const findButtonByText = (wrapper: ReturnType<typeof mount>, text: string) => {
  const button = wrapper.findAll('button').find(candidate => candidate.text().includes(text));
  expect(button).toBeTruthy();
  return button!;
};

describe('ReportModal download isolation', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    downloadSessionReportPdfMock.mockResolvedValue({
      blob: new Blob(['%PDF-1.4'], { type: 'application/pdf' }),
      filename: 'reliability-report.pdf',
    });
  });

  it('does not allow markdown export while PDF export is in progress', async () => {
    let resolvePdf: ((value: { blob: Blob; filename: string }) => void) | null = null;
    downloadSessionReportPdfMock.mockImplementation(
      () => new Promise<{ blob: Blob; filename: string }>(resolve => {
        resolvePdf = resolve;
      }),
    );

    const wrapper = mountReportModal();
    const pdfButton = findButtonByText(wrapper, 'PDF Document');
    const markdownButton = findButtonByText(wrapper, 'Markdown (.md)');

    await pdfButton.trigger('click');
    await markdownButton.trigger('click');

    expect(saveAsMock).not.toHaveBeenCalled();

    resolvePdf?.({ blob: new Blob(['%PDF-1.4'], { type: 'application/pdf' }), filename: 'report.pdf' });
    await flushPromises();
  });

  it('prevents duplicate PDF exports from repeated clicks while one is running', async () => {
    let resolvePdf: ((value: { blob: Blob; filename: string }) => void) | null = null;
    downloadSessionReportPdfMock.mockImplementation(
      () => new Promise<{ blob: Blob; filename: string }>(resolve => {
        resolvePdf = resolve;
      }),
    );

    const wrapper = mountReportModal();
    const pdfButton = findButtonByText(wrapper, 'PDF Document');

    await pdfButton.trigger('click');
    await pdfButton.trigger('click');

    expect(downloadSessionReportPdfMock).toHaveBeenCalledTimes(1);

    resolvePdf?.({ blob: new Blob(['%PDF-1.4'], { type: 'application/pdf' }), filename: 'report.pdf' });
    await flushPromises();
  });

  it('debounces repeated markdown export clicks into a single file write', async () => {
    const wrapper = mountReportModal();
    const markdownButton = findButtonByText(wrapper, 'Markdown (.md)');

    await markdownButton.trigger('click');
    await markdownButton.trigger('click');

    expect(saveAsMock).toHaveBeenCalledTimes(1);
  });
});
