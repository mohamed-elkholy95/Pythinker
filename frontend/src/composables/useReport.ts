import { ref, computed } from 'vue';
import type { ReportData, ReportSection } from '@/components/report/ReportCard.vue';
import type { FileInfo } from '@/api/file';

const isReportModalOpen = ref(false);
const currentReport = ref<ReportData | null>(null);

/**
 * Extract sections from markdown content for preview
 */
export function extractSectionsFromMarkdown(content: string): ReportSection[] {
  const sections: ReportSection[] = [];
  const lines = content.split('\n');

  let currentSection: ReportSection | null = null;
  let contentLines: string[] = [];

  for (const line of lines) {
    // Match headings (## or ### for sections)
    const headingMatch = line.match(/^(#{2,4})\s+(.+)$/);

    if (headingMatch) {
      // Save previous section if exists
      if (currentSection) {
        currentSection.preview = contentLines
          .join(' ')
          .replace(/\s+/g, ' ')
          .trim()
          .slice(0, 300);
        sections.push(currentSection);
      }

      // Start new section
      const level = headingMatch[1].length;
      const title = headingMatch[2].trim();
      currentSection = {
        title,
        preview: '',
        level
      };
      contentLines = [];
    } else if (currentSection) {
      // Collect content lines (skip empty lines and special markdown)
      const trimmed = line.trim();
      if (trimmed && !trimmed.startsWith('|') && !trimmed.startsWith('```') && !trimmed.startsWith('---')) {
        // Remove markdown formatting
        const cleanText = trimmed
          .replace(/\*\*(.+?)\*\*/g, '$1')
          .replace(/\*(.+?)\*/g, '$1')
          .replace(/\[(.+?)\]\(.+?\)/g, '$1')
          .replace(/`(.+?)`/g, '$1');
        contentLines.push(cleanText);
      }
    }
  }

  // Save last section
  if (currentSection) {
    currentSection.preview = contentLines
      .join(' ')
      .replace(/\s+/g, ' ')
      .trim()
      .slice(0, 300);
    sections.push(currentSection);
  }

  return sections;
}

/**
 * Extract title from markdown content
 */
export function extractTitleFromMarkdown(content: string): string {
  // Try to find h1 heading
  const h1Match = content.match(/^#\s+(.+)$/m);
  if (h1Match) return h1Match[1].trim();

  // Try to find first h2 heading
  const h2Match = content.match(/^##\s+(.+)$/m);
  if (h2Match) return h2Match[1].trim();

  // Return first line as fallback
  const firstLine = content.split('\n')[0];
  return firstLine?.trim() || 'Untitled Report';
}

/**
 * Create a ReportData object from markdown content
 */
export function createReportFromMarkdown(
  id: string,
  content: string,
  attachments?: FileInfo[],
  lastModified?: number
): ReportData {
  const title = extractTitleFromMarkdown(content);
  const sections = extractSectionsFromMarkdown(content);

  return {
    id,
    title,
    content,
    lastModified: lastModified || Date.now(),
    fileCount: attachments?.length || 0,
    sections,
    attachments
  };
}

/**
 * Composable for managing report display
 */
export function useReport() {
  const openReport = (report: ReportData) => {
    currentReport.value = report;
    isReportModalOpen.value = true;
  };

  const closeReport = () => {
    isReportModalOpen.value = false;
    // Delay clearing the report to allow for close animation
    setTimeout(() => {
      currentReport.value = null;
    }, 300);
  };

  const openReportFromMarkdown = (
    id: string,
    content: string,
    attachments?: FileInfo[],
    lastModified?: number
  ) => {
    const report = createReportFromMarkdown(id, content, attachments, lastModified);
    openReport(report);
  };

  return {
    isReportModalOpen,
    currentReport,
    openReport,
    closeReport,
    openReportFromMarkdown,
    createReportFromMarkdown,
    extractSectionsFromMarkdown,
    extractTitleFromMarkdown
  };
}

// Singleton instance for global state
export const reportState = {
  isOpen: isReportModalOpen,
  current: currentReport
};
