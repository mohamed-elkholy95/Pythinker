<template>
  <div class="ai-panel">
    <div class="ai-section">
      <div class="section-title">Generate Image</div>
      <textarea
        v-model="generatePrompt"
        class="ai-textarea"
        rows="3"
        placeholder="Describe the image you want to create..."
        :disabled="generating"
      />
      <button
        class="ai-btn primary"
        :disabled="!generatePrompt.trim() || generating"
        @click="handleGenerate"
      >
        <Loader2 v-if="generating && activeAction === 'generate'" :size="14" class="spin" />
        <Sparkles v-else :size="14" />
        <span>Generate</span>
      </button>
    </div>

    <div class="ai-divider" />

    <div class="ai-section">
      <div class="section-title">AI Canvas Edit</div>
      <textarea
        v-model="editPrompt"
        class="ai-textarea"
        rows="3"
        placeholder="Describe what to change on the canvas..."
        :disabled="generating"
      />
      <button
        class="ai-btn primary"
        :disabled="!editPrompt.trim() || !projectId || generating"
        @click="handleEdit"
      >
        <Loader2 v-if="generating && activeAction === 'edit'" :size="14" class="spin" />
        <Wand2 v-else :size="14" />
        <span>Apply</span>
      </button>
    </div>

    <div v-if="error" class="ai-error">
      <AlertCircle :size="14" />
      <span>{{ error }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { Sparkles, Wand2, Loader2, AlertCircle } from 'lucide-vue-next'
import { useCanvasAI } from '@/composables/useCanvasAI'
import type { CanvasProject } from '@/types/canvas'

const props = defineProps<{
  projectId: string | null
}>()

const emit = defineEmits<{
  (e: 'image-generated', urls: string[]): void
  (e: 'project-updated', project: CanvasProject): void
}>()

const { generating, error, generateImage, applyAIEdit } = useCanvasAI()

const generatePrompt = ref('')
const editPrompt = ref('')
const activeAction = ref<'generate' | 'edit' | null>(null)

async function handleGenerate() {
  if (!generatePrompt.value.trim()) return
  activeAction.value = 'generate'
  const urls = await generateImage(generatePrompt.value.trim())
  if (urls.length > 0) {
    emit('image-generated', urls)
    generatePrompt.value = ''
  }
  activeAction.value = null
}

async function handleEdit() {
  if (!editPrompt.value.trim() || !props.projectId) return
  activeAction.value = 'edit'
  const result = await applyAIEdit(props.projectId, editPrompt.value.trim())
  if (result) {
    emit('project-updated', result)
    editPrompt.value = ''
  }
  activeAction.value = null
}
</script>

<style scoped>
.ai-panel {
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 0;
}

.ai-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.section-title {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text-tertiary, #999999);
}

.ai-textarea {
  width: 100%;
  border: 1px solid var(--border-light, #e5e5e5);
  border-radius: 8px;
  padding: 8px 10px;
  font-size: 13px;
  color: var(--text-primary, #1a1a1a);
  background: var(--background-white-main, #ffffff);
  outline: none;
  resize: vertical;
  font-family: inherit;
  line-height: 1.4;
  transition: border-color 0.15s;
}

.ai-textarea:focus {
  border-color: var(--text-secondary, #666666);
}

.ai-textarea:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.ai-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  height: 32px;
  border: none;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.15s, opacity 0.15s;
}

.ai-btn.primary {
  background: var(--text-primary, #1a1a1a);
  color: var(--background-white-main, #ffffff);
}

.ai-btn.primary:hover:not(:disabled) {
  opacity: 0.85;
}

.ai-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.ai-divider {
  height: 1px;
  background: var(--border-light, #e5e5e5);
  margin: 16px 0;
}

.ai-error {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  padding: 8px 10px;
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: 8px;
  color: #dc2626;
  font-size: 12px;
  margin-top: 12px;
  line-height: 1.4;
}

.ai-error svg {
  flex-shrink: 0;
  margin-top: 1px;
}

.spin {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>
