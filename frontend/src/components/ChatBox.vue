<template>
    <div class="chatbox-wrapper">
        <div class="chatbox-container">
            <ConnectorBanner v-if="showConnectorBanner" />
            <ChatBoxFiles ref="chatBoxFileListRef" :attachments="attachments" @fileClick="$emit('fileClick', $event)" />
            <!-- Active session skills chip row -->
            <div v-if="sessionSkillChips.length > 0" class="session-skills-row">
              <div
                v-for="chip in sessionSkillChips"
                :key="chip.id"
                class="session-skill-chip"
              >
                <Puzzle :size="10" />
                <span>{{ chip.name }}</span>
                <button class="session-skill-remove" @click="removeSessionSkill(chip.id)">
                  <X :size="10" />
                </button>
              </div>
            </div>
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
                    <ConnectorButton />
                    <SkillPicker />
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
import { Paperclip, Puzzle, X } from 'lucide-vue-next';
import ConnectorButton from './connectors/ConnectorButton.vue';
import ConnectorBanner from './connectors/ConnectorBanner.vue';
import SkillPicker from './SkillPicker.vue';
import { useSkills } from '@/composables/useSkills';
import type { FileInfo } from '../api/file';
import { showInfoToast } from '../utils/toast';

const { t } = useI18n();
const { sessionSkillIds, availableSkills, removeSessionSkill, selectSkill } = useSkills();
const hasTextInput = ref(false);
const isComposing = ref(false);
const chatBoxFileListRef = ref();
const textareaRef = ref<HTMLTextAreaElement>();

// Session skill chips: resolve skill IDs to name/id pairs for display
const sessionSkillChips = computed(() => {
  return sessionSkillIds.value
    .map((id) => {
      const skill = availableSkills.value.find((s) => s.id === id);
      return skill ? { id: skill.id, name: skill.name } : { id, name: id };
    });
});

// Command → skill ID mapping for auto-detection
const COMMAND_SKILL_MAP: Record<string, string> = {
  'skill-creator': 'skill-creator',
  'build-skill': 'skill-creator',
  'brainstorm': 'brainstorming',
  'design': 'brainstorming',
  'write-plan': 'writing-plans',
  'plan': 'writing-plans',
  'tdd': 'test-driven-development',
  'debug': 'systematic-debugging',
  'verify': 'verification-before-completion',
};

// Threshold for converting pasted text to file attachment
const LONG_TEXT_CHAR_THRESHOLD = 500;  // Characters
const LONG_TEXT_LINE_THRESHOLD = 15;   // Lines


const props = defineProps<{
    modelValue: string;
    rows: number;
    isRunning: boolean;
    attachments: FileInfo[];
    showConnectorBanner?: boolean;
}>();

const sendEnabled = computed(() => {
    return chatBoxFileListRef.value?.isAllUploaded && hasTextInput.value;
});

const emit = defineEmits<{
    (e: 'update:modelValue', value: string): void;
    (e: 'submit'): void;
    (e: 'stop'): void;
    (e: 'fileClick', file: FileInfo): void;
}>();

/**
 * Generate a filename for the pasted content
 * Uses format: pasted_text_1.txt, pasted_text_2.txt, etc.
 * Counts existing pasted_text files in attachments to determine next number
 */
const generatePastedFilename = (): string => {
    // Find the highest number among existing pasted_text_*.txt files
    const pattern = /^pasted_text_(\d+)\.txt$/;
    let maxNumber = 0;

    for (const attachment of props.attachments) {
        const match = attachment.name.match(pattern);
        if (match) {
            const num = parseInt(match[1], 10);
            if (num > maxNumber) {
                maxNumber = num;
            }
        }
    }

    return `pasted_text_${maxNumber + 1}.txt`;
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

        // Generate numbered filename (pasted_text_1.txt, pasted_text_2.txt, etc.)
        const filename = generatePastedFilename();

        // Convert to File and upload
        const file = textToFile(pastedText, filename);

        // Upload via ChatBoxFiles component
        if (chatBoxFileListRef.value) {
            await chatBoxFileListRef.value.uploadFileFromBlob(file);
        }

        // Get line count for toast message
        const lineCount = pastedText.split('\n').length;

        // Show toast notification
        showInfoToast(t('Long text converted to file attachment ({lines} lines)', { lines: lineCount }));

        // If textarea is empty, add a vague prompt so user can decide what to do
        if (!props.modelValue.trim()) {
            emit('update:modelValue', t('Process this file'));
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

// Track which commands have already been auto-detected (prevent repeated toasts)
const detectedCommands = ref<Set<string>>(new Set());

watch(() => props.modelValue, (value) => {
    hasTextInput.value = value.trim() !== '';

    // Auto-detect /commands in input text
    const commandMatch = value.match(/\/([a-zA-Z0-9_-]+)/);
    if (commandMatch) {
      const command = commandMatch[1].toLowerCase();
      const skillId = COMMAND_SKILL_MAP[command];
      if (skillId && !detectedCommands.value.has(command)) {
        detectedCommands.value.add(command);
        selectSkill(skillId);
        showInfoToast(t('Skill auto-activated: {command}', { command: `/${command}` }));
      }
    }
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
    border-radius: 22px;
    transition: all 0.2s ease;
    position: relative;
    padding: 14px 0;
    max-height: 300px;
    background: var(--background-white-main);
    border: 1px solid var(--border-main);
    box-shadow: 0 14px 32px rgba(15, 23, 42, 0.08);
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
    background: var(--background-white-main);
    border: 1px solid var(--border-main);
    color: var(--text-secondary);
}

.chatbox-attach-btn:hover {
    background: var(--fill-tsp-gray-main);
    border-color: var(--border-dark);
    color: var(--text-primary);
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
    color: var(--text-tertiary);
}

.chatbox-send-btn.enabled {
    cursor: pointer;
    background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
    color: var(--text-white);
    box-shadow: 0 10px 20px rgba(59, 130, 246, 0.28);
}

.chatbox-send-btn.enabled:hover {
    box-shadow: 0 12px 24px rgba(59, 130, 246, 0.36);
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
    color: var(--text-white);
    box-shadow: 0 10px 20px rgba(59, 130, 246, 0.28);
}

.chatbox-stop-btn:hover {
    box-shadow: 0 12px 24px rgba(59, 130, 246, 0.36);
}

.stop-icon {
    width: 10px;
    height: 10px;
    background: white;
    border-radius: 2px;
}

.session-skills-row {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    padding: 0 14px 4px;
}

.session-skill-chip {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 2px 6px 2px 5px;
    border-radius: 10px;
    background: rgba(59, 130, 246, 0.08);
    border: 1px solid rgba(59, 130, 246, 0.2);
    color: #3b82f6;
    font-size: 11px;
    font-weight: 500;
    line-height: 1.2;
}

.session-skill-remove {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 14px;
    height: 14px;
    border-radius: 50%;
    border: none;
    background: transparent;
    color: #3b82f6;
    cursor: pointer;
    padding: 0;
    transition: background 0.1s ease;
}

.session-skill-remove:hover {
    background: rgba(59, 130, 246, 0.15);
}
</style>
