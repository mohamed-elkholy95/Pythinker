import type { FileInfo } from '@/api/file';

export interface ReportSection {
  title: string;
  preview: string;
  level?: number;
}

export interface ReportData {
  id: string;
  title: string;
  content: string;
  lastModified: number;
  fileCount?: number;
  sections?: ReportSection[];
  attachments?: FileInfo[];
}
