import type { FileInfo } from '@/api/file';

type ConsumeComposerDraftOptions = {
  message: string;
  attachments: FileInfo[];
  setMessage: (value: string) => void;
  setAttachments: (value: FileInfo[]) => void;
};

type ConsumedComposerDraft = {
  message: string;
  attachments: FileInfo[];
  restore: () => void;
};

export const consumeComposerDraft = ({
  message,
  attachments,
  setMessage,
  setAttachments,
}: ConsumeComposerDraftOptions): ConsumedComposerDraft => {
  const snapshot = {
    message,
    attachments: [...attachments],
  };

  setMessage('');
  setAttachments([]);

  return {
    ...snapshot,
    restore: () => {
      setMessage(snapshot.message);
      setAttachments([...snapshot.attachments]);
    },
  };
};
