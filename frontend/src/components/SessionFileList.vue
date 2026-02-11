<template>
    <Dialog v-model:open="visible">
        <DialogContent
            :hide-close-button="true"
            :title="previewFile ? getDisplayName(previewFile) : $t('All files in this task')"
            description="View and download session files"
            :class="cn(
                'p-0 flex flex-col overflow-hidden transition-all duration-200',
                'bg-[var(--background-white-main)]',
                previewFile
                    ? 'w-[95vw] max-w-[900px] h-[85vh] max-h-[800px]'
                    : 'w-[95vw] max-w-[600px] h-[680px]'
            )"
        >
            <!-- Header Bar -->
            <div class="modal-header">
                <div class="header-left">
                    <button
                        v-if="previewFile"
                        class="action-btn"
                        @click="closePreview"
                        :title="$t('Back')"
                    >
                        <ArrowLeft class="w-5 h-5" />
                    </button>
                    <div v-if="previewFile" class="header-icon">
                        <component :is="getFileIconComponent(previewFile.filename)" class="w-5 h-5 text-[var(--text-white)]" />
                    </div>
                    <div class="header-info">
                        <h2 class="header-title">
                            {{ previewFile ? getDisplayName(previewFile) : $t('All files in this task') }}
                        </h2>
                    </div>
                </div>
                <div class="header-actions">
                    <button
                        v-if="previewFile"
                        class="action-btn"
                        @click="openFileDownload(previewFile)"
                        :title="$t('Download')"
                    >
                        <Download class="w-5 h-5" />
                    </button>
                    <button
                        v-if="!previewFile"
                        class="action-btn"
                        @click="downloadAllFiles"
                        :disabled="isDownloadingZip || filteredFiles.length === 0"
                        :title="$t('Download all as ZIP')"
                    >
                        <FolderDown class="w-5 h-5" />
                    </button>
                    <button
                        class="action-btn"
                        @click="visible = false"
                        :title="$t('Close')"
                    >
                        <X class="w-5 h-5" />
                    </button>
                </div>
            </div>

            <!-- File Preview -->
            <div v-if="previewFile" class="flex-1 min-h-0 overflow-hidden flex flex-col">
                <component :is="getPreviewComponent(previewFile.filename)" :file="previewFile" class="flex-1 min-h-0" />
            </div>

            <!-- Filter Tabs -->
            <div v-if="!previewFile" class="px-6 py-4 flex-shrink-0">
                <div class="flex gap-2 flex-wrap">
                    <button
                        v-for="tab in filterTabs"
                        :key="tab.id"
                        @click="activeFilter = tab.id"
                        :class="[
                            'px-4 py-2 rounded-full text-sm font-medium transition-colors',
                            activeFilter === tab.id
                                ? 'bg-[var(--Button-primary-black)] text-[var(--text-onblack)]'
                                : 'bg-[var(--fill-tsp-white-main)] text-[var(--text-secondary)] hover:bg-[var(--fill-tsp-white-dark)] hover:text-[var(--text-primary)] border border-[var(--border-main)]'
                        ]"
                    >
                        {{ tab.label }}
                    </button>
                </div>
            </div>

            <!-- File List -->
            <div v-if="!previewFile" class="flex-1 min-h-0 flex flex-col overflow-hidden">
                <div v-if="filteredFiles.length > 0" class="flex-1 min-h-0 overflow-auto px-3 pb-4">
                    <!-- Grouped by date -->
                    <div v-for="group in groupedFiles" :key="group.label" class="mb-4">
                        <div class="px-3 py-2 text-xs font-medium text-[var(--text-tertiary)] uppercase tracking-wide">
                            {{ group.label }}
                        </div>
                        <div class="flex flex-col">
                            <div
                                v-for="file in group.files"
                                :key="file.file_id"
                                class="flex items-center gap-3 px-3 py-2.5 hover:bg-[var(--fill-tsp-gray-main)] transition-colors rounded-lg cursor-pointer group"
                                @click="showFile(file)"
                            >
                                <!-- File Icon -->
                                <div
                                    class="flex-shrink-0 w-10 h-10 rounded-lg flex items-center justify-center"
                                    :class="getFileIconBgClass(file.filename)"
                                >
                                    <component :is="getFileIconComponent(file.filename)" class="w-5 h-5 text-[var(--text-white)]" />
                                </div>

                                <!-- File Info -->
                                <div class="flex flex-col flex-1 min-w-0">
                                    <span class="text-sm text-[var(--text-primary)] truncate font-medium">
                                        {{ getDisplayName(file) }}
                                    </span>
                                    <span class="text-xs text-[var(--text-tertiary)]">
                                        {{ formatFileDate(file.upload_date) }}
                                    </span>
                                </div>

                                <!-- More Options Menu -->
                                <div class="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                                    <Popover>
                                        <PopoverTrigger as-child>
                                            <button
                                                class="flex h-8 w-8 items-center justify-center cursor-pointer hover:bg-[var(--fill-tsp-white-dark)] rounded-md"
                                                @click.stop
                                            >
                                                <MoreHorizontal class="size-5 text-[var(--icon-tertiary)]" />
                                            </button>
                                        </PopoverTrigger>
                                        <PopoverContent class="w-48 p-1" align="end">
                                            <button
                                                class="w-full flex items-center gap-2 px-3 py-2 text-sm text-[var(--text-primary)] hover:bg-[var(--fill-tsp-gray-main)] rounded-md"
                                                @click="openPreview(file)"
                                            >
                                                <Eye class="size-4" />
                                                {{ $t('Preview') }}
                                            </button>
                                            <button
                                                class="w-full flex items-center gap-2 px-3 py-2 text-sm text-[var(--text-primary)] hover:bg-[var(--fill-tsp-gray-main)] rounded-md"
                                                @click="openFileDownload(file)"
                                            >
                                                <Download class="size-4" />
                                                {{ $t('Download') }}
                                            </button>
                                            <button
                                                class="w-full flex items-center gap-2 px-3 py-2 text-sm text-[var(--text-primary)] hover:bg-[var(--fill-tsp-gray-main)] rounded-md"
                                                @click="copyFileLink(file)"
                                            >
                                                <Link class="size-4" />
                                                {{ $t('Copy link') }}
                                            </button>
                                        </PopoverContent>
                                    </Popover>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Empty State -->
                <div v-else class="flex-1 min-h-0 flex flex-col items-center justify-center gap-3">
                    <div class="w-16 h-16 rounded-full bg-[var(--fill-tsp-white-main)] flex items-center justify-center">
                        <FileQuestion class="size-8 text-[var(--icon-tertiary)]" />
                    </div>
                    <p class="text-[var(--text-tertiary)] text-sm">
                        {{ activeFilter === 'all' ? $t('No files yet') : $t('No files in this category') }}
                    </p>
                </div>
            </div>
        </DialogContent>
    </Dialog>
</template>

<script setup lang="ts">
import { X, Download, MoreHorizontal, Eye, Link, FileText, FileCode, FileImage, FileArchive, File, FolderDown, FileQuestion, Globe, ArrowLeft } from 'lucide-vue-next';
import { ref, watch, computed } from 'vue';
import { useRoute } from 'vue-router';
import { useI18n } from 'vue-i18n';
import type { FileInfo } from '../api/file';
import { getFileDownloadUrl, downloadFilesAsZip, downloadFile as downloadFileContent } from '../api/file';
import { getSessionFiles, getSharedSessionFiles } from '../api/agent';
import { useSessionFileList } from '../composables/useSessionFileList';
import { Dialog, DialogContent } from '@/components/ui/dialog';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { cn } from '@/lib/utils';
import { showSuccessToast, showErrorToast } from '../utils/toast';
import { getFileType } from '../utils/fileType';

const { t } = useI18n();
const route = useRoute();
const files = ref<FileInfo[]>([]);
const activeFilter = ref<string>('all');
const isDownloadingZip = ref(false);
const previewFile = ref<FileInfo | null>(null);

const { visible, shared } = useSessionFileList();

// Resolved titles for report files without metadata (fetched from content)
const resolvedTitles = ref<Record<string, string>>({});

// Filter tab definitions
const filterTabs = computed(() => [
    { id: 'all', label: t('All') },
    { id: 'documents', label: t('Documents') },
    { id: 'images', label: t('Images') },
    { id: 'code', label: t('Code files') },
    { id: 'links', label: t('Links') },
]);

// File extension categorization
const fileCategories: Record<string, string[]> = {
    documents: ['md', 'txt', 'pdf', 'doc', 'docx', 'rtf', 'odt', 'xls', 'xlsx', 'csv', 'ppt', 'pptx'],
    images: ['png', 'jpg', 'jpeg', 'gif', 'svg', 'webp', 'bmp', 'ico', 'tiff'],
    code: ['js', 'ts', 'jsx', 'tsx', 'vue', 'py', 'java', 'go', 'rs', 'rb', 'php', 'c', 'cpp', 'h', 'cs', 'swift', 'kt', 'scala', 'html', 'css', 'scss', 'less', 'json', 'xml', 'yaml', 'yml', 'toml', 'sh', 'bash', 'sql'],
    links: ['url', 'webloc', 'link'],
};

// Check if a file is a report file
const isReportFile = (file: FileInfo): boolean => {
    return file.metadata?.is_report === true || /^report-[0-9a-f-]+\.md$/i.test(file.filename);
};

// Get display name for a file (use metadata title or resolved title for reports)
const getDisplayName = (file: FileInfo): string => {
    if (isReportFile(file)) {
        if (file.metadata?.title) return file.metadata.title;
        if (resolvedTitles.value[file.file_id]) return resolvedTitles.value[file.file_id];
    }
    return file.filename;
};

// Get file extension
const getFileExtension = (filename: string): string => {
    return filename.split('.').pop()?.toLowerCase() || '';
};

// Get file category
const getFileCategory = (filename: string): string => {
    const ext = getFileExtension(filename);
    for (const [category, extensions] of Object.entries(fileCategories)) {
        if (extensions.includes(ext)) {
            return category;
        }
    }
    return 'other';
};

// Filter files based on active filter
const filteredFiles = computed(() => {
    if (activeFilter.value === 'all') {
        return files.value;
    }
    return files.value.filter(file => getFileCategory(file.filename) === activeFilter.value);
});

// Group files by date
const groupedFiles = computed(() => {
    const now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);
    const lastWeek = new Date(today);
    lastWeek.setDate(lastWeek.getDate() - 7);

    const groups: { label: string; files: FileInfo[] }[] = [
        { label: t('Today'), files: [] },
        { label: t('Yesterday'), files: [] },
        { label: t('This week'), files: [] },
        { label: t('Earlier'), files: [] },
    ];

    for (const file of filteredFiles.value) {
        const fileDate = file.upload_date ? new Date(file.upload_date) : new Date();

        if (fileDate >= today) {
            groups[0].files.push(file);
        } else if (fileDate >= yesterday) {
            groups[1].files.push(file);
        } else if (fileDate >= lastWeek) {
            groups[2].files.push(file);
        } else {
            groups[3].files.push(file);
        }
    }

    // Filter out empty groups
    return groups.filter(group => group.files.length > 0);
});

// Get file icon component based on extension
const getFileIconComponent = (filename: string) => {
    const ext = getFileExtension(filename);

    // Documents
    if (['md', 'txt', 'pdf', 'doc', 'docx', 'rtf', 'odt'].includes(ext)) {
        return FileText;
    }
    // Code files
    if (fileCategories.code.includes(ext)) {
        return FileCode;
    }
    // Images
    if (fileCategories.images.includes(ext)) {
        return FileImage;
    }
    // Archives
    if (['zip', 'tar', 'gz', 'rar', '7z', 'bz2'].includes(ext)) {
        return FileArchive;
    }
    // Links
    if (fileCategories.links.includes(ext)) {
        return Globe;
    }

    return File;
};

// Get file icon background class based on extension
const getFileIconBgClass = (filename: string): string => {
    const ext = getFileExtension(filename);

    // Code files - blue
    if (fileCategories.code.includes(ext)) {
        return 'bg-[var(--text-brand)]';
    }
    // Documents - blue
    if (['md', 'txt', 'pdf', 'doc', 'docx', 'rtf', 'odt'].includes(ext)) {
        return 'bg-[var(--text-brand)]';
    }
    // Spreadsheets - green
    if (['xls', 'xlsx', 'csv'].includes(ext)) {
        return 'bg-[var(--function-success)]';
    }
    // Presentations - orange
    if (['ppt', 'pptx'].includes(ext)) {
        return 'bg-[var(--function-warning)]';
    }
    // Images - green
    if (fileCategories.images.includes(ext)) {
        return 'bg-[var(--function-success)]';
    }
    // Archives - red
    if (['zip', 'tar', 'gz', 'rar', '7z', 'bz2'].includes(ext)) {
        return 'bg-[var(--function-error)]';
    }
    // Links - purple
    if (fileCategories.links.includes(ext)) {
        return 'bg-[var(--icon-secondary)]';
    }

    return 'bg-[var(--text-secondary)]';
};

// Format file date
const formatFileDate = (dateStr: string | undefined): string => {
    if (!dateStr) return '';

    const date = new Date(dateStr);
    const now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);

    if (date >= today) {
        return date.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
    } else if (date >= yesterday) {
        return t('Yesterday');
    } else {
        return date.toLocaleDateString('en-US', { weekday: 'long' });
    }
};

// Extract title from markdown content (first # heading)
const extractTitleFromMarkdown = (text: string): string | null => {
    const lines = text.split('\n');
    for (const line of lines) {
        const match = line.match(/^#\s+(.+)/);
        if (match) return match[1].trim();
    }
    return null;
};

// Resolve titles for report files that lack metadata.title
const resolveReportTitles = async (fileList: FileInfo[]) => {
    const reportsWithoutTitle = fileList.filter(
        f => isReportFile(f) && !f.metadata?.title && !resolvedTitles.value[f.file_id]
    );
    if (reportsWithoutTitle.length === 0) return;

    const results = await Promise.allSettled(
        reportsWithoutTitle.map(file =>
            downloadFileContent(file.file_id)
                .then(blob => blob.text())
                .then(text => extractTitleFromMarkdown(text))
        )
    );
    results.forEach((result, index) => {
        if (result.status === 'fulfilled' && result.value) {
            resolvedTitles.value[reportsWithoutTitle[index].file_id] = result.value;
        }
    });
};

const fetchFiles = async (sessionId: string) => {
    if (!sessionId) {
        return;
    }
    let response: FileInfo[] = [];
    if (shared.value) {
        response = await getSharedSessionFiles(sessionId);
    } else {
        response = await getSessionFiles(sessionId);
    }
    // Sort: report files first, then by upload date (newest first)
    files.value = response.sort((a, b) => {
        const aIsReport = isReportFile(a) ? 1 : 0;
        const bIsReport = isReportFile(b) ? 1 : 0;
        if (aIsReport !== bIsReport) return bIsReport - aIsReport;
        const dateA = a.upload_date ? new Date(a.upload_date).getTime() : 0;
        const dateB = b.upload_date ? new Date(b.upload_date).getTime() : 0;
        return dateB - dateA;
    });

    // Resolve titles for legacy report files without metadata
    resolveReportTitles(files.value);
};

const openFileDownload = async (fileInfo: FileInfo) => {
    const url = await getFileDownloadUrl(fileInfo);
    window.open(url, '_blank');
};

const downloadAllFiles = async () => {
    if (filteredFiles.value.length === 0) return;

    isDownloadingZip.value = true;
    try {
        const fileIds = filteredFiles.value.map(f => f.file_id);
        await downloadFilesAsZip(fileIds);
        showSuccessToast(t('Files downloaded'));
    } catch {
        showErrorToast(t('Failed to download files'));
    } finally {
        isDownloadingZip.value = false;
    }
};

const openPreview = (file: FileInfo) => {
    previewFile.value = file;
};

const closePreview = () => {
    previewFile.value = null;
};

const getPreviewComponent = (filename: string) => {
    return getFileType(filename).preview;
};

const showFile = (file: FileInfo) => {
    openPreview(file);
};

const copyFileLink = async (file: FileInfo) => {
    const url = await getFileDownloadUrl(file);
    await navigator.clipboard.writeText(url);
    showSuccessToast(t('Link copied to clipboard'));
};

watch(visible, (newVisible) => {
    if (newVisible) {
        activeFilter.value = 'all'; // Reset filter when opening
        previewFile.value = null; // Reset preview when opening
        resolvedTitles.value = {}; // Clear resolved titles
        const sessionId = route.params.sessionId as string;
        if (sessionId) {
            fetchFiles(sessionId);
        }
    } else {
        previewFile.value = null; // Reset preview when closing
    }
});
</script>

<style scoped>
/* ===== HEADER ===== */
.modal-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 16px;
    border-bottom: 1px solid var(--border-light);
    background: var(--background-white-main);
    flex-shrink: 0;
}

.header-left {
    display: flex;
    align-items: center;
    gap: 12px;
    min-width: 0;
    flex: 1;
}

.header-icon {
    flex-shrink: 0;
    width: 36px;
    height: 36px;
    border-radius: 8px;
    background: linear-gradient(135deg, var(--text-brand) 0%, var(--button-primary-hover) 100%);
    display: flex;
    align-items: center;
    justify-content: center;
}

.header-info {
    min-width: 0;
    flex: 1;
}

.header-title {
    font-size: 14px;
    font-weight: 600;
    color: var(--text-primary);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    margin: 0;
}

.header-actions {
    display: flex;
    align-items: center;
    gap: 4px;
}

.action-btn {
    width: 36px;
    height: 36px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 8px;
    color: var(--icon-tertiary);
    transition: all 0.15s ease;
}

.action-btn:hover {
    background: var(--fill-tsp-gray-main);
    color: var(--icon-secondary);
}

.action-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
}

/* ===== SCROLLBAR ===== */
:deep(.overflow-auto)::-webkit-scrollbar,
:deep(.overflow-y-auto)::-webkit-scrollbar,
:deep(.overflow-y-scroll)::-webkit-scrollbar {
    width: 6px;
    height: 6px;
}

:deep(.overflow-auto)::-webkit-scrollbar-track,
:deep(.overflow-y-auto)::-webkit-scrollbar-track,
:deep(.overflow-y-scroll)::-webkit-scrollbar-track {
    background: transparent;
}

:deep(.overflow-auto)::-webkit-scrollbar-thumb,
:deep(.overflow-y-auto)::-webkit-scrollbar-thumb,
:deep(.overflow-y-scroll)::-webkit-scrollbar-thumb {
    background: var(--fill-tsp-gray-dark);
    border-radius: 3px;
}

:deep(.overflow-auto)::-webkit-scrollbar-thumb:hover,
:deep(.overflow-y-auto)::-webkit-scrollbar-thumb:hover,
:deep(.overflow-y-scroll)::-webkit-scrollbar-thumb:hover {
    background: var(--border-dark);
}
</style>
