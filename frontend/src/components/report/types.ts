import type { FileInfo } from '@/api/file';
import type { SourceCitation } from '@/types/message';

export interface ReportSection {
  title: string;
  preview: string;
  level?: number;
}

export interface ReportData {
  id: string;
  title: string;
  content: string;
  author?: string;
  lastModified: number;
  fileCount?: number;
  sections?: ReportSection[];
  attachments?: FileInfo[];
  sources?: SourceCitation[];
}
