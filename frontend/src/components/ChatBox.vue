<template>
    <div class="chatbox-wrapper" :class="`expand-${props.expandDirection}`">
        <div class="chatbox-shell">
            <div class="chatbox-container">
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
                        @input="handleInput"
                        @compositionstart="isComposing = true" @compositionend="isComposing = false"
                        @keydown.enter.exact="handleEnterKeydown"
                        :placeholder="t('Give Pythinker a task to work on...')"
                        :style="textareaStyle"></textarea>
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
            <div v-if="showConnectorRow" class="chatbox-connector-row">
                <ConnectorBanner :forceVisible="true" @close="handleConnectorBannerClose" />
            </div>
        </div>
    </div>
</template>

<script setup lang="ts">
import { ref, watch, computed, onMounted, nextTick } from 'vue';
import SendIcon from './icons/SendIcon.vue';
import { useI18n } from 'vue-i18n';
import ChatBoxFiles from './ChatBoxFiles.vue';
import { Paperclip, Puzzle, X } from 'lucide-vue-next';
import ConnectorButton from './connectors/ConnectorButton.vue';
import ConnectorBanner from './connectors/ConnectorBanner.vue';
import SkillPicker from './SkillPicker.vue';
import { useSkills } from '@/composables/useSkills';
import { getCommandMap } from '@/api/skills';
import type { FileInfo } from '../api/file';
import { showInfoToast } from '../utils/toast';

const { t } = useI18n();
const { sessionSkillIds, availableSkills, removeSessionSkill, selectSkill } = useSkills();

// Command -> skill_id map (fetched from backend, includes all commands + aliases)
const commandSkillMap = ref<Record<string, string>>({});
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

const props = withDefaults(defineProps<{
    modelValue: string;
    rows: number;
    isRunning: boolean;
    attachments: FileInfo[];
    showConnectorBanner?: boolean;
    isBlocked?: boolean;
    expandDirection?: 'up' | 'down';
}>(), {
  expandDirection: 'up',
});
const isConnectorBannerClosed = ref(false);
const showConnectorRow = computed(() => !!props.showConnectorBanner && !isConnectorBannerClosed.value);

const MIN_TEXTAREA_HEIGHT = 46;
const MAX_TEXTAREA_HEIGHT = 220;
const ESTIMATED_LINE_HEIGHT = 24;
const ESTIMATED_VERTICAL_PADDING = 20;

const textareaStyle = ref({
  height: `${MIN_TEXTAREA_HEIGHT}px`,
  overflowY: 'hidden',
});

const resizeTextarea = (inputValue?: string) => {
  const textarea = textareaRef.value;
  if (!textarea) return;

  textarea.style.height = `${MIN_TEXTAREA_HEIGHT}px`;
  const measuredHeight = textarea.scrollHeight;
  const value = typeof inputValue === 'string' ? inputValue : textarea.value;
  const lineCount = Math.max((value || '').split('\n').length, 1);
  const estimatedHeight = lineCount * ESTIMATED_LINE_HEIGHT + ESTIMATED_VERTICAL_PADDING;
  const contentHeight = measuredHeight > MIN_TEXTAREA_HEIGHT ? measuredHeight : estimatedHeight;
  const nextHeight = Math.min(Math.max(contentHeight, MIN_TEXTAREA_HEIGHT), MAX_TEXTAREA_HEIGHT);

  textareaStyle.value = {
    height: `${nextHeight}px`,
    overflowY: contentHeight > MAX_TEXTAREA_HEIGHT ? 'auto' : 'hidden',
  };
};

const sendEnabled = computed(() => {
    return !props.isBlocked && chatBoxFileListRef.value?.isAllUploaded && hasTextInput.value;
});

const emit = defineEmits<{
    (e: 'update:modelValue', value: string): void;
    (e: 'submit'): void;
    (e: 'stop'): void;
    (e: 'fileClick', file: FileInfo): void;
}>();

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

const handleInput = (event: Event) => {
  const target = event.target as HTMLTextAreaElement;
  emit('update:modelValue', target.value);
  resizeTextarea(target.value);
};

const uploadFile = () => {
    chatBoxFileListRef.value?.uploadFile();
};

const handleConnectorBannerClose = () => {
  isConnectorBannerClosed.value = true;
};

// Track which commands have already been auto-detected (prevent repeated toasts)
const detectedCommands = ref<Set<string>>(new Set());

watch(() => props.modelValue, (value) => {
    hasTextInput.value = value.trim() !== '';

    // Reset detected commands when input is cleared (e.g. after send)
    if (!value.trim()) {
      detectedCommands.value.clear();
      return;
    }

    // Auto-detect slash commands: at start of message or after newline/space
    const commandMatch = value.match(/(?:^|[\s\n])\/([a-zA-Z0-9_-]+)/);
    if (commandMatch && Object.keys(commandSkillMap.value).length > 0) {
      const command = commandMatch[1].toLowerCase();
      const skillId = commandSkillMap.value[command];
      if (skillId && !detectedCommands.value.has(command)) {
        detectedCommands.value.add(command);
        selectSkill(skillId);
        showInfoToast(t('Skill auto-activated: {command}', { command: `/${command}` }));
      }
    }
});

watch(() => props.modelValue, async () => {
  await nextTick();
  resizeTextarea(props.modelValue);
});

watch(
  () => props.showConnectorBanner,
  (show) => {
    if (!show) {
      isConnectorBannerClosed.value = false;
    }
  }
);

onMounted(async () => {
  resizeTextarea();
  try {
    commandSkillMap.value = await getCommandMap();
  } catch (e) {
    console.warn('Failed to load command map for slash command detection:', e);
  }
});
</script>

<style scoped>
.chatbox-wrapper {
    padding-bottom: 12px;
    position: relative;
    z-index: 2;
    display: flex;
    flex-direction: column;
    width: 100%;
}

.chatbox-wrapper.expand-up {
    display: flex;
    flex-direction: column;
    justify-content: flex-end;
}

.chatbox-shell {
    display: flex;
    flex-direction: column;
    width: 100%;
    position: relative;
    background: var(--background-gray-main);
}

.chatbox-container {
    display: flex;
    flex-direction: column;
    gap: 12px;
    position: relative;
    padding: 12px 0;
    width: 100%;
    z-index: 2;
    max-height: 300px;
    background: var(--fill-input-chat);
    border-radius: 22px;
    border: 1px solid rgba(0, 0, 0, 0.08);
    box-shadow: 0 12px 32px rgba(0, 0, 0, 0.02);
    overflow: hidden;
    transition: border-color 0.15s ease, box-shadow 0.15s ease;
}

.chatbox-container:hover {
    border-color: rgba(0, 0, 0, 0.2);
}

.chatbox-container:focus-within {
    border-color: rgba(0, 0, 0, 0.2);
}

:global([data-theme='dark']) .chatbox-container {
    border-color: var(--border-main);
}

:global([data-theme='dark']) .chatbox-container:hover,
:global([data-theme='dark']) .chatbox-container:focus-within {
    border-color: var(--border-dark);
}

.chatbox-input-area {
    padding-left: 16px;
    padding-right: 8px;
    min-height: 50px;
    max-height: 216px;
}

.chatbox-textarea {
    display: flex;
    border-radius: 8px;
    flex: 1;
    background: transparent;
    padding: 0;
    padding-top: 1px;
    padding-right: 8px;
    border: 0;
    width: 100%;
    font-size: 15px;
    line-height: 24px;
    color: var(--text-primary);
    box-shadow: none;
    resize: none;
    min-height: 40px;
    outline: none;
    transition: padding-right 0.2s ease;
}

/* Custom scrollbar - only visible on hover */
.chatbox-textarea::-webkit-scrollbar {
    width: 6px;
}

.chatbox-textarea::-webkit-scrollbar-track {
    background: transparent;
    border-radius: 10px;
}

.chatbox-textarea::-webkit-scrollbar-thumb {
    background: transparent;
    border-radius: 10px;
    transition: background 0.2s ease;
}

.chatbox-textarea:hover::-webkit-scrollbar-thumb {
    background: rgba(0, 0, 0, 0.15);
}

.chatbox-textarea::-webkit-scrollbar-thumb:hover {
    background: rgba(0, 0, 0, 0.25);
}

:global([data-theme='dark']) .chatbox-textarea:hover::-webkit-scrollbar-thumb {
    background: rgba(255, 255, 255, 0.15);
}

:global([data-theme='dark']) .chatbox-textarea::-webkit-scrollbar-thumb:hover {
    background: rgba(255, 255, 255, 0.25);
}

/* Firefox scrollbar styling */
.chatbox-textarea {
    scrollbar-width: thin;
    scrollbar-color: transparent transparent;
}

.chatbox-textarea:hover {
    scrollbar-color: rgba(0, 0, 0, 0.15) transparent;
}

:global([data-theme='dark']) .chatbox-textarea:hover {
    scrollbar-color: rgba(255, 255, 255, 0.15) transparent;
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
    background: linear-gradient(135deg, #000000 0%, #0a0a0a 100%);
    color: var(--text-white);
    box-shadow: 0 10px 20px rgba(0, 0, 0, 0.28);
}

.chatbox-send-btn.enabled:hover {
    box-shadow: 0 12px 24px rgba(0, 0, 0, 0.36);
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
    background: linear-gradient(135deg, #000000 0%, #0a0a0a 100%);
    color: var(--text-white);
    box-shadow: 0 10px 20px rgba(0, 0, 0, 0.28);
}

.chatbox-stop-btn:hover {
    box-shadow: 0 12px 24px rgba(0, 0, 0, 0.36);
}

.chatbox-connector-row {
    margin-top: -22px;
    padding: 29px 20px 7px;
    background: rgba(55, 53, 47, 0.02);
    border-left: 1px solid var(--border-light);
    border-right: 1px solid var(--border-light);
    border-bottom: 1px solid var(--border-light);
    min-height: 0;
    display: flex;
    align-items: center;
    border-bottom-left-radius: 22px;
    border-bottom-right-radius: 22px;
    transition: border-color 0.15s ease;
    cursor: pointer;
}

:deep(.chatbox-connector-row .connector-banner) {
    margin-bottom: 0;
}

.chatbox-connector-row:hover {
    border-left-color: var(--border-main);
    border-right-color: var(--border-main);
    border-bottom-color: var(--border-main);
}

:global([data-theme='dark']) .chatbox-connector-row {
    background: rgba(255, 255, 255, 0.02);
}

:global(.dark) .chatbox-connector-row {
    background: rgba(255, 255, 255, 0.03);
}

:global([data-theme='dark']) .chatbox-connector-row:hover,
:global(.dark) .chatbox-connector-row:hover {
    border-left-color: var(--border-dark);
    border-right-color: var(--border-dark);
    border-bottom-color: var(--border-dark);
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
    background: rgba(0, 0, 0, 0.08);
    border: 1px solid rgba(0, 0, 0, 0.2);
    color: #000000;
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
    color: #000000;
    cursor: pointer;
    padding: 0;
    transition: background 0.1s ease;
}

.session-skill-remove:hover {
    background: rgba(59, 130, 246, 0.15);
}
</style>
