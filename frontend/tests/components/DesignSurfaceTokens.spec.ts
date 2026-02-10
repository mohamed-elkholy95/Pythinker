import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const SURFACE_FILES = [
  'src/pages/SessionHistoryPage.vue',
  'src/components/SandboxViewer.vue',
  'src/components/SessionReplayPlayer.vue',
  'src/components/ReplayTimeline.vue',
  'src/components/SessionFileList.vue',
];

const HARD_CODED_COLOR_LITERAL_PATTERN = /#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(/;
const HARD_CODED_TAILWIND_COLOR_CLASS_PATTERN =
  /(?<!--)\b(?:text|bg|border)-(?:white|black|red|blue|green|yellow|orange|purple|gray|slate|zinc|neutral|stone)(?:-\d{2,3})?\b/;

describe('design surface token usage', () => {
  it('uses semantic design tokens instead of hard-coded colors on standardized surfaces', () => {
    for (const file of SURFACE_FILES) {
      const content = readFileSync(resolve(file), 'utf-8');
      expect(HARD_CODED_COLOR_LITERAL_PATTERN.test(content)).toBe(false);
      expect(HARD_CODED_TAILWIND_COLOR_CLASS_PATTERN.test(content)).toBe(false);
    }
  });
});
