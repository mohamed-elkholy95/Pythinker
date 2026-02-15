<template>
  <SimpleBar
    ref="simpleBarRef"
    :autoFollow="follow"
    :autoFollowThreshold="24"
    @follow-change="handleFollowChange"
  >
    <div id="pythinker-chat-box" ref="chatContainerRef" class="relative flex flex-col h-full flex-1 flex-shrink-0 min-w-0 bg-[var(--background-gray-main)]">
      <ConnectionStatusBanner
        :sessionId="sessionId"
        :retryAttempt="connectionBannerRetryAttempt"
        :maxRetries="connectionBannerMaxRetries"
        :retryDelayMs="connectionBannerRetryDelayMs"
        :isDegraded="isStreamDegraded"
        @refresh="handleRetryConnection"
        @dismiss="dismissConnectionBanner"
      />
      <div ref="observerRef"
        class="chat-header flex flex-row items-center pt-3 pb-1 gap-1 ps-[8px] pe-[8px] sm:ps-[16px] sm:pe-[24px] sticky top-0 z-10 flex-shrink-0 bg-[var(--background-gray-main)]">
        <!-- Mobile sidebar toggle -->
        <button
          class="sm:hidden h-8 w-8 inline-flex items-center justify-center rounded-lg hover:bg-[var(--fill-tsp-gray-main)] transition-colors flex-shrink-0 -ml-0.5"
          @click="toggleLeftPanel"
          aria-label="Open sidebar"
        >
          <Menu :size="20" class="text-[var(--icon-secondary)]" />
        </button>
        <!-- Left side spacer (desktop only) -->
        <div class="hidden sm:flex items-center justify-start" style="width: calc((100% - min(768px, 100%)) / 2);">
        </div>
        <!-- Center content - matches chat content width -->
        <div class="max-w-full sm:max-w-[768px] sm:min-w-[400px] w-full flex items-center justify-between gap-3">
          <!-- Left: Title -->
          <div class="flex items-center gap-2 flex-1 min-w-0">
            <button class="chat-model-pill" type="button" aria-label="Current chat title">
              <span class="chat-title-text">
                {{ title }}
              </span>
              <ChevronRight class="chat-title-chevron" :size="16" />
            </button>
          </div>
          <!-- Right: Buttons -->
          <div class="flex items-center gap-1 flex-shrink-0">
              <span class="relative flex-shrink-0" aria-expanded="false" aria-haspopup="dialog">
                <Popover>
                  <PopoverTrigger>
                    <button
                      class="h-7 min-w-[56px] px-2 rounded-[8px] inline-flex items-center gap-1.5 clickable border border-[var(--border-main)] hover:border-[var(--border-dark)] hover:bg-[var(--fill-tsp-white-main)] transition-all">
                      <ShareIcon color="var(--icon-secondary)" />
                      <span class="text-[var(--text-secondary)] text-[13px] font-medium leading-[18px]">{{ t('Share') }}</span>
                    </button>
                  </PopoverTrigger>
                  <PopoverContent>
                    <div
                      class="w-[400px] flex flex-col rounded-2xl bg-[var(--background-menu-white)] shadow-[0px_8px_32px_0px_var(--shadow-S),0px_0px_0px_1px_var(--border-light)]"
                      style="max-width: calc(-16px + 100vw);">
                      <div class="flex flex-col pt-[12px] px-[16px] pb-[16px]">
                        <!-- Private mode option -->
                        <div @click="handleShareModeChange('private')"
                          :class="{'pointer-events-none opacity-50': sharingLoading}"
                          class="flex items-center gap-[10px] px-[8px] -mx-[8px] py-[8px] rounded-[8px] clickable hover:bg-[var(--fill-tsp-white-main)]">
                          <div
                            :class="shareMode === 'private' ? 'bg-[var(--Button-primary-black)]' : 'bg-[var(--fill-tsp-white-dark)]'"
                            class="w-[32px] h-[32px] rounded-[8px] flex items-center justify-center">
                            <Lock :size="16" :stroke="shareMode === 'private' ? 'var(--text-onblack)' : 'var(--icon-primary)'" :stroke-width="2" /></div>
                          <div class="flex flex-col flex-1 min-w-0">
                            <div class="text-sm font-medium text-[var(--text-primary)]">{{ t('Private Only') }}</div>
                            <div class="text-[13px] text-[var(--text-tertiary)]">{{ t('Only visible to you') }}</div>
                          </div><Check :size="20" :class="shareMode === 'private' ? 'ml-auto' : 'ml-auto invisible'" :color="shareMode === 'private' ? 'var(--icon-primary)' : 'var(--icon-tertiary)'" />
                        </div>
                        <!-- Public mode option -->
                        <div @click="handleShareModeChange('public')"
                          :class="{'pointer-events-none opacity-50': sharingLoading}"
                          class="flex items-center gap-[10px] px-[8px] -mx-[8px] py-[8px] rounded-[8px] clickable hover:bg-[var(--fill-tsp-white-main)]">
                          <div
                            :class="shareMode === 'public' ? 'bg-[var(--Button-primary-black)]' : 'bg-[var(--fill-tsp-white-dark)]'"
                            class="w-[32px] h-[32px] rounded-[8px] flex items-center justify-center">
                            <Globe :size="16" :stroke="shareMode === 'public' ? 'var(--text-onblack)' : 'var(--icon-primary)'" :stroke-width="2" /></div>
                          <div class="flex flex-col flex-1 min-w-0">
                            <div class="text-sm font-medium text-[var(--text-primary)]">{{ t('Public Access') }}</div>
                            <div class="text-[13px] text-[var(--text-tertiary)]">{{ t('Anyone with the link can view') }}</div>
                          </div><Check :size="20" :class="shareMode === 'public' ? 'ml-auto' : 'ml-auto invisible'" :color="shareMode === 'public' ? 'var(--icon-primary)' : 'var(--icon-tertiary)'" />
                        </div>
                        <div class="border-t border-[var(--border-main)] mt-[4px]"></div>
                        
                        <!-- Show instant share button when in private mode -->
                        <div v-if="shareMode === 'private'">
                          <button @click.stop="handleInstantShare"
                            :disabled="sharingLoading"
                            class="inline-flex items-center justify-center whitespace-nowrap font-medium transition-colors hover:opacity-90 active:opacity-80 bg-[var(--Button-primary-black)] text-[var(--text-onblack)] h-[36px] px-[12px] rounded-[10px] gap-[6px] text-sm min-w-16 mt-[16px] w-full disabled:opacity-50 disabled:cursor-not-allowed"
                            data-tabindex="" tabindex="-1">
                            <div v-if="sharingLoading" class="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                            <Link v-else :size="16" stroke="currentColor" :stroke-width="2" />
                            {{ sharingLoading ? t('Sharing...') : t('Share Instantly') }}
                          </button>
                        </div>
                        
                        <!-- Show copy link button when in public mode -->
                        <div v-else>
                          <button @click.stop="handleCopyLink"
                            :class="linkCopied ? 'inline-flex items-center justify-center whitespace-nowrap font-medium transition-colors active:opacity-80 bg-[var(--Button-primary-white)] text-[var(--text-primary)] hover:opacity-70 active:hover-60 h-[36px] px-[12px] rounded-[10px] gap-[6px] text-sm min-w-16 mt-[16px] w-full border border-[var(--border-btn-main)] shadow-none' : 'inline-flex items-center justify-center whitespace-nowrap font-medium transition-colors hover:opacity-90 active:opacity-80 bg-[var(--Button-primary-black)] text-[var(--text-onblack)] h-[36px] px-[12px] rounded-[10px] gap-[6px] text-sm min-w-16 mt-[16px] w-full'"
                            data-tabindex="" tabindex="-1">
                            <Link v-if="!linkCopied" :size="16" stroke="currentColor" :stroke-width="2" />
                            <Check v-else :size="16" color="var(--text-primary)" />
                            {{ linkCopied ? t('Link Copied') : t('Copy Link') }}
                          </button>
                        </div>
                      </div>
                    </div>
                  </PopoverContent>
                </Popover>
              </span>
              <button @click="handleFileListShow"
                class="h-8 w-8 flex items-center justify-center hover:bg-[var(--fill-tsp-gray-main)] rounded-lg cursor-pointer transition-colors">
                <FileSearch class="text-[var(--icon-secondary)]" :size="18" />
              </button>
          </div>
        </div>
        <!-- Right side - spacer -->
        <div class="flex-1"></div>
      </div>
      <div
        class="mx-auto w-full max-w-full px-5 sm:max-w-[768px] sm:min-w-[400px] flex flex-col flex-1"
        :class="{ 'chat-content-with-pinned-dock': shouldPinComposerToBottom }"
      >
        <div
          class="flex flex-col w-full pb-[80px] pt-[24px] flex-1"
          :class="{
            'chat-messages-with-pinned-dock': shouldPinComposerToBottom,
            'chat-messages-with-thumbnail-dock': shouldPinComposerToBottom && showThumbnailDockSpacer,
          }"
        >
          <ChatMessage v-for="(message, index) in messages" :key="message.id" :message="message"
            :activeThinkingStepId="activeThinkingStepId"
            :showStepLeadingConnector="shouldShowStepLeadingConnector(index)"
            :showStepConnector="shouldShowStepConnector(index)"
            :showAssistantHeader="shouldShowAssistantHeader(index)"
            :renderAsSummaryCard="shouldRenderSummaryCard(index)"
            :showAssistantCompletionFooter="assistantCompletionFooterIds.has(message.id) && !canShowSuggestions"
            @toolClick="handleToolClick"
            @reportOpen="handleReportOpen"
            @reportFileOpen="handleReportFileOpen"
            @showAllFiles="handleFileListShow"
            @reportRate="handleReportRate"
            @selectSuggestion="handleSuggestionSelect"
            @deepResearchRun="handleDeepResearchRun"
            @deepResearchSkip="handleDeepResearchSkip"
            @toggleAutoRun="handleToggleAutoRun" />
          <SessionWarmupMessage
            v-if="showSessionWarmupMessage"
            :state="warmupState"
            @retry="handleRetryInitialize"
          />

          <!-- Loading/Thinking indicators - fallback for discuss mode (no active step) -->
          <div v-if="showFloatingThinkingIndicator" class="flex items-center gap-2 pl-1">
            <ThinkingIndicator :showText="true" />
          </div>
          <LoadingIndicator v-else-if="!showSessionWarmupMessage && isLoading && !activeThinkingStepId && !hasRunningStep" :text="$t('Loading')" :pulse="isReceivingHeartbeats" />

          <!-- Waiting for user reply indicator -->
          <WaitingForReply v-if="isWaitingForReply" />

          <!-- Still working notice - heartbeats arriving but no real events -->
          <!-- Hide when warmup message is shown to avoid overlapping "taking longer" + "unstable" messages -->
          <div
            v-if="isStale && isLoading && !showSessionWarmupMessage"
            class="stale-notice flex items-center gap-3 px-4 py-3 mx-4 mb-2 rounded-xl border border-blue-200 dark:border-blue-800/40 bg-blue-50 dark:bg-blue-950/20 transition-all duration-300"
            role="status"
          >
            <div class="stale-pulse w-2.5 h-2.5 rounded-full bg-blue-400 dark:bg-blue-500 flex-shrink-0 animate-pulse" aria-hidden="true"></div>
            <div class="flex-1 min-w-0">
              <span class="text-sm font-medium text-blue-800 dark:text-blue-300">
                {{ isReceivingHeartbeats ? $t('Still working on your request...') : $t('Connection may be unstable...') }}
              </span>
              <span v-if="currentToolInfo" class="text-xs opacity-80 ml-1.5">
                ({{ currentToolInfo.name }})
              </span>
            </div>
            <button
              @click="handleStop"
              class="stale-stop-btn flex-shrink-0 px-3 py-1.5 text-xs font-medium rounded-lg bg-blue-100 dark:bg-blue-900/30 text-blue-800 dark:text-blue-300 hover:bg-blue-200 dark:hover:bg-blue-900/50 transition-colors"
            >
              {{ $t('Stop') }}
            </button>
          </div>

          <!-- Connection interrupted - SSE closed without completion -->
          <div
            v-if="responsePhase === 'timed_out'"
            class="timeout-notice flex items-center gap-3 px-4 py-3 mx-4 mt-[1cm] mb-2 rounded-xl border border-amber-200 dark:border-amber-800/40 bg-amber-50 dark:bg-amber-950/20 transition-all duration-300"
            role="status"
          >
            <div class="w-2.5 h-2.5 rounded-full bg-amber-400 dark:bg-amber-500 flex-shrink-0 animate-pulse" aria-hidden="true"></div>
            <div class="flex-1 min-w-0">
              <span class="text-sm font-medium text-amber-800 dark:text-amber-300">
                {{ autoRetryCount < 4
                  ? $t('Connection interrupted. Reconnecting automatically...')
                  : (isFallbackStatusPolling
                    ? $t('Connection interrupted. Checking task status in background...')
                    : $t('Connection interrupted. The agent may still be working.')) }}
              </span>
            </div>
            <button
              @click="handleRetryConnection"
              class="flex-shrink-0 px-3 py-1.5 text-xs font-medium rounded-lg bg-amber-100 dark:bg-amber-900/30 text-amber-800 dark:text-amber-300 hover:bg-amber-200 dark:hover:bg-amber-900/50 transition-colors"
            >
              {{ $t('Retry') }}
            </button>
          </div>

          <!-- Error notice - structured error with recovery hint -->
          <div
            v-if="responsePhase === 'error' && lastError"
            class="error-notice flex items-center gap-3 px-4 py-3 mx-4 mb-2 rounded-xl border border-red-200 dark:border-red-800/40 bg-red-50 dark:bg-red-950/20 transition-all duration-300"
            role="alert"
          >
            <div class="flex-1 min-w-0">
              <span class="text-sm font-medium text-red-800 dark:text-red-300">{{ lastError.message }}</span>
              <span v-if="lastError.hint" class="block mt-1 text-xs text-red-600 dark:text-red-400">{{ lastError.hint }}</span>
            </div>
            <button
              v-if="lastError.recoverable"
              @click="handleRetryConnection"
              class="flex-shrink-0 px-3 py-1.5 text-xs font-medium rounded-lg bg-red-100 dark:bg-red-900/30 text-red-800 dark:text-red-300 hover:bg-red-200 dark:hover:bg-red-900/50 transition-colors"
            >
              {{ $t('Retry') }}
            </button>
          </div>

          <!-- Task completed - green checkmark above suggestions when response is done -->
          <TaskCompletedFooter
            v-if="showGlobalTaskCompletedFooter"
            :showRating="false"
            class="mt-3 mb-1"
          />
          <!-- Suggestions - show in dedicated area after response is settled -->
          <Suggestions
            v-if="canShowSuggestions"
            :suggestions="suggestions"
            @select="handleSuggestionSelect"
            class="suggestions-enter"
          />

          <div
            v-if="showAgentGuidanceCta && !isLoading && !isThinking"
            class="mt-3 mb-1 rounded-xl border border-green-200 bg-green-50 px-3 py-2.5 dark:border-green-900/40 dark:bg-green-950/20"
          >
            <div class="flex items-start justify-between gap-3">
              <p class="text-sm text-green-800 dark:text-green-300">
                This looks like a complex task. Run it with full agent mode?
              </p>
              <button
                type="button"
                class="shrink-0 rounded-lg bg-green-600 px-3 py-1.5 text-xs font-semibold text-white transition-colors hover:bg-green-700"
                @click="handleUseAgentMode"
              >
                Use Agent Mode
              </button>
            </div>
          </div>
        </div>

        <div
          ref="chatBottomDockRef"
          class="chat-bottom-dock flex flex-col sticky bottom-0"
          :class="{ 'chat-bottom-dock-fixed': shouldPinComposerToBottom }"
          :style="chatBottomDockStyle"
        >
          <!-- Planning Progress Indicator - shows instant feedback before plan is ready -->
          <!-- Hide when timed_out to avoid flicker during auto-retry reconnect cycles -->
          <div
            v-if="!showSessionWarmupMessage && !isToolPanelOpen && responsePhase !== 'timed_out' && planningProgress && (!plan || plan.steps.length === 0)"
            class="planning-progress-indicator mb-2 bg-white dark:bg-[#2a2a2a] rounded-lg border border-gray-200 dark:border-[#3a3a3a] px-4 py-2.5 shadow-sm"
          >
            <!-- Content row -->
            <div class="flex items-center gap-3">
              <div class="planning-thinking flex-shrink-0">
                <ThinkingIndicator :showText="false" />
              </div>
              <div class="flex-1 min-w-0">
                <span class="planning-text-shimmer text-[15px] font-medium">
                  {{ currentPlanningMessage }}
                </span>
              </div>
              <div class="flex-shrink-0">
                <PlannerActivityIndicator />
              </div>
            </div>
          </div>

          <!-- Task Progress Bar Container - shown above ChatBox when ToolPanel is closed -->
          <div v-if="showTaskProgressBar" class="relative mb-2">
            <!-- Scroll to bottom button - positioned above progress bar -->
            <button
              @click="handleFollow"
              v-if="!follow"
              class="flex items-center justify-center w-[36px] h-[36px] rounded-full bg-[var(--background-menu-white)] hover:bg-[var(--background-gray-main)] clickable border border-[var(--border-main)] shadow-[0px_5px_16px_0px_var(--shadow-S),0px_0px_1.25px_0px_var(--shadow-S)] absolute end-0 z-30"
              style="top: calc(-48px + 1.5in - 1cm)"
            >
              <ArrowDown class="text-[var(--icon-primary)]" :size="20" />
            </button>

            <!-- Task Progress Bar -->
            <TaskProgressBar
              :plan="plan"
              :isLoading="isLoading"
              :isThinking="isThinking"
              :showThumbnail="shouldShowThumbnail"
              :sessionId="sessionId"
              :currentTool="currentToolInfo"
              :toolContent="lastNoMessageTool"
              :isInitializing="isInitializing || isSandboxInitializing"
              :isSummaryStreaming="isSummaryStreaming"
              :summaryStreamText="summaryStreamText"
              :isSessionComplete="isSessionComplete"
              :replayScreenshotUrl="replay.currentScreenshotUrl.value"
              @openPanel="handleOpenPanel"
              @requestRefresh="handleThumbnailRefresh"
            />
          </div>
          <ChatBox
            v-model="inputMessage"
            :rows="1"
            @submit="handleSubmit"
            :isRunning="isLoading"
            :isBlocked="isSandboxInitializing"
            @stop="handleStop"
            :attachments="attachments"
            @fileClick="handleAttachmentFileClick"
            expand-direction="up"
          />
        </div>
      </div>
      <!-- Wide Research Overlay -->
      <WideResearchOverlay
        :state="researchWorkflow.wideOverlayState.value"
        :phase="researchWorkflow.activePhase.value"
      />
    </div>
    <ToolPanel ref="toolPanel" :size="toolPanelSize" :sessionId="sessionId" :realTime="realTime"
      :isShare="false"
      :plan="plan"
      :isLoading="isLoading"
      :isThinking="isThinking"
      :summaryStreamText="summaryStreamText"
      :isSummaryStreaming="isSummaryStreaming"
      @jumpToRealTime="jumpToRealTime"
      :showTimeline="showTimelineControls"
      :timelineProgress="effectiveTimelineProgress"
      :timelineTimestamp="effectiveTimelineTimestamp"
      :timelineCanStepForward="effectiveCanStepForward"
      :timelineCanStepBackward="effectiveCanStepBackward"
      :isReplayMode="isReplayMode"
      :replayScreenshotUrl="replay.currentScreenshotUrl.value"
      :replayMetadata="replay.currentScreenshot.value"
      :replayScreenshots="replay.screenshots.value"
      @timelineStepForward="handleTimelineStepForward"
      @timelineStepBackward="handleTimelineStepBackward"
      @timelineSeek="handleTimelineSeek"
      @panelStateChange="handlePanelStateChange" />
  </SimpleBar>

  <!-- Connectors Dialog -->
  <ConnectorsDialog />

  <!-- Report Modal -->
  <ReportModal
    v-model:open="isReportModalOpen"
    :report="currentReport"
    :showToc="true"
    @close="closeReport"
    @download="handleReportDownload"
  />
  <Dialog v-model:open="filePreviewOpen">
    <DialogContent
      :hideCloseButton="true"
      :title="filePreviewFile?.filename || 'File preview'"
      description="View file preview"
      class="p-0 flex flex-col overflow-hidden transition-all duration-200 bg-[var(--background-white-main)] w-[95vw] max-w-[1100px] h-[85vh] max-h-[900px]"
    >
      <FilePanelContent
        v-if="filePreviewFile"
        :file="filePreviewFile"
        @hide="closeFilePreview"
      />
    </DialogContent>
  </Dialog>
</template>

<script setup lang="ts">
import SimpleBar from '../components/SimpleBar.vue';
import { ref, computed, onMounted, watch, nextTick, onUnmounted, reactive, toRefs } from 'vue';
import { useRouter, onBeforeRouteUpdate, onBeforeRouteLeave } from 'vue-router';
import { useDocumentVisibility } from '@vueuse/core';
import { useI18n } from 'vue-i18n';
import ChatBox from '../components/ChatBox.vue';
import ChatMessage from '../components/ChatMessage.vue';
import * as agentApi from '../api/agent';
import type { SSECallbacks, SSEGapInfo } from '../api/client';
import { Message, MessageContent, ToolContent, StepContent, AttachmentsContent, ReportContent, SkillDeliveryContent } from '../types/message';
import { waitForSessionReady } from '@/utils/sessionReady';
import {
  StepEventData,
  ToolEventData,
  MessageEventData,
  ErrorEventData,
  TitleEventData,
  PlanEventData,
  AgentSSEEvent,
  ModeChangeEventData,
  SuggestionEventData,
  ReportEventData,
  StreamEventData,
  ProgressEventData,
  DeepResearchEventData,
  WideResearchEventData,
  PhaseTransitionEventData,
  CheckpointSavedEventData,
  SkillDeliveryEventData,
  SkillActivationEventData,
  CanvasUpdateEventData,
} from '../types/event';
import type { DeepResearchContent } from '../types/message';
import Suggestions from '../components/Suggestions.vue';
import ToolPanel from '../components/ToolPanel.vue'
import { ArrowDown, FileSearch, Lock, Globe, Link, Check, ChevronRight, Menu } from 'lucide-vue-next';
import ShareIcon from '@/components/icons/ShareIcon.vue';
import { showErrorToast, showSuccessToast, showInfoToast } from '../utils/toast';
import type { FileInfo } from '../api/file';
import { useLeftPanel } from '../composables/useLeftPanel'
import { useSessionFileList } from '../composables/useSessionFileList'
import { useFilePanel } from '../composables/useFilePanel'
import { copyToClipboard } from '../utils/dom'
import { SessionStatus } from '../types/response';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import LoadingIndicator from '@/components/ui/LoadingIndicator.vue';
import TaskProgressBar from '@/components/TaskProgressBar.vue';
import SessionWarmupMessage from '@/components/SessionWarmupMessage.vue';
import { ReportModal, TaskCompletedFooter } from '@/components/report';
import FilePanelContent from '@/components/FilePanelContent.vue';
import type { ReportData } from '@/components/report';
import { useReport, extractSectionsFromMarkdown } from '@/composables/useReport';
import { Dialog, DialogContent } from '@/components/ui/dialog';
import ThinkingIndicator from '@/components/ui/ThinkingIndicator.vue';
import PlannerActivityIndicator from '@/components/ui/PlannerActivityIndicator.vue';
import WaitingForReply from '@/components/WaitingForReply.vue';
import WideResearchOverlay from '@/components/WideResearchOverlay.vue';
import ConnectionStatusBanner from '@/components/ConnectionStatusBanner.vue';
import { useSessionStatus } from '@/composables/useSessionStatus';
import { getToolDisplay } from '@/utils/toolDisplay';
import { useSkills } from '@/composables/useSkills';
import { useDeepResearch } from '@/composables/useDeepResearch';
import { useResearchWorkflow } from '@/composables/useResearchWorkflow';
import ConnectorsDialog from '@/components/connectors/ConnectorsDialog.vue';
import { useConnectorDialog } from '@/composables/useConnectorDialog';
import { useScreenshotReplay } from '@/composables/useScreenshotReplay';
import { useErrorBoundary } from '@/composables/useErrorBoundary';
import { shouldStopSessionOnExit } from '@/utils/sessionLifecycle';
import {
  isStructuredSummaryAssistantMessage,
  shouldNestAssistantMessageInStep,
  shouldShowAssistantHeaderForMessage,
} from '@/utils/assistantMessageLayout';
import { useResponsePhase } from '@/composables/useResponsePhase';
import { useSSEConnection } from '@/composables/useSSEConnection';
import { useSessionStreamController } from '@/composables/useSessionStreamController';
import { logSseDiagnostics } from '@/utils/sseDiagnostics';
import { isEventSourceResumeEnabled } from '@/utils/sseTransport';

const router = useRouter()
const { t } = useI18n()
const { toggleLeftPanel } = useLeftPanel()
const { showSessionFileList } = useSessionFileList()
const { hideFilePanel } = useFilePanel()
const { isReportModalOpen, currentReport, openReport, closeReport } = useReport()
const { emitStatusChange } = useSessionStatus()
const { getEffectiveSkillIds, clearSelectedSkills, lockSkillsForSession, clearSessionSkills, selectSkill } = useSkills()
const { toggleAutoRun } = useDeepResearch()
const researchWorkflow = useResearchWorkflow()
// ConnectorDialog composable — dialog manages its own visibility
useConnectorDialog()

// Error boundary — catches unhandled errors from child components to prevent page crashes
// eslint-disable-next-line @typescript-eslint/no-unused-vars -- wired for future error banner UI
const { lastCapturedError, clearError } = useErrorBoundary()

// Response phase state machine
const {
  phase: responsePhase,
  isLoading,
  isThinking,
  isSettled,
  isError: _isError,
  isTimedOut: _isTimedOut,
  isStopped: _isStopped,
  transitionTo,
  reset: _resetResponsePhase,
} = useResponsePhase()

// SSE connection management with stale detection
const handleStaleConnection = () => {
  console.warn('[SSE] Connection stale detected - attempting reconnection')
  logSseDiagnostics('ChatPage', 'stale:detected', {
    sessionId: sessionId.value ?? null,
    responsePhase: responsePhase.value,
    lastEventId: lastEventId.value || null,
  })
  // If we have a cancel function, trigger reconnection by canceling and restarting
  if (cancelCurrentChat.value && sessionId.value) {
    cancelCurrentChat.value()
    cancelCurrentChat.value = null
    // Reconnect by calling chat with empty message (resume stream)
    setTimeout(() => {
      chat('', [], { skipOptimistic: true })
    }, 1000)
  }
}

const {
  connectionState: _connectionState,
  lastEventTime,
  lastEventId,
  updateLastRealEventTime,
  isConnectionStale: _isConnectionStale,
  persistEventId: _persistEventId,
  getPersistedEventId: _getPersistedEventId,
  cleanupSessionStorage,
  startStaleDetection,
  stopStaleDetection,
} = useSSEConnection({
  staleThresholdMs: 60000, // 60 seconds
  onStaleDetected: handleStaleConnection,
  onDegradedDetected: () => {
    if (
      responsePhase.value === 'streaming'
      || responsePhase.value === 'connecting'
      || responsePhase.value === 'reconnecting'
    ) {
      transitionTo('degraded')
    }
  },
})
const isStreamDegraded = computed(() => _connectionState.value === 'degraded')
const connectionBannerRetryAttempt = ref<number | undefined>(undefined)
const connectionBannerMaxRetries = ref<number | undefined>(undefined)
const connectionBannerRetryDelayMs = ref<number | undefined>(undefined)

const dismissConnectionBanner = () => {
  connectionBannerRetryAttempt.value = undefined
  connectionBannerMaxRetries.value = undefined
  connectionBannerRetryDelayMs.value = undefined
}

const setConnectionBannerRetryState = ({ retryAttempt, maxRetries, retryDelayMs }: {
  retryAttempt?: number
  maxRetries?: number
  retryDelayMs?: number
}) => {
  connectionBannerRetryAttempt.value = retryAttempt
  connectionBannerMaxRetries.value = maxRetries
  connectionBannerRetryDelayMs.value = retryDelayMs
}

// Create initial state factory
const createInitialState = () => ({
  inputMessage: '',
  sessionId: undefined as string | undefined,
  messages: [] as Message[],
  toolPanelSize: 0,
  realTime: true,
  follow: true,
  title: t('New Chat'),
  plan: undefined as PlanEventData | undefined,
  lastNoMessageTool: undefined as ToolContent | undefined,
  lastMessageTool: undefined as ToolContent | undefined,
  lastTool: undefined as ToolContent | undefined,
  cancelCurrentChat: null as (() => void) | null,
  attachments: [] as FileInfo[],
  shareMode: 'private' as 'private' | 'public', // Default to private mode
  linkCopied: false,
  sharingLoading: false, // Loading state for share operations
  suggestions: [] as string[], // End-of-response suggestions
  receivedDoneEvent: false,
  lastHeartbeatAt: 0,
  agentMode: 'discuss' as 'discuss' | 'agent', // Current agent mode
  seenEventIds: new Map<string, number>(), // Track seen event IDs to prevent duplicates (bounded LRU map)
  thinkingText: '', // Accumulated streaming thinking text
  isThinkingStreaming: false, // True when streaming thinking is in progress
  summaryStreamText: '', // Accumulated streaming summary text
  isSummaryStreaming: false, // True when summary is streaming live
  allowStandaloneSummaryOnNextAssistant: false, // One-shot flag: render only the final summary assistant block outside step timeline
  isStale: false, // True when agent appears unresponsive (no events for 60s)
  filePreviewOpen: false,
  filePreviewFile: null as FileInfo | null,
  toolTimeline: [] as ToolContent[],
  panelToolId: undefined as string | undefined,
  isInitializing: false, // True when starting up the sandbox environment
  planningProgress: null as { phase: string; message: string; percent: number } | null, // Planning progress
  isWaitingForReply: false, // True when agent is waiting for user input
  followUpAnchorEventId: undefined as string | undefined, // Event ID to anchor follow-up context to
  pendingFollowUpSuggestion: undefined as string | undefined, // Suggestion waiting to be sent
  assistantCompletionFooterIds: new Set<string>(), // Assistant message IDs that should show green completion footer
  shortPathActivated: false, // Whether short completion path has been observed in this session
  showAgentGuidanceCta: false, // Whether to show "Use Agent Mode" CTA
  agentGuidancePrompt: undefined as string | undefined, // Prompt to replay with explicit agent guidance
  bypassShortPathLockOnce: false, // One-shot bypass when user explicitly clicks "Use Agent Mode"
  lastError: null as { message: string; type: string | null; recoverable: boolean; hint: string | null } | null,
  autoRetryCount: 0,
  isFallbackStatusPolling: false,
});

// Create reactive state
const state = reactive(createInitialState());

// Destructure refs from reactive state
const {
  inputMessage,
  sessionId,
  messages,
  toolPanelSize,
  realTime,
  follow,
  title,
  plan,
  lastNoMessageTool,
  lastTool,
  cancelCurrentChat,
  attachments,
  shareMode,
  linkCopied,
  sharingLoading,
  suggestions,
  receivedDoneEvent,
  lastHeartbeatAt,
  agentMode,
  seenEventIds,
  thinkingText,
  isThinkingStreaming,
  summaryStreamText,
  isSummaryStreaming,
  allowStandaloneSummaryOnNextAssistant,
  isStale,
  filePreviewOpen,
  filePreviewFile,
  toolTimeline,
  panelToolId,
  isInitializing,
  planningProgress,
  isWaitingForReply,
  followUpAnchorEventId,
  pendingFollowUpSuggestion,
  assistantCompletionFooterIds,
  shortPathActivated,
  showAgentGuidanceCta,
  agentGuidancePrompt,
  bypassShortPathLockOnce,
  lastError,
  autoRetryCount,
  isFallbackStatusPolling,
} = toRefs(state);

let activeChatStreamTraceId: string | null = null;
let activeStreamAttemptId = 0;

const beginStreamAttempt = (): number => {
  activeStreamAttemptId += 1;
  return activeStreamAttemptId;
}

const isActiveStreamAttempt = (attemptId: number): boolean => {
  return attemptId === activeStreamAttemptId;
}

const createScopedTransportCallbacks = (
  scope: 'transport' | 'transport_retry',
  attemptId: number,
): SSECallbacks<AgentSSEEvent['data']> => {
  const baseCallbacks = streamController.createTransportCallbacks(scope)

  return {
    onOpen: () => {
      if (!isActiveStreamAttempt(attemptId)) return
      baseCallbacks.onOpen?.()
    },
    onMessage: (payload) => {
      if (!isActiveStreamAttempt(attemptId)) return
      baseCallbacks.onMessage?.(payload)
    },
    onClose: (closeInfo) => {
      if (!isActiveStreamAttempt(attemptId)) return
      baseCallbacks.onClose?.(closeInfo)
    },
    onError: (error) => {
      if (!isActiveStreamAttempt(attemptId)) return
      baseCallbacks.onError?.(error)
    },
    onRetry: (attempt, maxAttempts) => {
      if (!isActiveStreamAttempt(attemptId)) return
      baseCallbacks.onRetry?.(attempt, maxAttempts)
    },
    onGapDetected: (info) => {
      if (!isActiveStreamAttempt(attemptId)) return
      baseCallbacks.onGapDetected?.(info)
    },
  }
}

const nextSseTraceId = (): string => {
  return `sse-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
}

const logChatSseDiagnostics = (message: string, details: Record<string, unknown> = {}) => {
  logSseDiagnostics('ChatPage', message, {
    sessionId: sessionId.value ?? null,
    responsePhase: responsePhase.value,
    receivedDoneEvent: receivedDoneEvent.value,
    lastEventId: lastEventId.value || null,
    traceId: activeChatStreamTraceId,
    ...details,
  })
}

// Response lifecycle: derived from responsePhase (isLoading and isThinking now from useResponsePhase)
// CRITICAL: Only show suggestions when session is COMPLETED (not on timeout/error)
// Timeout = agent may still be working; Completed = agent finished successfully
const canShowSuggestions = computed(() =>
  isSettled.value &&
  sessionStatus.value === SessionStatus.COMPLETED &&
  suggestions.value.length > 0 &&
  !isSummaryStreaming.value
)

const hasEmbeddedCompletionFooter = computed(() => {
  for (let i = messages.value.length - 1; i >= 0; i -= 1) {
    const messageType = messages.value[i].type;
    if (messageType === 'report' || messageType === 'skill_delivery') {
      return true;
    }
    // Stop scanning at the latest user/deep-research boundary.
    // Assistant/system noise after a report should not re-enable global footer.
    if (messageType === 'user' || messageType === 'deep_research') {
      return false;
    }
  }
  return false;
});

const showGlobalTaskCompletedFooter = computed(() =>
  canShowSuggestions.value && !hasEmbeddedCompletionFooter.value
);

// Screenshot replay for completed sessions.
// Must be initialized after sessionId ref is created to avoid TDZ runtime errors.
const replay = useScreenshotReplay(computed(() => sessionId.value))

const hasScreenshotReplay = computed(() => replay.hasScreenshots.value)

const isSessionComplete = computed(() => {
  return !!sessionStatus.value &&
    [SessionStatus.COMPLETED, SessionStatus.FAILED].includes(sessionStatus.value)
})

// Replay mode: session is completed/failed and has replay data
const isReplayMode = computed(() => {
  const ended = !isLoading.value && isSessionComplete.value
  return !!ended && hasScreenshotReplay.value
})

const isScreenshotReplayMode = computed(() => isReplayMode.value)

// Message ID counter for generating unique keys (avoids crypto overhead)
let messageIdCounter = 0;
const generateMessageId = () => `msg_${Date.now()}_${++messageIdCounter}`;

// Non-state refs that don't need reset
const toolPanel = ref<InstanceType<typeof ToolPanel>>()
const simpleBarRef = ref<InstanceType<typeof SimpleBar>>();
const observerRef = ref<HTMLDivElement>();
const chatContainerRef = ref<HTMLDivElement>();
const chatBottomDockRef = ref<HTMLDivElement>();
const chatBottomDockStyle = ref<Record<string, string>>({});
let chatContainerResizeObserver: ResizeObserver | null = null;

// Track session status
const sessionStatus = ref<SessionStatus | undefined>(undefined);
const isSandboxInitializing = computed(() => sessionStatus.value === SessionStatus.INITIALIZING);
const isWaitingForSessionReady = ref(false);
const pendingInitialMessage = ref<{ message: string; files: FileInfo[] } | null>(null);
const sessionInitTimedOut = ref(false);
const skipNextRouteReset = ref(false);

interface PendingSessionCreateState {
  pendingSessionCreate: boolean;
  mode?: 'agent' | 'discuss';
  message?: string;
  skills?: string[];
  files?: FileInfo[];
}

interface SessionTitleHintDetail {
  sessionId: string;
  title: string;
  status?: SessionStatus;
}

const emitSessionTitleHint = (detail: SessionTitleHintDetail) => {
  const normalizedTitle = detail.title?.trim();
  if (!detail.sessionId || !normalizedTitle) return;

  window.dispatchEvent(new CustomEvent<SessionTitleHintDetail>('pythinker:session-title-hint', {
    detail: {
      sessionId: detail.sessionId,
      title: normalizedTitle,
      status: detail.status,
    },
  }));
}

const hasUserMessages = computed(() =>
  messages.value.some((message) => message.type === 'user')
);

const hasAgentStartedResponding = computed(() => {
  // Check for message-based signals (assistant, tool, step, etc.)
  const hasMessageSignal = messages.value.some((message) =>
    message.type === 'assistant' ||
    message.type === 'tool' ||
    message.type === 'step' ||
    message.type === 'report' ||
    message.type === 'deep_research' ||
    message.type === 'skill_delivery'
  );

  // Check for early activity signals (progress or streaming)
  // This ensures lightweight direct responses don't show abrupt warmup->response transitions
  const hasEarlyActivitySignal =
    planningProgress.value !== null ||  // ProgressEvent received
    isThinkingStreaming.value;          // StreamEvent active

  return hasMessageSignal || hasEarlyActivitySignal;
});

const shouldPinComposerToBottom = computed(() =>
  isLoading.value || hasAgentStartedResponding.value || messages.value.length > 0
);

const updateChatBottomDockStyle = () => {
  if (!shouldPinComposerToBottom.value) {
    chatBottomDockStyle.value = {};
    return;
  }

  const chatContainer = chatContainerRef.value;
  if (!chatContainer) return;

  const rect = chatContainer.getBoundingClientRect();
  const horizontalPadding = 20;
  const maxDockWidth = 768;
  const availableWidth = Math.max(rect.width - horizontalPadding * 2, 280);
  const dockWidth = Math.min(maxDockWidth, availableWidth);
  const dockLeft = rect.left + (rect.width - dockWidth) / 2;

  chatBottomDockStyle.value = {
    left: `${Math.max(dockLeft, horizontalPadding)}px`,
    width: `${dockWidth}px`,
  };
};

const showSessionWarmupMessage = computed(() => {
  const hasPrompt = hasUserMessages.value || !!pendingInitialMessage.value?.message?.trim();
  if (!hasPrompt) return false;
  if (hasAgentStartedResponding.value) return false;
  if (sessionInitTimedOut.value) return true;

  return (
    isLoading.value ||
    isSandboxInitializing.value ||
    isWaitingForSessionReady.value ||
    isInitializing.value
  );
});

const warmupState = computed<'initializing' | 'thinking' | 'timed_out'>(() => {
  if (sessionInitTimedOut.value) return 'timed_out';
  if (isSandboxInitializing.value || isWaitingForSessionReady.value || isInitializing.value) {
    return 'initializing';
  }
  return 'thinking';
});

// Track active canvas project from canvas_update SSE events
const activeCanvasProjectId = ref<string | null>(null);

const refreshSessionStatus = async (targetSessionId?: string) => {
  const activeSessionId = targetSessionId ?? sessionId.value;
  if (!activeSessionId) {
    sessionStatus.value = undefined;
    return;
  }

  try {
    const session = await agentApi.getSession(activeSessionId);
    sessionStatus.value = session.status as SessionStatus;
    if (sessionStatus.value !== SessionStatus.INITIALIZING) {
      sessionInitTimedOut.value = false;
    }
  } catch {
    // Session status fetch failed - non-critical
  }
};

const maybeSendPendingInitialMessage = () => {
  const pending = pendingInitialMessage.value;
  if (pending && sessionStatus.value !== SessionStatus.INITIALIZING) {
    pendingInitialMessage.value = null;
    // Initial prompt is already rendered optimistically while session warms up.
    // Skip inserting a second optimistic bubble when it is actually sent.
    chat(pending.message, pending.files, { skipOptimistic: true });
  }
};

const getPendingSessionCreateState = (): PendingSessionCreateState | null => {
  const state = history.state as PendingSessionCreateState | null;
  if (!state?.pendingSessionCreate) return null;
  return state;
};

const initializePendingSession = async () => {
  const routeSessionId = router.currentRoute.value.params.sessionId;
  if (routeSessionId !== 'new') return false;

  const pendingState = getPendingSessionCreateState();
  if (!pendingState) return false;

  const pendingMessage = (pendingState.message || '').trim();
  const pendingFiles = Array.isArray(pendingState.files) ? pendingState.files : [];
  const pendingSkills = Array.isArray(pendingState.skills) ? pendingState.skills : [];
  const mode = pendingState.mode === 'discuss' ? 'discuss' : 'agent';

  // Show immediate chat view feedback while backend session is being created.
  if (pendingMessage || pendingFiles.length > 0) {
    addOptimisticUserMessage(pendingMessage, pendingFiles);
    isInitializing.value = true;
    transitionTo('connecting')
  }

  try {
    const session = await agentApi.createSession(mode);
    sessionId.value = session.session_id;
    if (pendingMessage) {
      emitSessionTitleHint({
        sessionId: session.session_id,
        title: pendingMessage,
        status: session.status,
      });
    }

    skipNextRouteReset.value = true;
    await router.replace({ path: `/chat/${session.session_id}` });

    if (pendingMessage || pendingFiles.length > 0) {
      // Apply selected skills right before sending the first message.
      for (const skillId of pendingSkills) {
        selectSkill(skillId);
      }
      pendingInitialMessage.value = { message: pendingMessage, files: pendingFiles };
      await refreshSessionStatus(session.session_id);
      await waitForSessionIfInitializing();
      maybeSendPendingInitialMessage();
    } else {
      await refreshSessionStatus(session.session_id);
      await restoreSession();
    }
  } catch {
    transitionTo('error')
    isInitializing.value = false;
    pendingInitialMessage.value = null;
    showErrorToast(t('Failed to create session, please try again later'));
  }

  return true;
};

const waitForSessionIfInitializing = async () => {
  if (!sessionId.value || isWaitingForSessionReady.value) return;
  if (sessionStatus.value !== SessionStatus.INITIALIZING) return;

  const targetSessionId = sessionId.value;
  isWaitingForSessionReady.value = true;
  sessionInitTimedOut.value = false;
  try {
    const result = await waitForSessionReady(targetSessionId, agentApi.getSessionStatus, {
      pollIntervalMs: 2000,
      maxWaitMs: 60000, // 60s for cold starts (Chrome init, sandbox warmup)
    });
    if (sessionId.value === targetSessionId) {
      sessionStatus.value = result.status;
      sessionInitTimedOut.value = result.timedOut && result.status === SessionStatus.INITIALIZING;
      if (!sessionInitTimedOut.value) {
        maybeSendPendingInitialMessage();
      }
    }
  } finally {
    isWaitingForSessionReady.value = false;
  }
};

const handleRetryInitialize = async () => {
  sessionInitTimedOut.value = false;
  await refreshSessionStatus();
  await waitForSessionIfInitializing();
  maybeSendPendingInitialMessage();
};

watch(sessionStatus, (status) => {
  if (status !== SessionStatus.INITIALIZING) {
    sessionInitTimedOut.value = false;
  }
});

// Watch sessionId changes to update status
watch(sessionId, async (newSessionId) => {
  // Clear session-level skills when switching sessions
  clearSessionSkills();

  await refreshSessionStatus(newSessionId);
  await waitForSessionIfInitializing();
}, { immediate: true });

/** Set lastError from SSE transport errors (client-side, not backend event). */
const setLastErrorFromTransportError = (error: Error) => {
  const msg = error.message ?? String(error);
  if (msg.includes('Max reconnection') || msg.includes('reconnection attempts')) {
    lastError.value = { message: msg, type: 'max_retries', recoverable: true, hint: 'Refresh the page' };
  } else if (msg.toLowerCase().includes('rate limit')) {
    lastError.value = { message: msg, type: 'rate_limit', recoverable: false, hint: 'Wait a minute' };
  } else if (msg.toLowerCase().includes('validation failed')) {
    lastError.value = { message: msg, type: 'validation', recoverable: false, hint: null };
  } else {
    lastError.value = { message: msg, type: null, recoverable: true, hint: null };
  }
};

const handleStreamGapDetected = (scope: 'transport' | 'transport_retry', info: SSEGapInfo) => {
  logChatSseDiagnostics(`${scope}:gap_detected`, {
    requestedEventId: info.requestedEventId ?? null,
    firstAvailableEventId: info.firstAvailableEventId ?? null,
    checkpointEventId: info.checkpointEventId ?? null,
  })
  if (info.checkpointEventId) {
    lastEventId.value = info.checkpointEventId
    if (sessionId.value) {
      _persistEventId(sessionId.value)
    }
  }
}

/** Deduplicated cleanup of streaming/thinking state. Use on SSE close/error. */
const cleanupStreamingState = () => {
  logChatSseDiagnostics('stream:cleanup')
  stopFallbackStatusPolling();
  thinkingText.value = '';
  isThinkingStreaming.value = false;
  summaryStreamText.value = '';
  isSummaryStreaming.value = false;
  allowStandaloneSummaryOnNextAssistant.value = false;
  isInitializing.value = false;
  planningProgress.value = null;
  stopPlanningMessageCycle();
  if (cancelCurrentChat.value) {
    cancelCurrentChat.value = null;
  }
  activeChatStreamTraceId = null;
};

const streamController = useSessionStreamController({
  responsePhase,
  receivedDoneEvent,
  seenEventIds,
  transitionTo,
  startStaleDetection,
  stopStaleDetection,
  cleanupStreamingState,
  dismissRetryBanner: dismissConnectionBanner,
  setRetryBannerState: setConnectionBannerRetryState,
  setLastErrorFromTransportError,
  handleStreamGapDetected,
  log: logChatSseDiagnostics,
})

// Reset all refs to their initial values
const resetState = () => {
  beginStreamAttempt();
  // Cancel any existing chat connection
  if (cancelCurrentChat.value) {
    cancelCurrentChat.value();
  }
  stopFallbackStatusPolling();

  // Do NOT cleanup sessionStorage here — event resume data persists across navigation
  // so returning to a session resumes from the correct position. Cleanup only in
  // handleStop, done handler, or explicit session deletion.

  researchWorkflow.reset();

  // Reset reactive state to initial values
  Object.assign(state, createInitialState());
};

// Auto-scroll is handled by the v-auto-follow-scroll directive on SimpleBar.
// The directive uses ResizeObserver (on content) + MutationObserver (childList)
// with RAF-throttled scrollTo, so no manual watchers are needed here.

watch(
  [shouldPinComposerToBottom, toolPanelSize],
  async () => {
    await nextTick();
    updateChatBottomDockStyle();
  },
  { immediate: true }
);

watch(filePreviewOpen, (isOpen) => {
  if (!isOpen) {
    filePreviewFile.value = null;
  }
});

// ===== Agent Connection Health Monitoring =====
const STALE_TIMEOUT_MS = 60000; // 60s without heartbeat = possibly unstable (avoids false positives on slow LLM/sandbox)
const HEARTBEAT_LIVENESS_MS = 25000; // Expect heartbeat every ~15s, allow 25s grace
const STALE_CHECK_INTERVAL_MS = 5000; // Check every 5 seconds
let staleCheckInterval: ReturnType<typeof setInterval> | null = null;

// Track whether we're receiving heartbeats (backend alive)
const isReceivingHeartbeats = computed(() => {
  if (lastHeartbeatAt.value === 0) return false;
  return (Date.now() - lastHeartbeatAt.value) < HEARTBEAT_LIVENESS_MS;
})

// Update last event time when any event is received
// Wrapper to update event time and reset stale flag
const updateEventTimeAndResetStale = () => {
  updateLastRealEventTime()
  isStale.value = false
}

// Check if connection appears stale
const checkStaleConnection = () => {
  if (!isLoading.value) {
    isStale.value = false;
    return;
  }

  const timeSinceLastEvent = Date.now() - lastEventTime.value;
  const timeSinceHeartbeat = lastHeartbeatAt.value > 0 ? Date.now() - lastHeartbeatAt.value : Infinity;

  // If heartbeats are arriving but no real events, we're alive but working
  // Only mark stale if BOTH real events AND heartbeats are missing
  if (timeSinceLastEvent > STALE_TIMEOUT_MS && timeSinceHeartbeat > STALE_TIMEOUT_MS && lastEventTime.value > 0) {
    isStale.value = true;
    logChatSseDiagnostics('stale:marked', {
      timeSinceLastEvent,
      timeSinceHeartbeat,
    })
  }
};

// Track if ToolPanel is open (needed for VNC thumbnail management)
const isToolPanelOpen = ref(false);

// Handler for TaskProgressBar's requestRefresh event (no-op with live VNC preview)
const handleThumbnailRefresh = () => {
  // With live VNC preview, no refresh is needed - it's always up to date
};

// Start stale detection when loading starts
watch(isLoading, (loading) => {
  if (loading) {
    updateEventTimeAndResetStale();
    if (!staleCheckInterval) {
      staleCheckInterval = setInterval(checkStaleConnection, STALE_CHECK_INTERVAL_MS);
    }
  } else {
    isStale.value = false;
    if (staleCheckInterval) {
      clearInterval(staleCheckInterval);
      staleCheckInterval = null;
    }
  }
});

// Auto-retry after timeout: progressive backoff (5s, 15s, 45s, 60s), max 4 attempts
const AUTO_RETRY_DELAYS_MS = [5000, 15000, 45000, 60000];
const FALLBACK_STATUS_POLL_INTERVAL_MS = 5000;
const FALLBACK_STATUS_POLL_MAX_ATTEMPTS = 24; // ~2 minutes

const stopFallbackStatusPolling = () => {
  streamController.clearReconnectCoordinator();
};

const pollSessionStatusFallback = async (): Promise<'continue' | 'stop'> => {
  if (!sessionId.value || responsePhase.value !== 'timed_out') {
    return 'stop';
  }

  try {
    const statusResp = await agentApi.getSessionStatus(sessionId.value);
    const status = statusResp.status as SessionStatus;
    if (status === SessionStatus.COMPLETED || status === SessionStatus.FAILED) {
      sessionStatus.value = status;
      emitStatusChange(sessionId.value, status);
      if (status === SessionStatus.COMPLETED) {
        transitionTo('completing');
        await replay.loadScreenshots();
      } else {
        transitionTo('error');
        if (!lastError.value) {
          lastError.value = {
            message: 'Task failed while reconnecting.',
            type: 'session_failed',
            recoverable: true,
            hint: 'Retry the connection to inspect details.',
          };
        }
      }
      return 'stop';
    }
  } catch {
    // Keep polling on transient errors; controller handles scheduling/attempt caps.
  }

  return 'continue';
};

// Cleanup on unmount
onUnmounted(() => {
  if (staleCheckInterval) {
    clearInterval(staleCheckInterval);
    staleCheckInterval = null;
  }
  stopFallbackStatusPolling();
  stopPlanningMessageCycle();
});

const getLastStep = (): StepContent | undefined => {
  return messages.value.filter(message => message.type === 'step').pop()?.content as StepContent;
}

const shouldShowStepConnector = (messageIndex: number): boolean => {
  const currentMessage = messages.value[messageIndex];
  if (!currentMessage || currentMessage.type !== 'step') return false;

  for (let i = messageIndex + 1; i < messages.value.length; i += 1) {
    if (messages.value[i].type === 'step') {
      return true;
    }
  }

  return false;
};

const shouldShowStepLeadingConnector = (messageIndex: number): boolean => {
  const currentMessage = messages.value[messageIndex];
  if (!currentMessage || currentMessage.type !== 'step') return false;

  for (let i = messageIndex - 1; i >= 0; i -= 1) {
    if (messages.value[i].type === 'step') {
      return true;
    }
  }

  return false;
};

const shouldShowAssistantHeader = (messageIndex: number): boolean => {
  return shouldShowAssistantHeaderForMessage(messages.value, messageIndex);
};

const shouldRenderSummaryCard = (messageIndex: number): boolean => {
  const currentMessage = messages.value[messageIndex];
  if (!currentMessage || currentMessage.type !== 'assistant') return false;

  const nextMessage = messages.value[messageIndex + 1];
  if (!nextMessage || nextMessage.type !== 'report') return false;

  const assistantText = ((currentMessage.content as MessageContent).content || '').trim();
  return isStructuredSummaryAssistantMessage(assistantText);
};

const addOptimisticUserMessage = (message: string, files: FileInfo[] = []) => {
  const normalizedMessage = message.trim();
  if (!normalizedMessage && files.length === 0) return;
  const nowInSeconds = Math.floor(Date.now() / 1000);

  if (normalizedMessage && messages.value.length > 0) {
    for (let i = messages.value.length - 1; i >= 0; i -= 1) {
      if (messages.value[i].type !== 'user') continue;
      const lastUserContent = messages.value[i].content as MessageContent;
      if (
        lastUserContent.content === normalizedMessage &&
        nowInSeconds - lastUserContent.timestamp <= 10
      ) {
        return;
      }
      break;
    }
  }

  if (normalizedMessage) {
    messages.value.push({
      id: generateMessageId(),
      type: 'user',
      content: {
        content: normalizedMessage,
        timestamp: nowInSeconds,
      } as MessageContent,
    });
  }

  if (files.length > 0) {
    messages.value.push({
      id: generateMessageId(),
      type: 'attachments',
      content: {
        role: 'user',
        attachments: files,
        timestamp: nowInSeconds,
      } as AttachmentsContent,
    });
  }
};

const currentRunningStepId = computed<string | undefined>(() => {
  for (let i = messages.value.length - 1; i >= 0; i -= 1) {
    const message = messages.value[i];
    if (message.type !== 'step') continue;
    const step = message.content as StepContent;
    if (step.status === 'running') return step.id;
  }
  return undefined;
});

const hasRunningStep = computed(() => !!currentRunningStepId.value);
const hasThinkingSignal = computed(() => isThinkingStreaming.value || isThinking.value);
const hasActiveToolCall = computed(() => lastTool.value?.status === 'calling');

// Identify the active step that should show the thinking indicator inside it.
// This is bound to actual runtime state: running step + thinking signal + no active tool call.
const activeThinkingStepId = computed<string | undefined>(() => {
  if (!isLoading.value) return undefined;
  if (!hasThinkingSignal.value) return undefined;
  if (hasActiveToolCall.value) return undefined;
  return currentRunningStepId.value;
});

// Show standalone thinking indicator whenever the agent is processing
// (no running step or active tool call visible).
const showFloatingThinkingIndicator = computed(() => {
  if (showSessionWarmupMessage.value) return false;
  if (!isLoading.value) return false;
  if (hasActiveToolCall.value) return false;
  if (hasRunningStep.value) return false;
  return true;
});

const showTaskProgressBar = computed(() =>
  !showSessionWarmupMessage.value &&
  !isToolPanelOpen.value &&
  (!!plan.value?.steps?.length || !!lastNoMessageTool.value || isInitializing.value || isSandboxInitializing.value)
);

// Add extra bottom scroll room when mini VNC thumbnail is rendered with the task progress bar.
const showThumbnailDockSpacer = computed(() => showTaskProgressBar.value && shouldShowThumbnail.value);

// Handle tool panel state changes
const handlePanelStateChange = (isOpen: boolean) => {
  isToolPanelOpen.value = isOpen;
};

// Computer-related tools that should show thumbnail
const COMPUTER_TOOLS = ['browser', 'shell', 'file', 'browser_agent', 'code_executor'];
const isComputerTool = (tool?: ToolContent | null) => {
  if (!tool) return false;
  return COMPUTER_TOOLS.includes(tool.name);
};

// Always show thumbnail when panel is closed and there's activity
const shouldShowThumbnail = computed(() => {
  if (isToolPanelOpen.value) return false;
  if (!sessionId.value) return false;
  // Show live VNC thumbnail when there's an active plan, loading, or tool activity
  return !!plan.value?.steps?.length || isLoading.value || isPlanCompleted.value || !!lastNoMessageTool.value;
});

const isPlanCompleted = computed(() => {
  return !!plan.value?.steps?.length && plan.value.steps.every(step => step.status === 'completed');
});


// Get current tool info for display
const currentToolInfo = computed(() => {
  const tool = lastNoMessageTool.value;
  if (!tool) return null;
  const display = getToolDisplay({
    name: tool.name,
    function: tool.function,
    args: tool.args,
    display_command: tool.display_command
  });

  return {
    name: display.displayName,
    function: display.actionLabel,
    functionArg: display.resourceLabel,
    status: tool.status,
    icon: display.icon
  };
});

const toolTimelineIndex = computed(() => {
  if (!panelToolId.value) return -1;
  return toolTimeline.value.findIndex(tool => tool.tool_call_id === panelToolId.value);
});

const toolTimelineProgress = computed(() => {
  const total = toolTimeline.value.length;
  if (total <= 1 || toolTimelineIndex.value < 0) return 0;
  return (toolTimelineIndex.value / (total - 1)) * 100;
});

const toolTimelineTimestamp = computed(() => {
  if (toolTimelineIndex.value >= 0) {
    return toolTimeline.value[toolTimelineIndex.value].timestamp;
  }
  return lastNoMessageTool.value?.timestamp;
});

const toolTimelineCanStepForward = computed(() => {
  const total = toolTimeline.value.length;
  return toolTimelineIndex.value >= 0 && toolTimelineIndex.value < total - 1;
});

const toolTimelineCanStepBackward = computed(() => toolTimelineIndex.value > 0);

const showTimelineControls = computed(() => {
  return isScreenshotReplayMode.value || toolTimelineIndex.value >= 0
});

// Effective timeline values — replay mode overrides tool timeline
const effectiveTimelineProgress = computed(() =>
  isScreenshotReplayMode.value ? replay.progress.value : toolTimelineProgress.value
);
const effectiveTimelineTimestamp = computed(() =>
  isScreenshotReplayMode.value ? replay.currentTimestamp.value : toolTimelineTimestamp.value
);
const effectiveCanStepForward = computed(() =>
  isScreenshotReplayMode.value ? replay.canStepForward.value : toolTimelineCanStepForward.value
);
const effectiveCanStepBackward = computed(() =>
  isScreenshotReplayMode.value ? replay.canStepBackward.value : toolTimelineCanStepBackward.value
);

// Handle opening the panel from TaskProgressBar
const handleOpenPanel = () => {
  if (lastNoMessageTool.value) {
    toolPanel.value?.showToolPanel(lastNoMessageTool.value, isLiveTool(lastNoMessageTool.value));
    panelToolId.value = lastNoMessageTool.value.tool_call_id;
  } else if (sessionId.value) {
    // Allow opening panel even without tool content - show live sandbox view
    const placeholderTool: ToolContent = {
      tool_call_id: `placeholder-${Date.now()}`,
      name: 'browser',
      function: 'browser_view',
      args: {},
      status: 'completed',
      timestamp: Date.now(),
    };
    toolPanel.value?.showToolPanel(placeholderTool, true);
    panelToolId.value = placeholderTool.tool_call_id;
  }
};

const upsertToolTimeline = (toolContent: ToolContent) => {
  if (!isComputerTool(toolContent)) return;
  const existingIndex = toolTimeline.value.findIndex(tool => tool.tool_call_id === toolContent.tool_call_id);
  if (existingIndex >= 0) {
    Object.assign(toolTimeline.value[existingIndex], toolContent);
    return;
  }
  toolTimeline.value.push(toolContent);
};

const maybeAppendAssistantMessageToStep = (
  messageData: MessageEventData,
  allowStandaloneSummary = false,
): boolean => {
  if (messageData.role !== 'assistant') return false;

  const text = (messageData.content || '').trim();
  if (!text) return false;

  let targetStep: StepContent | undefined;
  for (let i = messages.value.length - 1; i >= 0; i -= 1) {
    const candidate = messages.value[i];
    const candidateType = candidate.type as string;
    if (candidateType === 'step') {
      targetStep = candidate.content as StepContent;
      break;
    }
    // Stop if we hit another top-level conversational block.
    if (!['tool', 'attachments', 'thought', 'phase'].includes(candidateType)) {
      return false;
    }
  }
  if (!targetStep) return false;

  if (!shouldNestAssistantMessageInStep(text, targetStep, { allowStandaloneSummary })) {
    return false;
  }

  const lastTool = targetStep.tools[targetStep.tools.length - 1];
  if (lastTool?.name === 'message' && String(lastTool.args?.text || '') === text) {
    return true;
  }

  targetStep.tools.push({
    tool_call_id: `inline-message-${messageData.timestamp}-${targetStep.tools.length}`,
    name: 'message',
    function: 'message',
    args: { text },
    status: 'called',
    timestamp: messageData.timestamp,
  });

  return true;
};

const getAttachmentAliases = (file: FileInfo): Set<string> => {
  const aliases = new Set<string>();
  const normalizedFileId = (file.file_id || '').trim();
  const normalizedFilename = (file.filename || '').trim().toLowerCase();
  const normalizedSize = Number.isFinite(file.size) ? String(file.size) : '';

  if (normalizedFileId) {
    aliases.add(`id:${normalizedFileId}`);
  }
  if (normalizedFilename) {
    aliases.add(`name:${normalizedFilename}`);
    if (normalizedSize) {
      aliases.add(`name_size:${normalizedFilename}:${normalizedSize}`);
    }
  }

  return aliases;
};

const buildAttachmentKeySet = (files: FileInfo[]): Set<string> => {
  const keys = new Set<string>();
  for (const file of files) {
    for (const alias of getAttachmentAliases(file)) {
      keys.add(alias);
    }
  }
  return keys;
};

const hasAttachmentOverlap = (attachments: FileInfo[], reportAttachmentKeys: Set<string>): boolean => {
  return attachments.some((file) => {
    const aliases = getAttachmentAliases(file);
    for (const alias of aliases) {
      if (reportAttachmentKeys.has(alias)) {
        return true;
      }
    }
    return false;
  });
};

const removeRedundantAssistantAttachmentMessages = (reportAttachments: FileInfo[]): void => {
  if (reportAttachments.length === 0) return;

  const reportAttachmentKeys = buildAttachmentKeySet(reportAttachments);

  for (let i = messages.value.length - 1; i >= 0; i -= 1) {
    const message = messages.value[i];

    if (message.type === 'attachments') {
      const attachmentContent = message.content as AttachmentsContent;
      const isAssistantAttachment = attachmentContent.role === 'assistant';
      const overlapsReportFiles = hasAttachmentOverlap(attachmentContent.attachments ?? [], reportAttachmentKeys);

      if (isAssistantAttachment && overlapsReportFiles) {
        const remainingAttachments = (attachmentContent.attachments ?? []).filter(
          (file) => !hasAttachmentOverlap([file], reportAttachmentKeys),
        );
        if (remainingAttachments.length === 0) {
          messages.value.splice(i, 1);
        } else {
          attachmentContent.attachments = remainingAttachments;
        }
        continue;
      }
      break;
    }

    if (message.type === 'tool' || message.type === 'step' || message.type === 'phase' || message.type === 'thought') {
      continue;
    }

    break;
  }
};

const isInternalContextMessage = (messageData: MessageEventData): boolean => {
  const content = (messageData.content || '').trimStart();
  if (!content) return false;

  return (
    content.startsWith('[Session history for context]') ||
    content.startsWith('[User Browser Interaction]')
  );
};

// Handle message event
const handleMessageEvent = (messageData: MessageEventData) => {
  if (isInternalContextMessage(messageData)) {
    return;
  }

  const allowStandaloneSummary = messageData.role === 'assistant' && allowStandaloneSummaryOnNextAssistant.value;

  // Assistant message means agent finished thinking
  if (messageData.role === 'assistant') {
    // Track anchor event ID for follow-up suggestions
    followUpAnchorEventId.value = messageData.event_id;
  }

  // Clear summary streaming overlay — message takes over
  summaryStreamText.value = '';
  isSummaryStreaming.value = false;

  // Keep per-step narration nested inside the active step thread.
  if (maybeAppendAssistantMessageToStep(messageData, allowStandaloneSummary)) {
    if (messageData.role === 'assistant') {
      allowStandaloneSummaryOnNextAssistant.value = false;
    }
    return;
  }

  // Prevent duplicate user messages - check against LAST user message (not just last message)
  // This handles cases where tool/step events appear between duplicate user messages
  if (messageData.role === 'user' && messages.value.length > 0) {
    const incomingContent = (messageData.content || '').trim();
    // Find the last user message in the array
    for (let i = messages.value.length - 1; i >= 0; i--) {
      if (messages.value[i].type === 'user') {
        const lastUserContent = messages.value[i].content as MessageContent;
        if ((lastUserContent.content || '').trim() === incomingContent) {
          console.debug('Skipping duplicate user message:', messageData.content?.slice(0, 50));
          return;
        }
        break; // Only check the most recent user message
      }
    }
  }

  // Prevent duplicate assistant messages with same content
  if (messageData.role === 'assistant' && messages.value.length > 0) {
    for (let i = messages.value.length - 1; i >= 0; i--) {
      if (messages.value[i].type === 'assistant') {
        const lastAssistantContent = messages.value[i].content as MessageContent;
        if (lastAssistantContent.content === messageData.content) {
          console.debug('Skipping duplicate assistant message:', messageData.content?.slice(0, 50));
          return;
        }
        break; // Only check the most recent assistant message
      }
    }
  }

  messages.value.push({
    id: generateMessageId(),
    type: messageData.role,
    content: {
      ...messageData
    } as MessageContent,
  });

  if (messageData.role === 'assistant') {
    allowStandaloneSummaryOnNextAssistant.value = false;
  }

  if (messageData.attachments?.length > 0) {
    messages.value.push({
      id: generateMessageId(),
      type: 'attachments',
      content: {
        ...messageData
      } as AttachmentsContent,
    });
  }
}

// Handle tool event
const handleToolEvent = (toolData: ToolEventData) => {
  const lastStep = getLastStep();
  const toolContent: ToolContent = {
    ...toolData
  }
  if (lastTool.value && lastTool.value.tool_call_id === toolContent.tool_call_id) {
    Object.assign(lastTool.value, toolContent);
  } else {
    if (lastStep?.status === 'running') {
      // Check if tool already exists in this step (avoid duplicates from SSE reconnection)
      const existingTool = lastStep.tools.find(t => t.tool_call_id === toolContent.tool_call_id);
      if (existingTool) {
        Object.assign(existingTool, toolContent);
      } else {
        lastStep.tools.push(toolContent);
      }
    } else {
      messages.value.push({
        id: generateMessageId(),
        type: 'tool',
        content: toolContent,
      });
    }
    lastTool.value = toolContent;
  }
  if (toolContent.name !== 'message') {
    lastNoMessageTool.value = toolContent;
    upsertToolTimeline(toolContent);
    if (realTime.value) {
      panelToolId.value = toolContent.tool_call_id;
      if (isToolPanelOpen.value) {
        // Auto-switch panel content when panel is open and new tool starts
        toolPanel.value?.showToolPanel(toolContent, isLiveTool(toolContent));
      }
    }
  }
}

// Handle phase event - creates/updates phase message groups
const handlePhaseEvent = (phaseData: import('../types/event').AgentPhaseEventData) => {
  if (phaseData.status === 'started') {
    messages.value.push({
      id: generateMessageId(),
      type: 'phase',
      content: {
        phase_id: phaseData.phase_id,
        phase_type: phaseData.phase_type,
        label: phaseData.label,
        status: phaseData.status,
        order: phaseData.order,
        icon: phaseData.icon,
        color: phaseData.color,
        total_phases: phaseData.total_phases,
        steps: [],
        timestamp: phaseData.timestamp || Date.now(),
      } as import('../types/message').PhaseContent,
    })
  } else if (phaseData.status === 'completed' || phaseData.status === 'skipped') {
    // Find and update the phase message
    for (let i = messages.value.length - 1; i >= 0; i--) {
      const msg = messages.value[i]
      if (msg.type === 'phase') {
        const pc = msg.content as import('../types/message').PhaseContent
        if (pc.phase_id === phaseData.phase_id) {
          pc.status = phaseData.status
          if (phaseData.skip_reason) pc.skip_reason = phaseData.skip_reason
          break
        }
      }
    }
  }
}

// Find the current active phase message (if any)
const findActivePhaseMessage = (phaseId: string | undefined) => {
  if (!phaseId) return null
  for (let i = messages.value.length - 1; i >= 0; i--) {
    const msg = messages.value[i]
    if (msg.type === 'phase') {
      const pc = msg.content as import('../types/message').PhaseContent
      if (pc.phase_id === phaseId) return pc
    }
  }
  return null
}

// Handle step event
const handleStepEvent = (stepData: StepEventData) => {
  const lastStep = getLastStep();
  if (stepData.status === 'running') {
    const stepContent: StepContent = {
      ...stepData,
      tools: [],
      phase_id: stepData.phase_id,
      step_type: stepData.step_type,
    }

    // Try to nest step inside its phase group
    const phaseContent = findActivePhaseMessage(stepData.phase_id)
    if (phaseContent) {
      phaseContent.steps.push(stepContent)
    }

    // Always push as top-level message too (for timeline rendering)
    messages.value.push({
      id: generateMessageId(),
      type: 'step',
      content: stepContent,
    });
  } else if (stepData.status === 'completed') {
    // Find the matching step by ID and update its status
    const matchingStep = messages.value
      .filter(m => m.type === 'step')
      .map(m => m.content as StepContent)
      .find(s => s.id === stepData.id);
    if (matchingStep) {
      matchingStep.status = stepData.status;
    } else if (lastStep) {
      // Fallback: update last step if no ID match
      lastStep.status = stepData.status;
    }
    // Also update in phase
    if (stepData.phase_id) {
      const phaseContent = findActivePhaseMessage(stepData.phase_id)
      if (phaseContent) {
        const phaseStep = phaseContent.steps.find(s => s.id === stepData.id)
        if (phaseStep) phaseStep.status = stepData.status
      }
    }
  } else if (stepData.status === 'failed') {
    transitionTo('error')
    // Notify sidebar that session is no longer running
    if (sessionId.value) {
      emitStatusChange(sessionId.value, SessionStatus.COMPLETED);
    }
  }
}

// Handle error event (backend-sent error with structured data)
const handleErrorEvent = (errorData: ErrorEventData) => {
  lastError.value = {
    message: errorData.error || (errorData as unknown as { message?: string }).message || 'An unexpected error occurred',
    type: errorData.error_type ?? null,
    recoverable: errorData.recoverable ?? true,
    hint: errorData.retry_hint ?? null,
  };
  // Accept both schema-compliant `error` field and legacy `message` fallback
  const errorText = lastError.value.message;
  messages.value.push({
    id: generateMessageId(),
    type: 'assistant',
    content: {
      content: errorText,
      timestamp: errorData.timestamp
    } as MessageContent,
  });
  // Notify sidebar that session is no longer running
  if (sessionId.value) {
    emitStatusChange(sessionId.value, SessionStatus.COMPLETED);
  }
}

// Handle title event
const handleTitleEvent = (titleData: TitleEventData) => {
  title.value = titleData.title;
  if (sessionId.value && titleData.title?.trim()) {
    emitSessionTitleHint({
      sessionId: sessionId.value,
      title: titleData.title,
      status: sessionStatus.value,
    });
  }
}

// Handle plan event
const handlePlanEvent = (planData: PlanEventData) => {
  // Clear thinking text and planning progress when plan arrives
  thinkingText.value = '';
  isThinkingStreaming.value = false;
  planningProgress.value = null;  // Clear progress - plan is ready
  stopPlanningMessageCycle();
  plan.value = planData;
}

// Handle stream event (thinking text streaming or summary streaming)
const handleStreamEvent = (streamData: StreamEventData) => {
  researchWorkflow.handleStreamEvent(streamData);
  if (streamData.phase === 'reflection') {
    syncDeepResearchMessageMetadata();
  }
  const phase = streamData.phase || 'thinking';

  if (phase === 'summarizing') {
    if (streamData.content) {
      summaryStreamText.value += streamData.content;
    }
    if (streamData.is_final) {
      isSummaryStreaming.value = false;
      allowStandaloneSummaryOnNextAssistant.value = summaryStreamText.value.trim().length > 0;
      // Keep text visible briefly — cleared when ReportEvent arrives
    } else {
      isSummaryStreaming.value = true;
    }
    return;
  }

  // Default: thinking phase (existing behavior)
  if (streamData.is_final) {
    isThinkingStreaming.value = false;
    thinkingText.value = '';
  } else {
    isThinkingStreaming.value = true;
    thinkingText.value += streamData.content;
  }
}

// ===== Planning Messages - Interesting rotating phrases =====
const PLANNING_MESSAGES = [
  "Analyzing task complexity...",
  "Mapping out the approach...",
  "Crafting the perfect strategy...",
  "Connecting the dots...",
  "Architecting the solution...",
  "Weighing the options...",
  "Charting the course...",
  "Piecing together the puzzle...",
  "Calibrating the plan...",
  "Orchestrating the steps...",
  "Fine-tuning the approach...",
  "Exploring possibilities...",
  "Building the roadmap...",
  "Designing the workflow...",
  "Structuring the execution...",
];

const planningMessageIndex = ref(0);
let planningMessageInterval: ReturnType<typeof setInterval> | null = null;

// Cycle through planning messages for visual interest
const startPlanningMessageCycle = () => {
  if (planningMessageInterval) return;
  planningMessageIndex.value = Math.floor(Math.random() * PLANNING_MESSAGES.length);
  planningMessageInterval = setInterval(() => {
    planningMessageIndex.value = (planningMessageIndex.value + 1) % PLANNING_MESSAGES.length;
  }, 2500);
};

const stopPlanningMessageCycle = () => {
  if (planningMessageInterval) {
    clearInterval(planningMessageInterval);
    planningMessageInterval = null;
  }
};

// Computed: current planning message (cycles through interesting phrases)
const currentPlanningMessage = computed(() => {
  return PLANNING_MESSAGES[planningMessageIndex.value];
});

// Handle progress event (instant feedback during planning)
const handleProgressEvent = (progressData: ProgressEventData) => {
  // Heartbeat: update timestamp for liveness tracking
  if (progressData.phase === 'heartbeat') {
    lastHeartbeatAt.value = Date.now();
    logChatSseDiagnostics('event:heartbeat', {
      heartbeatAt: lastHeartbeatAt.value,
    })
    return;
  }

  // Start message cycling if not already running
  startPlanningMessageCycle();

  // Update planning progress for UI
  planningProgress.value = {
    phase: progressData.phase,
    message: progressData.message,
    percent: progressData.progress_percent || 0
  };

  // Clear initialization state on first progress event
  if (isInitializing.value) {
    isInitializing.value = false;
  }

  // Clear progress when planning is complete (plan event will follow)
  if (progressData.phase === 'finalizing' && progressData.progress_percent && progressData.progress_percent >= 80) {
    // Keep progress visible until plan arrives
  }
}

// Handle mode change event
const handleModeChangeEvent = (modeData: ModeChangeEventData) => {
  agentMode.value = modeData.mode;
}

// Handle suggestion event
const handleSuggestionEvent = (suggestionData: SuggestionEventData) => {
  suggestions.value = suggestionData.suggestions;
  if (suggestionData.anchor_event_id) {
    followUpAnchorEventId.value = suggestionData.anchor_event_id;
  }
}

const SUGGESTION_STOPWORDS = new Set([
  'about', 'after', 'again', 'also', 'been', 'before', 'being', 'between', 'could', 'does',
  'from', 'have', 'into', 'just', 'make', 'more', 'most', 'only', 'over', 'same',
  'that', 'than', 'their', 'them', 'then', 'there', 'they', 'this', 'what', 'when',
  'where', 'which', 'while', 'will', 'with', 'would', 'your'
]);

const extractTopicHint = (text: string): string | null => {
  const cleaned = text
    .toLowerCase()
    .replace(/[`*_#>[\](){}.,!?;:"']/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();

  if (!cleaned) return null;

  const tokens = cleaned
    .split(' ')
    .filter(token => token.length >= 4 && !SUGGESTION_STOPWORDS.has(token));

  if (tokens.length === 0) return null;
  return tokens.slice(0, 3).join(' ');
};

const buildCompletionFallbackSuggestions = (): string[] => {
  let assistantContext = '';
  let latestUserMessage = '';

  for (let i = messages.value.length - 1; i >= 0; i--) {
    const message = messages.value[i];
    if (message.type === 'assistant') {
      if (!assistantContext) {
        assistantContext = (message.content as MessageContent).content || '';
      }
      continue;
    }
    if (message.type === 'report') {
      if (!assistantContext) {
        const reportContent = message.content as ReportContent;
        assistantContext = `${reportContent.title || ''} ${reportContent.content || ''}`;
      }
      continue;
    }
    if (message.type === 'user') {
      latestUserMessage = ((message.content as MessageContent).content || '').trim();
      break;
    }
  }

  // Skip suggestions for greeting/trivial responses
  const combined = `${latestUserMessage} ${assistantContext}`.trim().toLowerCase();
  if (combined.length < 80 && !assistantContext.includes('```') && !assistantContext.includes('#')) {
    const greetingPatterns = /^(hi|hello|hey|good\s*(morning|afternoon|evening)|thanks|thank\s*you|ok|sure|yes|no|bye|goodbye|welcome)\b/i;
    if (greetingPatterns.test(latestUserMessage.trim()) || greetingPatterns.test(assistantContext.trim())) {
      return []; // No suggestions for greetings
    }
  }

  const contextText = `${latestUserMessage} ${assistantContext}`.toLowerCase();
  const topicHint = extractTopicHint(`${latestUserMessage} ${assistantContext}`);

  if (contextText.includes('pirate') || /\barrr+\b/.test(contextText)) {
    return [
      "Tell me a pirate story.",
      "What's your favorite pirate saying?",
      "How do pirates find treasure?",
    ];
  }

  if (topicHint) {
    return [
      `Can you expand on ${topicHint} with an example?`,
      `What are the best next steps for ${topicHint}?`,
      `What trade-offs should I consider for ${topicHint}?`,
    ];
  }

  return [
    "Can you explain this in more detail?",
    "What are the best next steps?",
    "Can you give me a practical example?",
  ];
};

const ensureCompletionSuggestions = () => {
  if (suggestions.value.length > 0) return;
  suggestions.value = buildCompletionFallbackSuggestions();

  // Find anchor event ID from latest assistant or report message
  for (let i = messages.value.length - 1; i >= 0; i--) {
    const message = messages.value[i];
    if (message.type === 'assistant') {
      const content = message.content as MessageContent;
      if (content.event_id) {
        followUpAnchorEventId.value = content.event_id;
        break;
      }
    }
    if (message.type === 'report') {
      const content = message.content as ReportContent;
      if (content.event_id) {
        followUpAnchorEventId.value = content.event_id;
        break;
      }
    }
  }
};

const SHORT_COMPLETION_MAX_CHARS = 220;
const COMPLEX_PROMPT_MIN_CHARS = 70;
const COMPLEX_PROMPT_PATTERNS = [
  /\b(build|implement|create|develop|design|architect|refactor)\b/i,
  /\b(debug|fix|investigate|analyze)\b/i,
  /\b(plan|step[-\s]?by[-\s]?step|workflow|roadmap)\b/i,
  /\bapi|backend|frontend|database|integration|deployment\b/i,
  /\bcomprehensive|detailed|end-to-end|production\b/i,
];

const shouldShowShortCompletionFooter = (assistantContent: string): boolean => {
  const content = assistantContent.trim();
  if (!content || content.length > SHORT_COMPLETION_MAX_CHARS) {
    return false;
  }

  // Keep the fast-route completion footer focused on simple short replies.
  const hasStructuredMarkdown = /(^|\n)\s*(#{1,6}\s|[-*+]\s|\d+\.\s|```|\|.+\|)/m.test(content);
  return !hasStructuredMarkdown;
};

const isComplexTaskPrompt = (text: string): boolean => {
  const normalized = text.trim();
  if (!normalized) return false;
  if (normalized.length >= COMPLEX_PROMPT_MIN_CHARS) return true;
  return COMPLEX_PROMPT_PATTERNS.some((pattern) => pattern.test(normalized));
};

const markShortAssistantCompletion = (): boolean => {
  for (let i = messages.value.length - 1; i >= 0; i -= 1) {
    const message = messages.value[i];

    // Long/report flows already have their own completion footer with rating.
    if (message.type === 'report' || message.type === 'skill_delivery') {
      return false;
    }

    if (message.type !== 'assistant') {
      continue;
    }

    const content = ((message.content as MessageContent).content || '').trim();
    if (shouldShowShortCompletionFooter(content)) {
      assistantCompletionFooterIds.value.add(message.id);
      shortPathActivated.value = true;
      return true;
    }
    return false;
  }
  return false;
};

// Handle report event
const handleReportEvent = (reportData: ReportEventData) => {
  // Clear summary streaming overlay — report card takes over
  summaryStreamText.value = '';
  isSummaryStreaming.value = false;
  allowStandaloneSummaryOnNextAssistant.value = false;

  const reportAttachments = reportData.attachments ?? [];
  removeRedundantAssistantAttachmentMessages(reportAttachments);

  // Track anchor event ID for follow-up suggestions
  followUpAnchorEventId.value = reportData.event_id;

  const sections = extractSectionsFromMarkdown(reportData.content);
  const nextReportContent: ReportContent = {
    id: reportData.id,
    event_id: reportData.event_id,
    title: reportData.title,
    content: reportData.content,
    lastModified: reportData.timestamp * 1000,
    fileCount: reportAttachments.length,
    sections,
    sources: reportData.sources,
    attachments: reportAttachments,
    timestamp: reportData.timestamp,
  };

  // Resume/replay may surface the same report more than once; update in place.
  for (let i = messages.value.length - 1; i >= 0; i -= 1) {
    const existingMessage = messages.value[i];
    if (existingMessage.type !== 'report') continue;

    const existingContent = existingMessage.content as ReportContent;
    if (existingContent.id === reportData.id || existingContent.event_id === reportData.event_id) {
      existingMessage.content = nextReportContent;
      return;
    }
  }

  messages.value.push({
    id: generateMessageId(),
    type: 'report',
    content: nextReportContent,
  });
}

// Handle deep research event
const handleDeepResearchEvent = (data: DeepResearchEventData) => {
  const workflowState = researchWorkflow.handleDeepResearchEvent(data);

  // Find existing deep research message
  const idx = messages.value.findIndex(
    m => m.type === 'deep_research' &&
         (m.content as DeepResearchContent).research_id === data.research_id
  );

  if (idx >= 0) {
    // Update existing message
    const existingContent = messages.value[idx].content as DeepResearchContent;
    messages.value[idx].content = {
      ...existingContent,
      status: workflowState.status,
      queries: data.queries,
      completed_count: data.completed_queries,
      total_count: data.total_queries,
      auto_run: data.auto_run,
      phase: workflowState.phase ?? undefined,
      phase_label: workflowState.phase_label ?? undefined,
      latest_reflection: workflowState.latest_reflection,
      checkpoints: workflowState.checkpoints,
    } as DeepResearchContent;
  } else {
    // Create new message
    messages.value.push({
      id: generateMessageId(),
      type: 'deep_research',
      content: {
        research_id: data.research_id,
        status: workflowState.status,
        queries: data.queries || [],
        completed_count: data.completed_queries,
        total_count: data.total_queries,
        auto_run: data.auto_run,
        phase: workflowState.phase ?? undefined,
        phase_label: workflowState.phase_label ?? undefined,
        latest_reflection: workflowState.latest_reflection,
        checkpoints: workflowState.checkpoints,
        timestamp: data.timestamp
      } as DeepResearchContent
    });
  }
};

const syncDeepResearchMessageMetadata = (researchId?: string) => {
  const findTargetIndex = (): number => {
    if (researchId) {
      return messages.value.findIndex(
        (message) =>
          message.type === 'deep_research' &&
          (message.content as DeepResearchContent).research_id === researchId,
      );
    }

    for (let i = messages.value.length - 1; i >= 0; i -= 1) {
      if (messages.value[i].type === 'deep_research') return i;
    }
    return -1;
  };

  const idx = findTargetIndex();
  if (idx < 0) return;

  const current = messages.value[idx].content as DeepResearchContent;
  const workflowState = researchWorkflow.getDeepResearchState(current.research_id, current.status);
  messages.value[idx].content = {
    ...current,
    phase: workflowState.phase ?? undefined,
    phase_label: workflowState.phase_label ?? undefined,
    latest_reflection: workflowState.latest_reflection,
    checkpoints: workflowState.checkpoints,
  } as DeepResearchContent;
};

const handlePhaseTransitionEvent = (data: PhaseTransitionEventData) => {
  researchWorkflow.handlePhaseTransitionEvent(data);
  syncDeepResearchMessageMetadata(data.research_id);
};

const handleCheckpointSavedEvent = (data: CheckpointSavedEventData) => {
  researchWorkflow.handleCheckpointSavedEvent(data);
  syncDeepResearchMessageMetadata(data.research_id);
};

// Handle deep research run (approve)
const handleDeepResearchRun = async (_researchId: string) => {
  if (!sessionId.value) return;
  try {
    await agentApi.approveDeepResearch(sessionId.value);
  } catch {
    showErrorToast(t('Failed to start research'));
  }
};

// Handle deep research skip
const handleDeepResearchSkip = async (_researchId: string, queryId?: string) => {
  if (!sessionId.value) return;
  try {
    await agentApi.skipDeepResearchQuery(sessionId.value, queryId);
  } catch {
    showErrorToast(t('Failed to skip query'));
  }
};

// Handle toggle auto-run preference
const handleToggleAutoRun = () => {
  toggleAutoRun();
};

// Handle wide research SSE events
const handleWideResearchEvent = (data: WideResearchEventData) => {
  researchWorkflow.handleWideResearchEvent(data);
};

// Handle skill delivery events
const handleSkillDeliveryEvent = (data: SkillDeliveryEventData) => {
  showInfoToast(`Skill "${data.name}" package ready`);
  messages.value.push({
    id: generateMessageId(),
    type: 'skill_delivery',
    content: {
      package_id: data.package_id,
      name: data.name,
      description: data.description,
      version: data.version,
      icon: data.icon,
      category: data.category,
      author: data.author,
      file_tree: data.file_tree,
      files: data.files,
      file_id: data.file_id,
      skill_id: data.skill_id,
      timestamp: data.timestamp,
    } as SkillDeliveryContent,
  });
};

// Handle skill activation events
const handleSkillActivationEvent = (data: SkillActivationEventData) => {
  if (data.skill_names.length > 0) {
    showInfoToast(`Skills activated: ${data.skill_names.join(', ')}`);
  }
  // Lock activated skills for the session so they persist across messages
  if (data.skill_ids?.length > 0) {
    lockSkillsForSession(data.skill_ids);
  }
};

// Handle canvas update events
const handleCanvasUpdateEvent = (data: CanvasUpdateEventData) => {
  activeCanvasProjectId.value = data.project_id;
};

// Handle suggestion selection (user clicks a suggestion)
const handleSuggestionSelect = (suggestion: string) => {
  inputMessage.value = suggestion;
  pendingFollowUpSuggestion.value = suggestion; // Track that this came from a suggestion
  suggestions.value = []; // Clear suggestions after selection
  handleSubmit();
}

// Handle report open (from ChatMessage)
const handleReportOpen = (report: ReportData) => {
  openReport(report);
}

const closeFilePreview = () => {
  filePreviewOpen.value = false;
  filePreviewFile.value = null;
};

// Handle report file open
const handleReportFileOpen = (file: FileInfo) => {
  hideFilePanel();
  filePreviewFile.value = file;
  filePreviewOpen.value = true;
}

// Handle attached file click (open in modal)
const handleAttachmentFileClick = (file: FileInfo) => {
  hideFilePanel();
  filePreviewFile.value = file;
  filePreviewOpen.value = true;
}

// Handle report rate
const handleReportRate = async (rating: number, feedback?: string) => {
  if (!sessionId.value || !currentReport.value) return;
  try {
    await agentApi.submitRating(sessionId.value, currentReport.value.id, rating, feedback);
    showSuccessToast(t('Rating submitted'));
  } catch {
    showErrorToast(t('Failed to submit rating'));
  }
}

// Handle report download
const handleReportDownload = () => {
  if (!currentReport.value) return;

  const blob = new Blob([currentReport.value.content], { type: 'text/markdown' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${currentReport.value.title.replace(/[^a-zA-Z0-9]/g, '_')}.md`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

const shouldReplayHistoryEvent = (event: AgentSSEEvent): boolean => {
  // Stream token chunks are transient UI state. Replaying them from persisted
  // history creates heavy restore payloads and can interleave with live resume.
  return event.event !== 'stream';
};

// Process a single event (extracted from handleEvent for batching)
const processEvent = (event: AgentSSEEvent) => {
  // Deduplicate events based on event_id to prevent duplicate messages
  const eventId = event.data?.event_id;
  if (streamController.isDuplicateEvent(eventId)) {
    console.debug('Skipping duplicate event:', eventId);
    logChatSseDiagnostics('event:duplicate_skipped', {
      event: event.event,
      eventId,
    })
    return;
  }
  streamController.trackSeenEventId(eventId);
  logChatSseDiagnostics('event:process', {
    event: event.event,
    eventId: eventId ?? null,
  })

  // End initialization phase when first event arrives
  if (isInitializing.value) {
    isInitializing.value = false;
  }

  // Update last event time for stale connection detection
  updateEventTimeAndResetStale();

  // Transition to streaming on first real event
  if (
    responsePhase.value === 'connecting'
    || responsePhase.value === 'reconnecting'
    || responsePhase.value === 'degraded'
  ) {
    transitionTo('streaming')
  }

  if (event.event === 'message') {
    handleMessageEvent(event.data as MessageEventData);
    // Clear suggestions when new message arrives
    suggestions.value = [];
  } else if (event.event === 'tool') {
    handleToolEvent(event.data as ToolEventData);
  } else if (event.event === 'step') {
    handleStepEvent(event.data as StepEventData);
  } else if (event.event === 'phase') {
    handlePhaseEvent(event.data as import('../types/event').AgentPhaseEventData);
  } else if (event.event === 'done') {
    dismissConnectionBanner();
    logChatSseDiagnostics('event:done_received', {
      eventId: eventId ?? null,
      queuedAfterDone: streamController.getPendingEventCount(),
    })
    receivedDoneEvent.value = true;
    ensureCompletionSuggestions();
    markShortAssistantCompletion();
    isWaitingForReply.value = false;
    transitionTo('completing') // → auto-settles to 'settled' after 300ms
    // Notify sidebar that session is no longer running
    if (sessionId.value) {
      emitStatusChange(sessionId.value, SessionStatus.COMPLETED);
      cleanupSessionStorage(sessionId.value);
    }
    // Load screenshots for replay mode (seamless live → replay transition)
    sessionStatus.value = SessionStatus.COMPLETED;
    replay.loadScreenshots();
  } else if (event.event === 'wait') {
    // Agent is waiting for user input - show waiting indicator
    dismissConnectionBanner();
    isWaitingForReply.value = true;
    transitionTo('settled')
  } else if (event.event === 'error') {
    const errorData = event.data as ErrorEventData;
    const isRecoverableTimeout = errorData.error_type === 'timeout' && (errorData.recoverable ?? true);
    const isRecoverableStreamGap = errorData.error_code === 'stream_gap_detected';

    if (isRecoverableStreamGap) {
      logChatSseDiagnostics('event:stream_gap_warning_ignored', {
        requestedEventId: errorData.details?.requested_event_id ?? null,
        firstAvailableEventId: errorData.details?.first_available_event_id ?? null,
        checkpointEventId: errorData.checkpoint_event_id ?? null,
      })
      // Stream-gap warnings are transport-level resume diagnostics.
      // The client already handles checkpoint resumption via onGapDetected.
      // Avoid surfacing this as a user-facing error message.
      return;
    }

    if (isRecoverableTimeout) {
      // Backend may still be actively processing long-running work.
      // Treat timeout errors as recoverable transport interruptions so reconnect logic can resume.
      lastError.value = {
        message: errorData.error || 'Chat stream timed out',
        type: errorData.error_type ?? null,
        recoverable: true,
        hint: errorData.retry_hint ?? null,
      };
      transitionTo('timed_out')
    } else {
      transitionTo('error')
      handleErrorEvent(errorData);
    }
  } else if (event.event === 'title') {
    handleTitleEvent(event.data as TitleEventData);
  } else if (event.event === 'plan') {
    handlePlanEvent(event.data as PlanEventData);
  } else if (event.event === 'mode_change') {
    handleModeChangeEvent(event.data as ModeChangeEventData);
  } else if (event.event === 'suggestion') {
    handleSuggestionEvent(event.data as SuggestionEventData);
  } else if (event.event === 'report') {
    handleReportEvent(event.data as ReportEventData);
  } else if (event.event === 'stream') {
    handleStreamEvent(event.data as StreamEventData);
  } else if (event.event === 'progress') {
    handleProgressEvent(event.data as ProgressEventData);
  } else if (event.event === 'deep_research') {
    handleDeepResearchEvent(event.data as DeepResearchEventData);
  } else if (event.event === 'wide_research') {
    handleWideResearchEvent(event.data as WideResearchEventData);
  } else if (event.event === 'phase_transition') {
    handlePhaseTransitionEvent(event.data as PhaseTransitionEventData);
  } else if (event.event === 'checkpoint_saved') {
    handleCheckpointSavedEvent(event.data as CheckpointSavedEventData);
  } else if (event.event === 'skill_delivery') {
    handleSkillDeliveryEvent(event.data as SkillDeliveryEventData);
  } else if (event.event === 'skill_activation') {
    handleSkillActivationEvent(event.data as SkillActivationEventData);
  } else if (event.event === 'canvas_update') {
    handleCanvasUpdateEvent(event.data as CanvasUpdateEventData);
  }
  lastEventId.value = event.data.event_id;
  // Persist lastEventId to sessionStorage for proper event resumption on page refresh
  if (event.data.event_id && sessionId.value) {
    _persistEventId(sessionId.value);
  }
}

streamController.setEventProcessor(processEvent);

// Public event handler - queues events for batched processing
const handleEvent = (event: AgentSSEEvent) => {
  streamController.enqueueEvent(event);
};

const handleSubmit = () => {
  chat(inputMessage.value, attachments.value);
}

const markLastUserMessageAsAgentModeUpgrade = () => {
  for (let i = messages.value.length - 1; i >= 0; i -= 1) {
    if (messages.value[i].type === 'user') {
      (messages.value[i].content as MessageContent).agentModeUpgrade = true;
      return;
    }
  }
};

const handleUseAgentMode = () => {
  const originalPrompt = (agentGuidancePrompt.value || '').trim();
  if (!originalPrompt) return;

  bypassShortPathLockOnce.value = true;
  showAgentGuidanceCta.value = false;
  markLastUserMessageAsAgentModeUpgrade();

  const guidedPrompt = `Use full agent mode for this task. First create a clear plan, then execute it:\n\n${originalPrompt}`;
  chat(guidedPrompt, [], { skipOptimistic: true });
};

// Track last sent message to prevent duplicate submissions
let lastSentMessage = '';
let lastSentTime = 0;

const chat = async (
  message: string = '',
  files: FileInfo[] = [],
  options?: { skipOptimistic?: boolean }
) => {
  const streamAttemptId = beginStreamAttempt();
  if (!sessionId.value) return;
  const normalizedMessage = message.trim();

  // Prevent duplicate message submission within 2 seconds
  const now = Date.now();
  if (normalizedMessage && normalizedMessage === lastSentMessage && now - lastSentTime < 2000) {
    console.debug('Preventing duplicate message submission');
    return;
  }
  if (normalizedMessage) {
    lastSentMessage = normalizedMessage;
    lastSentTime = now;
    showAgentGuidanceCta.value = false;
    agentGuidancePrompt.value = undefined;
  }

  const bypassShortPathLock = bypassShortPathLockOnce.value;
  if (bypassShortPathLockOnce.value) {
    bypassShortPathLockOnce.value = false;
  }

  // Keep short path sticky: after short path is activated, complex prompts
  // require explicit user confirmation via "Use Agent Mode".
  if (
    !bypassShortPathLock &&
    normalizedMessage &&
    shortPathActivated.value &&
    isComplexTaskPrompt(normalizedMessage)
  ) {
    if (!options?.skipOptimistic) {
      addOptimisticUserMessage(normalizedMessage, files);
    }
    inputMessage.value = '';
    clearSelectedSkills();
    suggestions.value = [];
    isWaitingForReply.value = false;
    transitionTo('settled')
    showAgentGuidanceCta.value = true;
    agentGuidancePrompt.value = normalizedMessage;
    return;
  }

  // Build follow-up context if this message came from a suggestion click
  const followUp = pendingFollowUpSuggestion.value && followUpAnchorEventId.value
    ? {
        selected_suggestion: pendingFollowUpSuggestion.value,
        anchor_event_id: followUpAnchorEventId.value,
        source: 'suggestion_click' as const,
      }
    : null;

  // Clear pending follow-up state after building the context
  pendingFollowUpSuggestion.value = undefined;

  // Cancel any existing chat connection before starting a new one
  if (cancelCurrentChat.value) {
    cancelCurrentChat.value();
    cancelCurrentChat.value = null;
  }

  // Session reactivation: when sending a new message to a completed/failed
  // session, reset completion state so the UI shows the initializing spinner
  // instead of stale "completed" chrome.  Clear lastEventId so the backend
  // streams from the beginning of the new task rather than trying to resume
  // from the previous task's event cursor.
  if (isSessionComplete.value && normalizedMessage) {
    sessionStatus.value = SessionStatus.RUNNING;
    isInitializing.value = true;
    shortPathActivated.value = false;
    lastEventId.value = '';
    if (sessionId.value) {
      cleanupSessionStorage(sessionId.value);
      emitStatusChange(sessionId.value, SessionStatus.RUNNING);
    }
  }

  // Automatically enable follow mode when sending message
  follow.value = true;

  if (!options?.skipOptimistic && (normalizedMessage || files.length > 0)) {
    addOptimisticUserMessage(normalizedMessage, files);
  }

  // Clear input field and per-message skill picks (session skills persist)
  inputMessage.value = '';
  clearSelectedSkills();
  suggestions.value = [];
  receivedDoneEvent.value = false;
  lastHeartbeatAt.value = 0;
  isWaitingForReply.value = false;
  transitionTo('connecting')
  dismissConnectionBanner();

  // Set initialization state when starting a new chat
  // (when there are no messages or only 1 message which is the user's first message)
  if (normalizedMessage && !hasAgentStartedResponding.value) {
    isInitializing.value = true;
  }

  activeChatStreamTraceId = nextSseTraceId()
  logChatSseDiagnostics('chat:start', {
    messageLength: normalizedMessage.length,
    attachmentCount: files.length,
    hasFollowUp: Boolean(followUp),
  })
  // #region agent log
  fetch('http://127.0.0.1:7243/ingest/1df5c82e-6b29-49c4-bf13-84d843ab6ab0',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'ChatPage.vue:chat:sending',message:'chat() sending to backend',data:{sessionId:sessionId.value,messageLength:normalizedMessage.length,messagePreview:normalizedMessage.slice(0,80)||'(empty)',lastEventId:lastEventId.value||null,sessionStatus:sessionStatus.value,isSessionComplete:isSessionComplete.value},timestamp:Date.now(),hypothesisId:'E'})}).catch(()=>{});
  // #endregion

  try {
    const effectiveSkillIds = getEffectiveSkillIds();
    const shouldUseNativeEventSourceResume =
      isEventSourceResumeEnabled() &&
      normalizedMessage.length === 0 &&
      files.length === 0 &&
      !followUp &&
      effectiveSkillIds.length === 0;

    const transportCallbacks = createScopedTransportCallbacks('transport', streamAttemptId);

    // Use the split event handler function and store the cancel function
    if (shouldUseNativeEventSourceResume) {
      const cancelFn = await agentApi.resumeChatWithSessionEventSource(
        sessionId.value,
        lastEventId.value,
        transportCallbacks,
      );
      if (!isActiveStreamAttempt(streamAttemptId)) {
        cancelFn();
        return;
      }
      cancelCurrentChat.value = cancelFn;
    } else {
      const cancelFn = await agentApi.chatWithSession(
        sessionId.value,
        normalizedMessage,
        lastEventId.value,
        files.map((file: FileInfo) => ({
          file_id: file.file_id,
          filename: file.filename,
          content_type: file.content_type,
          size: file.size,
          upload_date: file.upload_date
        })),
        effectiveSkillIds, // session + per-message skills
        undefined, // options
        transportCallbacks,
        followUp
      );
      if (!isActiveStreamAttempt(streamAttemptId)) {
        cancelFn();
        return;
      }
      cancelCurrentChat.value = cancelFn;
    }
  } catch (error) {
    logChatSseDiagnostics('chat:start_failed', {
      message: error instanceof Error ? error.message : String(error),
    })
    transitionTo('error')
    cancelCurrentChat.value = null;
  }
}

const restoreSession = async () => {
  if (!sessionId.value) {
    showErrorToast(t('Session not found'));
    return;
  }

  // Load lastEventId from sessionStorage for proper event resumption
  const savedEventId = _getPersistedEventId(sessionId.value);
  if (savedEventId) {
    lastEventId.value = savedEventId;
    console.log('[RESTORE] Loaded lastEventId from sessionStorage:', savedEventId);
  }

  // #region agent log
  fetch('http://127.0.0.1:7243/ingest/1df5c82e-6b29-49c4-bf13-84d843ab6ab0',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'ChatPage.vue:restoreSession:start',message:'restoreSession called',data:{sessionId:sessionId.value,savedEventId:savedEventId||null},timestamp:Date.now(),hypothesisId:'E'})}).catch(()=>{});
  // #endregion

  const session = await agentApi.getSession(sessionId.value);
  sessionStatus.value = session.status as SessionStatus;
  console.log('[RESTORE] Session:', sessionId.value, 'Status:', sessionStatus.value, 'LastEventId:', lastEventId.value);

  // Initialize share mode based on session state
  shareMode.value = session.is_shared ? 'public' : 'private';
  realTime.value = false;

  // Drain any pending batched events before replaying persisted history.
  streamController.flushPendingEvents();

  for (const event of session.events) {
    if (!shouldReplayHistoryEvent(event)) continue;
    handleEvent(event);
  }

  // Flush replayed history immediately so auto-resume evaluates fully
  // hydrated state (prevents footer/order races after refresh).
  streamController.flushPendingEvents();

  realTime.value = true;
  if (sessionStatus.value === SessionStatus.INITIALIZING) {
    await waitForSessionIfInitializing();
  }
  if (sessionStatus.value === SessionStatus.RUNNING || sessionStatus.value === SessionStatus.PENDING) {
    transitionTo('connecting') // Will transition to 'streaming' on first event
    receivedDoneEvent.value = false;

    // #region agent log
    fetch('http://127.0.0.1:7243/ingest/1df5c82e-6b29-49c4-bf13-84d843ab6ab0',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'ChatPage.vue:restoreSession:auto_resume_path',message:'session is RUNNING/PENDING, will try auto-resume',data:{sessionId:sessionId.value,sessionStatus:sessionStatus.value,lastEventId:lastEventId.value||null,eventCount:session.events?.length||0},timestamp:Date.now(),hypothesisId:'E'})}).catch(()=>{});
    // #endregion

    // Defense-in-depth: if event replay already set status to COMPLETED (via DoneEvent
    // handler), the condition above will be false and we skip auto-resume. But if the
    // server returned "running" AND events didn't include a DoneEvent (edge case),
    // do a lightweight status re-check to avoid restarting a completed task.
    const freshStatus = await agentApi.getSessionStatus(sessionId.value);
    if (freshStatus && ['completed', 'failed'].includes(freshStatus.status)) {
      console.log('[RESTORE] Status re-check shows session is', freshStatus.status, '- not resuming');
      // #region agent log
      fetch('http://127.0.0.1:7243/ingest/1df5c82e-6b29-49c4-bf13-84d843ab6ab0',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'ChatPage.vue:restoreSession:status_recheck_completed',message:'STATUS RE-CHECK shows completed/failed, NOT resuming',data:{sessionId:sessionId.value,freshStatus:freshStatus.status},timestamp:Date.now(),hypothesisId:'E'})}).catch(()=>{});
      // #endregion
      sessionStatus.value = freshStatus.status === 'completed' ? SessionStatus.COMPLETED : SessionStatus.FAILED;
      replay.loadScreenshots();
      return;
    }

    // Check if this session was manually stopped (prevents auto-resume on page refresh)
    // Using sessionStorage: persists on refresh, cleared on tab close
    const stoppedKey = `pythinker-stopped-${sessionId.value}`;
    const wasManuallyStopped = sessionStorage.getItem(stoppedKey);

    if (wasManuallyStopped) {
      // Parse timestamp-based stop flag (new format: JSON with timestamp)
      // Old format ('true') is treated as stale
      let isStale = true;
      try {
        const parsed = JSON.parse(wasManuallyStopped);
        if (parsed?.timestamp) {
          const ageMs = Date.now() - parsed.timestamp;
          isStale = ageMs > 60_000; // >60s old = stale
        }
      } catch {
        // Old 'true' format or invalid JSON — treat as stale
      }

      if (isStale) {
        console.log('[RESTORE] Stop flag is stale (>60s or old format), removing and resuming');
        sessionStorage.removeItem(stoppedKey);
        // Fall through to auto-resume below
      } else {
        console.log('[RESTORE] Session was recently stopped, not auto-resuming');
        sessionStorage.removeItem(stoppedKey);
        return;
      }
    }

    // No stop flag - safe to auto-resume
    console.log('[RESTORE] No stop flag, auto-resuming session');
    // #region agent log
    fetch('http://127.0.0.1:7243/ingest/1df5c82e-6b29-49c4-bf13-84d843ab6ab0',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'ChatPage.vue:restoreSession:calling_chat',message:'calling chat() for auto-resume (no message)',data:{sessionId:sessionId.value,lastEventId:lastEventId.value||null},timestamp:Date.now(),hypothesisId:'E'})}).catch(()=>{});
    // #endregion
    await chat();
  } else if (sessionStatus.value === SessionStatus.COMPLETED || sessionStatus.value === SessionStatus.FAILED) {
    // Load screenshots for replay mode
    replay.loadScreenshots()
  }
  agentApi.clearUnreadMessageCount(sessionId.value);
}



onBeforeRouteUpdate(async (to, from, next) => {
  if (skipNextRouteReset.value) {
    skipNextRouteReset.value = false;
    if (to.params.sessionId) {
      sessionId.value = String(to.params.sessionId);
    }
    next();
    return;
  }

  // Only reset state when actually switching to a different session
  // This prevents cancelling the active chat on same-session route updates
  const prevSessionId = from.params.sessionId as string | undefined;
  const nextSessionId = to.params.sessionId as string | undefined;
  const isSwitchingSession = prevSessionId !== nextSessionId;

  // Stop the current session if it's still running AND we're switching sessions
  if (isSwitchingSession && prevSessionId && shouldStopSessionOnExit(sessionStatus.value)) {
    try {
      await agentApi.stopSession(prevSessionId);
      emitStatusChange(prevSessionId, SessionStatus.COMPLETED);
    } catch {
      // Non-critical — backend safety net will clean up
    }
  }

  // Only reset state and clear UI when actually switching sessions
  if (isSwitchingSession) {
    toolPanel.value?.clearContent();  // Clear tool panel content when switching sessions
    hideFilePanel();
    resetState();  // This cancels the chat - only do it when switching sessions
    if (nextSessionId) {
      messages.value = [];
      sessionId.value = nextSessionId;
      restoreSession();
    }
  }
  next();
})

// Initialize active conversation
// Handle insert message event from settings (e.g., "Build with Pythinker" button)
const handleInsertMessage = (event: Event) => {
  const detail = (event as CustomEvent<{ message: string; skillId?: string }>).detail;
  inputMessage.value = detail.message;
  // Auto-select the skill if provided
  if (detail.skillId) {
    selectSkill(detail.skillId);
  }
};

onMounted(async () => {
  hideFilePanel();
  // Listen for message insert event from settings dialog
  window.addEventListener('pythinker:insert-chat-message', handleInsertMessage);
  window.addEventListener('resize', updateChatBottomDockStyle);

  if (typeof ResizeObserver !== 'undefined' && chatContainerRef.value) {
    chatContainerResizeObserver = new ResizeObserver(() => {
      updateChatBottomDockStyle();
    });
    chatContainerResizeObserver.observe(chatContainerRef.value);
  }
  await nextTick();
  updateChatBottomDockStyle();

  if (await initializePendingSession()) {
    return;
  }

  const routeParams = router.currentRoute.value.params;
  if (routeParams.sessionId) {
    if (routeParams.sessionId === 'new') {
      await router.replace('/chat');
      return;
    }
    // If sessionId is included in URL, use it directly
    sessionId.value = String(routeParams.sessionId) as string;
    // Do not auto-send messages from history.state on existing sessions.
    // Pending initial prompts are handled exclusively via /chat/new bootstrap flow.
    if ((history.state as PendingSessionCreateState | null)?.pendingSessionCreate) {
      history.replaceState({}, document.title);
    }
    await restoreSession();
  }
});

// ======================================================================
// Tab visibility: sync session status when user returns to tab
// ======================================================================
const documentVisibility = useDocumentVisibility();

watch(documentVisibility, async (newVisibility) => {
  if (newVisibility !== 'visible' || !sessionId.value) return;

  // Only check if session was active when we left
  const activeStatuses = [SessionStatus.RUNNING, SessionStatus.INITIALIZING, SessionStatus.PENDING];
  if (!activeStatuses.includes(sessionStatus.value)) return;

  try {
    const status = await agentApi.getSessionStatus(sessionId.value);
    if (status.status !== sessionStatus.value) {
      console.log('[VISIBILITY] Session status changed while away:', sessionStatus.value, '->', status.status);
      sessionStatus.value = status.status as SessionStatus;

      // If session completed/failed while tab was hidden, load final state
      if (status.status === 'completed' || status.status === 'failed') {
        replay.loadScreenshots();
      }
    }
  } catch {
    // Session may have been deleted — clear state
    console.log('[VISIBILITY] Session status check failed, session may no longer exist');
  }
});

// Keep session runtime alive when navigating away from chat.
// Sandbox teardown is handled by explicit stop/delete/new-task flows.
onBeforeRouteLeave(async (_to, _from, next) => {
  next();
});

onUnmounted(() => {
  beginStreamAttempt();
  window.removeEventListener('pythinker:insert-chat-message', handleInsertMessage);
  window.removeEventListener('resize', updateChatBottomDockStyle);
  if (chatContainerResizeObserver) {
    chatContainerResizeObserver.disconnect();
    chatContainerResizeObserver = null;
  }
  if (cancelCurrentChat.value) {
    cancelCurrentChat.value();
    cancelCurrentChat.value = null;
  }
  // Cancel any pending event batch processing
  streamController.clearPendingEvents();
})

const isLastNoMessageTool = (tool: ToolContent) => {
  return tool.tool_call_id === lastNoMessageTool.value?.tool_call_id;
}

const isLiveTool = (tool: ToolContent) => {
  if (tool.status === 'calling') {
    return true;
  }
  if (!isLastNoMessageTool(tool)) {
    return false;
  }
  if (tool.timestamp > Date.now() - 5 * 60 * 1000) {
    return true;
  }
  return false;
}

const showToolFromTimeline = (index: number) => {
  if (toolTimeline.value.length === 0) return;
  const clampedIndex = Math.max(0, Math.min(index, toolTimeline.value.length - 1));
  const tool = toolTimeline.value[clampedIndex];
  if (!tool) return;
  realTime.value = false;
  panelToolId.value = tool.tool_call_id;
  toolPanel.value?.showToolPanel(tool, isLiveTool(tool));
}

const handleTimelineStepForward = () => {
  if (isScreenshotReplayMode.value) { replay.stepForward(); return; }
  if (!toolTimelineCanStepForward.value) return;
  showToolFromTimeline(toolTimelineIndex.value + 1);
}

const handleTimelineStepBackward = () => {
  if (isScreenshotReplayMode.value) { replay.stepBackward(); return; }
  if (!toolTimelineCanStepBackward.value) return;
  showToolFromTimeline(toolTimelineIndex.value - 1);
}

const handleTimelineSeek = (progress: number) => {
  if (isScreenshotReplayMode.value) { replay.seekByProgress(progress); return; }
  if (toolTimeline.value.length === 0) return;
  const maxIndex = toolTimeline.value.length - 1;
  const targetIndex = Math.round((progress / 100) * maxIndex);
  showToolFromTimeline(targetIndex);
}

const handleToolClick = (tool: ToolContent) => {
  realTime.value = false;
  if (sessionId.value) {
    toolPanel.value?.showToolPanel(tool, isLiveTool(tool));
    panelToolId.value = tool.tool_call_id;
  }
}

const jumpToRealTime = () => {
  realTime.value = true;
  if (lastNoMessageTool.value) {
    toolPanel.value?.showToolPanel(lastNoMessageTool.value, isLiveTool(lastNoMessageTool.value));
    panelToolId.value = lastNoMessageTool.value.tool_call_id;
  }
}

const handleFollow = () => {
  follow.value = true;
  simpleBarRef.value?.scrollToBottom('smooth');
}

const handleFollowChange = (isFollowing: boolean) => {
  follow.value = isFollowing;
}

// Scroll follow state is managed by v-auto-follow-scroll directive via handleFollowChange.
// No manual scroll handler needed.

const handleStop = async () => {
  beginStreamAttempt();
  stopFallbackStatusPolling();
  // Cancel the SSE stream FIRST to prevent any reconnect/resume logic
  if (cancelCurrentChat.value) {
    cancelCurrentChat.value();
    cancelCurrentChat.value = null;
  }
  if (sessionId.value) {
    // Clear lastEventId from sessionStorage since session is stopped (use centralized cleanup)
    cleanupSessionStorage(sessionId.value);
    // Mark this session as manually stopped to prevent auto-resume on page refresh
    // Set AFTER cleanup so the flag isn't immediately removed
    sessionStorage.setItem(`pythinker-stopped-${sessionId.value}`, JSON.stringify({ timestamp: Date.now() }));
    // Await the stop request so backend teardown completes before the user
    // can trigger a new message (prevents stop/chat race condition).
    try {
      await agentApi.stopSession(sessionId.value);
    } catch {
      // Non-critical — backend safety net will clean up
    }
    // Notify sidebar that session is no longer running
    emitStatusChange(sessionId.value, SessionStatus.COMPLETED);
  }
  // Reset to stopped state
  transitionTo('stopped')
  isStale.value = false;
  isWaitingForReply.value = false;
  cleanupStreamingState();
  // NO ensureCompletionSuggestions() — user intentionally stopped
  sessionStatus.value = SessionStatus.COMPLETED;
}

const handleRetryConnection = async () => {
  const streamAttemptId = beginStreamAttempt();
  if (!sessionId.value) return;
  stopFallbackStatusPolling();
  if (cancelCurrentChat.value) {
    cancelCurrentChat.value();
    cancelCurrentChat.value = null;
  }
  receivedDoneEvent.value = false;
  lastHeartbeatAt.value = 0;

  // Status reconciliation: if session already completed/failed, skip SSE and settle
  try {
    const statusResp = await agentApi.getSessionStatus(sessionId.value);
    const status = statusResp.status as SessionStatus;
    if (status === SessionStatus.COMPLETED || status === SessionStatus.FAILED) {
      sessionStatus.value = status;
      emitStatusChange(sessionId.value, status);
      transitionTo('completing');
      await replay.loadScreenshots();
      return;
    }
  } catch {
    // Network error — fall through to SSE reconnect (which has its own retry logic)
  }

  transitionTo('connecting')
  activeChatStreamTraceId = nextSseTraceId()
  logChatSseDiagnostics('chat:retry_start', {
    resumeFromEventId: lastEventId.value || null,
  })
  try {
    const transportRetryCallbacks = createScopedTransportCallbacks('transport_retry', streamAttemptId);

    if (isEventSourceResumeEnabled()) {
      const cancelFn = await agentApi.resumeChatWithSessionEventSource(
        sessionId.value,
        lastEventId.value,
        transportRetryCallbacks,
      );
      if (!isActiveStreamAttempt(streamAttemptId)) {
        cancelFn();
        return;
      }
      cancelCurrentChat.value = cancelFn;
    } else {
      const cancelFn = await agentApi.chatWithSession(
        sessionId.value,
        '', // empty message — just reconnect
        lastEventId.value,
        [],
        [],
        undefined,
        transportRetryCallbacks,
      );
      if (!isActiveStreamAttempt(streamAttemptId)) {
        cancelFn();
        return;
      }
      cancelCurrentChat.value = cancelFn;
    }
  } catch (error) {
    logChatSseDiagnostics('chat:retry_failed', {
      message: error instanceof Error ? error.message : String(error),
    })
    transitionTo('error')
  }
}

streamController.setupReconnectCoordinator({
  autoRetryCount,
  isFallbackStatusPolling,
  onRetryConnection: handleRetryConnection,
  pollFallbackStatus: pollSessionStatusFallback,
  maxAutoRetries: 4,
  autoRetryDelaysMs: AUTO_RETRY_DELAYS_MS,
  fallbackPollIntervalMs: FALLBACK_STATUS_POLL_INTERVAL_MS,
  fallbackPollMaxAttempts: FALLBACK_STATUS_POLL_MAX_ATTEMPTS,
})

const handleFileListShow = () => {
  showSessionFileList()
}

// Share functionality handlers
const handleShareModeChange = async (mode: 'private' | 'public') => {
  if (!sessionId.value || sharingLoading.value) return;
  
  // If mode is same as current, no need to call API
  if (shareMode.value === mode) {
    linkCopied.value = false;
    return;
  }
  
  try {
    sharingLoading.value = true;
    
    if (mode === 'public') {
      await agentApi.shareSession(sessionId.value);
    } else {
      await agentApi.unshareSession(sessionId.value);
    }
    
    shareMode.value = mode;
    linkCopied.value = false;
  } catch {
    showErrorToast(t('Failed to change sharing settings'));
  } finally {
    sharingLoading.value = false;
  }
}

const handleInstantShare = async () => {
  if (!sessionId.value) return;
  
  try {
    sharingLoading.value = true;
    await agentApi.shareSession(sessionId.value);
    shareMode.value = 'public';
    linkCopied.value = false;
  } catch {
    showErrorToast(t('Failed to share session'));
  } finally {
    sharingLoading.value = false;
  }
}

const handleCopyLink = async () => {
  if (!sessionId.value) return;
  
  const shareUrl = `${window.location.origin}/share/${sessionId.value}`;
  
  try {
    const success = await copyToClipboard(shareUrl);
    
    if (success) {
      linkCopied.value = true;
      setTimeout(() => {
        linkCopied.value = false;
      }, 3000);
      showSuccessToast(t('Link copied to clipboard'));
    } else {
      showErrorToast(t('Failed to copy link'));
    }
  } catch {
    showErrorToast(t('Failed to copy link'));
  }
}
</script>

<style scoped>
/* ===== CHAT HEADER ===== */
.chat-header {
  background-color: var(--background-gray-main);
}

.chat-model-pill {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  min-width: 0;
  height: 32px;
  border-radius: 8px;
  padding: 0 8px;
  transition: background-color 0.15s ease;
}

.chat-model-pill:hover {
  background: var(--fill-tsp-white-main);
}

.chat-title-text {
  color: var(--text-primary);
  font-size: 16px;
  line-height: 20px;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  letter-spacing: -0.01em;
}

.chat-title-chevron {
  color: var(--text-tertiary);
  transform: rotate(90deg);
  flex-shrink: 0;
}

.chat-bottom-dock {
  padding-top: 8px;
  z-index: 20;
}

.chat-content-with-pinned-dock {
  padding-bottom: calc(8px + env(safe-area-inset-bottom));
}

.chat-messages-with-pinned-dock {
  padding-bottom: calc(196px + env(safe-area-inset-bottom));
}

.chat-messages-with-thumbnail-dock {
  padding-bottom: calc(296px + env(safe-area-inset-bottom));
}

.chat-bottom-dock-fixed {
  position: fixed;
  bottom: 0;
  z-index: 40;
  max-width: calc(100vw - 40px);
  padding-bottom: calc(12px + env(safe-area-inset-bottom));
}

:deep(.dark) .chat-bottom-dock,
.dark .chat-bottom-dock,
:deep(.dark) .chat-bottom-dock-fixed,
.dark .chat-bottom-dock-fixed {
  background: transparent;
}

@media (max-width: 640px) {
  .chat-messages-with-pinned-dock {
    padding-bottom: calc(212px + env(safe-area-inset-bottom));
  }

  .chat-messages-with-thumbnail-dock {
    padding-bottom: calc(312px + env(safe-area-inset-bottom));
  }
}

/* 120-degree diagonal shimmer text effect */
.thinking-text-shimmer {
  background: linear-gradient(
    120deg,
    #1f2937 0%,
    #1f2937 40%,
    #9ca3af 50%,
    #1f2937 60%,
    #1f2937 100%
  );
  background-size: 300% 300%;
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
  animation: text-shimmer 2s ease-in-out infinite;
}

/* Dark mode */
:deep(.dark) .thinking-text-shimmer,
.dark .thinking-text-shimmer {
  background: linear-gradient(
    120deg,
    #e5e7eb 0%,
    #e5e7eb 40%,
    #6b7280 50%,
    #e5e7eb 60%,
    #e5e7eb 100%
  );
  background-size: 300% 300%;
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
}

@keyframes text-shimmer {
  0% {
    background-position: 100% 0%;
  }
  100% {
    background-position: 0% 100%;
  }
}

/* ===== PLANNING PROGRESS SHIMMER ===== */
.planning-progress-indicator {
  transition: all 0.3s ease;
  background: linear-gradient(180deg, #ffffff 0%, #fafafa 100%);
  border: 1px solid rgba(15, 23, 42, 0.08);
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.08);
}

.planning-thinking :deep(.thinking-lamp) {
  width: 20px;
  height: 24px;
}

.planning-percent {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 44px;
  height: 24px;
  border-radius: 999px;
  padding: 0 8px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.04em;
  color: var(--text-secondary);
  background: var(--fill-tsp-gray-main);
  border: 1px solid var(--border-light);
}

.planning-text-shimmer {
  background: linear-gradient(
    120deg,
    #6b7280 0%,
    #6b7280 35%,
    #d1d5db 50%,
    #6b7280 65%,
    #6b7280 100%
  );
  background-size: 300% 300%;
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
  animation: planning-shimmer 2.5s ease-in-out infinite;
}

/* Dark mode - planning shimmer (silver) */
:deep(.dark) .planning-text-shimmer,
.dark .planning-text-shimmer {
  background: linear-gradient(
    120deg,
    #9ca3af 0%,
    #9ca3af 35%,
    #f3f4f6 50%,
    #9ca3af 65%,
    #9ca3af 100%
  );
  background-size: 300% 300%;
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
}

:deep(.dark) .planning-progress-indicator,
.dark .planning-progress-indicator {
  background: linear-gradient(180deg, #1f2937 0%, #111827 100%);
  border: 1px solid rgba(148, 163, 184, 0.2);
  box-shadow: 0 12px 28px rgba(0, 0, 0, 0.35);
}

@keyframes planning-shimmer {
  0% {
    background-position: 100% 50%;
  }
  50% {
    background-position: 0% 50%;
  }
  100% {
    background-position: 100% 50%;
  }
}

/* ===== STALE NOTICE (reassuring, not alarming) ===== */
.stale-notice {
  background: rgba(59, 130, 246, 0.06);
  border-color: rgba(59, 130, 246, 0.2);
  color: #1d4ed8;
}

.stale-pulse {
  background: #000000;
  animation: stale-pulse 2s ease-in-out infinite;
}

.stale-stop-btn {
  background: rgba(59, 130, 246, 0.12);
  color: #0a0a0a;
}

.stale-stop-btn:hover {
  background: rgba(59, 130, 246, 0.2);
}

:deep(.dark) .stale-notice,
.dark .stale-notice {
  background: rgba(96, 165, 250, 0.08);
  border-color: rgba(96, 165, 250, 0.25);
  color: #e5e5e5;
}

:deep(.dark) .stale-pulse,
.dark .stale-pulse {
  background: #ffffff;
}

:deep(.dark) .stale-stop-btn,
.dark .stale-stop-btn {
  background: rgba(96, 165, 250, 0.15);
  color: #e5e5e5;
}

:deep(.dark) .stale-stop-btn:hover,
.dark .stale-stop-btn:hover {
  background: rgba(96, 165, 250, 0.25);
}

@keyframes stale-pulse {
  0%, 100% {
    opacity: 1;
    transform: scale(1);
  }
  50% {
    opacity: 0.6;
    transform: scale(0.9);
  }
}

</style>
