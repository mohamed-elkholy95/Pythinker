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
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { X, Mail, Lock, KeyRound, Pencil, ShieldCheck } from 'lucide-vue-next'
import { useAuth } from '../../composables/useAuth'
import { changeFullname } from '../../api/auth'
import { showSuccessToast, showErrorToast } from '../../utils/toast'
import ChangePasswordDialog from './ChangePasswordDialog.vue'

const { t } = useI18n()
const { currentUser, loadCurrentUser } = useAuth()

// Dialog refs
const changePasswordDialogRef = ref<InstanceType<typeof ChangePasswordDialog>>()

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
  } catch (error: any) {
    // Reset local state to original value
    localFullname.value = currentUser.value?.fullname || ''

    // Show error message
    const errorMessage = error?.response?.data?.message || error?.message || t('Failed to update full name')
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
  background: linear-gradient(135deg, var(--text-brand) 0%, #60a5fa 100%);
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
  background: linear-gradient(135deg, var(--text-brand) 0%, #60a5fa 100%);
  border-radius: 50%;
  box-shadow: 0 4px 16px rgba(59, 130, 246, 0.3);
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
