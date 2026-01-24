<template>
    <div class="absolute z-[1000] pointer-events-auto" v-if="visible">
        <div class="w-full h-full bg-black/60 backdrop-blur-[4px] fixed inset-0 data-[state=open]:animate-dialog-bg-fade-in data-[state=closed]:animate-dialog-bg-fade-out"
            style="position: fixed; overflow: auto; inset: 0px;" @click="hideSessionFileList"></div>
        <div role="dialog"
            class="bg-[var(--background-menu-white)] rounded-[20px] border border-white/5 fixed left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 max-w-[95%] max-h-[95%] overflow-hidden data-[state=open]:animate-dialog-slide-in-from-bottom data-[state=closed]:animate-dialog-slide-out-to-bottom h-[680px] flex flex-col"
            style="width: 600px;">
            <!-- Header -->
            <header class="flex items-center justify-between pt-6 pr-6 pl-6 pb-4 flex-shrink-0">
                <h1 class="text-[var(--text-primary)] text-lg font-semibold">{{ $t('All files in this task') }}</h1>
                <div class="flex items-center gap-2">
                    <button
                        class="flex h-8 w-8 items-center justify-center cursor-pointer hover:bg-[var(--fill-tsp-gray-main)] rounded-lg"
                        @click="downloadAllFiles"
                        :title="$t('Download all')"
                    >
                        <FolderDown class="size-5 text-[var(--icon-tertiary)]" />
                    </button>
                    <button
                        class="flex h-8 w-8 items-center justify-center cursor-pointer hover:bg-[var(--fill-tsp-gray-main)] rounded-lg"
                        @click="hideSessionFileList"
                    >
                        <X class="size-5 text-[var(--icon-tertiary)]" />
                    </button>
                </div>
            </header>

            <!-- Filter Tabs -->
            <div class="px-6 pb-4 flex-shrink-0">
                <div class="flex gap-2 flex-wrap">
                    <button
                        v-for="tab in filterTabs"
                        :key="tab.id"
                        @click="activeFilter = tab.id"
                        :class="[
                            'px-4 py-2 rounded-full text-sm font-medium transition-colors',
                            activeFilter === tab.id
                                ? 'bg-[var(--Button-primary-black)] text-white'
                                : 'bg-[var(--fill-tsp-white-main)] text-[var(--text-secondary)] hover:bg-[var(--fill-tsp-white-dark)] border border-[var(--border-main)]'
                        ]"
                    >
                        {{ tab.label }}
                    </button>
                </div>
            </div>

            <!-- File List -->
            <div class="flex-1 min-h-0 flex flex-col overflow-hidden">
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
                                    <component :is="getFileIconComponent(file.filename)" class="w-5 h-5 text-white" />
                                </div>

                                <!-- File Info -->
                                <div class="flex flex-col flex-1 min-w-0">
                                    <span class="text-sm text-[var(--text-primary)] truncate font-medium">
                                        {{ file.filename }}
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
                                                @click="previewFile(file)"
                                            >
                                                <Eye class="size-4" />
                                                {{ $t('Preview') }}
                                            </button>
                                            <button
                                                class="w-full flex items-center gap-2 px-3 py-2 text-sm text-[var(--text-primary)] hover:bg-[var(--fill-tsp-gray-main)] rounded-md"
                                                @click="downloadFile(file)"
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
        </div>
    </div>
</template>

<script setup lang="ts">
import { X, Download, MoreHorizontal, Eye, Link, FileText, FileCode, FileImage, FileArchive, File, FolderDown, FileQuestion, Globe } from 'lucide-vue-next';
import { ref, watch, computed } from 'vue';
import { useRoute } from 'vue-router';
import { useI18n } from 'vue-i18n';
import type { FileInfo } from '../api/file';
import { getFileDownloadUrl } from '../api/file';
import { getSessionFiles, getSharedSessionFiles } from '../api/agent';
import { useSessionFileList } from '../composables/useSessionFileList';
import { useFilePanel } from '../composables/useFilePanel';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { showSuccessToast } from '../utils/toast';

const { t } = useI18n();
const route = useRoute();
const files = ref<FileInfo[]>([]);
const activeFilter = ref<string>('all');

const { showFilePanel } = useFilePanel();
const { visible, hideSessionFileList, shared } = useSessionFileList();

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
        return 'bg-[#4285f4]';
    }
    // Documents - blue
    if (['md', 'txt', 'pdf', 'doc', 'docx', 'rtf', 'odt'].includes(ext)) {
        return 'bg-[#4285f4]';
    }
    // Spreadsheets - green
    if (['xls', 'xlsx', 'csv'].includes(ext)) {
        return 'bg-[#34A853]';
    }
    // Presentations - orange
    if (['ppt', 'pptx'].includes(ext)) {
        return 'bg-[#EA4335]';
    }
    // Images - green
    if (fileCategories.images.includes(ext)) {
        return 'bg-[#10B981]';
    }
    // Archives - red
    if (['zip', 'tar', 'gz', 'rar', '7z', 'bz2'].includes(ext)) {
        return 'bg-[#EA4335]';
    }
    // Links - purple
    if (fileCategories.links.includes(ext)) {
        return 'bg-[#9333EA]';
    }

    return 'bg-[#6B7280]';
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
    // Sort by upload date, newest first
    files.value = response.sort((a, b) => {
        const dateA = a.upload_date ? new Date(a.upload_date).getTime() : 0;
        const dateB = b.upload_date ? new Date(b.upload_date).getTime() : 0;
        return dateB - dateA;
    });
};

const downloadFile = async (fileInfo: FileInfo) => {
    const url = await getFileDownloadUrl(fileInfo);
    window.open(url, '_blank');
};

const downloadAllFiles = async () => {
    for (const file of filteredFiles.value) {
        await downloadFile(file);
    }
};

const previewFile = (file: FileInfo) => {
    showFilePanel(file);
    hideSessionFileList();
};

const showFile = (file: FileInfo) => {
    showFilePanel(file);
    hideSessionFileList();
};

const copyFileLink = async (file: FileInfo) => {
    const url = await getFileDownloadUrl(file);
    await navigator.clipboard.writeText(url);
    showSuccessToast(t('Link copied to clipboard'));
};

watch(visible, (newVisible) => {
    if (newVisible) {
        activeFilter.value = 'all'; // Reset filter when opening
        const sessionId = route.params.sessionId as string;
        if (sessionId) {
            fetchFiles(sessionId);
        }
    }
});
</script>
