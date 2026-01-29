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
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { UserCog, LogOut, Shield, Key } from 'lucide-vue-next'
import { useAuth } from '../../composables/useAuth'
import { getCachedAuthProvider } from '../../api/auth'

const router = useRouter()
const { t } = useI18n()
const { currentUser, logout } = useAuth()
const authProvider = ref<string | null>(null)

// Emit events for parent components
const emit = defineEmits<{
  navigateToProfile: []
}>()

// Get first letter of user's fullname for avatar display
const avatarLetter = computed(() => {
  return currentUser.value?.fullname?.charAt(0)?.toUpperCase() || 'U'
})

// Handle profile icon click
const handleProfileClick = () => {
  emit('navigateToProfile')
}

// Handle logout action
const handleLogout = async () => {
  try {
    await logout()
    router.push('/login')
  } catch (error) {
    console.error('Logout failed:', error)
  }
}

onMounted(async () => {
  authProvider.value = await getCachedAuthProvider()
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
  background: linear-gradient(135deg, var(--text-brand) 0%, #60a5fa 100%);
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
  background: linear-gradient(135deg, var(--text-brand) 0%, #60a5fa 100%);
  border-radius: 50%;
  border: 3px solid var(--background-white-main);
  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.25);
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

.action-btn-danger {
  background: var(--function-error-tsp);
  color: var(--function-error);
  border: 1px solid transparent;
}

.action-btn-danger:hover {
  background: rgba(239, 68, 68, 0.15);
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
</style>
