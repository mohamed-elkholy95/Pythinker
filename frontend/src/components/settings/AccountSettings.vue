<template>
  <div class="account-settings">
    <!-- User Profile Card -->
    <div class="profile-card">
      <div class="profile-card-bg"></div>
      <div class="profile-content">
        <!-- Avatar Section -->
        <div class="avatar-section">
          <div class="avatar-wrapper">
            <div class="avatar-ring"></div>
            <div class="avatar">
              {{ avatarLetter }}
            </div>
            <div class="avatar-status"></div>
          </div>
        </div>

        <!-- User Info -->
        <div class="user-info">
          <h3 class="user-name">{{ currentUser?.fullname || t('Unknown User') }}</h3>
          <p class="user-email">{{ currentUser?.email || t('No email') }}</p>
        </div>

        <!-- Action Buttons -->
        <div class="profile-actions">
          <button class="action-btn action-btn-primary" @click="handleProfileClick">
            <UserCog class="w-[18px] h-[18px]" />
            <span>Edit Profile</span>
          </button>
          <button
            v-if="authProvider !== 'none'"
            class="action-btn action-btn-danger"
            @click="handleLogout"
          >
            <LogOut class="w-[18px] h-[18px]" />
            <span>Sign Out</span>
          </button>
        </div>
      </div>
    </div>

    <!-- Quick Stats -->
    <div class="quick-stats">
      <div class="stat-item">
        <div class="stat-icon">
          <Shield class="w-4 h-4" />
        </div>
        <div class="stat-content">
          <span class="stat-label">Account Status</span>
          <span class="stat-value stat-value-success">Active</span>
        </div>
      </div>
      <div class="stat-item">
        <div class="stat-icon">
          <Key class="w-4 h-4" />
        </div>
        <div class="stat-content">
          <span class="stat-label">Authentication</span>
          <span class="stat-value">{{ authProvider === 'none' ? 'Local' : authProvider || 'Email' }}</span>
        </div>
      </div>
    </div>

    <!-- Linked Channels -->
    <div class="linked-channels">
      <div class="channels-header">
        <div class="channels-icon-box">
          <Link2 class="w-[18px] h-[18px]" />
        </div>
        <div class="channels-header-text">
          <h4 class="channels-title">Linked Channels</h4>
          <p class="channels-desc">Connect messaging apps to access your sessions anywhere</p>
        </div>
      </div>

      <!-- Error banner -->
      <Transition name="slide-fade">
        <div v-if="channelError" class="channel-error" @click="channelError = null">
          <AlertCircle class="w-3.5 h-3.5" />
          <span>{{ channelError }}</span>
        </div>
      </Transition>

      <!-- Loading skeleton -->
      <div v-if="isLoadingChannels" class="channel-skeleton">
        <div class="skeleton-icon" />
        <div class="skeleton-lines">
          <div class="skeleton-line skeleton-line-short" />
          <div class="skeleton-line skeleton-line-long" />
        </div>
      </div>

      <!-- Telegram channel row -->
      <template v-else>
        <!-- State: Linked -->
        <Transition name="channel-swap" mode="out-in">
          <div v-if="telegramLinked" key="linked" class="channel-item channel-item-linked">
            <div class="channel-info">
              <div class="channel-icon channel-icon-telegram">
                <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor"><path d="M11.944 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0a12 12 0 0 0-.056 0zm4.962 7.224c.1-.002.321.023.465.14a.506.506 0 0 1 .171.325c.016.093.036.306.02.472-.18 1.898-.962 6.502-1.36 8.627-.168.9-.499 1.201-.82 1.23-.696.065-1.225-.46-1.9-.902-1.056-.693-1.653-1.124-2.678-1.8-1.185-.78-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 3.345-.479.33-.913.49-1.302.48-.428-.008-1.252-.241-1.865-.44-.752-.245-1.349-.374-1.297-.789.027-.216.325-.437.893-.663 3.498-1.524 5.83-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635z"/></svg>
                <div class="channel-linked-badge">
                  <Check class="w-2.5 h-2.5" />
                </div>
              </div>
              <div class="channel-details">
                <span class="channel-name">Telegram</span>
                <div class="channel-meta">
                  <span class="channel-status channel-status-linked">{{ telegramSenderId }}</span>
                  <span v-if="telegramLinkedAt" class="channel-linked-date">Linked {{ telegramLinkedAt }}</span>
                </div>
              </div>
            </div>
            <button
              class="unlink-btn"
              :class="{ 'unlink-btn-confirm': unlinkConfirm === 'telegram' }"
              :disabled="isUnlinking"
              @click="handleUnlink('telegram')"
            >
              {{ unlinkConfirm === 'telegram' ? 'Confirm?' : 'Unlink' }}
            </button>
          </div>

          <!-- State: Code display -->
          <div v-else-if="linkCode" key="code" class="channel-item channel-item-code">
            <!-- Countdown progress bar -->
            <div class="code-progress-track">
              <div
                class="code-progress-bar"
                :class="{ 'code-progress-urgent': countdownUrgent }"
                :style="{ width: `${countdownProgress * 100}%` }"
              />
            </div>

            <div class="code-body">
              <!-- Step instructions -->
              <div class="code-steps">
                <div class="code-step">
                  <span class="code-step-num">1</span>
                  <span class="code-step-text">Copy the command below</span>
                </div>
                <div class="code-step">
                  <span class="code-step-num">2</span>
                  <span class="code-step-text">Send it to your Telegram bot</span>
                </div>
              </div>

              <!-- Code field -->
              <div class="code-field">
                <code class="code-value">/link {{ linkCode }}</code>
                <button
                  class="copy-btn"
                  :class="{ 'copy-btn-success': isCopied }"
                  :title="isCopied ? 'Copied!' : 'Copy to clipboard'"
                  @click="copyCode"
                >
                  <Transition name="icon-swap" mode="out-in">
                    <Check v-if="isCopied" key="check" class="w-4 h-4" />
                    <Copy v-else key="copy" class="w-4 h-4" />
                  </Transition>
                </button>
              </div>

              <!-- Timer row -->
              <div class="code-timer-row">
                <div class="code-timer">
                  <Clock class="w-3 h-3" />
                  <span :class="{ 'code-timer-urgent': countdownUrgent }">
                    Expires in {{ formatCountdown(codeCountdown) }}
                  </span>
                </div>
                <button class="code-cancel-link" @click="cancelCode">Cancel</button>
              </div>
            </div>
          </div>

          <!-- State: Unlinked -->
          <div v-else key="unlinked" class="channel-item channel-item-unlinked">
            <div class="channel-info">
              <div class="channel-icon channel-icon-inactive">
                <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor"><path d="M11.944 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0a12 12 0 0 0-.056 0zm4.962 7.224c.1-.002.321.023.465.14a.506.506 0 0 1 .171.325c.016.093.036.306.02.472-.18 1.898-.962 6.502-1.36 8.627-.168.9-.499 1.201-.82 1.23-.696.065-1.225-.46-1.9-.902-1.056-.693-1.653-1.124-2.678-1.8-1.185-.78-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 3.345-.479.33-.913.49-1.302.48-.428-.008-1.252-.241-1.865-.44-.752-.245-1.349-.374-1.297-.789.027-.216.325-.437.893-.663 3.498-1.524 5.83-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635z"/></svg>
              </div>
              <div class="channel-details">
                <span class="channel-name">Telegram</span>
                <span class="channel-status">Not linked</span>
              </div>
            </div>
            <button
              class="link-btn"
              :disabled="isGenerating"
              @click="handleGenerateCode"
            >
              <template v-if="isGenerating">
                <span class="link-btn-spinner" />
                Generating...
              </template>
              <template v-else>
                <ExternalLink class="w-3.5 h-3.5" />
                Link
              </template>
            </button>
          </div>
        </Transition>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { UserCog, LogOut, Shield, Key, Link2, Copy, Check, AlertCircle, Clock, ExternalLink } from 'lucide-vue-next'
import { useAuth } from '../../composables/useAuth'
import { getCachedAuthProvider } from '../../api/auth'
import { generateLinkCode, getLinkedChannels, unlinkChannel } from '../../api/channelLinks'
import type { LinkedChannel } from '../../api/channelLinks'

const router = useRouter()
const { t } = useI18n()
const { currentUser, logout } = useAuth()
const authProvider = ref<string | null>(null)

// Channel linking state
const linkCode = ref<string | null>(null)
const codeCountdown = ref(0)
const codeMaxSeconds = ref(900)
const isGenerating = ref(false)
const linkedChannels = ref<LinkedChannel[]>([])
const isCopied = ref(false)
const unlinkConfirm = ref<string | null>(null)
const isUnlinking = ref(false)
const channelError = ref<string | null>(null)
const isLoadingChannels = ref(true)
let countdownInterval: ReturnType<typeof setInterval> | null = null
let copyTimeout: ReturnType<typeof setTimeout> | null = null
let unlinkTimeout: ReturnType<typeof setTimeout> | null = null

// Emit events for parent components
const emit = defineEmits<{
  navigateToProfile: []
}>()

// Get first letter of user's fullname for avatar display
const avatarLetter = computed(() => {
  return currentUser.value?.fullname?.charAt(0)?.toUpperCase() || 'U'
})

// Computed: is Telegram linked?
const telegramLinked = computed(() =>
  linkedChannels.value.some((c) => c.channel === 'telegram'),
)

// Computed: Telegram display name
const telegramSenderId = computed(() => {
  const tg = linkedChannels.value.find((c) => c.channel === 'telegram')
  if (!tg) return ''
  const parts = tg.sender_id.split('|')
  return parts.length > 1 ? `@${parts[1]}` : tg.sender_id
})

// Countdown progress (1.0 → 0.0)
const countdownProgress = computed(() => {
  if (codeMaxSeconds.value <= 0) return 0
  return codeCountdown.value / codeMaxSeconds.value
})

// Countdown urgency color
const countdownUrgent = computed(() => codeCountdown.value <= 60)

// Telegram linked-at date
const telegramLinkedAt = computed(() => {
  const tg = linkedChannels.value.find((c) => c.channel === 'telegram')
  if (!tg?.linked_at) return ''
  const d = new Date(tg.linked_at)
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
})

// Format countdown as M:SS
const formatCountdown = (seconds: number) => {
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${m}:${s.toString().padStart(2, '0')}`
}

// Handle profile icon click
const handleProfileClick = () => {
  emit('navigateToProfile')
}

// Handle logout action
const handleLogout = async () => {
  try {
    await logout()
    router.push('/login')
  } catch {
    // Logout failed - redirect anyway
  }
}

// Generate a link code for Telegram
const handleGenerateCode = async () => {
  isGenerating.value = true
  channelError.value = null
  try {
    const result = await generateLinkCode('telegram')
    linkCode.value = result.code
    codeCountdown.value = result.expires_in_seconds
    codeMaxSeconds.value = result.expires_in_seconds

    if (countdownInterval) clearInterval(countdownInterval)
    countdownInterval = setInterval(() => {
      codeCountdown.value--
      if (codeCountdown.value <= 0) {
        if (countdownInterval) clearInterval(countdownInterval)
        countdownInterval = null
        linkCode.value = null
      }
    }, 1000)
  } catch {
    channelError.value = 'Failed to generate link code. Please try again.'
  } finally {
    isGenerating.value = false
  }
}

// Copy /link CODE to clipboard with visual feedback
const copyCode = async () => {
  if (linkCode.value) {
    await navigator.clipboard.writeText(`/link ${linkCode.value}`)
    isCopied.value = true
    if (copyTimeout) clearTimeout(copyTimeout)
    copyTimeout = setTimeout(() => {
      isCopied.value = false
    }, 2000)
  }
}

// Cancel code display
const cancelCode = () => {
  if (countdownInterval) clearInterval(countdownInterval)
  countdownInterval = null
  linkCode.value = null
  codeCountdown.value = 0
}

// Unlink a channel (two-step confirmation)
const handleUnlink = (channel: string) => {
  if (unlinkConfirm.value === channel) {
    confirmUnlink(channel)
  } else {
    unlinkConfirm.value = channel
    if (unlinkTimeout) clearTimeout(unlinkTimeout)
    unlinkTimeout = setTimeout(() => {
      unlinkConfirm.value = null
    }, 3000)
  }
}

const confirmUnlink = async (channel: string) => {
  isUnlinking.value = true
  channelError.value = null
  try {
    await unlinkChannel(channel)
    linkedChannels.value = linkedChannels.value.filter((c) => c.channel !== channel)
    unlinkConfirm.value = null
  } catch {
    channelError.value = 'Failed to unlink channel. Please try again.'
  } finally {
    isUnlinking.value = false
  }
}

// Load linked channels from the API
const loadLinkedChannels = async () => {
  isLoadingChannels.value = true
  try {
    linkedChannels.value = await getLinkedChannels()
  } catch {
    // Failed to load — channels will appear as unlinked
  } finally {
    isLoadingChannels.value = false
  }
}

onMounted(async () => {
  authProvider.value = await getCachedAuthProvider()
  await loadLinkedChannels()
})

onUnmounted(() => {
  if (countdownInterval) clearInterval(countdownInterval)
  if (copyTimeout) clearTimeout(copyTimeout)
  if (unlinkTimeout) clearTimeout(unlinkTimeout)
})
</script>

<style scoped>
.account-settings {
  display: flex;
  flex-direction: column;
  gap: 20px;
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

/* Profile Card */
.profile-card {
  position: relative;
  background: var(--fill-tsp-white-main);
  border: 1px solid var(--border-light);
  border-radius: 16px;
  overflow: hidden;
}

.profile-card-bg {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 80px;
  background: linear-gradient(
    135deg,
    var(--fill-blue) 0%,
    rgba(59, 130, 246, 0.05) 100%
  );
}

.profile-content {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 24px;
  padding-top: 48px;
}

/* Avatar */
.avatar-section {
  position: relative;
  margin-bottom: 16px;
}

.avatar-wrapper {
  position: relative;
}

.avatar-ring {
  position: absolute;
  inset: -4px;
  border-radius: 50%;
  background: linear-gradient(135deg, var(--text-brand) 0%, #1a1a1a 100%);
  opacity: 0.3;
  animation: pulse 2s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% {
    transform: scale(1);
    opacity: 0.3;
  }
  50% {
    transform: scale(1.05);
    opacity: 0.2;
  }
}

.avatar {
  position: relative;
  width: 72px;
  height: 72px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 32px;
  font-weight: 700;
  color: #fff;
  background: linear-gradient(135deg, var(--text-brand) 0%, #1a1a1a 100%);
  border-radius: 50%;
  border: 3px solid var(--background-white-main);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.25);
}

.avatar-status {
  position: absolute;
  bottom: 2px;
  right: 2px;
  width: 16px;
  height: 16px;
  background: var(--function-success);
  border: 3px solid var(--background-white-main);
  border-radius: 50%;
}

/* User Info */
.user-info {
  text-align: center;
  margin-bottom: 20px;
}

.user-name {
  font-size: 20px;
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 4px;
  letter-spacing: -0.01em;
}

.user-email {
  font-size: 13px;
  color: var(--text-tertiary);
}

/* Action Buttons */
.profile-actions {
  display: flex;
  gap: 12px;
  width: 100%;
  max-width: 320px;
}

.action-btn {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 12px 16px;
  font-size: 13px;
  font-weight: 600;
  border-radius: 10px;
  transition: all 0.2s ease;
}

.action-btn-primary {
  background: var(--fill-tsp-white-dark);
  color: var(--text-primary);
  border: 1px solid var(--border-main);
}

.action-btn-primary:hover {
  background: var(--fill-tsp-white-main);
  border-color: var(--border-dark);
}

.action-btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.action-btn-secondary {
  background: var(--fill-tsp-white-dark);
  color: var(--text-secondary);
  border: 1px solid var(--border-light);
}

.action-btn-secondary:hover {
  background: var(--fill-tsp-white-main);
  border-color: var(--border-main);
}

.action-btn-danger {
  background: var(--function-error-tsp);
  color: var(--function-error);
  border: 1px solid transparent;
}

.action-btn-danger:hover {
  background: rgba(239, 68, 68, 0.15);
}

.action-btn-sm {
  flex: none;
  padding: 8px 16px;
  font-size: 12px;
}

/* Quick Stats */
.quick-stats {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
}

.stat-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px;
  background: var(--fill-tsp-white-main);
  border: 1px solid var(--border-light);
  border-radius: 12px;
  transition: all 0.2s ease;
}

.stat-item:hover {
  background: var(--fill-tsp-white-dark);
  border-color: var(--border-main);
}

.stat-icon {
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

.stat-content {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.stat-label {
  font-size: 11px;
  font-weight: 500;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.stat-value {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  text-transform: capitalize;
}

.stat-value-success {
  color: var(--function-success);
}

/* ─── Linked Channels Section ─── */
.linked-channels {
  background: var(--fill-tsp-white-main);
  border: 1px solid var(--border-light);
  border-radius: 14px;
  padding: 20px;
}

.channels-header {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  margin-bottom: 16px;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--border-light);
}

.channels-icon-box {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  background: rgba(0, 136, 204, 0.08);
  border-radius: 10px;
  color: #0088cc;
  flex-shrink: 0;
}

.channels-header-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.channels-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
  line-height: 1.4;
}

.channels-desc {
  font-size: 12px;
  color: var(--text-tertiary);
  margin: 0;
  line-height: 1.4;
}

/* Error banner */
.channel-error {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  margin-bottom: 12px;
  background: var(--function-error-tsp);
  border: 1px solid rgba(239, 68, 68, 0.15);
  border-radius: 8px;
  font-size: 12px;
  color: var(--function-error);
  cursor: pointer;
}

/* Loading skeleton */
.channel-skeleton {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px;
  background: var(--fill-tsp-white-dark);
  border-radius: 10px;
}

.skeleton-icon {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  background: var(--fill-tsp-white-main);
  animation: skeleton-pulse 1.5s ease-in-out infinite;
}

.skeleton-lines {
  display: flex;
  flex-direction: column;
  gap: 6px;
  flex: 1;
}

.skeleton-line {
  height: 10px;
  border-radius: 4px;
  background: var(--fill-tsp-white-main);
  animation: skeleton-pulse 1.5s ease-in-out infinite;
}

.skeleton-line-short { width: 60px; }
.skeleton-line-long { width: 120px; animation-delay: 0.15s; }

@keyframes skeleton-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

/* Channel item base */
.channel-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px;
  background: var(--fill-tsp-white-dark);
  border: 1px solid var(--border-light);
  border-radius: 10px;
  transition: border-color 0.2s ease, background 0.2s ease;
}

.channel-item:hover {
  border-color: var(--border-main);
}

/* Linked state */
.channel-item-linked {
  border-color: var(--function-success-border);
  background: var(--function-success-tsp);
}

.channel-item-linked:hover {
  border-color: var(--function-success-border);
}

/* Unlinked state */
.channel-item-unlinked {
  border-style: dashed;
}

/* Code display state */
.channel-item-code {
  flex-direction: column;
  align-items: stretch;
  padding: 0;
  overflow: hidden;
  background: var(--background-white-main);
  border-color: rgba(0, 136, 204, 0.2);
}

.channel-info {
  display: flex;
  align-items: center;
  gap: 12px;
}

.channel-icon {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 10px;
  flex-shrink: 0;
}

.channel-icon-telegram {
  background: rgba(0, 136, 204, 0.1);
  color: #0088cc;
}

.channel-icon-inactive {
  background: var(--fill-tsp-white-dark);
  color: var(--text-tertiary);
}

.channel-linked-badge {
  position: absolute;
  bottom: -3px;
  right: -3px;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  background: var(--function-success);
  color: #fff;
  border-radius: 50%;
  border: 2px solid var(--background-white-main);
}

.channel-details {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.channel-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}

.channel-meta {
  display: flex;
  align-items: center;
  gap: 6px;
}

.channel-status {
  font-size: 12px;
  color: var(--text-tertiary);
}

.channel-status-linked {
  color: var(--function-success);
  font-weight: 500;
}

.channel-linked-date {
  font-size: 11px;
  color: var(--text-tertiary);
}

.channel-linked-date::before {
  content: "\00b7";
  margin-right: 6px;
}

/* Unlink button (two-step confirm) */
.unlink-btn {
  flex-shrink: 0;
  padding: 6px 14px;
  font-size: 12px;
  font-weight: 500;
  color: var(--text-tertiary);
  background: transparent;
  border: 1px solid var(--border-light);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.unlink-btn:hover {
  color: var(--function-error);
  border-color: rgba(239, 68, 68, 0.3);
  background: var(--function-error-tsp);
}

.unlink-btn-confirm {
  color: #fff;
  background: var(--function-error);
  border-color: var(--function-error);
  animation: btn-attention 0.3s ease;
}

.unlink-btn-confirm:hover {
  color: #fff;
  background: #dc2626;
  border-color: #dc2626;
}

@keyframes btn-attention {
  0% { transform: scale(1); }
  50% { transform: scale(1.05); }
  100% { transform: scale(1); }
}

/* Link button */
.link-btn {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-primary);
  background: var(--fill-tsp-white-dark);
  border: 1px solid var(--border-main);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.link-btn:hover {
  background: var(--fill-tsp-white-main);
  border-color: var(--border-dark);
}

.link-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.link-btn-spinner {
  width: 12px;
  height: 12px;
  border: 2px solid var(--border-main);
  border-top-color: var(--text-primary);
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* ─── Code Display (link-in-progress) ─── */
.code-progress-track {
  height: 3px;
  background: var(--fill-tsp-white-dark);
  overflow: hidden;
}

.code-progress-bar {
  height: 100%;
  background: #0088cc;
  border-radius: 0 2px 2px 0;
  transition: width 1s linear;
}

.code-progress-urgent {
  background: var(--function-error);
}

.code-body {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 16px;
}

.code-steps {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.code-step {
  display: flex;
  align-items: center;
  gap: 10px;
}

.code-step-num {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  font-size: 11px;
  font-weight: 700;
  color: #0088cc;
  background: rgba(0, 136, 204, 0.08);
  border-radius: 50%;
  flex-shrink: 0;
}

.code-step-text {
  font-size: 12px;
  color: var(--text-secondary);
}

.code-field {
  display: flex;
  align-items: center;
  gap: 8px;
}

.code-value {
  flex: 1;
  padding: 12px 16px;
  background: var(--fill-tsp-white-main);
  border: 1px solid var(--border-main);
  border-radius: 8px;
  font-family: 'SF Mono', 'Fira Code', 'Cascadia Code', monospace;
  font-size: 16px;
  font-weight: 600;
  letter-spacing: 0.12em;
  color: var(--text-primary);
  text-align: center;
  user-select: all;
}

.copy-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 42px;
  height: 42px;
  background: var(--fill-tsp-white-main);
  border: 1px solid var(--border-main);
  border-radius: 8px;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.2s ease;
  flex-shrink: 0;
}

.copy-btn:hover {
  background: var(--fill-tsp-white-dark);
  color: var(--text-primary);
  border-color: var(--border-dark);
}

.copy-btn-success {
  color: var(--function-success);
  border-color: var(--function-success-border);
  background: var(--function-success-tsp);
}

.copy-btn-success:hover {
  color: var(--function-success);
  border-color: var(--function-success-border);
  background: var(--function-success-tsp);
}

.code-timer-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.code-timer {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  font-weight: 500;
  color: var(--text-tertiary);
  font-variant-numeric: tabular-nums;
}

.code-timer-urgent {
  color: var(--function-error);
}

.code-cancel-link {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-tertiary);
  background: none;
  border: none;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 6px;
  transition: all 0.2s ease;
}

.code-cancel-link:hover {
  color: var(--text-secondary);
  background: var(--fill-tsp-white-dark);
}

/* ─── Transitions ─── */
.channel-swap-enter-active,
.channel-swap-leave-active {
  transition: all 0.25s ease;
}

.channel-swap-enter-from {
  opacity: 0;
  transform: translateY(6px);
}

.channel-swap-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}

.slide-fade-enter-active,
.slide-fade-leave-active {
  transition: all 0.2s ease;
}

.slide-fade-enter-from,
.slide-fade-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}

.icon-swap-enter-active,
.icon-swap-leave-active {
  transition: all 0.15s ease;
}

.icon-swap-enter-from {
  opacity: 0;
  transform: scale(0.6);
}

.icon-swap-leave-to {
  opacity: 0;
  transform: scale(0.6);
}
</style>
