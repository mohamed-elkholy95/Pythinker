<template>
    <div class="chatbox-wrapper">
        <div class="chatbox-container">
            <ChatBoxFiles ref="chatBoxFileListRef" :attachments="attachments" />
            <div class="chatbox-input-area">
                <textarea
                    ref="textareaRef"
                    class="chatbox-textarea"
                    :rows="rows" :value="modelValue"
                    @input="$emit('update:modelValue', ($event.target as HTMLTextAreaElement).value)"
                    @compositionstart="isComposing = true" @compositionend="isComposing = false"
                    @keydown.enter.exact="handleEnterKeydown"
                    @paste="handlePaste"
                    :placeholder="t('Give Pythinker a task to work on...')"
                    :style="{ height: '46px' }"></textarea>
            </div>
            <footer class="chatbox-footer">
                <div class="chatbox-actions-left">
                    <button @click="uploadFile" class="chatbox-attach-btn">
                        <Paperclip :size="16" />
                    </button>
                </div>
                <div class="chatbox-actions-right">
                    <button v-if="!isRunning || sendEnabled"
                        class="chatbox-send-btn"
                        :class="{ 'disabled': !sendEnabled, 'enabled': sendEnabled }"
                        @click="handleSubmit">
                        <SendIcon :disabled="!sendEnabled" />
                    </button>
                    <button v-else @click="handleStop" class="chatbox-stop-btn">
                        <div class="stop-icon"></div>
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
        { regex: /^(SELECT\s+.+\s+FROM|INSERT\s+INTO|UPDATE\s+\w+\s+SET|DELETE\s+FROM|CREATE\s+(TABLE|DATABASE|INDEX|VIEW|SCHEMA|PROCEDURE|FUNCTION)|DROP\s+(TABLE|DATABASE|INDEX|VIEW|SCHEMA)|ALTER\s+TABLE)\s+/im, ext: 'sql', lang: 'SQL' },
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

<style scoped>
.chatbox-wrapper {
    padding-bottom: 12px;
    position: relative;
}

.chatbox-container {
    display: flex;
    flex-direction: column;
    gap: 12px;
    border-radius: 20px;
    transition: all 0.2s ease;
    position: relative;
    padding: 14px 0;
    max-height: 300px;
    background: var(--fill-input-chat);
    border: 1px solid var(--bolt-elements-borderColor);
}

.chatbox-container:focus-within {
    border-color: var(--bolt-elements-borderColorActive);
}

.chatbox-input-area {
    overflow-y: auto;
    padding-left: 16px;
    padding-right: 8px;
}

.chatbox-textarea {
    display: flex;
    border-radius: 8px;
    overflow: hidden;
    flex: 1;
    background: transparent;
    padding: 0;
    padding-top: 1px;
    border: 0;
    width: 100%;
    font-size: 15px;
    line-height: 1.5;
    color: var(--text-primary);
    box-shadow: none;
    resize: none;
    min-height: 40px;
    outline: none;
}

.chatbox-textarea::placeholder {
    color: var(--text-disable);
}

.chatbox-textarea:focus {
    outline: none;
    box-shadow: none;
}

.chatbox-footer {
    display: flex;
    flex-direction: row;
    justify-content: space-between;
    width: 100%;
    padding: 0 12px;
}

.chatbox-actions-left {
    display: flex;
    gap: 8px;
    padding-right: 8px;
    align-items: center;
}

.chatbox-actions-right {
    display: flex;
    gap: 8px;
}

.chatbox-attach-btn {
    width: 34px;
    height: 34px;
    border-radius: 50%;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    flex-shrink: 0;
    transition: all 0.15s ease;
    background: var(--bolt-elements-bg-depth-4);
    border: 1px solid var(--bolt-elements-borderColor);
    color: var(--bolt-elements-textTertiary);
}

.chatbox-attach-btn:hover {
    background: var(--bolt-elements-item-backgroundActive);
    border-color: var(--bolt-elements-borderColor);
    color: var(--bolt-elements-textSecondary);
}

.chatbox-send-btn {
    width: 34px;
    height: 34px;
    padding: 0;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.2s ease;
    font-size: 14px;
    font-weight: 500;
}

.chatbox-send-btn.disabled {
    cursor: not-allowed;
    background: var(--bolt-elements-bg-depth-3);
    color: var(--bolt-elements-textTertiary);
}

.chatbox-send-btn.enabled {
    cursor: pointer;
    background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
    color: white;
    box-shadow: 0 2px 8px rgba(59, 130, 246, 0.35);
}

.chatbox-send-btn.enabled:hover {
    box-shadow: 0 4px 12px rgba(59, 130, 246, 0.45);
    transform: scale(1.05);
}

.chatbox-send-btn.enabled:active {
    transform: scale(0.98);
}

.chatbox-stop-btn {
    width: 34px;
    height: 34px;
    padding: 0;
    border-radius: 50%;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    transition: all 0.2s ease;
    background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
    color: white;
    box-shadow: 0 2px 8px rgba(59, 130, 246, 0.35);
}

.chatbox-stop-btn:hover {
    box-shadow: 0 4px 12px rgba(59, 130, 246, 0.45);
}

.stop-icon {
    width: 10px;
    height: 10px;
    background: white;
    border-radius: 2px;
}
</style>
