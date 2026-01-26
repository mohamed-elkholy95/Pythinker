<template>
    <div class="pb-3 relative bg-[var(--background-gray-main)]">
        <div
            class="flex flex-col gap-3 rounded-[22px] transition-all relative bg-[var(--fill-input-chat)] py-3 max-h-[300px] shadow-[0px_12px_32px_0px_rgba(0,0,0,0.02)] border border-black/8 dark:border-[var(--border-main)]">
            <ChatBoxFiles ref="chatBoxFileListRef" :attachments="attachments" />
            <div class="overflow-y-auto pl-4 pr-2">
                <textarea
                    ref="textareaRef"
                    class="flex rounded-md border-input focus-visible:outline-none focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50 overflow-hidden flex-1 bg-transparent p-0 pt-[1px] border-0 focus-visible:ring-0 focus-visible:ring-offset-0 w-full placeholder:text-[var(--text-disable)] text-[15px] shadow-none resize-none min-h-[40px]"
                    :rows="rows" :value="modelValue"
                    @input="$emit('update:modelValue', ($event.target as HTMLTextAreaElement).value)"
                    @compositionstart="isComposing = true" @compositionend="isComposing = false"
                    @keydown.enter.exact="handleEnterKeydown"
                    @paste="handlePaste"
                    :placeholder="t('Give Manus a task to work on...')"
                    :style="{ height: '46px' }"></textarea>
            </div>
            <footer class="flex flex-row justify-between w-full px-3">
                <div class="flex gap-2 pr-2 items-center">
                    <button @click="uploadFile"
                        class="rounded-full border border-[var(--border-main)] inline-flex items-center justify-center gap-1 clickable cursor-pointer text-xs text-[var(--text-secondary)] hover:bg-[var(--fill-tsp-gray-main)] w-8 h-8 p-0 data-[popover-trigger]:bg-[var(--fill-tsp-gray-main)] shrink-0"
                        aria-expanded="false" aria-haspopup="dialog">
                        <Paperclip :size="16" />
                    </button>
                </div>
                <div class="flex gap-2">
                    <button v-if="!isRunning || sendEnabled"
                        class="whitespace-nowrap text-sm font-medium focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50 text-primary-foreground hover:bg-primary/90 p-0 w-8 h-8 rounded-full flex items-center justify-center transition-colors hover:opacity-90"
                        :class="!sendEnabled ? 'cursor-not-allowed bg-[var(--fill-tsp-white-dark)]' : 'cursor-pointer bg-[var(--Button-primary-black)]'"
                        @click="handleSubmit">
                        <SendIcon :disabled="!sendEnabled" />
                    </button>
                    <button v-else @click="handleStop"
                        class="inline-flex items-center justify-center whitespace-nowrap text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring bg-[var(--Button-primary-black)] text-[var(--text-onblack)] gap-[4px] hover:opacity-90 rounded-full p-0 w-8 h-8">
                        <div class="w-[10px] h-[10px] bg-[var(--icon-onblack)] rounded-[2px]">
                        </div>
                    </button>
                </div>
            </footer>
        </div>
    </div>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue';
import SendIcon from './icons/SendIcon.vue';
import { useI18n } from 'vue-i18n';
import ChatBoxFiles from './ChatBoxFiles.vue';
import { Paperclip } from 'lucide-vue-next';
import type { FileInfo } from '../api/file';
import { showInfoToast } from '../utils/toast';

const { t } = useI18n();
const hasTextInput = ref(false);
const isComposing = ref(false);
const chatBoxFileListRef = ref();
const textareaRef = ref<HTMLTextAreaElement>();

// Threshold for converting pasted text to file attachment
const LONG_TEXT_CHAR_THRESHOLD = 500;  // Characters
const LONG_TEXT_LINE_THRESHOLD = 15;   // Lines

const props = defineProps<{
    modelValue: string;
    rows: number;
    isRunning: boolean;
    attachments: FileInfo[];
}>();

const sendEnabled = computed(() => {
    return chatBoxFileListRef.value?.isAllUploaded && hasTextInput.value;
});

const emit = defineEmits<{
    (e: 'update:modelValue', value: string): void;
    (e: 'submit'): void;
    (e: 'stop'): void;
}>();

/**
 * Detect if pasted text is code based on common patterns
 */
const detectCodeType = (text: string): { isCode: boolean; extension: string; language: string } => {
    const lines = text.split('\n');
    const firstLines = lines.slice(0, 10).join('\n');

    // Check for common code patterns
    const patterns = [
        { regex: /^(import|from)\s+\w+/m, ext: 'py', lang: 'Python' },
        { regex: /^(def|class|async def)\s+\w+/m, ext: 'py', lang: 'Python' },
        { regex: /^(const|let|var|function|import|export)\s+/m, ext: 'js', lang: 'JavaScript' },
        { regex: /^(interface|type|enum)\s+\w+/m, ext: 'ts', lang: 'TypeScript' },
        { regex: /<\?php/m, ext: 'php', lang: 'PHP' },
        { regex: /^package\s+\w+/m, ext: 'java', lang: 'Java' },
        { regex: /^(func|package|import)\s+/m, ext: 'go', lang: 'Go' },
        { regex: /^(fn|use|mod|impl|struct|enum)\s+/m, ext: 'rs', lang: 'Rust' },
        { regex: /^#include\s+[<"]/m, ext: 'cpp', lang: 'C++' },
        { regex: /^(SELECT|INSERT|UPDATE|DELETE|CREATE|DROP|ALTER)\s+/im, ext: 'sql', lang: 'SQL' },
        { regex: /^<!DOCTYPE|^<html|^<\?xml/im, ext: 'html', lang: 'HTML' },
        { regex: /^\s*[\w-]+\s*:\s*[\w#"']/m, ext: 'css', lang: 'CSS' },
        { regex: /^(apiVersion|kind|metadata):/m, ext: 'yaml', lang: 'YAML' },
        { regex: /^\s*\{[\s\S]*"[\w]+"\s*:/m, ext: 'json', lang: 'JSON' },
        { regex: /^#!\/.*\/(bash|sh|zsh)/m, ext: 'sh', lang: 'Shell' },
    ];

    for (const pattern of patterns) {
        if (pattern.regex.test(firstLines)) {
            return { isCode: true, extension: pattern.ext, language: pattern.lang };
        }
    }

    // Check for general code indicators
    const codeIndicators = [
        /[{}();].*[{}();]/,  // Multiple brackets/semicolons
        /^\s{2,}(if|for|while|return|else)/m,  // Indented control flow
        /\w+\s*\([^)]*\)\s*[{;]/,  // Function calls/definitions
    ];

    for (const indicator of codeIndicators) {
        if (indicator.test(firstLines)) {
            return { isCode: true, extension: 'txt', language: 'Code' };
        }
    }

    return { isCode: false, extension: 'txt', language: 'Text' };
};

/**
 * Generate a filename for the pasted content
 */
const generateFilename = (text: string): string => {
    const { extension, language } = detectCodeType(text);
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);

    if (extension !== 'txt') {
        return `pasted-${language.toLowerCase()}-${timestamp}.${extension}`;
    }

    return `pasted-text-${timestamp}.txt`;
};

/**
 * Check if text should be converted to a file attachment
 */
const shouldConvertToFile = (text: string): boolean => {
    const charCount = text.length;
    const lineCount = text.split('\n').length;

    return charCount >= LONG_TEXT_CHAR_THRESHOLD || lineCount >= LONG_TEXT_LINE_THRESHOLD;
};

/**
 * Convert text to a File object
 */
const textToFile = (text: string, filename: string): File => {
    const blob = new Blob([text], { type: 'text/plain' });
    return new File([blob], filename, { type: 'text/plain' });
};

/**
 * Handle paste event - convert long text to file attachment
 */
const handlePaste = async (event: ClipboardEvent) => {
    const clipboardData = event.clipboardData;
    if (!clipboardData) return;

    // Check if there are files being pasted (e.g., images)
    if (clipboardData.files.length > 0) {
        // Let default behavior handle file paste, or handle explicitly
        return;
    }

    const pastedText = clipboardData.getData('text/plain');
    if (!pastedText) return;

    // Check if the pasted text is long enough to convert
    if (shouldConvertToFile(pastedText)) {
        // Prevent default paste behavior
        event.preventDefault();

        // Generate filename based on content type
        const filename = generateFilename(pastedText);

        // Convert to File and upload
        const file = textToFile(pastedText, filename);

        // Upload via ChatBoxFiles component
        if (chatBoxFileListRef.value) {
            await chatBoxFileListRef.value.uploadFileFromBlob(file);
        }

        // Get content info for toast message
        const { language } = detectCodeType(pastedText);
        const lineCount = pastedText.split('\n').length;

        // Show toast notification
        showInfoToast(t('Long text converted to file attachment ({lines} lines)', { lines: lineCount }));

        // If textarea is empty, add a helpful prompt
        if (!props.modelValue.trim()) {
            emit('update:modelValue', t('Analyze the attached {language} content', { language: language.toLowerCase() }));
        }
    }
    // Otherwise, let normal paste happen
};

const handleEnterKeydown = (event: KeyboardEvent) => {
    if (isComposing.value) {
        // If in input method composition state, do nothing and allow default behavior
        return;
    }

    // Not in input method composition state and has text input, prevent default behavior and submit
    if (sendEnabled.value) {
        event.preventDefault();
        handleSubmit();
    }
};

const handleSubmit = () => {
    if (!sendEnabled.value) return;
    emit('submit');
};

const handleStop = () => {
    emit('stop');
};

const uploadFile = () => {
    chatBoxFileListRef.value?.uploadFile();
};

watch(() => props.modelValue, (value) => {
    hasTextInput.value = value.trim() !== '';
});
</script>