import { describe, expect, it } from 'vitest';

import {
  collapseDuplicateReportBlocks,
  prepareMarkdownForViewer,
  preparePlainTextForViewer,
  stripLegacyPreviouslyCalledMarkers,
} from '../reportContentNormalizer';
import { createReportFromMarkdown } from '../../../composables/useReport';

describe('reportContentNormalizer', () => {
  it('strips legacy previously-called markers without changing surrounding content', () => {
    const text = '# Report\n\n[Previously called retrieve_result]\n\nBody text.';

    expect(stripLegacyPreviouslyCalledMarkers(text)).toBe('# Report\n\nBody text.');
  });

  it('removes legacy markers before building report data', () => {
    const report = createReportFromMarkdown(
      'report-1',
      '# Report\n\n[Previously called retrieve_result]\n\n## Overview\n\nBody text.',
    );

    expect(report.content).not.toContain('[Previously called retrieve_result]');
    expect(report.title).toBe('Report');
    expect(report.sections).toEqual([
      {
        title: 'Overview',
        preview: 'Body text.',
        level: 2,
      },
    ]);
  });

  it('removes legacy markers from markdown viewer content', () => {
    const viewer = prepareMarkdownForViewer(
      '# Report\n\n[Previously called retrieve_result]\n\n## Overview\n\nBody text.',
    );

    expect(viewer).not.toContain('[Previously called retrieve_result]');
    expect(viewer).toContain('Body text.');
    expect(collapseDuplicateReportBlocks(viewer)).toBe(viewer);
  });

  it('removes legacy markers from plain text viewer content', () => {
    const viewer = preparePlainTextForViewer('[Previously called retrieve_result]\nBody text.');

    expect(viewer).not.toContain('[Previously called retrieve_result]');
    expect(viewer).toContain('Body text.');
    expect(viewer).toContain('```text');
  });
});
