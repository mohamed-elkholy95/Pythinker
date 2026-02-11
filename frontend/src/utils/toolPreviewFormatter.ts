import type { ToolContent } from '@/types/message';
import type { ConsoleRecord } from '@/types/response';

export interface FormattedToolPreview {
  previewText: string;
  filePath: string;
  searchResults: Array<{ title?: string; name?: string; url?: string; link?: string; snippet?: string }>;
  searchQuery: string;
}

const truncate = (value: string, maxLength: number) => (
  value.length > maxLength ? value.slice(0, maxLength) : value
);

const formatConsoleOutput = (records: ConsoleRecord[], maxLength: number): string => (
  truncate(
    records.map((record: ConsoleRecord) => {
      const prompt = record.ps1 ? `${record.ps1} ` : '$ ';
      const command = record.command || '';
      const output = record.output || '';
      return `${prompt}${command}\n${output}`;
    }).join('\n'),
    maxLength
  )
);

const formatShellLikePreview = (toolContent: ToolContent, maxLength: number): string => {
  const command = String(toolContent.args?.command || toolContent.command || '');
  const stdout = String(toolContent.stdout || toolContent.content?.stdout || '');
  const stderr = String(toolContent.stderr || toolContent.content?.stderr || '');
  const consoleOutput = toolContent.content?.console;

  if (Array.isArray(consoleOutput)) {
    return formatConsoleOutput(consoleOutput as ConsoleRecord[], maxLength);
  }

  let output = '';
  if (command) output += `$ ${command}\n`;
  if (stdout) output += stdout;
  if (stderr) output += `\n[stderr]\n${stderr}`;

  if (output.trim()) return truncate(output, maxLength);
  if (command) return truncate(`$ ${command}`, maxLength);
  if (typeof consoleOutput === 'string') return truncate(consoleOutput, maxLength);

  return '';
};

const formatFileLikePreview = (toolContent: ToolContent, maxLength: number): string => {
  const argContent = toolContent.args?.content;
  if (typeof argContent === 'string' && argContent.length > 0) {
    return truncate(argContent, maxLength);
  }

  const contentPayload = toolContent.content?.content;
  if (typeof contentPayload === 'string' && contentPayload.length > 0) {
    return truncate(contentPayload, maxLength);
  }

  if (toolContent.stdout) {
    return truncate(String(toolContent.stdout), maxLength);
  }

  return '';
};

export const extractToolPreview = (
  toolContent?: ToolContent | null,
  maxLength = 500
): FormattedToolPreview => {
  if (!toolContent) {
    return {
      previewText: '',
      filePath: '',
      searchResults: [],
      searchQuery: ''
    };
  }

  const toolName = toolContent.name || '';
  const toolFunc = toolContent.function || '';
  const isShellOrCode = toolName.includes('shell')
    || toolName.includes('code')
    || toolFunc.includes('shell')
    || toolFunc.includes('code');

  const previewText = isShellOrCode
    ? formatShellLikePreview(toolContent, maxLength)
    : formatFileLikePreview(toolContent, maxLength);

  const filePath = String(
    toolContent.args?.file
      || toolContent.file_path
      || toolContent.args?.filename
      || ''
  );

  const searchResults = (toolContent.content?.results || []) as Array<{
    title?: string;
    name?: string;
    url?: string;
    link?: string;
    snippet?: string;
  }>;
  const searchQuery = String(toolContent.args?.query || '');

  return {
    previewText,
    filePath,
    searchResults,
    searchQuery
  };
};
