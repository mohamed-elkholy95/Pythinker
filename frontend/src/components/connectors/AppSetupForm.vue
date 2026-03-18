<template>
  <div class="app-setup">
    <!-- Header with connector info -->
    <div class="app-setup-header">
      <button class="app-setup-back" @click="emit('cancel')">
        <ArrowLeft :size="16" />
      </button>
      <div class="app-setup-icon" :style="{ backgroundColor: connector.brand_color + '14' }">
        <component :is="iconComponent" :size="24" :color="connector.brand_color" />
      </div>
      <div>
        <div class="app-setup-name">{{ connector.name }}</div>
        <div class="app-setup-desc">{{ connector.description }}</div>
      </div>
    </div>

    <!-- Credential form -->
    <form class="custom-form" @submit.prevent="handleSubmit">
      <div
        v-for="field in connector.mcp_template?.credential_fields ?? []"
        :key="field.key"
        class="custom-form-field"
      >
        <label class="custom-form-label" :for="`setup-${field.key}`">
          {{ field.label }} <span v-if="field.required">*</span>
        </label>
        <p v-if="field.description" class="app-setup-field-desc">{{ field.description }}</p>
        <input
          :id="`setup-${field.key}`"
          v-model="credentials[field.key]"
          :type="field.secret ? 'password' : 'text'"
          class="custom-form-input"
          :placeholder="field.placeholder"
          :required="field.required"
          autocomplete="off"
        />
      </div>

      <!-- Error message -->
      <div v-if="errorMessage" class="test-result test-error">
        {{ errorMessage }}
      </div>

      <!-- Actions -->
      <div class="custom-form-actions">
        <button type="button" class="custom-form-cancel" @click="emit('cancel')">
          {{ t('Cancel') }}
        </button>
        <button type="submit" class="custom-form-submit" :disabled="!isValid || submitting">
          <template v-if="submitting">
            <span class="app-setup-spinner" />
            {{ t('Connecting...') }}
          </template>
          <template v-else>
            {{ t('Connect') }}
          </template>
        </button>
      </div>
    </form>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, reactive } from 'vue';
import { useI18n } from 'vue-i18n';
import {
  ArrowLeft,
  Globe,
  Mail,
  Calendar,
  HardDrive,
  MessageSquare,
  BookOpen,
  CheckSquare,
  LayoutGrid,
  Server,
  MapPin,
  type LucideIcon,
} from 'lucide-vue-next';
import type { CatalogConnector } from '@/api/connectors';

const ICON_MAP: Record<string, LucideIcon> = {
  Globe,
  Mail,
  Calendar,
  HardDrive,
  MessageSquare,
  BookOpen,
  CheckSquare,
  LayoutGrid,
  Server,
  MapPin,
};

const props = defineProps<{
  connector: CatalogConnector;
}>();

const emit = defineEmits<{
  (e: 'submit', connectorId: string, credentials: Record<string, string>): void;
  (e: 'cancel'): void;
}>();

const { t } = useI18n();

const iconComponent = computed(() => ICON_MAP[props.connector.icon] ?? Globe);

// Build reactive credentials object from template fields
const credentials = reactive<Record<string, string>>({});
if (props.connector.mcp_template) {
  for (const field of props.connector.mcp_template.credential_fields) {
    credentials[field.key] = '';
  }
}

const submitting = ref(false);
const errorMessage = ref<string | null>(null);

const isValid = computed(() => {
  if (!props.connector.mcp_template) return false;
  for (const field of props.connector.mcp_template.credential_fields) {
    if (field.required && !credentials[field.key]?.trim()) return false;
  }
  return true;
});

function handleSubmit() {
  if (!isValid.value || submitting.value) return;
  errorMessage.value = null;
  const creds: Record<string, string> = {};
  for (const [key, value] of Object.entries(credentials)) {
    if (value.trim()) creds[key] = value.trim();
  }
  emit('submit', props.connector.id, creds);
}

defineExpose({ setSubmitting, setError });

function setSubmitting(val: boolean) {
  submitting.value = val;
}

function setError(msg: string | null) {
  errorMessage.value = msg;
}
</script>

<style scoped>
.app-setup {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.app-setup-header {
  display: flex;
  align-items: center;
  gap: 12px;
}

.app-setup-back {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  border: 1px solid var(--border-main);
  background: transparent;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: var(--text-tertiary);
  flex-shrink: 0;
}

.app-setup-back:hover {
  background: var(--fill-tsp-gray-main);
  color: var(--text-primary);
}

.app-setup-icon {
  width: 44px;
  height: 44px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.app-setup-name {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  line-height: 1.3;
}

.app-setup-desc {
  font-size: 13px;
  color: var(--text-tertiary);
  line-height: 1.4;
}

.app-setup-field-desc {
  font-size: 12px;
  color: var(--text-tertiary);
  margin: 0;
  line-height: 1.4;
}

.app-setup-spinner {
  display: inline-block;
  width: 14px;
  height: 14px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: white;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
  margin-right: 4px;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

/* Reuse custom-form styles from CustomMcpForm */
.custom-form {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.custom-form-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.custom-form-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
}

.custom-form-input {
  padding: 8px 12px;
  border-radius: 8px;
  border: 1px solid var(--border-main);
  background: var(--background-white-main);
  color: var(--text-primary);
  font-size: 13px;
  outline: none;
  transition: border-color 0.15s;
}

.custom-form-input:focus {
  border-color: var(--border-dark);
}

.custom-form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding-top: 4px;
}

.custom-form-cancel {
  padding: 8px 16px;
  border-radius: 8px;
  border: 1px solid var(--border-main);
  background: transparent;
  color: var(--text-secondary);
  font-size: 13px;
  cursor: pointer;
}

.custom-form-cancel:hover {
  background: var(--fill-tsp-gray-main);
}

.custom-form-submit {
  padding: 8px 20px;
  border-radius: 8px;
  border: none;
  background: linear-gradient(135deg, #000000, #0a0a0a);
  color: white;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
}

.custom-form-submit:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.custom-form-submit:not(:disabled):hover {
  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3);
}

.test-result {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 8px;
  font-size: 12px;
}

.test-error {
  background: rgba(239, 68, 68, 0.08);
  color: #ef4444;
}
</style>
