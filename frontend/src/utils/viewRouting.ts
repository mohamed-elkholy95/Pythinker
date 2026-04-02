import type { ToolContent } from '@/types/message';
import type { ContentViewType } from '@/constants/tool';
import type { StreamingContentType } from '@/types/streaming';

const IMAGE_EXTENSION_RE =
  /\.(png|jpe?g|gif|bmp|webp|svg|ico|tiff?|heic|heif)(?:$|[?#])/i;

const CHART_FUNCTIONS = new Set([
  'code_generate_chart',
  'chart_create',
  'slides_add_chart',
]);

function normalize(value: unknown): string {
  if (typeof value !== 'string') return '';
  return value.trim().toLowerCase();
}

function hasImageExtension(value: string): boolean {
  return IMAGE_EXTENSION_RE.test(value);
}

function extractResourceStrings(tool?: Partial<ToolContent>): string[] {
  if (!tool?.args) return [];

  const candidateKeys = [
    'file',
    'path',
    'filename',
    'src',
    'url',
    'image',
    'image_url',
    'image_path',
  ];

  const values: string[] = [];
  for (const key of candidateKeys) {
    const raw = tool.args[key];
    if (typeof raw === 'string' && raw.trim()) {
      values.push(raw.trim());
    }
  }
  return values;
}

export function isChartDomainTool(tool?: Partial<ToolContent>): boolean {
  const name = normalize(tool?.name);
  const fn = normalize(tool?.function);

  if (name === 'chart') return true;
  if (fn.startsWith('chart_')) return true;
  if (CHART_FUNCTIONS.has(fn)) return true;
  return fn.includes('chart');
}

export function isCanvasDomainTool(tool?: Partial<ToolContent>): boolean {
  const name = normalize(tool?.name);
  const fn = normalize(tool?.function);

  if (name === 'canvas') return true;
  if (fn.startsWith('canvas_')) return true;
  if (isChartDomainTool(tool)) return true;

  if (name.includes('design') || fn.includes('design')) return true;
  if (name.includes('image')) return true;
  if (fn.includes('image') && (name === 'canvas' || fn.includes('canvas'))) return true;

  if (name === 'file') {
    return extractResourceStrings(tool).some(hasImageExtension);
  }

  return false;
}

export function isLiveDomainTool(tool?: Partial<ToolContent>): boolean {
  const name = normalize(tool?.name);
  const fn = normalize(tool?.function);

  if (name.startsWith('browser') || name === 'playwright') return true;
  if (name === 'search' || name === 'web_search' || fn.includes('search')) return true;
  if (name === 'shell' || name === 'terminal' || fn.startsWith('terminal_') || name === 'code_executor' || name === 'code_execute') return true;
  if (name === 'file' || fn.startsWith('file_')) return true;

  return false;
}

export function shouldShowUnifiedStreamingView(params: {
  isLive: boolean;
  currentViewType?: ContentViewType | null;
  streamingContent?: string;
  contentType: StreamingContentType;
  summaryPhase?: boolean;
  summaryStreamText?: string;
}): boolean {
  if (!params.isLive || !params.streamingContent) return false;
  if (params.summaryPhase || params.summaryStreamText) return false;
  if (params.contentType === 'search') return false;
  // Terminal-classified streams (shell/exec) belong in the xterm panel, not the generic streamer.
  if (params.contentType === 'terminal') return false;
  if (params.currentViewType === 'terminal') return false;
  return true;
}
