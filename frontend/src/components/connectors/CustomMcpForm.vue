<template>
  <form class="custom-form" @submit.prevent="handleSubmit">
    <div class="custom-form-field">
      <label class="custom-form-label">{{ t('Name') }} *</label>
      <input
        v-model="formData.name"
        type="text"
        class="custom-form-input"
        :placeholder="t('My MCP Server')"
        maxlength="100"
        required
      />
    </div>

    <div class="custom-form-field">
      <label class="custom-form-label">{{ t('Transport') }} *</label>
      <select v-model="formData.transport" class="custom-form-input" required>
        <option value="stdio">stdio</option>
        <option value="sse">SSE</option>
        <option value="streamable-http">Streamable HTTP</option>
      </select>
    </div>

    <div v-if="formData.transport === 'stdio'" class="custom-form-field">
      <label class="custom-form-label">{{ t('Command') }} *</label>
      <select v-model="formData.command" class="custom-form-input" required>
        <option value="">{{ t('Select command...') }}</option>
        <option v-for="cmd in allowedCommands" :key="cmd" :value="cmd">{{ cmd }}</option>
      </select>
    </div>

    <div v-if="formData.transport === 'stdio'" class="custom-form-field">
      <label class="custom-form-label">{{ t('Arguments') }}</label>
      <input
        v-model="argsString"
        type="text"
        class="custom-form-input"
        :placeholder="t('Comma-separated args, e.g. -y,@modelcontextprotocol/server-everything')"
      />
    </div>

    <div v-if="formData.transport !== 'stdio'" class="custom-form-field">
      <label class="custom-form-label">{{ t('URL') }} *</label>
      <input
        v-model="formData.url"
        type="url"
        class="custom-form-input"
        placeholder="https://mcp-server.example.com/sse"
        maxlength="2048"
        :required="formData.transport !== 'stdio'"
      />
    </div>

    <div v-if="formData.transport !== 'stdio'" class="custom-form-field">
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
      <label class="custom-form-label">{{ t('Environment Variables') }}</label>
      <div v-for="(envVar, idx) in envVars" :key="idx" class="custom-form-kv-row">
        <input v-model="envVar.key" class="custom-form-input custom-form-kv-key" :placeholder="t('Key')" />
        <input v-model="envVar.value" class="custom-form-input custom-form-kv-value" :placeholder="t('Value')" />
        <button type="button" class="custom-form-kv-remove" @click="removeEnvVar(idx)">
          <X :size="14" />
        </button>
      </div>
      <button v-if="envVars.length < 20" type="button" class="custom-form-add-btn" @click="addEnvVar">
        <Plus :size="14" /> {{ t('Add Env Var') }}
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
import type { CreateCustomMcpRequest } from '@/api/connectors';

const { t } = useI18n();

const emit = defineEmits<{
  (e: 'submit', data: CreateCustomMcpRequest): void;
  (e: 'cancel'): void;
}>();

const allowedCommands = [
  'npx', 'node', 'python', 'python3', 'uvx', 'docker',
  'deno', 'bun', 'tsx', 'ts-node', 'pipx',
];

const formData = reactive({
  name: '',
  transport: 'stdio',
  command: '',
  url: '',
  description: '',
});

const argsString = ref('');
const headers = ref<Array<{ key: string; value: string }>>([]);
const envVars = ref<Array<{ key: string; value: string }>>([]);

const isValid = computed(() => {
  if (!formData.name.trim()) return false;
  if (formData.transport === 'stdio' && !formData.command) return false;
  if (formData.transport !== 'stdio') {
    if (!formData.url.trim()) return false;
    if (!formData.url.startsWith('http://') && !formData.url.startsWith('https://')) return false;
  }
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

function addEnvVar() {
  if (envVars.value.length < 20) {
    envVars.value.push({ key: '', value: '' });
  }
}

function removeEnvVar(idx: number) {
  envVars.value.splice(idx, 1);
}

function kvToObj(arr: Array<{ key: string; value: string }>): Record<string, string> {
  const obj: Record<string, string> = {};
  for (const item of arr) {
    if (item.key.trim()) {
      obj[item.key.trim()] = item.value;
    }
  }
  return obj;
}

function handleSubmit() {
  if (!isValid.value) return;
  const parsedArgs = argsString.value
    .split(',')
    .map((a) => a.trim())
    .filter(Boolean);
  const headersObj = kvToObj(headers.value);
  const envObj = kvToObj(envVars.value);

  emit('submit', {
    name: formData.name.trim(),
    transport: formData.transport,
    command: formData.transport === 'stdio' ? formData.command : undefined,
    args: parsedArgs.length > 0 ? parsedArgs : undefined,
    url: formData.transport !== 'stdio' ? formData.url.trim() : undefined,
    headers: Object.keys(headersObj).length > 0 ? headersObj : undefined,
    env: Object.keys(envObj).length > 0 ? envObj : undefined,
    description: formData.description.trim() || undefined,
  });
  // Reset form
  formData.name = '';
  formData.transport = 'stdio';
  formData.command = '';
  formData.url = '';
  formData.description = '';
  argsString.value = '';
  headers.value = [];
  envVars.value = [];
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
  background: linear-gradient(135deg, #3b82f6, #2563eb);
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
