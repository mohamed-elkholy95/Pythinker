import { describe, expect, it } from 'vitest';
import type { FileInfo } from '@/api/file';
import { consumeComposerDraft } from '@/utils/composerDraft';

const makeFile = (overrides: Partial<FileInfo> = {}): FileInfo => ({
  file_id: 'file-1',
  filename: 'notes.txt',
  content_type: 'text/plain',
  size: 42,
  upload_date: '2026-03-31T18:00:00Z',
  ...overrides,
});

describe('consumeComposerDraft', () => {
  it('captures the current draft and clears the live composer state immediately', () => {
    let message = 'create a comprehensive research report about: clean code';
    let attachments: FileInfo[] = [makeFile()];

    const draft = consumeComposerDraft({
      message,
      attachments,
      setMessage: (value) => { message = value; },
      setAttachments: (value) => { attachments = value; },
    });

    expect(draft.message).toBe('create a comprehensive research report about: clean code');
    expect(draft.attachments).toEqual([makeFile()]);
    expect(message).toBe('');
    expect(attachments).toEqual([]);
  });

  it('restores the cleared draft if navigation fails', () => {
    let message = 'draft task';
    let attachments: FileInfo[] = [makeFile(), makeFile({ file_id: 'file-2', filename: 'diagram.png' })];

    const draft = consumeComposerDraft({
      message,
      attachments,
      setMessage: (value) => { message = value; },
      setAttachments: (value) => { attachments = value; },
    });

    draft.restore();

    expect(message).toBe('draft task');
    expect(attachments).toEqual([
      makeFile(),
      makeFile({ file_id: 'file-2', filename: 'diagram.png' }),
    ]);
  });
});
