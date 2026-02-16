/**
 * Streaming content types for unified streaming system
 *
 * @see docs/architecture/UNIFIED_STREAMING_ARCHITECTURE.md
 */
export type StreamingContentType =
  | 'terminal'   // ANSI-colored terminal output
  | 'code'       // Syntax-highlighted code
  | 'markdown'   // Rendered markdown
  | 'json'       // Formatted JSON
  | 'search'     // Progressive search results
  | 'text';      // Plain text

/**
 * Configuration for streaming content rendering
 */
export interface StreamingContentConfig {
  type: StreamingContentType;
  language?: string;
  theme?: 'light' | 'dark';
  lineNumbers?: boolean;
  autoScroll?: boolean;
  showCursor?: boolean;
}

/**
 * Streaming event metadata from backend
 */
export interface StreamingMetadata {
  chunkIndex: number;
  totalBytes: number;
  progressPercent?: number;
  elapsedMs?: number;
  isComplete: boolean;
}

/**
 * Detect content type from function name
 */
export function detectContentType(functionName: string): StreamingContentType {
  const mapping: Record<string, StreamingContentType> = {
    // Terminal operations
    'shell_exec': 'terminal',
    'code_execute': 'terminal',
    'code_execute_python': 'terminal',
    'code_execute_javascript': 'terminal',
    'shell_view': 'terminal',
    'shell_wait': 'terminal',

    // File operations
    'file_write': 'code',
    'file_str_replace': 'code',
    'file_read': 'code',
    'file_view': 'code',

    // Search operations
    'info_search_web': 'search',
    'web_search': 'search',
    'wide_research': 'search',
    'search': 'search',

    // Browser operations
    'browser_view': 'text',
    'browser_console_view': 'terminal',
    'browser_console_exec': 'terminal',

    // Code artifacts
    'code_save_artifact': 'code',
    'code_read_artifact': 'code',
    'code_list_artifacts': 'json',

    // JSON/structured output
    'git_status': 'json',
    'workspace_tree': 'json',
  };

  return mapping[functionName] || 'text';
}

/**
 * Detect programming language from file path or content
 */
export function detectLanguage(filePath?: string, _content?: string): string {
  if (!filePath) return 'text';

  const ext = filePath.split('.').pop()?.toLowerCase();
  const languageMap: Record<string, string> = {
    // Programming languages
    'py': 'python',
    'js': 'javascript',
    'ts': 'typescript',
    'jsx': 'javascriptreact',
    'tsx': 'typescriptreact',
    'vue': 'vue',
    'java': 'java',
    'cpp': 'cpp',
    'c': 'c',
    'cs': 'csharp',
    'go': 'go',
    'rs': 'rust',
    'rb': 'ruby',
    'php': 'php',
    'swift': 'swift',
    'kt': 'kotlin',
    'scala': 'scala',

    // Web technologies
    'html': 'html',
    'css': 'css',
    'scss': 'scss',
    'sass': 'sass',
    'less': 'less',

    // Config/Data formats
    'json': 'json',
    'yaml': 'yaml',
    'yml': 'yaml',
    'toml': 'toml',
    'xml': 'xml',
    'md': 'markdown',
    'markdown': 'markdown',

    // Shell scripts
    'sh': 'shell',
    'bash': 'bash',
    'zsh': 'zsh',
    'fish': 'fish',

    // SQL
    'sql': 'sql',

    // Docker
    'dockerfile': 'dockerfile',

    // Other
    'txt': 'text',
  };

  return languageMap[ext || ''] || 'text';
}
