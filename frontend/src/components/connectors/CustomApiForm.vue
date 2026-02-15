<template>
  <form class="custom-form" @submit.prevent="handleSubmit">
    <div class="custom-form-field">
      <label class="custom-form-label">{{ t('Name') }} *</label>
      <input
        v-model="formData.name"
        type="text"
        class="custom-form-input"
        :placeholder="t('My API Connector')"
        maxlength="100"
        required
      />
    </div>

    <div class="custom-form-field">
      <label class="custom-form-label">{{ t('Base URL') }} *</label>
      <input
        v-model="formData.base_url"
        type="url"
        class="custom-form-input"
        placeholder="https://api.example.com"
        maxlength="2048"
        required
      />
    </div>

    <div class="custom-form-field">
      <label class="custom-form-label">{{ t('Auth Type') }}</label>
      <select v-model="formData.auth_type" class="custom-form-input">
        <option value="none">{{ t('None') }}</option>
        <option value="api_key">{{ t('API Key') }}</option>
        <option value="bearer">{{ t('Bearer Token') }}</option>
        <option value="basic">{{ t('Basic Auth') }}</option>
      </select>
    </div>

    <div v-if="formData.auth_type !== 'none'" class="custom-form-field">
      <label class="custom-form-label">{{ t('API Key / Token') }} *</label>
      <input
        v-model="formData.api_key"
        type="password"
        class="custom-form-input"
        :placeholder="t('Enter your key or token')"
        :required="formData.auth_type !== 'none'"
      />
    </div>

    <div class="custom-form-field">
      <label class="custom-form-label">{{ t('Headers') }}</label>
      <div v-for="(header, idx) in headers" :key="idx" class="custom-form-kv-row">
        <input v-model="header.key" class="custom-form-input custom-form-kv-key" :placeholder="t('Key')" />
        <input v-model="header.value" class="custom-form-input custom-form-kv-value" :placeholder="t('Value')" />
        <button type="button" class="custom-form-kv-remove" @click="removeHeader(idx)">
          <X :size="14" />
        </button>
      </div>
      <button v-if="headers.length < 20" type="button" class="custom-form-add-btn" @click="addHeader">
        <Plus :size="14" /> {{ t('Add Header') }}
      </button>
    </div>

    <div class="custom-form-field">
      <label class="custom-form-label">{{ t('Description') }}</label>
      <input
        v-model="formData.description"
        type="text"
        class="custom-form-input"
        :placeholder="t('Optional description')"
        maxlength="500"
      />
    </div>

    <div class="custom-form-actions">
      <button type="button" class="custom-form-cancel" @click="$emit('cancel')">{{ t('Cancel') }}</button>
      <button type="submit" class="custom-form-submit" :disabled="!isValid">{{ t('Create') }}</button>
    </div>
  </form>
</template>

<script setup lang="ts">
import { ref, reactive, computed } from 'vue';
import { useI18n } from 'vue-i18n';
import { X, Plus } from 'lucide-vue-next';
import type { CreateCustomApiRequest } from '@/api/connectors';

const { t } = useI18n();

const emit = defineEmits<{
  (e: 'submit', data: CreateCustomApiRequest): void;
  (e: 'cancel'): void;
}>();

const formData = reactive({
  name: '',
  base_url: '',
  auth_type: 'none',
  api_key: '',
  description: '',
});

const headers = ref<Array<{ key: string; value: string }>>([]);

const isValid = computed(() => {
  if (!formData.name.trim()) return false;
  if (!formData.base_url.trim()) return false;
  if (!formData.base_url.startsWith('http://') && !formData.base_url.startsWith('https://')) return false;
  if (formData.auth_type !== 'none' && !formData.api_key.trim()) return false;
  return true;
});

function addHeader() {
  if (headers.value.length < 20) {
    headers.value.push({ key: '', value: '' });
  }
}

function removeHeader(idx: number) {
  headers.value.splice(idx, 1);
}

function handleSubmit() {
  if (!isValid.value) return;
  const headersObj: Record<string, string> = {};
  for (const h of headers.value) {
    if (h.key.trim()) {
      headersObj[h.key.trim()] = h.value;
    }
  }
  emit('submit', {
    name: formData.name.trim(),
    base_url: formData.base_url.trim(),
    auth_type: formData.auth_type,
    api_key: formData.api_key || undefined,
    headers: Object.keys(headersObj).length > 0 ? headersObj : undefined,
    description: formData.description.trim() || undefined,
  });
  // Reset form
  formData.name = '';
  formData.base_url = '';
  formData.auth_type = 'none';
  formData.api_key = '';
  formData.description = '';
  headers.value = [];
}
</script>

<style scoped>
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

.custom-form-kv-row {
  display: flex;
  gap: 6px;
  align-items: center;
  margin-top: 4px;
}

.custom-form-kv-key {
  flex: 1;
}

.custom-form-kv-value {
  flex: 2;
}

.custom-form-kv-remove {
  width: 28px;
  height: 28px;
  border-radius: 6px;
  border: 1px solid var(--border-main);
  background: transparent;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: var(--text-tertiary);
  flex-shrink: 0;
}

.custom-form-kv-remove:hover {
  background: #fee2e2;
  color: #ef4444;
  border-color: #fecaca;
}

.custom-form-add-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  font-size: 12px;
  color: var(--text-secondary);
  border: 1px dashed var(--border-main);
  border-radius: 6px;
  background: transparent;
  cursor: pointer;
  margin-top: 4px;
  width: fit-content;
}

.custom-form-add-btn:hover {
  border-color: var(--border-dark);
  color: var(--text-primary);
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
}

.custom-form-submit:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.custom-form-submit:not(:disabled):hover {
  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3);
}
</style>
