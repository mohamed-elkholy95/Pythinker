<template>
  <div class="profile-settings">
    <!-- Profile Header -->
    <div class="profile-header">
      <div class="avatar-section">
        <div class="avatar-wrapper">
          <div class="avatar-ring"></div>
          <div class="avatar">{{ avatarLetter }}</div>
        </div>
      </div>

      <div class="name-edit-section">
        <label class="field-label">{{ t('Name') }}</label>
        <div class="name-input-wrapper">
          <input
            maxlength="20"
            class="name-input"
            v-model="localFullname"
            @blur="handleFullnameSubmit"
            @keyup.enter="handleFullnameSubmit"
            :placeholder="t('Unknown User')"
          />
          <button
            v-if="localFullname"
            class="clear-btn"
            @click="clearFullname"
          >
            <X class="w-4 h-4" />
          </button>
        </div>
        <span class="char-count">{{ localFullname.length }}/20</span>
      </div>
    </div>

    <!-- Profile Details -->
    <div class="profile-details">
      <!-- Email -->
      <div class="detail-row">
        <div class="detail-icon">
          <Mail class="w-4 h-4" />
        </div>
        <div class="detail-content">
          <span class="detail-label">{{ t('Email') }}</span>
          <span class="detail-value">{{ currentUser?.email || t('No email') }}</span>
        </div>
        <div class="detail-badge badge-readonly">
          <Lock class="w-3 h-3" />
          <span>Read only</span>
        </div>
      </div>

      <!-- Password -->
      <div class="detail-row">
        <div class="detail-icon">
          <KeyRound class="w-4 h-4" />
        </div>
        <div class="detail-content">
          <span class="detail-label">{{ t('Password') }}</span>
          <div class="password-dots">
            <span v-for="i in 8" :key="i" class="dot"></span>
          </div>
        </div>
        <button class="update-btn" @click="openChangePasswordDialog">
          <Pencil class="w-3.5 h-3.5" />
          <span>{{ t('Update Password') }}</span>
        </button>
      </div>
    </div>

    <!-- Two-Factor Authentication -->
    <div class="totp-section">
      <div class="totp-header">
        <div class="totp-icon-box">
          <ShieldCheck class="w-[18px] h-[18px]" />
        </div>
        <div class="totp-header-text">
          <h4 class="totp-title">Two-Factor Authentication</h4>
          <p class="totp-desc">
            {{ currentUser?.totp_enabled
              ? 'Your account is protected with an authenticator app.'
              : 'Add an extra layer of security with an authenticator app.'
            }}
          </p>
        </div>
        <span
          v-if="currentUser?.totp_enabled"
          class="totp-badge totp-badge-enabled"
        >Enabled</span>
        <span v-else class="totp-badge totp-badge-disabled">Disabled</span>
      </div>

      <!-- Setup Flow -->
      <template v-if="!currentUser?.totp_enabled">
        <!-- Step 1: Not started -->
        <div v-if="!totpSetupData" class="totp-action">
          <button class="totp-setup-btn" :disabled="isTotpLoading" @click="handleTotpSetup">
            <LoaderCircle v-if="isTotpLoading" :size="14" class="animate-spin" />
            <ShieldPlus v-else class="w-3.5 h-3.5" />
            <span>{{ isTotpLoading ? 'Setting up...' : 'Enable 2FA' }}</span>
          </button>
        </div>

        <!-- Step 2: QR code + verify -->
        <div v-else class="totp-setup-flow">
          <div class="totp-qr-section">
            <p class="totp-instruction">Scan this QR code with your authenticator app (Google Authenticator, Authy, etc.)</p>
            <div class="totp-qr-wrapper">
              <canvas ref="qrCanvasRef" class="totp-qr-canvas" />
            </div>
            <div class="totp-secret-row">
              <span class="totp-secret-label">Manual entry key:</span>
              <code class="totp-secret-value">{{ totpSetupData.secret }}</code>
              <button class="totp-copy-btn" @click="copySecret">
                <Check v-if="isSecretCopied" class="w-3 h-3" />
                <Copy v-else class="w-3 h-3" />
              </button>
            </div>
          </div>

          <div class="totp-verify-section">
            <label class="totp-verify-label">Enter the 6-digit code to verify</label>
            <div class="totp-verify-input-row">
              <input
                v-model="totpVerifyCode"
                class="totp-verify-input"
                inputmode="numeric"
                maxlength="6"
                placeholder="000000"
                :disabled="isTotpLoading"
                @input="onVerifyInput"
              />
              <button
                class="totp-verify-btn"
                :disabled="!isTotpCodeValid || isTotpLoading"
                @click="handleTotpVerify"
              >
                <LoaderCircle v-if="isTotpLoading" :size="14" class="animate-spin" />
                <span>Verify</span>
              </button>
            </div>
          </div>

          <button class="totp-cancel-link" @click="cancelTotpSetup">Cancel setup</button>
        </div>
      </template>

      <!-- Disable Flow -->
      <template v-else>
        <div class="totp-disable-section">
          <div v-if="!showDisableInput" class="totp-action">
            <button class="totp-disable-btn" @click="showDisableInput = true">
              <ShieldOff class="w-3.5 h-3.5" />
              <span>Disable 2FA</span>
            </button>
          </div>
          <div v-else class="totp-verify-section">
            <label class="totp-verify-label">Enter your current 2FA code to disable</label>
            <div class="totp-verify-input-row">
              <input
                v-model="totpDisableCode"
                class="totp-verify-input"
                inputmode="numeric"
                maxlength="6"
                placeholder="000000"
                :disabled="isTotpLoading"
                @input="onDisableInput"
              />
              <button
                class="totp-verify-btn totp-verify-btn-danger"
                :disabled="!isTotpDisableCodeValid || isTotpLoading"
                @click="handleTotpDisable"
              >
                <LoaderCircle v-if="isTotpLoading" :size="14" class="animate-spin" />
                <span>Disable</span>
              </button>
            </div>
            <button class="totp-cancel-link" @click="showDisableInput = false; totpDisableCode = ''">Cancel</button>
          </div>
        </div>
      </template>
    </div>

    <!-- Security Info -->
    <div class="security-info">
      <div class="security-icon">
        <ShieldCheck class="w-5 h-5" />
      </div>
      <div class="security-content">
        <h5 class="security-title">Account Security</h5>
        <p class="security-desc">
          Your password is encrypted and stored securely. We recommend using a strong, unique password.
        </p>
      </div>
    </div>

    <!-- Change Password Dialog -->
    <ChangePasswordDialog ref="changePasswordDialogRef" />
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { X, Mail, Lock, KeyRound, Pencil, ShieldCheck, ShieldPlus, ShieldOff, LoaderCircle, Copy, Check } from 'lucide-vue-next'
import QRCode from 'qrcode'
import { useAuth } from '../../composables/useAuth'
import { changeFullname, totpSetup, totpVerify, totpDisable, type TotpSetupResponse } from '../../api/auth'
import { showSuccessToast, showErrorToast } from '../../utils/toast'
import { AxiosError } from 'axios'
import ChangePasswordDialog from './ChangePasswordDialog.vue'

const { t } = useI18n()
const { currentUser, loadCurrentUser } = useAuth()

// Dialog refs
const changePasswordDialogRef = ref<InstanceType<typeof ChangePasswordDialog>>()

// ── TOTP 2FA State ──
const isTotpLoading = ref(false)
const totpSetupData = ref<TotpSetupResponse | null>(null)
const totpVerifyCode = ref('')
const totpDisableCode = ref('')
const showDisableInput = ref(false)
const isSecretCopied = ref(false)
const qrCanvasRef = ref<HTMLCanvasElement | null>(null)

const isTotpCodeValid = computed(() => /^\d{6}$/.test(totpVerifyCode.value))
const isTotpDisableCodeValid = computed(() => /^\d{6}$/.test(totpDisableCode.value))

// Strip non-digits and auto-submit at 6
const onVerifyInput = () => {
  totpVerifyCode.value = totpVerifyCode.value.replace(/\D/g, '').slice(0, 6)
  if (isTotpCodeValid.value) handleTotpVerify()
}
const onDisableInput = () => {
  totpDisableCode.value = totpDisableCode.value.replace(/\D/g, '').slice(0, 6)
  if (isTotpDisableCodeValid.value) handleTotpDisable()
}

const handleTotpSetup = async () => {
  isTotpLoading.value = true
  try {
    const data = await totpSetup()
    totpSetupData.value = data
    await nextTick()
    if (qrCanvasRef.value) {
      await QRCode.toCanvas(qrCanvasRef.value, data.provisioning_uri, {
        width: 200,
        margin: 2,
        color: { dark: '#000000', light: '#ffffff' },
      })
    }
  } catch (error: unknown) {
    const msg = error instanceof AxiosError ? error.response?.data?.message : 'Failed to set up 2FA'
    showErrorToast(msg || 'Failed to set up 2FA')
  } finally {
    isTotpLoading.value = false
  }
}

const handleTotpVerify = async () => {
  if (!isTotpCodeValid.value) return
  isTotpLoading.value = true
  try {
    await totpVerify({ code: totpVerifyCode.value })
    showSuccessToast('Two-factor authentication enabled!')
    totpSetupData.value = null
    totpVerifyCode.value = ''
    await loadCurrentUser()
  } catch (error: unknown) {
    totpVerifyCode.value = ''
    const msg = error instanceof AxiosError ? error.response?.data?.message : 'Invalid code'
    showErrorToast(msg || 'Invalid code. Please try again.')
  } finally {
    isTotpLoading.value = false
  }
}

const handleTotpDisable = async () => {
  if (!isTotpDisableCodeValid.value) return
  isTotpLoading.value = true
  try {
    await totpDisable({ code: totpDisableCode.value })
    showSuccessToast('Two-factor authentication disabled.')
    totpDisableCode.value = ''
    showDisableInput.value = false
    await loadCurrentUser()
  } catch (error: unknown) {
    totpDisableCode.value = ''
    const msg = error instanceof AxiosError ? error.response?.data?.message : 'Invalid code'
    showErrorToast(msg || 'Invalid code. Please try again.')
  } finally {
    isTotpLoading.value = false
  }
}

const cancelTotpSetup = () => {
  totpSetupData.value = null
  totpVerifyCode.value = ''
}

const copySecret = async () => {
  if (!totpSetupData.value) return
  try {
    await navigator.clipboard.writeText(totpSetupData.value.secret)
    isSecretCopied.value = true
    setTimeout(() => { isSecretCopied.value = false }, 2000)
  } catch {
    showErrorToast('Failed to copy to clipboard')
  }
}

// Local fullname state
const localFullname = ref(currentUser.value?.fullname || '')

// Watch for currentUser changes to sync localFullname
watch(currentUser, (newUser) => {
  if (newUser) {
    localFullname.value = newUser.fullname || ''
  }
}, { immediate: true })

// Update fullname function
const updateFullname = async (newFullname: string) => {
  // Skip if empty or same as current
  if (!newFullname.trim() || newFullname === currentUser.value?.fullname) {
    return
  }

  try {
    await changeFullname({ fullname: newFullname.trim() })
    // Refresh current user data to get updated info
    await loadCurrentUser()
    showSuccessToast(t('Full name updated successfully'))
  } catch (error: unknown) {
    // Reset local state to original value
    localFullname.value = currentUser.value?.fullname || ''

    // Show error message
    let errorMessage = t('Failed to update full name')
    if (error instanceof AxiosError && error.response?.data?.message) {
      errorMessage = error.response.data.message
    } else if (error instanceof Error) {
      errorMessage = error.message
    }
    showErrorToast(errorMessage)
  }
}

// Handle input change on blur or Enter
const handleFullnameSubmit = () => {
  updateFullname(localFullname.value)
}

// Clear fullname input
const clearFullname = () => {
  localFullname.value = ''
}

// Get first letter of user's fullname for avatar display
const avatarLetter = computed(() => {
  return currentUser.value?.fullname?.charAt(0)?.toUpperCase() || 'U'
})

// Open change password dialog
const openChangePasswordDialog = () => {
  changePasswordDialogRef.value?.open()
}
</script>

<style scoped>
.profile-settings {
  display: flex;
  flex-direction: column;
  gap: 24px;
  width: 100%;
  animation: fadeIn 0.4s ease-out;
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(8px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* Profile Header */
.profile-header {
  display: flex;
  align-items: flex-start;
  gap: 24px;
  padding: 24px;
  background: linear-gradient(135deg, var(--fill-blue) 0%, rgba(59, 130, 246, 0.02) 100%);
  border: 1px solid rgba(59, 130, 246, 0.1);
  border-radius: 16px;
}

.avatar-section {
  flex-shrink: 0;
}

.avatar-wrapper {
  position: relative;
}

.avatar-ring {
  position: absolute;
  inset: -3px;
  border-radius: 50%;
  background: linear-gradient(135deg, var(--text-brand) 0%, #1a1a1a 100%);
  opacity: 0.3;
}

.avatar {
  position: relative;
  width: 80px;
  height: 80px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 36px;
  font-weight: 700;
  color: #fff;
  background: linear-gradient(135deg, var(--text-brand) 0%, #1a1a1a 100%);
  border-radius: 50%;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.3);
}

.name-edit-section {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.field-label {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.name-input-wrapper {
  position: relative;
  display: flex;
  align-items: center;
}

.name-input {
  width: 100%;
  max-width: 280px;
  height: 44px;
  padding: 0 40px 0 16px;
  background: var(--background-white-main);
  border: 1px solid var(--border-main);
  border-radius: 10px;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  transition: all 0.2s ease;
}

.name-input:hover {
  border-color: var(--border-dark);
}

.name-input:focus {
  outline: none;
  border-color: var(--text-brand);
  box-shadow: 0 0 0 3px var(--fill-blue);
}

.name-input::placeholder {
  color: var(--text-disable);
  font-weight: 400;
}

.clear-btn {
  position: absolute;
  right: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  color: var(--icon-tertiary);
  border-radius: 6px;
  transition: all 0.2s ease;
}

.clear-btn:hover {
  background: var(--fill-tsp-white-dark);
  color: var(--icon-secondary);
}

.char-count {
  font-size: 11px;
  color: var(--text-tertiary);
}

/* Profile Details */
.profile-details {
  display: flex;
  flex-direction: column;
  background: var(--fill-tsp-white-main);
  border: 1px solid var(--border-light);
  border-radius: 14px;
  overflow: hidden;
}

.detail-row {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 16px 20px;
}

.detail-row:not(:last-child) {
  border-bottom: 1px solid var(--border-light);
}

.detail-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  background: var(--fill-tsp-white-dark);
  border-radius: 10px;
  color: var(--icon-secondary);
  flex-shrink: 0;
}

.detail-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.detail-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
}

.detail-value {
  font-size: 14px;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.password-dots {
  display: flex;
  align-items: center;
  gap: 4px;
}

.dot {
  width: 8px;
  height: 8px;
  background: var(--icon-tertiary);
  border-radius: 50%;
}

.detail-badge {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 10px;
  font-size: 11px;
  font-weight: 500;
  border-radius: 6px;
}

.badge-readonly {
  background: var(--fill-tsp-white-dark);
  color: var(--text-tertiary);
}

.update-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
  background: var(--background-white-main);
  border: 1px solid var(--border-main);
  border-radius: 8px;
  transition: all 0.2s ease;
}

.update-btn:hover {
  background: var(--fill-tsp-white-main);
  border-color: var(--border-dark);
}

/* ─── TOTP 2FA Section ─── */
.totp-section {
  background: var(--fill-tsp-white-main);
  border: 1px solid var(--border-light);
  border-radius: 14px;
  padding: 20px;
}

.totp-header {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--border-light);
  margin-bottom: 16px;
}

.totp-icon-box {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  background: rgba(59, 130, 246, 0.08);
  border-radius: 10px;
  color: var(--text-brand);
  flex-shrink: 0;
}

.totp-header-text {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.totp-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.totp-desc {
  font-size: 12px;
  color: var(--text-tertiary);
  margin: 0;
  line-height: 1.4;
}

.totp-badge {
  flex-shrink: 0;
  padding: 4px 10px;
  font-size: 11px;
  font-weight: 600;
  border-radius: 6px;
  letter-spacing: 0.02em;
}

.totp-badge-enabled {
  background: var(--function-success-tsp);
  color: var(--function-success);
}

.totp-badge-disabled {
  background: var(--fill-tsp-white-dark);
  color: var(--text-tertiary);
}

.totp-action {
  display: flex;
  gap: 10px;
}

.totp-setup-btn,
.totp-disable-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  font-size: 13px;
  font-weight: 600;
  border-radius: 8px;
  transition: all 0.2s ease;
  cursor: pointer;
}

.totp-setup-btn {
  background: var(--text-brand);
  color: #fff;
  border: none;
}

.totp-setup-btn:hover:not(:disabled) {
  opacity: 0.9;
}

.totp-setup-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.totp-disable-btn {
  background: var(--function-error-tsp);
  color: var(--function-error);
  border: 1px solid transparent;
}

.totp-disable-btn:hover {
  background: rgba(239, 68, 68, 0.15);
}

/* Setup flow */
.totp-setup-flow {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.totp-qr-section {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}

.totp-instruction {
  font-size: 13px;
  color: var(--text-secondary);
  text-align: center;
  margin: 0;
  line-height: 1.4;
}

.totp-qr-wrapper {
  padding: 12px;
  background: #fff;
  border: 1px solid var(--border-light);
  border-radius: 12px;
}

.totp-qr-canvas {
  display: block;
  width: 200px;
  height: 200px;
}

.totp-secret-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: var(--fill-tsp-white-dark);
  border: 1px solid var(--border-light);
  border-radius: 8px;
  max-width: 100%;
  overflow: hidden;
}

.totp-secret-label {
  font-size: 11px;
  color: var(--text-tertiary);
  white-space: nowrap;
  flex-shrink: 0;
}

.totp-secret-value {
  font-family: 'SF Mono', 'Fira Code', monospace;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: 0.05em;
  user-select: all;
  overflow: hidden;
  text-overflow: ellipsis;
}

.totp-copy-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  color: var(--icon-tertiary);
  border-radius: 4px;
  flex-shrink: 0;
  transition: all 0.15s ease;
}

.totp-copy-btn:hover {
  color: var(--icon-primary);
  background: var(--fill-tsp-white-main);
}

/* Verify / Disable input */
.totp-verify-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.totp-verify-label {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary);
}

.totp-verify-input-row {
  display: flex;
  gap: 8px;
}

.totp-verify-input {
  flex: 1;
  max-width: 160px;
  height: 40px;
  padding: 0 14px;
  background: var(--fill-input-chat);
  border: 1px solid var(--border-main);
  border-radius: 8px;
  font-family: 'SF Mono', 'Fira Code', monospace;
  font-size: 18px;
  font-weight: 600;
  letter-spacing: 0.3em;
  text-align: center;
  color: var(--text-primary);
  transition: border-color 0.2s ease;
}

.totp-verify-input:focus {
  outline: none;
  border-color: var(--text-brand);
  box-shadow: 0 0 0 3px var(--fill-blue);
}

.totp-verify-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 0 18px;
  height: 40px;
  font-size: 13px;
  font-weight: 600;
  background: var(--text-brand);
  color: #fff;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.totp-verify-btn:hover:not(:disabled) {
  opacity: 0.9;
}

.totp-verify-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.totp-verify-btn-danger {
  background: var(--function-error);
}

.totp-cancel-link {
  align-self: flex-start;
  font-size: 12px;
  font-weight: 500;
  color: var(--text-tertiary);
  background: none;
  border: none;
  cursor: pointer;
  padding: 4px 0;
  transition: color 0.15s ease;
}

.totp-cancel-link:hover {
  color: var(--text-secondary);
}

.totp-disable-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* Security Info */
.security-info {
  display: flex;
  gap: 14px;
  padding: 16px;
  background: rgba(34, 197, 94, 0.05);
  border: 1px solid rgba(34, 197, 94, 0.15);
  border-radius: 12px;
}

.security-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  background: rgba(34, 197, 94, 0.1);
  border-radius: 10px;
  color: var(--function-success);
  flex-shrink: 0;
}

.security-content {
  flex: 1;
}

.security-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 4px;
}

.security-desc {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.4;
}
</style>
