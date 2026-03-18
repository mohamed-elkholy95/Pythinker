<template>
  <form class="custom-form" @submit.prevent="handleSubmit">
    <div class="custom-form-field">
      <label class="custom-form-label" for="custom-mcp-name">{{ t('Name') }} *</label>
      <input
        v-model="formData.name"
        id="custom-mcp-name"
        name="name"
        type="text"
        class="custom-form-input"
        :placeholder="t('My MCP Server')"
        maxlength="100"
        required
      />
    </div>

    <div class="custom-form-field">
      <label class="custom-form-label" for="custom-mcp-transport">{{ t('Transport') }} *</label>
      <select
        id="custom-mcp-transport"
        name="transport"
        v-model="formData.transport"
        class="custom-form-input"
        required
      >
        <option value="stdio">stdio</option>
        <option value="sse">SSE</option>
        <option value="streamable-http">Streamable HTTP</option>
      </select>
    </div>

    <div v-if="formData.transport === 'stdio'" class="custom-form-field">
      <label class="custom-form-label" for="custom-mcp-command">{{ t('Command') }} *</label>
      <select
        id="custom-mcp-command"
        name="command"
        v-model="formData.command"
        class="custom-form-input"
        required
      >
        <option value="">{{ t('Select command...') }}</option>
        <option v-for="cmd in allowedCommands" :key="cmd" :value="cmd">{{ cmd }}</option>
      </select>
    </div>

    <div v-if="formData.transport === 'stdio'" class="custom-form-field">
      <label class="custom-form-label" for="custom-mcp-args">{{ t('Arguments') }}</label>
      <input
        v-model="argsString"
        id="custom-mcp-args"
        name="args"
        type="text"
        class="custom-form-input"
        :placeholder="t('Comma-separated args, e.g. -y,@modelcontextprotocol/server-everything')"
      />
    </div>

    <div v-if="formData.transport !== 'stdio'" class="custom-form-field">
      <label class="custom-form-label" for="custom-mcp-url">{{ t('URL') }} *</label>
      <input
        v-model="formData.url"
        id="custom-mcp-url"
        name="url"
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
        <input
          v-model="header.key"
          :id="`custom-mcp-header-key-${idx}`"
          :name="`headers[${idx}][key]`"
          class="custom-form-input custom-form-kv-key"
          :placeholder="t('Key')"
        />
        <input
          v-model="header.value"
          :id="`custom-mcp-header-value-${idx}`"
          :name="`headers[${idx}][value]`"
          class="custom-form-input custom-form-kv-value"
          :placeholder="t('Value')"
        />
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
        <input
          v-model="envVar.key"
          :id="`custom-mcp-env-key-${idx}`"
          :name="`env[${idx}][key]`"
          class="custom-form-input custom-form-kv-key"
          :placeholder="t('Key')"
        />
        <input
          v-model="envVar.value"
          :id="`custom-mcp-env-value-${idx}`"
          :name="`env[${idx}][value]`"
          class="custom-form-input custom-form-kv-value"
          :placeholder="t('Value')"
        />
        <button type="button" class="custom-form-kv-remove" @click="removeEnvVar(idx)">
          <X :size="14" />
        </button>
      </div>
      <button v-if="envVars.length < 20" type="button" class="custom-form-add-btn" @click="addEnvVar">
        <Plus :size="14" /> {{ t('Add Env Var') }}
      </button>
    </div>

    <div class="custom-form-field">
      <label class="custom-form-label" for="custom-mcp-description">{{ t('Description') }}</label>
      <input
        v-model="formData.description"
        id="custom-mcp-description"
        name="description"
        type="text"
        class="custom-form-input"
        :placeholder="t('Optional description')"
        maxlength="500"
      />
    </div>

    <!-- Test Connection -->
    <div v-if="testResult" class="test-result" :class="testResult.success ? 'test-success' : 'test-error'">
      <CheckCircle v-if="testResult.success" class="w-4 h-4" />
      <AlertCircle v-else class="w-4 h-4" />
      <span v-if="testResult.success">
        Connected in {{ testResult.latency_ms }}ms — {{ testResult.tools_count }} tool(s) found
      </span>
      <span v-else>{{ testResult.error || 'Connection failed' }}</span>
    </div>

    <div class="custom-form-actions">
      <button
        type="button"
        class="custom-form-test"
        :disabled="!isValid || isTesting"
        @click="handleTestConnection"
      >
        {{ isTesting ? t('Testing...') : t('Test Connection') }}
      </button>
      <div class="actions-spacer" />
      <button type="button" class="custom-form-cancel" @click="$emit('cancel')">{{ t('Cancel') }}</button>
      <button type="submit" class="custom-form-submit" :disabled="!isValid">{{ t('Create') }}</button>
    </div>
  </form>
</template>

<script setup lang="ts">
import { ref, reactive, computed } from 'vue';
import { useI18n } from 'vue-i18n';
import { X, Plus, CheckCircle, AlertCircle } from 'lucide-vue-next';
import type { CreateCustomMcpRequest } from '@/api/connectors';
import type { McpTestConnectionResponse } from '@/api/mcp';
import { testMcpConnection } from '@/api/mcp';

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

const isTesting = ref(false);
const testResult = ref<McpTestConnectionResponse | null>(null);

async function handleTestConnection() {
  if (!isValid.value || isTesting.value) return;
  isTesting.value = true;
  testResult.value = null;
  try {
    const parsedArgs = argsString.value.split(',').map((a) => a.trim()).filter(Boolean);
    const headersObj = kvToObj(headers.value);
    const envObj = kvToObj(envVars.value);
    testResult.value = await testMcpConnection({
      name: formData.name.trim(),
      transport: formData.transport,
      command: formData.transport === 'stdio' ? formData.command : undefined,
      args: parsedArgs.length > 0 ? parsedArgs : undefined,
      url: formData.transport !== 'stdio' ? formData.url.trim() : undefined,
      headers: Object.keys(headersObj).length > 0 ? headersObj : undefined,
      env: Object.keys(envObj).length > 0 ? envObj : undefined,
    });
  } catch (e) {
    testResult.value = {
      success: false,
      latency_ms: 0,
      tools_count: 0,
      error: e instanceof Error ? e.message : 'Connection test failed',
    };
  } finally {
    isTesting.value = false;
  }
}

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
  testResult.value = null;
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

.custom-form-test {
  padding: 8px 14px;
  border-radius: 8px;
  border: 1px solid var(--border-main);
  background: var(--fill-tsp-gray-main);
  color: var(--text-secondary);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.15s;
}
.custom-form-test:hover:not(:disabled) {
  background: var(--fill-tsp-gray-hover);
  color: var(--text-primary);
}
.custom-form-test:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.actions-spacer {
  flex: 1;
}

.test-result {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 8px;
  font-size: 12px;
}
.test-success {
  background: rgba(34, 197, 94, 0.08);
  color: #16a34a;
}
.test-error {
  background: rgba(239, 68, 68, 0.08);
  color: #ef4444;
}
</style>
