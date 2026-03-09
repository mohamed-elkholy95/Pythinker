import { defineAsyncComponent, type Component } from 'vue';
import { useI18n } from 'vue-i18n';
import {
  FileText,
  FileCode,
  FileSpreadsheet,
  FileImage,
  FileVideo,
  FileAudio,
  FileArchive,
  File,
  FileJson,
  FileBarChart,
  Link as LinkIcon,
} from 'lucide-vue-next';
const UnknownFilePreview = defineAsyncComponent(
  () => import('../components/filePreviews/UnknownFilePreview.vue')
);
const TiptapFilePreview = defineAsyncComponent(
  () => import('../components/filePreviews/TiptapFilePreview.vue')
);
const CodeFilePreview = defineAsyncComponent(
  () => import('../components/filePreviews/CodeFilePreview.vue')
);
const ImageFilePreview = defineAsyncComponent(
  () => import('../components/filePreviews/ImageFilePreview.vue')
);
const HtmlFilePreview = defineAsyncComponent(
  () => import('../components/filePreviews/HtmlFilePreview.vue')
);

export interface FileType {
  icon: Component; // Lucide icon component
  preview: Component;
  // Phase 5: Flag for interactive chart HTML (opens in new tab)
  isInteractiveChart?: boolean;
}

/**
 * Get Lucide icon component for a file based on its extension
 * Uses tree-shakeable Lucide icons for optimal bundle size
 */
export const getFileIconComponent = (filename: string): Component => {
  const ext = filename.split('.').pop()?.toLowerCase();

  // Text/Document files
  if (['txt', 'md', 'markdown', 'log', 'text', 'rtf'].includes(ext || '')) {
    return FileText;
  }

  // PDF files
  if (ext === 'pdf') {
    return FileText; // Use FileText for PDFs (Lucide doesn't have specific PDF icon)
  }

  // Documents (Office)
  if (['doc', 'docx', 'odt'].includes(ext || '')) {
    return FileText;
  }

  // Spreadsheets
  if (['csv', 'xls', 'xlsx', 'ods'].includes(ext || '')) {
    return FileSpreadsheet;
  }

  // Presentations
  if (['ppt', 'pptx', 'odp'].includes(ext || '')) {
    return FileBarChart; // Use chart icon for presentations
  }

  // Code files
  const codeExtensions = [
    'js', 'ts', 'jsx', 'tsx', 'vue',
    'py', 'java', 'c', 'cpp', 'h', 'hpp',
    'go', 'rs', 'php', 'rb', 'swift',
    'kt', 'scala', 'html', 'css', 'scss',
    'sh', 'bash', 'sql',
  ];
  if (ext && codeExtensions.includes(ext)) {
    return FileCode;
  }

  // JSON/YAML/Config files
  if (['json', 'yaml', 'yml', 'toml', 'ini', 'conf', 'xml'].includes(ext || '')) {
    return FileJson;
  }

  // Image files
  const imageExtensions = ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp', 'svg', 'ico', 'tiff', 'tif', 'heic', 'heif'];
  if (ext && imageExtensions.includes(ext)) {
    return FileImage;
  }

  // Video files
  const videoExtensions = ['mp4', 'avi', 'mov', 'wmv', 'flv', 'webm', 'mkv', '3gp', 'ogv'];
  if (ext && videoExtensions.includes(ext)) {
    return FileVideo;
  }

  // Audio files
  const audioExtensions = ['mp3', 'wav', 'flac', 'aac', 'ogg', 'wma', 'm4a', 'opus'];
  if (ext && audioExtensions.includes(ext)) {
    return FileAudio;
  }

  // Archive files
  const archiveExtensions = ['zip', 'rar', '7z', 'tar', 'gz', 'bz2', 'xz', 'lzma'];
  if (ext && archiveExtensions.includes(ext)) {
    return FileArchive;
  }

  // Link files
  if (['url', 'webloc', 'link'].includes(ext || '')) {
    return LinkIcon;
  }

  // Charts
  if (ext === 'chart') {
    return FileBarChart;
  }

  // Default fallback
  return File;
};

/**
 * Returns a CSS colour string for a file icon based on its extension.
 * Keeps universally-recognised type colours (PDF red, spreadsheet green, etc.)
 * that stay consistent across light and dark themes.
 */
export const getFileIconColor = (filename: string): string => {
  const ext = filename.split('.').pop()?.toLowerCase() ?? '';

  // PDF — red
  if (ext === 'pdf') return '#ef4444';

  // Spreadsheets / CSV — green
  if (['csv', 'xls', 'xlsx', 'ods'].includes(ext)) return '#22c55e';

  // Word documents — blue
  if (['doc', 'docx', 'odt', 'rtf'].includes(ext)) return '#3b82f6';

  // Presentations — orange
  if (['ppt', 'pptx', 'odp'].includes(ext)) return '#f97316';

  // Images — purple
  if (['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp', 'svg', 'ico', 'tiff', 'tif', 'heic', 'heif'].includes(ext)) return '#a855f7';

  // Video — rose
  if (['mp4', 'avi', 'mov', 'wmv', 'flv', 'webm', 'mkv', '3gp', 'ogv'].includes(ext)) return '#f43f5e';

  // Audio — violet
  if (['mp3', 'wav', 'flac', 'aac', 'ogg', 'wma', 'm4a', 'opus'].includes(ext)) return '#8b5cf6';

  // Archives — amber
  if (['zip', 'rar', '7z', 'tar', 'gz', 'bz2', 'xz', 'lzma'].includes(ext)) return '#f59e0b';

  // JSON / config / data — yellow
  if (['json', 'yaml', 'yml', 'toml', 'xml'].includes(ext)) return '#eab308';

  // Code — cyan
  const codeExts = [
    'js', 'ts', 'jsx', 'tsx', 'vue', 'py', 'java', 'c', 'cpp',
    'h', 'hpp', 'go', 'rs', 'php', 'rb', 'swift', 'kt', 'scala',
    'html', 'css', 'scss', 'sh', 'bash', 'sql',
  ];
  if (codeExts.includes(ext)) return '#06b6d4';

  // Interactive chart
  if (ext === 'chart') return '#6366f1';

  // Markdown / reports — blue
  if (['md', 'markdown'].includes(ext)) return '#3b82f6';

  // Plain text / logs — slate
  if (['txt', 'log', 'text'].includes(ext)) return '#64748b';

  // Fallback — theme icon colour
  return 'var(--icon-secondary)';
};

/**
 * Check if a file is an interactive Plotly chart based on metadata (Phase 5)
 */
export const isInteractiveChartFile = (metadata?: Record<string, any>): boolean => {
  if (!metadata) return false;

  // Only allow HTML files with explicit chart metadata
  const isChart = metadata.is_comparison_chart === true || metadata.is_chart === true;
  const isPlotly = metadata.chart_engine === 'plotly';

  return isChart && isPlotly;
};

/**
 * Check if a file is a chart PNG file based on metadata or filename
 */
export const isChartPngFile = (filename: string, metadata?: Record<string, any>): boolean => {
  const ext = filename.split('.').pop()?.toLowerCase();
  if (ext !== 'png') return false;

  // Check metadata first
  if (metadata) {
    const isChart = metadata.is_comparison_chart === true || metadata.is_chart === true;
    const isPlotly = metadata.chart_engine === 'plotly';
    if (isChart && isPlotly) return true;
  }

  // Fallback to filename pattern
  return filename.startsWith('chart-') || filename.startsWith('comparison-chart-');
};

/**
 * Get the corresponding HTML chart file for a PNG chart file
 */
export const getChartHtmlFile = (pngFile: any, allFiles: any[]): any | null => {
  if (!isChartPngFile(pngFile.filename, pngFile.metadata)) return null;

  // Find corresponding HTML file by replacing .png with .html
  const htmlFilename = pngFile.filename.replace(/\.png$/, '.html');
  return allFiles.find(f => f.filename === htmlFilename && isInteractiveChartFile(f.metadata));
};

// Text files that should use TipTap editor
const textFileExtensions = [
  'txt', 'md', 'markdown',
  'log', 'text',
];

const codeFileExtensions = [
  'py', 'js', 'ts', 'jsx', 'tsx', 'vue',
  'java', 'c', 'cpp', 'h', 'hpp',
  'go', 'rust', 'php', 'ruby', 'swift',
  'kotlin', 'scala', 'haskell', 'erlang', 'elixir',
  'ocaml', 'fsharp', 'dart', 'julia',
  'lua', 'perl', 'r', 'sh', 'bash',
  'css', 'scss', 'sass', 'less',
  'html', 'xml', 'json', 'yaml', 'yml',
  'sql', 'dockerfile', 'toml', 'ini', 'conf',
];

const imageFileExtensions = [
  'jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp', 'svg', 'ico', 'tiff', 'tif', 'heic', 'heif',
];

const documentFileExtensions = [
  'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'odt', 'ods', 'odp',
];

const videoFileExtensions = [
  'mp4', 'avi', 'mov', 'wmv', 'flv', 'webm', 'mkv', '3gp', 'ogv',
];

const audioFileExtensions = [
  'mp3', 'wav', 'flac', 'aac', 'ogg', 'wma', 'm4a', 'opus',
];

const archiveFileExtensions = [
  'zip', 'rar', '7z', 'tar', 'gz', 'bz2', 'xz', 'lzma',
];

export const getFileType = (filename: string, metadata?: Record<string, any>): FileType => {
  const file_extension = filename.split('.').pop()?.toLowerCase();
  const iconComponent = getFileIconComponent(filename);

  // Phase 5: Check for interactive chart HTML files FIRST (before generic HTML handling)
  if (file_extension === 'html' && isInteractiveChartFile(metadata)) {
    return {
      icon: FileBarChart, // Use chart icon for interactive charts
      preview: HtmlFilePreview,
      isInteractiveChart: true,
    };
  }

  // Text files (markdown, txt, log) use TipTap editor
  if (file_extension && textFileExtensions.includes(file_extension)) {
    return {
      icon: iconComponent,
      preview: TiptapFilePreview,
    };
  }

  // Code files use syntax-highlighted code preview
  if (file_extension && codeFileExtensions.includes(file_extension)) {
    return {
      icon: iconComponent,
      preview: CodeFilePreview,
    };
  }

  // Image files
  if (file_extension && imageFileExtensions.includes(file_extension)) {
    return {
      icon: iconComponent,
      preview: ImageFilePreview,
    };
  }

  return {
    icon: iconComponent,
    preview: UnknownFilePreview,
  };
};

/**
 * Get file type text based on file extension
 * @param filename - The filename to analyze
 * @param metadata - Optional file metadata (for detecting interactive charts)
 * @returns Localized description of file type
 */
export const getFileTypeText = (filename: string, metadata?: Record<string, any>): string => {
  const { t } = useI18n();
  const file_extension = filename.split('.').pop()?.toLowerCase();

  if (!file_extension) {
    return t('File');
  }

  // Phase 5: Interactive chart HTML files
  if (file_extension === 'html' && isInteractiveChartFile(metadata)) {
    return t('Interactive Chart');
  }

  // Text files
  if (file_extension === 'txt') {
    return t('Text');
  }

  // Markdown files
  if (file_extension === 'md') {
    return t('Markdown');
  }

  // Code files
  if (codeFileExtensions.includes(file_extension)) {
    return t('Code');
  }

  // Image files
  if (imageFileExtensions.includes(file_extension)) {
    return t('Image');
  }

  // Document files
  if (file_extension === 'pdf') {
    return t('PDF');
  }
  if (['doc', 'docx'].includes(file_extension)) {
    return t('Word');
  }
  if (['xls', 'xlsx'].includes(file_extension)) {
    return t('Excel');
  }
  if (['ppt', 'pptx'].includes(file_extension)) {
    return t('PowerPoint');
  }
  if (documentFileExtensions.includes(file_extension)) {
    return t('Document');
  }

  // Video files
  if (videoFileExtensions.includes(file_extension)) {
    return t('Video');
  }

  // Audio files
  if (audioFileExtensions.includes(file_extension)) {
    return t('Audio');
  }

  // Archive files
  if (archiveFileExtensions.includes(file_extension)) {
    return t('Archive');
  }

  // Default
  return t('File');
};

/**
 * Format file size from bytes to human readable format
 * @param bytes - File size in bytes
 * @param decimals - Number of decimal places (default: 1)
 * @returns Formatted file size string
 */
export function formatFileSize(bytes: number, decimals: number = 1): string {
  if (bytes === 0) return '0 B';

  const k = 1024;
  const dm = decimals < 0 ? 0 : decimals;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB'];

  const i = Math.floor(Math.log(bytes) / Math.log(k));

  return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
} 
