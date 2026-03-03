<template>
  <SimpleBar>
    <div class="agents-page">
      <div v-if="isLoading" class="agents-loading">
        <Loader2 class="w-5 h-5 animate-spin" />
        <span>Loading agent channels...</span>
      </div>

      <template v-else-if="isTelegramLinked">
        <section class="agents-linked">
          <div class="linked-badge">
            <CheckCircle2 class="w-4 h-4" />
            Telegram connected
          </div>
          <h1>Telegram connected</h1>
          <p>This is your own chat workspace. Messages from your linked Telegram account appear in your tasks.</p>

          <div class="linked-actions">
            <button class="primary-action" type="button" @click="handleRefresh">
              <RefreshCw class="w-4 h-4" />
              Refresh chats
            </button>
          </div>
        </section>

        <section class="sessions-section">
          <div class="sessions-header">
            <h2>Your chats</h2>
            <span>{{ recentSessions.length }} sessions</span>
          </div>

          <div v-if="recentSessions.length === 0" class="empty-sessions">
            <MessageSquare class="w-5 h-5" />
            <p>No Telegram chats yet. Send your first message to the bot.</p>
          </div>

          <div v-else class="sessions-grid">
            <button
              v-for="session in recentSessions"
              :key="session.session_id"
              type="button"
              class="session-card"
              @click="openSession(session.session_id)"
            >
              <div class="session-card-top">
                <span class="session-status">{{ session.status }}</span>
                <span class="session-time">{{ formatSessionTime(session.latest_message_at) }}</span>
              </div>
              <h3>{{ session.title || session.latest_message || 'Untitled chat' }}</h3>
              <p>{{ session.latest_message || 'Open chat to continue.' }}</p>
            </button>
          </div>
        </section>
      </template>

      <template v-else>
        <section class="hero-section">
          <div class="hero-art">
            <div class="phone-shell">
              <div class="phone-card">
                <div class="phone-card-avatar">P</div>
                <div class="phone-card-lines">
                  <div class="line line-strong"></div>
                  <div class="line"></div>
                </div>
              </div>
            </div>

            <div class="orbit orbit-telegram">
              <Send class="w-4 h-4" />
            </div>
            <div class="orbit orbit-line">LINE</div>
            <div class="orbit orbit-messenger">M</div>
            <div class="orbit orbit-whatsapp">
              <Phone class="w-4 h-4" />
            </div>
          </div>

          <h1>Deploy your agent for web apps</h1>
        </section>

        <section class="feature-cards">
          <article class="feature-card">
            <BadgeCheck class="w-4 h-4" />
            <h3>Brand-consistent AI identity</h3>
            <p>Trained on your workflows, integrated with your tools.</p>
          </article>
          <article class="feature-card">
            <Monitor class="w-4 h-4" />
            <h3>Persistent memory & computer</h3>
            <p>24/7 cloud assistant that keeps full context and memory.</p>
          </article>
          <article class="feature-card">
            <Puzzle class="w-4 h-4" />
            <h3>Custom skills</h3>
            <p>Equip your assistant with expert knowledge in specific areas.</p>
          </article>
          <article class="feature-card">
            <MessageCircle class="w-4 h-4" />
            <h3>Works in your messenger</h3>
            <p>Available in Telegram. More messengers coming soon.</p>
          </article>
        </section>

        <section class="cta-section">
          <button class="primary-action" type="button" :disabled="isGenerating" @click="generate">
            <Loader2 v-if="isGenerating" class="w-4 h-4 animate-spin" />
            <Send v-else class="w-4 h-4" />
            Get started on Telegram
          </button>

          <div v-if="bindCommand" class="bind-panel">
            <p class="bind-title">Send this command in Telegram</p>
            <div class="bind-row">
              <code>{{ activeCommand }}</code>
              <button type="button" class="icon-btn" @click="copyCommand">
                <Check v-if="isCopied" class="w-4 h-4" />
                <Copy v-else class="w-4 h-4" />
              </button>
            </div>
            <div class="bind-meta">
              <span>
                <Clock3 class="w-3.5 h-3.5" />
                Expires in {{ formatCountdown(countdown) }}
              </span>
              <button type="button" class="inline-link" @click="openDeepLink">Open Telegram</button>
            </div>
          </div>

          <p v-if="feedback" class="feedback">{{ feedback }}</p>
          <p v-if="error" class="error">{{ error }}</p>
        </section>
      </template>
    </div>
  </SimpleBar>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  BadgeCheck,
  Check,
  CheckCircle2,
  Clock3,
  Copy,
  Loader2,
  MessageCircle,
  MessageSquare,
  Monitor,
  Phone,
  Puzzle,
  RefreshCw,
  Send,
} from 'lucide-vue-next'
import SimpleBar from '@/components/SimpleBar.vue'
import { getSessions } from '@/api/agent'
import { useTelegramLink } from '@/composables/useTelegramLink'
import type { ListSessionItem } from '@/types/response'

const router = useRouter()
const isLoading = ref(true)
const sessions = ref<ListSessionItem[]>([])

const {
  isTelegramLinked,
  isGenerating,
  bindCommand,
  activeCommand,
  isCopied,
  error,
  feedback,
  countdown,
  generate,
  copyCommand,
  openDeepLink,
  loadChannels,
  formatCountdown,
} = useTelegramLink()

const recentSessions = computed(() =>
  [...sessions.value]
    .filter((s) => s.source === 'telegram')
    .sort((a, b) => (b.latest_message_at || 0) - (a.latest_message_at || 0))
    .slice(0, 12),
)

const loadSessions = async () => {
  const response = await getSessions()
  sessions.value = response.sessions
}

const loadAll = async () => {
  isLoading.value = true
  error.value = null
  try {
    await Promise.all([loadChannels(), loadSessions()])
  } catch {
    error.value = 'Failed to load agent state. Please refresh.'
  } finally {
    isLoading.value = false
  }
}

const formatSessionTime = (unixSeconds: number | null) => {
  if (!unixSeconds) return 'No activity'
  const date = new Date(unixSeconds * 1000)
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

const openSession = (sessionId: string) => {
  void router.push(`/chat/${sessionId}`)
}

const handleRefresh = async () => {
  await loadAll()
}

onMounted(async () => {
  await loadAll()
})
</script>

<style scoped>
.agents-page {
  min-height: 100%;
  padding: 36px 24px 40px;
  max-width: 1120px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 28px;
}

.agents-loading {
  height: 50vh;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: var(--text-secondary);
  font-size: 14px;
}

.hero-section {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 18px;
}

.hero-section h1 {
  margin: 0;
  text-align: center;
  font-size: clamp(34px, 4vw, 50px);
  font-family: "Georgia", "Times New Roman", serif;
  line-height: 1.08;
  color: #1f2a37;
  letter-spacing: -0.02em;
}

.hero-art {
  position: relative;
  width: 320px;
  height: 200px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.phone-shell {
  width: 208px;
  height: 168px;
  border: 4px solid #d8d8d8;
  border-radius: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(180deg, #f7f7f7, #efefef);
}

.phone-card {
  width: 248px;
  height: 62px;
  border-radius: 16px;
  background: #ececec;
  box-shadow: 0 18px 34px rgba(0, 0, 0, 0.14);
  border: 1px solid #e1e1e1;
  padding: 12px 16px;
  display: flex;
  align-items: center;
  gap: 12px;
  position: absolute;
}

.phone-card-avatar {
  width: 28px;
  height: 28px;
  border-radius: 999px;
  background: #fff;
  color: #111827;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  font-weight: 700;
}

.phone-card-lines {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.line {
  height: 7px;
  border-radius: 999px;
  background: #d4d4d4;
}

.line-strong {
  width: 66%;
  background: #c8c8c8;
}

.orbit {
  position: absolute;
  width: 48px;
  height: 48px;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  font-size: 11px;
  font-weight: 700;
  box-shadow: 0 8px 20px rgba(0, 0, 0, 0.14);
}

.orbit-telegram {
  left: 38px;
  top: 58px;
  background: linear-gradient(180deg, #4ca9e8, #2695e0);
}

.orbit-line {
  left: 134px;
  top: -2px;
  background: #06c755;
}

.orbit-messenger {
  right: 32px;
  top: -2px;
  background: #5b3cff;
}

.orbit-whatsapp {
  right: -12px;
  top: 58px;
  background: #25d366;
}

.feature-cards {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.feature-card {
  min-height: 136px;
  border-radius: 16px;
  border: 1px solid #e2e2e2;
  background: rgba(255, 255, 255, 0.82);
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.feature-card h3 {
  margin: 0;
  font-size: 26px;
  line-height: 1.18;
  font-family: "Georgia", "Times New Roman", serif;
  color: #1f2a37;
  letter-spacing: -0.01em;
}

.feature-card p {
  margin: 0;
  font-size: 13px;
  line-height: 1.55;
  color: #6b7280;
}

.feature-card :deep(svg) {
  color: #4b5563;
}

.cta-section {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}

.primary-action {
  height: 42px;
  border-radius: 12px;
  border: none;
  background: #101114;
  color: #fff;
  padding: 0 18px;
  font-size: 24px;
  font-family: "Georgia", "Times New Roman", serif;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  transition: opacity 0.2s ease;
}

.primary-action:hover:not(:disabled) {
  opacity: 0.9;
}

.primary-action:disabled {
  opacity: 0.65;
  cursor: not-allowed;
}

.bind-panel {
  width: min(560px, 100%);
  border: 1px solid #e3e3e3;
  border-radius: 14px;
  background: #fff;
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.bind-title {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: #374151;
}

.bind-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.bind-row code {
  flex: 1;
  min-width: 0;
  border: 1px solid #dddddd;
  border-radius: 10px;
  padding: 10px;
  background: #fafafa;
  font-size: 12px;
  color: #111827;
  overflow-x: auto;
  white-space: nowrap;
}

.icon-btn {
  width: 38px;
  height: 38px;
  border-radius: 10px;
  border: 1px solid #d9d9d9;
  background: #fff;
  color: #4b5563;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
}

.bind-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  font-size: 12px;
  color: #6b7280;
}

.bind-meta span {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.inline-link {
  border: none;
  background: transparent;
  color: #2563eb;
  cursor: pointer;
  font-size: 12px;
  font-weight: 600;
}

.feedback,
.error {
  margin: 0;
  font-size: 12px;
}

.feedback {
  color: #059669;
}

.error {
  color: #dc2626;
}

.agents-linked {
  border: 1px solid #e3e7ec;
  border-radius: 18px;
  background: linear-gradient(180deg, #ffffff, #f8fafc);
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.linked-badge {
  width: fit-content;
  height: 28px;
  border-radius: 999px;
  padding: 0 10px;
  background: #ecfdf3;
  color: #047857;
  font-size: 12px;
  font-weight: 600;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.agents-linked h1 {
  margin: 0;
  font-size: clamp(28px, 3vw, 40px);
  font-family: "Georgia", "Times New Roman", serif;
  color: #111827;
}

.agents-linked p {
  margin: 0;
  color: #4b5563;
  font-size: 14px;
  line-height: 1.55;
  max-width: 700px;
}

.linked-actions {
  padding-top: 4px;
}

.sessions-section {
  border: 1px solid #e5e7eb;
  border-radius: 18px;
  background: #fff;
  padding: 18px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.sessions-header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
}

.sessions-header h2 {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  color: #111827;
}

.sessions-header span {
  font-size: 12px;
  font-weight: 600;
  color: #6b7280;
}

.empty-sessions {
  min-height: 120px;
  border-radius: 12px;
  border: 1px dashed #d1d5db;
  color: #6b7280;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 16px;
}

.empty-sessions p {
  margin: 0;
  font-size: 13px;
}

.sessions-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.session-card {
  border-radius: 12px;
  border: 1px solid #e5e7eb;
  background: #fcfcfd;
  padding: 12px;
  text-align: left;
  display: flex;
  flex-direction: column;
  gap: 8px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.session-card:hover {
  border-color: #c7d2fe;
  background: #f8faff;
}

.session-card-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}

.session-status {
  text-transform: capitalize;
  font-size: 11px;
  font-weight: 700;
  color: #4338ca;
}

.session-time {
  font-size: 11px;
  color: #6b7280;
}

.session-card h3 {
  margin: 0;
  font-size: 14px;
  line-height: 1.4;
  color: #111827;
}

.session-card p {
  margin: 0;
  font-size: 12px;
  line-height: 1.5;
  color: #6b7280;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

@media (max-width: 1080px) {
  .feature-cards {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .sessions-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 720px) {
  .agents-page {
    padding: 22px 14px 26px;
  }

  .hero-art {
    width: 288px;
    height: 180px;
  }

  .phone-shell {
    transform: scale(0.9);
  }

  .feature-cards {
    grid-template-columns: 1fr;
  }

  .sessions-grid {
    grid-template-columns: 1fr;
  }

  .bind-meta {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
