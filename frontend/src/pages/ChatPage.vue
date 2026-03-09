<template>
  <SimpleBar
    ref="simpleBarRef"
    :autoFollow="follow"
    :autoFollowThreshold="24"
    @follow-change="handleFollowChange"
  >
    <div ref="chatSplitRef" class="chat-split-shell">
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
      <div ref="_observerRef"
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
          <div class="flex items-center gap-2 flex-1 min-w-0 pr-2">
            <button class="chat-model-pill min-w-0 shrink flex items-center gap-1" type="button" aria-label="Current chat title">
              <span class="chat-title-text truncate">
                {{ title }}
              </span>
            </button>
            <span
              v-if="sessionSource === 'telegram'"
              class="chat-source-badge"
              data-testid="chat-source-telegram"
              title="Telegram session"
              aria-label="Telegram session"
            >
              <Send :size="10" />
              <span>Telegram</span>
            </span>
            <ResearchModeBadge :mode="sessionResearchMode" :compact="isToolPanelOpen" />
          </div>
	          <!-- Right: Buttons -->
	          <div class="flex items-center gap-1 flex-shrink-0">
              <div class="chat-view-toggle" role="tablist" aria-label="Chat display mode">
                <button
                  type="button"
                  class="chat-view-toggle-btn sm:px-[10px] px-[8px]"
                  :class="{ 'chat-view-toggle-btn-active': chatViewMode === 'chat' }"
                  role="tab"
                  :aria-selected="chatViewMode === 'chat'"
                  @click="handleChatViewModeChange('chat')"
                >
                  <MessageSquareText :size="14" />
                  <span class="hidden sm:inline">Chat</span>
                </button>
                <button
                  type="button"
                  class="chat-view-toggle-btn sm:px-[10px] px-[8px]"
                  :class="{ 'chat-view-toggle-btn-active': chatViewMode === 'reasoning' }"
                  role="tab"
                  :aria-selected="chatViewMode === 'reasoning'"
                  @click="handleChatViewModeChange('reasoning')"
                >
                  <GitBranch :size="14" />
                  <span class="hidden sm:inline">Reasoning</span>
                </button>
              </div>
	              <span class="relative flex-shrink-0">
	                <Popover>
	                  <PopoverTrigger as-child>
                    <button
                      class="h-7 rounded-[8px] inline-flex items-center justify-center clickable border border-[var(--border-main)] hover:border-[var(--border-dark)] hover:bg-[var(--fill-tsp-white-main)] transition-all"
                      :class="[isToolPanelOpen ? 'w-7 px-0 gap-0' : 'w-7 px-0 gap-0 sm:w-auto sm:min-w-[56px] sm:px-2 sm:gap-1.5']"
                      aria-haspopup="dialog"
                    >
                      <ShareIcon color="var(--icon-secondary)" />
                      <span
                        class="text-[var(--text-secondary)] text-[13px] font-medium leading-[18px]"
                        :class="[isToolPanelOpen ? 'hidden' : 'hidden sm:inline']"
                      >
                        {{ t('Share') }}
                      </span>
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
                            :class="shareMode === 'private' ? 'bg-[var(--Button-primary-black)] text-[var(--text-onblack)]' : 'bg-[var(--fill-tsp-gray-main)] text-[var(--icon-primary)]'"
                            class="w-[32px] h-[32px] rounded-[8px] flex items-center justify-center">
                            <Lock :size="16" stroke="currentColor" :stroke-width="2" /></div>
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
                            :class="shareMode === 'public' ? 'bg-[var(--Button-primary-black)] text-[var(--text-onblack)]' : 'bg-[var(--fill-tsp-gray-main)] text-[var(--icon-primary)]'"
                            class="w-[32px] h-[32px] rounded-[8px] flex items-center justify-center">
                            <Globe :size="16" stroke="currentColor" :stroke-width="2" /></div>
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
              <button
                @click="handleFileListShow"
                class="h-7 w-7 rounded-[8px] inline-flex items-center justify-center clickable border border-[var(--border-main)] hover:border-[var(--border-dark)] hover:bg-[var(--fill-tsp-white-main)] transition-all"
                :title="t('All files in this task')"
                aria-label="All files in this task"
              >
                <FileSearch class="text-[var(--icon-secondary)]" :size="15" />
              </button>
              <!-- Context panel button removed — ContextPanel component not yet implemented -->

          </div>
        </div>
        <!-- Right side - spacer -->
        <div class="flex-1"></div>
      </div>
      <!-- Phase progress strip - shown above messages during active agent runs -->
      <div
        v-if="showPhaseStrip"
        class="mx-auto w-full max-w-full px-5 sm:max-w-[768px] sm:min-w-[400px]"
      >
        <PhaseStrip
          :current-phase="phaseStripPhase!"
          :start-time="phaseStripStartTime"
          :step-progress="phaseStripStepProgress"
          @cancel="handleCancel"
        />
      </div>
	      <div
          v-if="chatViewMode === 'chat'"
	        class="mx-auto w-full max-w-full px-5 sm:max-w-[768px] sm:min-w-[400px] flex flex-col flex-1"
          :style="chatContentStyle"
	      >
        <div
          class="flex flex-col w-full pt-[24px] flex-1"
          :style="chatMessagesStyle"
        >
          <ChatMessage v-for="(message, index) in messages" :key="message.id" :message="message"
            :activeThinkingStepId="isChatMode ? undefined : activeThinkingStepId"
            :showStepLeadingConnector="!isChatMode && shouldShowStepLeadingConnector(index)"
            :showStepConnector="!isChatMode && shouldShowStepConnector(index)"
            :showAssistantHeader="shouldShowAssistantHeader(index)"
            :renderAsSummaryCard="shouldRenderSummaryCard(index)"
            :showAssistantCompletionFooter="assistantCompletionFooterIds.has(message.id) && !canShowSuggestions"
            :sources="sourcesForMessageMap.get(index)"
            :isFastSearchSession="sessionResearchMode === 'fast_search'"
            :activeReasoningState="!isChatMode && !showTaskProgressBar && !showPlanningCard && message.id === activeAssistantMessageId ? activeReasoningState : undefined"
            :thinkingText="message.id === activeAssistantMessageId ? thinkingText : undefined"
            :liveActivity="!isChatMode && !showTaskProgressBar && !showPlanningCard && message.id === activeAssistantMessageId ? liveActivity : undefined"
            @toolClick="handleToolClick"
            @reportOpen="handleReportOpen"
            @reportFileOpen="handleReportFileOpen"
            @showAllFiles="handleFileListShow"
            @reportRate="handleReportRate"
            @selectSuggestion="handleSuggestionSelect" />
          <SessionWarmupMessage
            v-if="showSessionWarmupMessage"
            :state="warmupState"
            @retry="handleRetryInitialize"
          />

          <!-- Loading/Thinking indicators - fallback for discuss mode (no active step) -->
          <div v-if="showFloatingThinkingIndicator" class="flex items-center gap-2 pl-1 mt-4">
            <ThinkingIndicator :showText="true" />
          </div>
          <LoadingIndicator v-else-if="!showSessionWarmupMessage && isLoading && !activeThinkingStepId && !hasRunningStep" :text="$t('Loading')" :pulse="isReceivingHeartbeats" />

          <!-- Waiting for user reply indicator -->
          <WaitingForReply v-if="isWaitingForReply" />
          <div
            v-if="isWaitingForReply && showTakeoverCta"
            class="mt-2 mb-1 rounded-xl border border-blue-200 bg-blue-50 px-3 py-2.5 dark:border-blue-900/40 dark:bg-blue-950/20"
          >
            <div class="flex items-start justify-between gap-3">
              <p class="text-sm text-blue-800 dark:text-blue-300">
                {{ takeoverCtaMessage }}
              </p>
              <button
                type="button"
                class="shrink-0 rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-semibold text-white transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60"
                :disabled="takeoverStarting"
                @click="handleStartTakeoverFromCta"
              >
                {{ takeoverStarting ? 'Starting...' : 'Take over browser' }}
              </button>
            </div>
          </div>

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

          <!-- Connection interrupted - SSE closed without completion (amber) -->
          <!-- Also shows when timeoutReason is null (transport-level timeouts from useSessionStreamController) -->
          <div
            v-if="responsePhase === 'timed_out' && (!timeoutReason || timeoutReason === 'connection')"
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

          <!-- Workflow timeout - agent idle or wall-clock limit (blue, with Continue) -->
          <div
            v-if="responsePhase === 'timed_out' && (timeoutReason === 'workflow_idle' || timeoutReason === 'workflow_limit')"
            class="timeout-notice flex items-center gap-3 px-4 py-3 mx-4 mt-[1cm] mb-2 rounded-xl border border-blue-200 dark:border-blue-800/40 bg-blue-50 dark:bg-blue-950/20 transition-all duration-300"
            role="status"
          >
            <div class="w-2.5 h-2.5 rounded-full bg-blue-400 dark:bg-blue-500 flex-shrink-0 animate-pulse" aria-hidden="true"></div>
            <div class="flex-1 min-w-0">
              <span class="text-sm font-medium text-blue-800 dark:text-blue-300">{{ lastError?.message }}</span>
              <span v-if="lastError?.hint" class="block mt-1 text-xs text-blue-600 dark:text-blue-400">{{ lastError.hint }}</span>
            </div>
            <button
              @click="handleContinueAfterTimeout"
              class="flex-shrink-0 px-3 py-1.5 text-xs font-medium rounded-lg bg-blue-100 dark:bg-blue-900/30 text-blue-800 dark:text-blue-300 hover:bg-blue-200 dark:hover:bg-blue-900/50 transition-colors"
            >
              {{ $t('Continue') }}
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

          <!-- Failed session banner — shown when session was loaded/restored as FAILED
               but no structured lastError was captured. Gives user immediate visibility
               that this task did not complete successfully (Issue #10). -->
          <div
            v-if="sessionStatus === 'failed' && !lastError && !isLoading"
            class="flex items-center gap-3 px-4 py-3 mx-4 mb-2 rounded-xl border border-red-200 dark:border-red-800/40 bg-red-50 dark:bg-red-950/20 transition-all duration-300"
            role="alert"
          >
            <div class="w-2.5 h-2.5 rounded-full bg-red-400 dark:bg-red-500 flex-shrink-0" aria-hidden="true"></div>
            <div class="flex-1 min-w-0">
              <span class="text-sm font-medium text-red-800 dark:text-red-300">{{ $t('This task encountered an error and did not complete successfully.') }}</span>
              <span class="block mt-1 text-xs text-red-600 dark:text-red-400">{{ $t('You can start a new task or review the steps above for details.') }}</span>
            </div>
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
          ref="_chatBottomDockRef"
          class="chat-bottom-dock flex flex-col sticky bottom-0 mt-auto"
          :class="{ 'chat-bottom-dock-fixed': shouldPinComposerToBottom }"
          :style="chatBottomDockStyle"
        >
          <!-- Planning Progress Card - shows instant feedback before plan is ready -->
          <!-- Hide when timed_out to avoid flicker during auto-retry reconnect cycles -->
          <Transition name="planning-card">
            <PlanningCard
              v-if="showPlanningCard && activePlanningCardState"
              class="mb-2"
              :title="activePlanningCardState.title"
              :phase="activePlanningCardState.phase"
              :message="activePlanningCardState.message"
              :progressPercent="activePlanningCardState.progressPercent"
              :complexityCategory="activePlanningCardState.complexityCategory"
            />
          </Transition>

          <!-- Partial Results - provisional findings accumulated during execution -->
          <PartialResults :results="partialResults" />

          <!-- Scroll to bottom button - positioned above progress bar with measured spacing -->
          <div v-if="!follow" class="flex justify-end mb-2">
            <button
              @click="handleFollow"
              class="flex items-center justify-center w-[36px] h-[36px] rounded-full bg-[var(--background-menu-white)] hover:bg-[var(--background-gray-main)] clickable border border-[var(--border-main)] shadow-[0px_5px_16px_0px_var(--shadow-S),0px_0px_1.25px_0px_var(--shadow-S)]"
            >
              <ArrowDown class="text-[var(--icon-primary)]" :size="20" />
            </button>
          </div>

          <!-- Task Progress Bar Container - shown above ChatBox when ToolPanel is closed -->
          <div v-if="showTaskProgressBar" class="relative mb-2">

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
              :finalReportText="finalReportText"
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
      <div
        v-else
        class="mx-auto w-full max-w-full px-5 sm:max-w-[1280px] flex flex-col flex-1 min-h-0 pb-3"
      >
        <ReasoningTreeView
          ref="reasoningTreeRef"
          class="flex-1 min-h-0"
          :messages="messages"
          :activeReasoningState="activeReasoningState"
          :thinkingText="thinkingText"
        />
      </div>
	      <!-- Wide Research UI removed — behavior absorbed into Deep Research mode -->
	      </div>

      <div v-if="isToolPanelOpen && !isMobileViewport" class="relative h-full w-[8px] flex-shrink-0">
        <div
          class="absolute top-0 bottom-0 start-[-6px] w-[20px] z-[70] py-[12px] chat-live-splitter"
          :class="{ dragging: isSplitDragging, hovering: isSplitHovering, focused: isSplitFocused }"
          :style="splitterTrackStyle"
          tabindex="0"
          role="separator"
          aria-label="Resize chat and live view panels"
          aria-orientation="vertical"
          :aria-valuenow="toolPanelSize"
          :aria-valuemin="SPLIT_MIN_PANEL_WIDTH_PX"
          :aria-valuemax="Math.round(getPanelMaxWidth())"
          @pointerenter="isSplitHovering = true"
          @pointerleave="isSplitHovering = false"
          @pointermove="isSplitHovering = true"
          @focus="isSplitFocused = true"
          @blur="isSplitFocused = false"
          @pointerdown.prevent="handleSplitterPointerDown"
          @wheel.prevent="handleSplitterWheel"
          @keydown="handleSplitterKeydown"
          @dblclick="resetToolPanelWidth"
        >
          <div
            class="w-[4px] h-full mx-auto rounded-full chat-live-splitter-handle"
            :style="splitterHandleStyle"
          ></div>
        </div>
      </div>

      <ToolPanel ref="toolPanel" :size="toolPanelSize" :sessionId="sessionId" :realTime="realTime"
        :isShare="false"
        :plan="plan"
        :isLoading="isLoading"
        :isThinking="isThinking"
        :summaryStreamText="summaryStreamText"
        :finalReportText="finalReportText"
        :isSummaryStreaming="isSummaryStreaming"
        @jumpToRealTime="jumpToRealTime"
        :showTimeline="showTimelineControls"
        :timelineProgress="toolTimelineProgress"
        :timelineTimestamp="toolTimelineTimestamp"
        :timelineCanStepForward="toolTimelineCanStepForward"
        :timelineCanStepBackward="toolTimelineCanStepBackward"
        :toolTimeline="toolTimeline"
        :timelineCurrentStep="toolTimelineCurrentStep"
        :timelineTotalSteps="toolTimeline.length"
        :isReplayMode="isReplayMode"
        :replayScreenshotUrl="replay.currentScreenshotUrl.value"
        :replayMetadata="replay.currentScreenshot.value"
        :replayScreenshots="replay.screenshots.value"
        :activeCanvasUpdate="activeCanvasUpdate"
        @timelineStepForward="handleTimelineStepForward"
        @timelineStepBackward="handleTimelineStepBackward"
        @timelineSeek="handleTimelineSeek"
        @panelStateChange="handlePanelStateChange" />
    </div>
  </SimpleBar>

  <!-- Connectors Dialog -->
  <ConnectorsDialog />

  <!-- Report Modal -->
  <ReportModal
    v-model:open="isReportModalOpen"
    :report="currentReport"
    :sessionId="sessionId"
    :showToc="true"
    @close="closeReport"
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

  <!-- Side Panels — ContextPanel + CheckoutDialog not yet implemented, refs removed to silence warnings -->
</template>

<script setup lang="ts">
import SimpleBar from '../components/SimpleBar.vue';
import type { ReasoningStage, LiveActivity } from '@/components/ReasoningPipeline.vue';
import { ref, computed, onMounted, watch, nextTick, onUnmounted, reactive, toRefs, shallowRef, triggerRef } from 'vue';
import { useRouter, onBeforeRouteUpdate, onBeforeRouteLeave } from 'vue-router';
import { useDocumentVisibility } from '@vueuse/core';
import { useI18n } from 'vue-i18n';
import ChatBox from '../components/ChatBox.vue';
import ChatMessage from '../components/ChatMessage.vue';
import ReasoningTreeView from '@/components/reasoning/ReasoningTreeView.vue';
import * as agentApi from '../api/agent';
import type { ThinkingMode } from '../api/agent';
import type { SSECallbacks, SSEGapInfo } from '../api/client';
import { Message, MessageContent, ToolContent, StepContent, AttachmentsContent, ReportContent, SkillDeliveryContent, ThoughtContent } from '../types/message';
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
  PlanningPhase,
  PhaseTransitionEventData,
  CheckpointSavedEventData,
  SkillDeliveryEventData,
  SkillActivationEventData,
  CanvasUpdateEventData,
  ToolStreamEventData,
  WorkspaceEventData,
  ThoughtEventData,
  WaitEventData,
  PartialResultEventData,
} from '../types/event';
import Suggestions from '../components/Suggestions.vue';
import ToolPanel from '../components/ToolPanel.vue'
import { ArrowDown, FileSearch, Lock, Globe, Link, Check, Menu, MessageSquareText, GitBranch, Send } from 'lucide-vue-next';
import ShareIcon from '@/components/icons/ShareIcon.vue';
import { showErrorToast, showSuccessToast, showInfoToast } from '../utils/toast';
import { downloadFile } from '../api/file';
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
import { collapseDuplicateReportBlocks, preparePlainTextForViewer } from '@/components/report/reportContentNormalizer';
import { useReport, extractSectionsFromMarkdown } from '@/composables/useReport';
import { Dialog, DialogContent } from '@/components/ui/dialog';
import ThinkingIndicator from '@/components/ui/ThinkingIndicator.vue';
import PlanningCard from '@/components/PlanningCard.vue';
import PartialResults from '@/components/PartialResults.vue';
import PhaseStrip from '@/components/PhaseStrip.vue';
import WaitingForReply from '@/components/WaitingForReply.vue';
// WideResearchOverlay removed — absorbed into Deep Research mode
import ConnectionStatusBanner from '@/components/ConnectionStatusBanner.vue';
import ResearchModeBadge from '@/components/ResearchModeBadge.vue';
import { useSessionStatus } from '@/composables/useSessionStatus';
import { getToolDisplay } from '@/utils/toolDisplay';
import { useSkills } from '@/composables/useSkills';
import { useResearchWorkflow } from '@/composables/useResearchWorkflow';
import ConnectorsDialog from '@/components/connectors/ConnectorsDialog.vue';
import { useConnectorDialog } from '@/composables/useConnectorDialog';
import { useScreenshotReplay } from '@/composables/useScreenshotReplay';
import { useErrorBoundary } from '@/composables/useErrorBoundary';
import { shouldStopSessionOnExit } from '@/utils/sessionLifecycle';
import { toEpochSeconds } from '@/utils/time';
import {
  buildPlanningCardState,
  createPlanningPreviewBatcher,
  normalizePlanningPhase,
  shouldDismissPlanningHandoff,
  shouldShowPlanningCard,
} from '@/utils/planningCard';
import { resolveChatDockLayout } from '@/utils/chatDockLayout';
import {
  getRestoreAbortReason,
  isTerminalSessionStatus,
  shouldReplayHistoryEvent,
} from '@/utils/chatRestoreGuards';
import { normalizeTransientTools } from '@/utils/sessionFinalization';
import { shouldPreserveDealToolInLiveView } from '@/utils/dealLiveViewSelection';
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
import { useToolStore } from '@/stores/toolStore';
import { useConnectionStore } from '@/stores/connectionStore';
import { useUIStore } from '@/stores/uiStore';
import { createEventHandlerRegistry, dispatchEvent } from '@/composables/useEventHandlerRegistry';
import { useMcpStatus } from '@/composables/useMcpStatus';

// ── Pinia stores (dual-write: stores mirror local state during migration) ──
const toolStore = useToolStore()
const connectionStore = useConnectionStore()
const uiStore = useUIStore()

const router = useRouter()
const { t } = useI18n()
const { toggleLeftPanel } = useLeftPanel()
const { showSessionFileList } = useSessionFileList()
const { hideFilePanel } = useFilePanel()
const { isReportModalOpen, currentReport, openReport, closeReport } = useReport()
const { emitStatusChange } = useSessionStatus()
const { getEffectiveSkillIds, clearSelectedSkills, lockSkillsForSession, clearSessionSkills, selectSkill } = useSkills()
const researchWorkflow = useResearchWorkflow()
// ConnectorDialog composable — dialog manages its own visibility
useConnectorDialog()

// Error boundary — catches unhandled errors from child components to prevent page crashes
const { lastCapturedError: _lastCapturedError, clearError: _clearError } = useErrorBoundary()

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
let staleReconnectTimer: ReturnType<typeof setTimeout> | null = null
let linkCopiedTimer: ReturnType<typeof setTimeout> | null = null
let planningHandoffTimer: ReturnType<typeof setTimeout> | null = null
const PLANNING_HANDOFF_MS = 650

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
    staleReconnectTimer = setTimeout(() => {
      staleReconnectTimer = null
      chat('', [], { skipOptimistic: true })
    }, 1000)
  }
}

const {
  connectionState: _connectionState,
  lastEventTime: _lastEventTime,
  lastEventId,
  updateLastRealEventTime,
  isConnectionStale: _isConnectionStale,
  persistEventId: _persistEventId,
  getPersistedEventId: _getPersistedEventId,
  cleanupSessionStorage,
  startStaleDetection,
  stopStaleDetection,
} = useSSEConnection({
  staleThresholdMs: 120000, // 120s (4× heartbeat) — only stale when NO events at all
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
  finalReportText: '', // Persisted final report markdown for live-view completion state
  allowStandaloneSummaryOnNextAssistant: false, // One-shot flag: render only the final summary assistant block outside step timeline
  isStale: false, // True when agent appears unresponsive (no events for 60s)
  filePreviewOpen: false,
  filePreviewFile: null as FileInfo | null,
  toolTimeline: [] as ToolContent[],
  panelToolId: undefined as string | undefined,
  isInitializing: false, // True when starting up the sandbox environment
  planningProgress: null as { phase: 'received' | 'analyzing' | 'planning' | 'verifying' | 'executing_setup' | 'finalizing' | 'waiting'; message: string; percent: number; estimatedDurationSeconds?: number; complexityCategory?: 'simple' | 'medium' | 'complex' } | null, // Planning progress
  isWaitingForReply: false, // True when agent is waiting for user input
  showTakeoverCta: false, // Show one-click takeover CTA for captcha/login waits
  takeoverCtaReason: undefined as string | undefined,
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
  agentModeOriginalPrompt: null as string | null, // Tracks original prompt for agent-mode echo suppression
  timeoutReason: null as 'connection' | 'workflow_idle' | 'workflow_limit' | null, // Discriminates timeout source
  activeReasoningState: 'idle' as ReasoningStage, // Reasoning pipeline state for active assistant message
  phaseStripStartTime: 0 as number, // Timestamp when current agent run started (for PhaseStrip elapsed timer)
  partialResults: [] as { stepIndex: number; stepTitle: string; headline: string; sourcesCount: number }[], // Provisional findings during execution
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
  finalReportText,
  allowStandaloneSummaryOnNextAssistant,
  isStale,
  filePreviewOpen,
  filePreviewFile,
  toolTimeline,
  panelToolId,
  isInitializing,
  planningProgress,
  isWaitingForReply,
  showTakeoverCta,
  takeoverCtaReason,
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
  agentModeOriginalPrompt,
  timeoutReason,
  activeReasoningState,
  phaseStripStartTime,
  partialResults,
} = toRefs(state);

const chatViewMode = ref<'chat' | 'reasoning'>('chat');
const reasoningTreeRef = ref<InstanceType<typeof ReasoningTreeView> | null>(null);
const plannerThinkingPreview = ref('');
const planningPreviewBatcher = createPlanningPreviewBatcher((nextText) => {
  plannerThinkingPreview.value = nextText;
});
type ActivePlanningCardState = {
  title?: string
  phase: PlanningPhase
  message: string
  progressPercent?: number
  complexityCategory?: 'simple' | 'medium' | 'complex'
}
const planningHandoffState = ref<ActivePlanningCardState | null>(null);

const clearPlanningHandoff = (): void => {
  if (planningHandoffTimer) {
    clearTimeout(planningHandoffTimer);
    planningHandoffTimer = null;
  }
  planningHandoffState.value = null;
};

const startPlanningHandoff = (
  complexityCategory?: 'simple' | 'medium' | 'complex',
): void => {
  clearPlanningHandoff();
  planningHandoffState.value = {
    title: 'Plan ready',
    phase: 'executing_setup',
    message: 'Starting execution from the approved plan.',
    progressPercent: 100,
    complexityCategory,
  };
  planningHandoffTimer = setTimeout(() => {
    planningHandoffTimer = null;
    planningHandoffState.value = null;
  }, PLANNING_HANDOFF_MS);
};

// Track latest running step description for NeuralFlow
const lastStepDescription = ref<string | undefined>(undefined)

// Build live activity object for NeuralFlow from the latest tool + planning state
const liveActivity = computed<LiveActivity>(() => ({
  toolName: lastTool.value?.name,
  toolStatus: lastTool.value?.status,
  toolArgs: lastTool.value?.args,
  stepDescription: lastStepDescription.value,
  progressMessage: planningProgress.value?.message,
}))

const takeoverStarting = ref(false);
const TAKEOVER_WAIT_REASONS = new Set(['captcha', 'login', '2fa', 'payment', 'verification']);

const clearTakeoverCta = () => {
  showTakeoverCta.value = false;
  takeoverCtaReason.value = undefined;
};

const setTakeoverCtaFromMetadata = (waitReason?: string, takeoverSuggestion?: string) => {
  const normalizedReason = (waitReason || '').trim().toLowerCase();
  const normalizedSuggestion = (takeoverSuggestion || '').trim().toLowerCase();
  const shouldShow = normalizedSuggestion === 'browser' || TAKEOVER_WAIT_REASONS.has(normalizedReason);

  showTakeoverCta.value = shouldShow;
  takeoverCtaReason.value = shouldShow && normalizedReason ? normalizedReason : undefined;
};

const takeoverCtaMessage = computed(() => {
  switch ((takeoverCtaReason.value || '').toLowerCase()) {
    case 'captcha':
      return 'Captcha detected. Take over the browser to continue.';
    case 'login':
      return 'Login required. Take over the browser to continue.';
    case '2fa':
      return '2FA verification required. Take over the browser to continue.';
    case 'payment':
      return 'Payment verification required. Take over the browser to continue.';
    case 'verification':
      return 'Manual verification required. Take over the browser to continue.';
    default:
      return 'The agent is waiting for your browser input. Take over to continue.';
  }
});

const handleStartTakeoverFromCta = async () => {
  if (!sessionId.value || takeoverStarting.value) return;
  takeoverStarting.value = true;
  try {
    const reason = takeoverCtaReason.value || 'manual';
    const status = await agentApi.startTakeover(sessionId.value, reason);
    if (status.takeover_state !== 'takeover_active') {
      showErrorToast('Unable to start browser takeover. Please try again.');
      return;
    }
    clearTakeoverCta();
    window.dispatchEvent(
      new CustomEvent('takeover', {
        detail: { sessionId: sessionId.value, active: true },
      }),
    );
  } catch {
    showErrorToast('Unable to start browser takeover. Please try again.');
  } finally {
    takeoverStarting.value = false;
  }
};

const canOpenLiveViewPanel = computed(() => chatViewMode.value !== 'reasoning');

const showToolPanelIfAllowed = (tool: ToolContent, isLive: boolean) => {
  if (!canOpenLiveViewPanel.value) return false;
  toolPanel.value?.showToolPanel(tool, isLive);
  // Dual-write: mirror panel state to Pinia stores
  uiStore.setRightPanel(true)
  return true;
};

const handleChatViewModeChange = (mode: 'chat' | 'reasoning') => {
  chatViewMode.value = mode;
  if (mode === 'reasoning') {
    // Disable auto-follow BEFORE the DOM swap so the MutationObserver-triggered
    // auto-scroll (requestAnimationFrame) doesn't race against scrollToTop.
    follow.value = false;
    toolPanel.value?.hideToolPanel(false);
    panelToolId.value = undefined;
    nextTick(() => {
      simpleBarRef.value?.scrollToTop();
      reasoningTreeRef.value?.scrollToTop();
    });
  }
};

// Buffer for tool_stream events that arrive before tool(calling)
// Keyed by tool_call_id → { content, functionName, contentType }
const streamingContentBuffer = new Map<string, { content: string; functionName: string; contentType: string }>();

// Eagerly-extracted search sources keyed by tool_call_id.
// Populated in handleToolEvent when a search tool completes (status='called'),
// eliminating the need for lazy extraction during render (which has reactivity edge cases
// with cross-message Object.assign mutations through deeply nested reactive proxies).
// Uses shallowRef + triggerRef so individual .set() calls trigger a single notification
// rather than deep-tracking every consumer (avoids N+1 re-renders during streaming).
const searchSourcesCache = shallowRef(new Map<string, import('../types/message').SourceCitation[]>());

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
      // Post-stream reconciliation: when stream closes without a done event,
      // poll the backend to detect if the session actually completed.
      // This handles network drops, backend restarts, and other edge cases
      // where the done event is lost before reaching the frontend.
      if (!receivedDoneEvent.value && !isSessionComplete.value && sessionId.value) {
        reconcileSessionStatus();
      }
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
    // Stop scanning at the latest user boundary.
    // Assistant/system noise after a report should not re-enable global footer.
    if (messageType === 'user') {
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
    [SessionStatus.COMPLETED, SessionStatus.FAILED, SessionStatus.CANCELLED].includes(sessionStatus.value)
})

// Replay mode: session is completed/failed and has replay data
const isReplayMode = computed(() => {
  const ended = !isLoading.value && isSessionComplete.value
  return !!ended && hasScreenshotReplay.value
})

// Message ID counter for generating unique keys (avoids crypto overhead)
let messageIdCounter = 0;
const generateMessageId = () => `msg_${Date.now()}_${++messageIdCounter}`;

// Non-state refs that don't need reset
const toolPanel = ref<InstanceType<typeof ToolPanel>>()
const simpleBarRef = ref<InstanceType<typeof SimpleBar>>();
const _observerRef = ref<HTMLDivElement>();
const chatSplitRef = ref<HTMLDivElement>();
const chatContainerRef = ref<HTMLDivElement>();
const _chatBottomDockRef = ref<HTMLDivElement>();
const chatBottomDockHeight = ref(0);
const chatBottomDockStyle = ref<Record<string, string>>({});
let chatContainerResizeObserver: ResizeObserver | null = null;
let chatBottomDockResizeObserver: ResizeObserver | null = null;
const MOBILE_VIEWPORT_BREAKPOINT = 640;
const isTouchLikeViewport = () =>
  window.innerWidth < MOBILE_VIEWPORT_BREAKPOINT
  && window.matchMedia('(hover: none), (pointer: coarse)').matches;
const isMobileViewport = ref(isTouchLikeViewport());
const isSplitDragging = ref(false);
const isSplitHovering = ref(false);
const isSplitFocused = ref(false);
let splitPointerMoveHandler: ((event: PointerEvent) => void) | null = null;
let splitPointerUpHandler: ((event: PointerEvent) => void) | null = null;

const SPLIT_MIN_PANEL_WIDTH_PX = 340;
const SPLIT_MIN_CHAT_WIDTH_PX = 420;
const SPLIT_WHEEL_STEP_PX = 24;
const splitIsActive = computed(() => isSplitHovering.value || isSplitDragging.value || isSplitFocused.value);

const splitterTrackStyle = computed<Record<string, string>>(() => ({
  cursor: 'ew-resize',
  borderRadius: '9999px',
  backgroundColor: splitIsActive.value ? 'rgba(59, 130, 246, 0.12)' : 'transparent',
  transition: 'background-color 0.12s ease',
}));

const splitterHandleStyle = computed<Record<string, string>>(() => ({
  backgroundColor: splitIsActive.value
    ? 'var(--status-running, #3b82f6)'
    : 'var(--border-dark, rgba(17, 24, 39, 0.22))',
  opacity: splitIsActive.value ? '1' : '0.9',
  transform: splitIsActive.value ? 'scaleX(1.65)' : 'scaleX(1)',
  boxShadow: splitIsActive.value
    ? '0 0 0 1px rgba(59, 130, 246, 0.45), 0 0 10px rgba(59, 130, 246, 0.28)'
    : 'none',
  transition: 'background-color 0.12s ease, opacity 0.12s ease, transform 0.12s ease, box-shadow 0.12s ease',
}));

// Track session status
const sessionStatus = ref<SessionStatus | undefined>(undefined);
const isSandboxInitializing = computed(() => sessionStatus.value === SessionStatus.INITIALIZING);
const isCancelling = ref(false);
const isWaitingForSessionReady = ref(false);
const pendingInitialMessage = ref<{ message: string; files: FileInfo[]; thinkingMode: ThinkingMode } | null>(null);
const currentThinkingMode = ref<ThinkingMode>('auto');
const sessionInitTimedOut = ref(false);
const isChatModeOverride = ref<boolean | null>(null);
const isChatMode = computed(() => {
  // Manual override from Chat Mode button
  if (isChatModeOverride.value !== null) return isChatModeOverride.value;
  // Auto-detect: if first user message is a simple greeting, treat as chat mode
  const firstUserMsg = messages.value.find(m => m.type === 'user');
  if (!firstUserMsg) return false;
  const text = ((firstUserMsg as any).message || '').trim().toLowerCase();
  const greetings = ['hello', 'hi', 'hey', 'howdy', 'hola', 'greetings', 'yo', 'sup', 'good morning', 'good afternoon', 'good evening'];
  return greetings.includes(text);
});
// Route guard: skip reset when navigating to a session we just created.
// Stores the target session ID instead of a boolean flag to avoid race conditions
// where the flag could be consumed by a different navigation event.
const skipResetForSessionId = ref<string | null>(null);

interface PendingSessionCreateState {
  pendingSessionCreate: boolean;
  mode?: 'agent' | 'discuss';
  research_mode?: agentApi.ResearchMode;
  chat_mode?: boolean;
  message?: string;
  skills?: string[];
  files?: FileInfo[];
  thinking_mode?: ThinkingMode;
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

const chatDockLayout = computed(() =>
  resolveChatDockLayout({
    isPinned: shouldPinComposerToBottom.value,
    dockHeight: chatBottomDockHeight.value,
  }),
);

const chatContentStyle = computed<Record<string, string>>(() => ({
  paddingBottom: `calc(${chatDockLayout.value.contentPaddingBottomPx}px + env(safe-area-inset-bottom))`,
}));

const chatMessagesStyle = computed<Record<string, string>>(() => ({
  paddingBottom: `calc(${chatDockLayout.value.messagesPaddingBottomPx}px + env(safe-area-inset-bottom))`,
}));

const measureChatBottomDock = () => {
  const chatBottomDock = _chatBottomDockRef.value;
  chatBottomDockHeight.value = chatBottomDock
    ? Math.max(Math.ceil(chatBottomDock.getBoundingClientRect().height), 0)
    : 0;
};

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

const updateChatBottomDockMetrics = () => {
  measureChatBottomDock();
  updateChatBottomDockStyle();
};

const getSplitContainerWidth = () => {
  return chatSplitRef.value?.clientWidth || window.innerWidth;
};

const getPanelMaxWidth = () => {
  const containerWidth = getSplitContainerWidth();
  return Math.max(SPLIT_MIN_PANEL_WIDTH_PX, containerWidth - SPLIT_MIN_CHAT_WIDTH_PX);
};

const clampPanelWidth = (width: number) => {
  const maxWidth = getPanelMaxWidth();
  return Math.min(Math.max(width, SPLIT_MIN_PANEL_WIDTH_PX), maxWidth);
};

const getCurrentPanelWidth = () => {
  const containerWidth = getSplitContainerWidth();
  const defaultWidth = containerWidth / 2;
  const requested = toolPanelSize.value > 0 ? toolPanelSize.value : defaultWidth;
  return clampPanelWidth(requested);
};

const setPanelWidth = (width: number) => {
  if (isMobileViewport.value) return;
  toolPanelSize.value = Math.round(clampPanelWidth(width));
};

const adjustPanelWidth = (delta: number) => {
  setPanelWidth(getCurrentPanelWidth() + delta);
};

const stopSplitterDrag = () => {
  if (splitPointerMoveHandler) {
    window.removeEventListener('pointermove', splitPointerMoveHandler);
    splitPointerMoveHandler = null;
  }
  if (splitPointerUpHandler) {
    window.removeEventListener('pointerup', splitPointerUpHandler);
    window.removeEventListener('pointercancel', splitPointerUpHandler);
    splitPointerUpHandler = null;
  }
  isSplitDragging.value = false;
  isSplitHovering.value = false;
  document.body.style.cursor = '';
  document.body.style.userSelect = '';
};

const handleSplitterPointerDown = (event: PointerEvent) => {
  if (isMobileViewport.value || !isToolPanelOpen.value) return;

  const startX = event.clientX;
  const startWidth = getCurrentPanelWidth();

  isSplitDragging.value = true;
  document.body.style.cursor = 'ew-resize';
  document.body.style.userSelect = 'none';

  splitPointerMoveHandler = (moveEvent: PointerEvent) => {
    const deltaX = moveEvent.clientX - startX;
    setPanelWidth(startWidth - deltaX);
  };

  splitPointerUpHandler = () => {
    stopSplitterDrag();
  };

  window.addEventListener('pointermove', splitPointerMoveHandler);
  window.addEventListener('pointerup', splitPointerUpHandler);
  window.addEventListener('pointercancel', splitPointerUpHandler);
};

const handleSplitterWheel = (event: WheelEvent) => {
  if (isMobileViewport.value || !isToolPanelOpen.value) return;
  const direction = event.deltaY < 0 ? 1 : -1;
  adjustPanelWidth(direction * SPLIT_WHEEL_STEP_PX);
};

const handleSplitterKeydown = (event: KeyboardEvent) => {
  if (isMobileViewport.value || !isToolPanelOpen.value) return;

  const KEYBOARD_STEP_PX = 40; // Larger step for keyboard (feels more responsive)

  switch (event.key) {
    case 'ArrowLeft':
      event.preventDefault();
      adjustPanelWidth(KEYBOARD_STEP_PX); // Expand panel (decrease chat width)
      break;
    case 'ArrowRight':
      event.preventDefault();
      adjustPanelWidth(-KEYBOARD_STEP_PX); // Shrink panel (increase chat width)
      break;
    case 'Home':
      event.preventDefault();
      setPanelWidth(getPanelMaxWidth());
      break;
    case 'End':
      event.preventDefault();
      setPanelWidth(SPLIT_MIN_PANEL_WIDTH_PX);
      break;
    case 'Enter':
    case ' ':
      event.preventDefault();
      resetToolPanelWidth();
      break;
  }
};

const resetToolPanelWidth = () => {
  toolPanelSize.value = 0;
};

const handleViewportResize = () => {
  isMobileViewport.value = isTouchLikeViewport();
  updateChatBottomDockMetrics();

  if (isMobileViewport.value) {
    stopSplitterDrag();
    return;
  }

  if (isToolPanelOpen.value && toolPanelSize.value > 0) {
    toolPanelSize.value = Math.round(clampPanelWidth(toolPanelSize.value));
  }
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

// Track the latest canvas update event so same-project updates still propagate.
const activeCanvasUpdate = ref<CanvasUpdateEventData | null>(null);

// Track the session's research mode (set from SSE event or session creation)
const sessionResearchMode = ref<agentApi.ResearchMode | null>(null);
const sessionSource = ref<string>('web');

const refreshSessionStatus = async (targetSessionId?: string) => {
  const activeSessionId = targetSessionId ?? sessionId.value;
  if (!activeSessionId) {
    sessionStatus.value = undefined;
    return;
  }

  try {
    const statusResp = await agentApi.getSessionStatus(activeSessionId);
    sessionStatus.value = statusResp.status as SessionStatus;
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
    chat(pending.message, pending.files, { skipOptimistic: true, thinkingMode: pending.thinkingMode });
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
  const pendingThinkingMode: ThinkingMode = pendingState.thinking_mode || 'auto';
  const mode = pendingState.mode === 'discuss' ? 'discuss' : 'agent';
  const researchMode = pendingState.research_mode || 'deep_research';

  // Track chat mode to suppress planning UI — persist to sessionStorage
  if (pendingState.chat_mode) {
    isChatModeOverride.value = true;
  }

  // Show immediate chat view feedback while backend session is being created.
  if (pendingMessage || pendingFiles.length > 0) {
    addOptimisticUserMessage(pendingMessage, pendingFiles);
    isInitializing.value = true;
    transitionTo('connecting')
  }

  try {
    const idempotencyKey = crypto.randomUUID();
    const session = await agentApi.createSession(mode, { research_mode: researchMode, sandbox_wait_seconds: 0, idempotencyKey });
    sessionResearchMode.value = researchMode;
    sessionSource.value = 'web';
    sessionId.value = session.session_id;
    if (pendingMessage) {
      emitSessionTitleHint({
        sessionId: session.session_id,
        title: pendingMessage,
        status: session.status,
      });
    }

    skipResetForSessionId.value = session.session_id;
    await router.replace({ path: `/chat/${session.session_id}` });

    // Persist chat mode flag AFTER session ID is known
    if (isChatMode.value) {
      try { sessionStorage.setItem(`chatMode:${session.session_id}`, '1'); } catch { /* storage unavailable */ }
    }

    if (pendingMessage || pendingFiles.length > 0) {
      // Apply selected skills right before sending the first message.
      for (const skillId of pendingSkills) {
        selectSkill(skillId);
      }
      pendingInitialMessage.value = { message: pendingMessage, files: pendingFiles, thinkingMode: pendingThinkingMode };
      await refreshSessionStatus(session.session_id);
      await waitForSessionIfInitializing();
      maybeSendPendingInitialMessage();
    } else {
      await refreshSessionStatus(session.session_id);
      await restoreSession(session.session_id, 'session_create');
    }
  } catch {
    transitionTo('error')
    isInitializing.value = false;
    pendingInitialMessage.value = null;
    // Remove the optimistic user message that was added before createSession
    if (pendingMessage || pendingFiles.length > 0) {
      messages.value = [];
    }
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

// Watch sessionId changes to update status (skip initial mount — restoreSession handles it)
watch(sessionId, async (newSessionId, oldSessionId) => {
  if (!oldSessionId) return;
  // Clear session-level skills when switching sessions
  clearSessionSkills();

  await refreshSessionStatus(newSessionId);
  await waitForSessionIfInitializing();
});

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
  planningPreviewBatcher.reset('');
  clearPlanningHandoff();
  isThinkingStreaming.value = false;
  summaryStreamText.value = '';
  isSummaryStreaming.value = false;
  allowStandaloneSummaryOnNextAssistant.value = false;
  isInitializing.value = false;
  planningProgress.value = null;
  lastStepDescription.value = undefined;
  if (cancelCurrentChat.value) {
    cancelCurrentChat.value = null;
  }
  activeChatStreamTraceId = null;
};

/**
 * Post-stream reconciliation: poll backend status after SSE closes without a done event.
 * Handles network drops, backend restarts, and other edge cases where the done event
 * is lost before reaching the frontend.
 */
const reconcileSessionStatus = async () => {
  const sid = sessionId.value;
  if (!sid) return;

  // Brief delay to let any in-flight events flush
  await new Promise((r) => setTimeout(r, 800));

  // Re-check guards after await — session may have settled in the meantime
  if (receivedDoneEvent.value || isSessionComplete.value) return;
  if (sessionId.value !== sid) return; // navigated away

  logChatSseDiagnostics('reconcile:start');

  try {
    const statusResp = await agentApi.getSessionStatus(sid);
    const status = statusResp.status as SessionStatus;

    if (sessionId.value !== sid) return; // guard again after async

    if (
      status === SessionStatus.COMPLETED ||
      status === SessionStatus.FAILED ||
      status === SessionStatus.CANCELLED
    ) {
      logChatSseDiagnostics('reconcile:settled', { status });
      finalizeSession('reconcile', status);
    } else {
      logChatSseDiagnostics('reconcile:still_running', { status });
    }
  } catch (err) {
    logChatSseDiagnostics('reconcile:error', { error: String(err) });
    // Non-critical — don't propagate. User can always refresh.
  }
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
  invalidateRestoreEpoch('reset_state');
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

  // Clear streaming content buffer and search sources cache
  streamingContentBuffer.clear();
  searchSourcesCache.value = new Map();

  // Reset session research mode
  sessionResearchMode.value = null;
  sessionSource.value = 'web';
  isChatModeOverride.value = null;

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
    updateChatBottomDockMetrics();
  },
  { immediate: true }
);

watch(filePreviewOpen, (isOpen) => {
  if (!isOpen) {
    filePreviewFile.value = null;
  }
});

// ===== Agent Connection Health Monitoring =====
// Stale detection consolidated in connectionStore (single source of truth).
// Local refs kept as thin aliases for backward-compatible reads.
const updateEventTimeAndResetStale = () => {
  updateLastRealEventTime()
  isStale.value = false
  connectionStore.updateLastRealEventTime()
}

// Track if ToolPanel is open (needed for live preview thumbnail management)
const isToolPanelOpen = ref(false);
// Tracks whether user manually closed the panel during the current agent run.
// Prevents auto-reopening until the next user message is sent.
const userDismissedPanel = ref(false);

// Handler for TaskProgressBar's requestRefresh event (no-op with live preview)
const handleThumbnailRefresh = () => {
  // With live preview, no refresh is needed - it's always up to date
};

// Delegate stale detection lifecycle to connectionStore
watch(isLoading, (loading) => {
  if (loading) {
    connectionStore.startStaleDetection()
  } else {
    connectionStore.stopStaleDetection()
    isStale.value = false
  }
});

// Sync store stale state back to local ref (backward compat until full migration)
watch(() => connectionStore.isStale, (stale) => {
  isStale.value = stale
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
    if (isTerminalSessionStatus(status)) {
      if (status === SessionStatus.FAILED && !lastError.value) {
        lastError.value = {
          message: 'Task failed while reconnecting.',
          type: 'session_failed',
          recoverable: true,
          hint: 'Retry the connection to inspect details.',
        };
      }
      finalizeSession('reconcile', status);
      if (status === SessionStatus.FAILED) {
        transitionTo('error');
      }
      return 'stop';
    }
  } catch {
    // Keep polling on transient errors; controller handles scheduling/attempt caps.
  }

  return 'continue';
};

// Cleanup on unmount
// Note: stale check interval + heartbeat bridge are now managed by connectionStore.
// connectionStore.stopStaleDetection() is triggered reactively via the isLoading watcher above.
onUnmounted(() => {
  if (staleReconnectTimer) {
    clearTimeout(staleReconnectTimer);
    staleReconnectTimer = null;
  }
  clearPlanningHandoff();
  planningPreviewBatcher.dispose();
  connectionStore.stopStaleDetection();
  stopFallbackStatusPolling();
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

// Resolve citation sources for assistant messages.
// Strategy 1: forward-scan for the nearest report message (research mode — has structured sources).
// Strategy 2: lookup eagerly-cached search sources from searchSourcesCache (populated in handleToolEvent).
// Strategy 3 (fallback): backward-scan tool messages for search results in case cache was missed.
// All scans stay within the same conversational turn (bounded by user messages).
const SEARCH_TOOL_FUNCTIONS = new Set(['info_search_web', 'web_search', 'search', 'wide_research']);

const extractSearchSourcesFromTool = (tool: ToolContent): import('../types/message').SourceCitation[] => {
  const fn = (tool.function || tool.name || '').toLowerCase();
  if (!SEARCH_TOOL_FUNCTIONS.has(fn)) return [];
  const payload = tool.content as Record<string, unknown> | undefined;
  const results = (payload?.results ?? payload?.data) as Array<{ title?: string; link?: string; url?: string; snippet?: string }> | undefined;
  if (!Array.isArray(results)) return [];
  return results
    .filter((r) => !!(r.link || r.url))
    .map((r) => ({
      url: (r.link || r.url)!,
      title: r.title || '',
      snippet: r.snippet,
      access_time: '',
      source_type: 'search' as const,
    }));
};

// Memoized Map of messageIndex → SourceCitation[] for assistant messages.
// Recomputed only when messages or searchSourcesCache change (not per-message per-tick).
const sourcesForMessageMap = computed(() => {
  const map = new Map<number, import('../types/message').SourceCitation[]>();
  const cache = searchSourcesCache.value;
  const msgs = messages.value;

  for (let idx = 0; idx < msgs.length; idx++) {
    const current = msgs[idx];
    if (!current || current.type !== 'assistant') continue;

    // Strategy 1: forward-scan for a report message with structured sources
    let found: import('../types/message').SourceCitation[] | undefined;
    for (let i = idx + 1; i < msgs.length; i++) {
      const m = msgs[i];
      if (m.type === 'user') break;
      if (m.type === 'report') {
        const sources = (m.content as ReportContent).sources;
        if (sources?.length) { found = sources; break; }
      }
    }
    if (found) { map.set(idx, found); continue; }

    // Strategy 2: use eagerly-cached search sources (populated when tool events arrived).
    // Strategy 3 (fallback): extract from tool content directly (covers cache miss / reconnection).
    const collected: import('../types/message').SourceCitation[] = [];
    for (let i = idx - 1; i >= 0; i--) {
      const m = msgs[i];
      if (m.type === 'user') break;

      if (m.type === 'tool') {
        const tool = m.content as ToolContent;
        const cached = cache.get(tool.tool_call_id);
        collected.push(...(cached ?? extractSearchSourcesFromTool(tool)));
      }

      if (m.type === 'step') {
        const step = m.content as StepContent;
        for (const tool of (step.tools ?? [])) {
          const cached = cache.get(tool.tool_call_id);
          collected.push(...(cached ?? extractSearchSourcesFromTool(tool)));
        }
      }
    }
    if (collected.length) map.set(idx, collected);
  }
  return map;
});

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
const hasVisibleExecutionStep = computed(() => {
  for (let i = messages.value.length - 1; i >= 0; i -= 1) {
    const message = messages.value[i];
    if (message.type === 'user') break;
    if (message.type !== 'step') continue;
    const step = message.content as StepContent;
    if (step.status === 'running' || step.status === 'started') {
      return true;
    }
  }
  return false;
});
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

// Compute the ID of the last assistant message
const activeAssistantMessageId = computed(() => {
  for (let i = messages.value.length - 1; i >= 0; i--) {
    if (messages.value[i].type === 'assistant') {
      return messages.value[i].id;
    }
  }
  return null;
});

const isTaskCompleted = computed(() =>
  receivedDoneEvent.value || sessionStatus.value === SessionStatus.COMPLETED
);

const showTaskProgressBar = computed(() =>
  !isChatMode.value &&
  !showSessionWarmupMessage.value &&
  !isToolPanelOpen.value &&
  (!!plan.value?.steps?.length || !!lastNoMessageTool.value || isInitializing.value || isSandboxInitializing.value)
);

const planningCardState = computed(() => buildPlanningCardState({
  planningProgress: planningProgress.value
    ? {
        phase: planningProgress.value.phase,
        message: planningProgress.value.message,
        percent: planningProgress.value.percent,
        complexityCategory: planningProgress.value.complexityCategory,
      }
    : null,
  isThinkingStreaming: isThinkingStreaming.value,
  thinkingText: plannerThinkingPreview.value,
}));

const activePlanningCardState = computed<ActivePlanningCardState | null>(() =>
  planningHandoffState.value ?? planningCardState.value
);

const showPlanningCard = computed(() =>
  !hasVisibleExecutionStep.value &&
  shouldShowPlanningCard({
    isChatMode: isChatMode.value,
    showSessionWarmupMessage: showSessionWarmupMessage.value,
    isToolPanelOpen: isToolPanelOpen.value,
    isTaskCompleted: isTaskCompleted.value,
    responsePhase: responsePhase.value === 'timed_out' ? 'timed_out' : 'streaming',
    sessionResearchMode: sessionResearchMode.value,
    hasActivePlanningCard: !!activePlanningCardState.value,
    hasPlanningHandoff: !!planningHandoffState.value,
    planStepCount: plan.value?.steps?.length ?? 0,
  })
);

// ── PhaseStrip computed state ─────────────────────────────────────────────
type PhaseStripPhase = 'planning' | 'verifying' | 'searching' | 'writing' | 'done'

const phaseStripPhase = computed<PhaseStripPhase | null>(() => {
  // After task is completed, show 'done' briefly (template hides strip shortly after)
  if (isTaskCompleted.value) return 'done'

  const progress = planningProgress.value
  if (progress) {
    const phaseMap: Record<string, PhaseStripPhase> = {
      received: 'planning',
      analyzing: 'planning',
      planning: 'planning',
      verifying: 'verifying',
      executing_setup: 'searching',
      finalizing: 'writing',
      waiting: 'searching',
    }
    return phaseMap[progress.phase] ?? 'planning'
  }

  // No planning progress — derive phase from execution state
  if (!isLoading.value) return null

  if (isSummaryStreaming.value) return 'writing'
  if (hasRunningStep.value || plan.value?.steps?.length) return 'searching'

  return null
})

const phaseStripStepProgress = computed<{ current: number; total: number } | null>(() => {
  const steps = plan.value?.steps
  if (!steps || steps.length === 0) return null
  const completed = steps.filter(
    (s: { status?: string }) => s.status === 'completed' || s.status === 'failed' || s.status === 'skipped'
  ).length
  return { current: completed, total: steps.length }
})

const showPhaseStrip = computed(() =>
  !isChatMode.value &&
  isLoading.value &&
  phaseStripPhase.value !== null &&
  phaseStripStartTime.value > 0
)

// Handle tool panel state changes
const handlePanelStateChange = (isOpen: boolean, userAction: boolean = false) => {
  isToolPanelOpen.value = isOpen;
  // Dual-write: mirror panel state to Pinia stores
  uiStore.setRightPanel(isOpen)
  if (!isOpen && userAction) {
    userDismissedPanel.value = true;
    uiStore.setUserDismissedPanel(true)
  }
};


// Show live preview thumbnail whenever the agent is actively working.
// Covers every activity signal so the user always has visual feedback.
const shouldShowThumbnail = computed(() => {
  if (isToolPanelOpen.value) return false;
  if (!sessionId.value) return false;

  // 1. SSE stream is live (connecting / streaming / completing / reconnecting / degraded)
  if (isLoading.value) return true;

  // 2. Sandbox or session is still booting up
  if (isInitializing.value || isSandboxInitializing.value) return true;

  // 3. Thinking or summary text is streaming in real-time
  if (isThinkingStreaming.value || isSummaryStreaming.value) return true;

  // 4. Plan steps exist and at least one is not yet completed
  if (plan.value?.steps?.length && !isPlanCompleted.value) return true;

  // 5. A tool was invoked and the session hasn't finished yet
  //    (lastNoMessageTool persists after completion — gate on !isTaskCompleted)
  if (lastNoMessageTool.value && !isTaskCompleted.value) return true;

  // 6. Completed session with tool history — show final screenshot / last tool preview
  //    LiveMiniPreview renders shouldShowFinalScreenshot for this case.
  if (isTaskCompleted.value && lastNoMessageTool.value) return true;

  return false;
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

/** 1-based current step for display (0 when nothing selected). */
const toolTimelineCurrentStep = computed(() =>
  toolTimelineIndex.value >= 0 ? toolTimelineIndex.value + 1 : 0
);

const showTimelineControls = computed(() => toolTimeline.value.length > 0);

// Handle opening the panel from TaskProgressBar
const handleOpenPanel = () => {
  if (!canOpenLiveViewPanel.value) return;
  if (lastNoMessageTool.value) {
    if (showToolPanelIfAllowed(lastNoMessageTool.value, isLiveTool(lastNoMessageTool.value))) {
      panelToolId.value = lastNoMessageTool.value.tool_call_id;
    }
  } else if (sessionId.value) {
    // Allow opening panel even without tool content - show live sandbox view
    const placeholderTool: ToolContent = {
      tool_call_id: `placeholder-${Date.now()}`,
      name: 'browser',
      function: 'browser_view',
      args: {},
      status: 'called',
      timestamp: Math.floor(Date.now() / 1000),
    };
    if (showToolPanelIfAllowed(placeholderTool, true)) {
      panelToolId.value = placeholderTool.tool_call_id;
    }
  }
};

const upsertToolTimeline = (toolContent: ToolContent) => {
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

  // Suppress agent-mode guided prompt echo from server.
  // When the user clicks "Use Agent Mode", we send a guided prompt wrapping the original.
  // The server echoes it back as a user message — suppress it to avoid a duplicate bubble.
  if (messageData.role === 'user' && agentModeOriginalPrompt.value) {
    const incoming = (messageData.content || '').trim();
    if (incoming.includes(agentModeOriginalPrompt.value)) {
      agentModeOriginalPrompt.value = null;
      console.debug('Suppressed agent-mode guided prompt echo');
      return;
    }
    agentModeOriginalPrompt.value = null;
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
          // Expected during SSE reconnection replay — suppress silently
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

// Handle tool_stream event — buffer partial content before tool(calling)
const TERMINAL_BUFFER_MAX = 50_000; // 50 KB — prevent memory pressure from long output
const handleToolStreamEvent = (data: ToolStreamEventData) => {
  const existing = streamingContentBuffer.get(data.tool_call_id);
  if (existing && data.content_type === 'terminal') {
    // Terminal output: APPEND delta to existing buffer (capped)
    existing.content += data.partial_content;
    if (existing.content.length > TERMINAL_BUFFER_MAX) {
      existing.content = existing.content.slice(-TERMINAL_BUFFER_MAX);
    }
  } else if (data.content_type === 'terminal') {
    // First terminal chunk — create buffer
    streamingContentBuffer.set(data.tool_call_id, {
      content: data.partial_content,
      functionName: data.function_name,
      contentType: data.content_type,
    });
  } else {
    // Non-terminal content: REPLACE (existing behavior for file content)
    streamingContentBuffer.set(data.tool_call_id, {
      content: data.partial_content,
      functionName: data.function_name,
      contentType: data.content_type,
    });
  }

  // Live-update lastTool streaming_content for already-rendered tools
  if (lastTool.value && lastTool.value.tool_call_id === data.tool_call_id) {
    const buffered = streamingContentBuffer.get(data.tool_call_id);
    if (buffered) {
      lastTool.value.streaming_content = buffered.content;
      lastTool.value.streaming_content_type = buffered.contentType;
    }
  }

  // ── Dual-write: mirror streaming content to Pinia store ──
  const storeBuffered = streamingContentBuffer.get(data.tool_call_id)
  if (storeBuffered) {
    toolStore.setStreamingContent(
      data.tool_call_id,
      storeBuffered.content,
      storeBuffered.functionName,
      storeBuffered.contentType,
    )
  }
}

const applyToolProgressUpdate = (
  tool: ToolContent | undefined,
  data: import('../types/event').ToolProgressEventData,
): boolean => {
  if (!tool || tool.tool_call_id !== data.tool_call_id) return false;
  tool.progress_percent = data.progress_percent;
  tool.current_step = data.current_step;
  tool.elapsed_ms = data.elapsed_ms;
  if (data.checkpoint_data) {
    tool.checkpoint_data = data.checkpoint_data;
  }
  return true;
};

// Handle tool_progress event — update progress on active tool
const handleToolProgressEvent = (data: import('../types/event').ToolProgressEventData) => {
  applyToolProgressUpdate(lastTool.value, data);
  applyToolProgressUpdate(lastNoMessageTool.value, data);

  const timelineTool = toolTimeline.value.find((tool) => tool.tool_call_id === data.tool_call_id);
  applyToolProgressUpdate(timelineTool, data);

  const lastStep = getLastStep();
  if (lastStep) {
    const stepTool = lastStep.tools.find((tool) => tool.tool_call_id === data.tool_call_id);
    applyToolProgressUpdate(stepTool, data);
  }
}

// Map tool function names → NeuralFlow reasoning stage
const TOOL_STAGE_MAP: Record<string, ReasoningStage> = {
  // Search / retrieval
  web_search: 'retrieval',
  search: 'retrieval',
  tavily_search: 'retrieval',
  serper_search: 'retrieval',
  brave_search: 'retrieval',
  duckduckgo_search: 'retrieval',
  // Browser
  browser_navigate: 'retrieval',
  browser_click: 'retrieval',
  browser_input: 'retrieval',
  browser_screenshot: 'retrieval',
  browser_agent: 'retrieval',
  browser: 'retrieval',
  // File ops
  read_file: 'parsing',
  write_file: 'generation',
  list_files: 'parsing',
  file_read: 'parsing',
  file_write: 'generation',
  // Terminal / code execution
  terminal: 'planning',
  run_terminal_cmd: 'planning',
  execute_code: 'generation',
  bash: 'generation',
  python: 'generation',
  // Memory / knowledge
  remember: 'intent',
  recall: 'intent',
  memory_search: 'intent',
};

// Handle tool event
const handleToolEvent = (toolData: ToolEventData) => {
  const functionName = (((toolData as unknown as Record<string, unknown>).function_name as string) || toolData.function || '').toLowerCase();
  const toolName = functionName;
  const mappedStage = TOOL_STAGE_MAP[toolName];
  activeReasoningState.value = mappedStage ?? 'retrieval';
  const lastStep = getLastStep();
  // Merge buffered streaming content into the tool content
  const buffered = streamingContentBuffer.get(toolData.tool_call_id);
  const toolContent: ToolContent = {
    ...toolData,
    ...(buffered && {
      streaming_content: buffered.content,
      streaming_content_type: buffered.contentType,
    }),
  }
  if (buffered) {
    streamingContentBuffer.delete(toolData.tool_call_id);
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
    if (isLoading.value) {
      finalReportText.value = '';
    }
    const preservedTool = shouldPreserveDealToolInLiveView(lastNoMessageTool.value, toolContent)
      ? lastNoMessageTool.value
      : undefined;
    const panelTool = preservedTool ?? toolContent;

    if (!preservedTool) {
      lastNoMessageTool.value = toolContent;
    }
    upsertToolTimeline(toolContent);

    // Auto-resume to real-time when a new tool starts during a live session
    // and the user had navigated backward in the timeline.
    if (!realTime.value && isLoading.value && toolContent.status === 'calling') {
      realTime.value = true;
    }

    if (realTime.value && canOpenLiveViewPanel.value) {
      panelToolId.value = panelTool.tool_call_id;
      if (isToolPanelOpen.value) {
        // Auto-switch panel content when panel is open and new tool starts
        showToolPanelIfAllowed(panelTool, isLiveTool(panelTool));
      } else if (!userDismissedPanel.value) {
        // Auto-open panel on first tool event (user hasn't dismissed it yet)
        showToolPanelIfAllowed(panelTool, isLiveTool(panelTool));
      }
    }
  }

  // Eagerly extract and cache search sources when a search tool completes.
  // This decouples source availability from reactive dependency tracking during render,
  // matching the pattern used by the report flow (sources attached directly to the event).
  if (toolContent.status === 'called') {
    const sources = extractSearchSourcesFromTool(toolContent);
    if (sources.length > 0) {
      searchSourcesCache.value.set(toolContent.tool_call_id, sources);
      triggerRef(searchSourcesCache);
      // Dual-write: mirror to Pinia store
      toolStore.cacheSearchSources(toolContent.tool_call_id, sources);
    }
  }

  // ── Dual-write: mirror tool event to Pinia store ──
  toolStore.recordToolCall(toolContent)

  if (functionName === 'message_ask_user') {
    const args = toolData.args || {};
    const waitReason = typeof args.wait_reason === 'string' ? args.wait_reason : undefined;
    const takeoverSuggestion =
      typeof args.suggest_user_takeover === 'string' ? args.suggest_user_takeover : undefined;
    setTakeoverCtaFromMetadata(waitReason, takeoverSuggestion);
  }
}

// Map agent phase_type → NeuralFlow reasoning stage
const PHASE_TYPE_STAGE_MAP: Partial<Record<string, ReasoningStage>> = {
  planning:    'planning',
  research:    'retrieval',
  execution:   'generation',
  verification:'quality_checking',
  reflection:  'quality_checking',
  search:      'retrieval',
  browsing:    'retrieval',
  coding:      'generation',
  analysis:    'intent',
  summarize:   'generation',
};

// Handle phase event - creates/updates phase message groups
const handlePhaseEvent = (phaseData: import('../types/event').AgentPhaseEventData) => {
  if (phaseData.status === 'started' && phaseData.phase_type) {
    const mapped = PHASE_TYPE_STAGE_MAP[phaseData.phase_type.toLowerCase()];
    if (mapped) activeReasoningState.value = mapped;
  }
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
        timestamp: phaseData.timestamp || Math.floor(Date.now() / 1000),
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
  // Sync NeuralFlow with step lifecycle
  if (stepData.status === 'running' || stepData.status === 'started') {
    activeReasoningState.value = 'planning';
    lastStepDescription.value = stepData.description
  } else if (stepData.status === 'completed') {
    activeReasoningState.value = 'quality_checking';
    lastStepDescription.value = undefined
  }
  const lastStep = getLastStep();
  if (stepData.status === 'running' || stepData.status === 'started') {
    // Check if a running step with the same ID already exists (progressive update pattern)
    // Used by finalization steps that emit multiple RUNNING events with changing descriptions
    const existingRunningStep = messages.value
      .filter(m => m.type === 'step')
      .map(m => m.content as StepContent)
      .find(s => s.id === stepData.id && (s.status === 'running' || s.status === 'started'));

    if (existingRunningStep) {
      // Push the current description into history and update to new description
      if (!existingRunningStep.sub_stage_history) existingRunningStep.sub_stage_history = [];
      existingRunningStep.sub_stage_history.push(existingRunningStep.description);
      existingRunningStep.description = stepData.description;
      return;
    }

    const stepContent: StepContent = {
      ...stepData,
      tools: [],
      phase_id: stepData.phase_id,
      step_type: stepData.step_type,
    }

    // Try to nest step inside its phase group
    const phaseContent = findActivePhaseMessage(stepData.phase_id ?? undefined)
    if (phaseContent) {
      phaseContent.steps.push(stepContent)
    }

    // Always push as top-level message too (for timeline rendering)
    messages.value.push({
      id: generateMessageId(),
      type: 'step',
      content: stepContent,
    });

    // Sync running/started status into plan.value so TaskProgressBar shows in-progress indicator
    if (plan.value?.steps) {
      const planStep = plan.value.steps.find(s => s.id === stepData.id)
      if (planStep) planStep.status = 'running'
    }
  } else if (stepData.status === 'completed' || stepData.status === 'failed' || stepData.status === 'blocked' || stepData.status === 'skipped') {
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
    // Sync step status into plan.value so TaskProgressBar updates immediately
    // (plan.value.steps is the single source of truth for progress count)
    if (plan.value?.steps) {
      const planStep = plan.value.steps.find(s => s.id === stepData.id)
      if (planStep) planStep.status = stepData.status
    }

    if (stepData.status === 'failed' || stepData.status === 'blocked') {
      transitionTo('error')
      // Notify sidebar that session is no longer running
      if (sessionId.value) {
        emitStatusChange(sessionId.value, SessionStatus.COMPLETED);
      }
    }
  }
}

const THOUGHT_STAGE_MAP: Record<NonNullable<ThoughtEventData['thought_type']>, ReasoningStage> = {
  observation: 'parsing',
  analysis: 'intent',
  hypothesis: 'planning',
  conclusion: 'quality_checking',
};

const getLatestRunningStep = (): StepContent | undefined => {
  return [...messages.value]
    .reverse()
    .filter((message) => message.type === 'step')
    .map((message) => message.content as StepContent)
    .find((step) => step.status === 'running' || step.status === 'started');
};

const handleThoughtEvent = (thoughtData: ThoughtEventData) => {
  if (thoughtData.thought_type && THOUGHT_STAGE_MAP[thoughtData.thought_type]) {
    activeReasoningState.value = THOUGHT_STAGE_MAP[thoughtData.thought_type];
  }

  if (thoughtData.status === 'chain_complete') {
    activeReasoningState.value = 'quality_checking';
  }

  const thoughtText = thoughtData.content?.trim();
  if (!thoughtText) {
    return;
  }

  const thoughtContent: ThoughtContent = {
    id: thoughtData.event_id || `thought-${Date.now()}`,
    text: thoughtText,
    thought_type: thoughtData.thought_type,
    confidence: thoughtData.confidence,
    timestamp: thoughtData.timestamp,
  };

  const runningStep = getLatestRunningStep();
  if (!runningStep) {
    return;
  }

  if (!runningStep.items) {
    runningStep.items = [];
  }

  const thoughtAlreadyPresent = runningStep.items.some((item) => {
    if (item.type !== 'thought') return false;
    const existingThought = item.content as ThoughtContent;
    return existingThought.id === thoughtContent.id || existingThought.text === thoughtContent.text;
  });

  if (thoughtAlreadyPresent) {
    return;
  }

  runningStep.items.push({
    type: 'thought',
    timestamp: thoughtData.timestamp || Math.floor(Date.now() / 1000),
    content: thoughtContent,
  });
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
  const handoffComplexity = planningProgress.value?.complexityCategory;
  thinkingText.value = '';
  planningPreviewBatcher.reset('');
  isThinkingStreaming.value = false;
  planningProgress.value = null;  // Clear progress - plan is ready
  startPlanningHandoff(handoffComplexity);
  plan.value = planData;
}

// Handle stream event (thinking text streaming or summary streaming)
const handleStreamEvent = (streamData: StreamEventData) => {
  activeReasoningState.value = 'generation';
  researchWorkflow.handleStreamEvent(streamData);
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
    planningPreviewBatcher.reset('');
  } else {
    const nextThinkingText = `${thinkingText.value}${streamData.content}`;
    isThinkingStreaming.value = true;
    thinkingText.value = nextThinkingText;
    planningPreviewBatcher.push(nextThinkingText);
  }
}

// Task completion should immediately hide planner progress UI.
watch(isTaskCompleted, (completed) => {
  if (!completed) return;
  planningProgress.value = null;
  planningPreviewBatcher.reset('');
  clearPlanningHandoff();
});

watch(hasVisibleExecutionStep, (isVisible) => {
  if (!shouldDismissPlanningHandoff(isVisible)) return;
  clearPlanningHandoff();
});

// Handle progress event (instant feedback during planning)
// Note: heartbeat progress events never reach here — client.ts filters them
// and dispatches sse:heartbeat custom events instead (handled by startHeartbeatBridge).
const handleProgressEvent = (progressData: ProgressEventData) => {
  // Ignore late progress events after completion (can occur during stream tailing).
  if (isTaskCompleted.value) {
    planningProgress.value = null;
    planningPreviewBatcher.reset('');
    return;
  }

  // Update planning progress for UI
  const phase = normalizePlanningPhase(progressData.phase);
    
  if (phase === 'received') activeReasoningState.value = 'parsing';
  else if (phase === 'analyzing') activeReasoningState.value = 'intent';
  else if (phase === 'planning') activeReasoningState.value = 'planning';
  else if (phase === 'verifying') activeReasoningState.value = 'quality_checking';
  else if (phase === 'executing_setup') activeReasoningState.value = 'generation';

  planningPreviewBatcher.cancelPending();

  planningProgress.value = {
    phase,
    message: progressData.message,
    percent: progressData.progress_percent || 0,
    estimatedDurationSeconds: progressData.estimated_duration_seconds,
    complexityCategory: progressData.complexity_category,
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
  partialResults.value = [];

  const reportAttachments = reportData.attachments ?? [];
  removeRedundantAssistantAttachmentMessages(reportAttachments);

  // Track anchor event ID for follow-up suggestions
  followUpAnchorEventId.value = reportData.event_id;

  const normalizedReportContent = collapseDuplicateReportBlocks(reportData.content);
  finalReportText.value = normalizedReportContent;
  const sections = extractSectionsFromMarkdown(normalizedReportContent);
  const epochSec = toEpochSeconds(reportData.timestamp) ?? Math.floor(Date.now() / 1000);
  const nextReportContent: ReportContent = {
    id: reportData.id,
    event_id: reportData.event_id,
    title: reportData.title,
    content: normalizedReportContent,
    lastModified: epochSec * 1000,
    fileCount: reportAttachments.length,
    sections,
    sources: reportData.sources,
    attachments: reportAttachments,
    timestamp: epochSec,
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

const handlePhaseTransitionEvent = (data: PhaseTransitionEventData) => {
  researchWorkflow.handlePhaseTransitionEvent(data);
};

const handleCheckpointSavedEvent = (data: CheckpointSavedEventData) => {
  researchWorkflow.handleCheckpointSavedEvent(data);
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

// Handle canvas update events — auto-open panel with canvas view
const handleCanvasUpdateEvent = (data: CanvasUpdateEventData) => {
  activeCanvasUpdate.value = data;

  const syntheticStatus = sessionStatus.value === SessionStatus.RUNNING ? 'running' : 'called';
  const syntheticTool: ToolContent = {
    timestamp: Date.now(),
    event_id: data.event_id,
    tool_call_id: `canvas-live-${data.project_id}-${data.version}-${data.event_id || data.timestamp}`,
    name: 'canvas',
    function: data.operation || 'canvas_create_project',
    args: { project_id: data.project_id },
    content: {
      project_id: data.project_id,
      session_id: data.session_id,
      project_name: data.project_name,
      operation: data.operation,
      element_count: data.element_count,
      version: data.version,
      changed_element_ids: data.changed_element_ids,
    },
    status: syntheticStatus,
  };

  if (realTime.value && canOpenLiveViewPanel.value) {
    panelToolId.value = syntheticTool.tool_call_id;
    if (isToolPanelOpen.value || !userDismissedPanel.value) {
      showToolPanelIfAllowed(syntheticTool, true);
    }
  }
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

const textPreviewExtensions = new Set(['md', 'markdown', 'txt', 'log', 'text']);

const canOpenInReportModal = (file: FileInfo): boolean => {
  const ext = file.filename.split('.').pop()?.toLowerCase() || '';
  return textPreviewExtensions.has(ext);
};

const openTextFileInReportModal = async (file: FileInfo) => {
  try {
    const blob = await downloadFile(file.file_id);
    const textContent = await blob.text();
    const extension = file.filename.split('.').pop()?.toLowerCase() || '';
    const contentForModal =
      extension === 'md' || extension === 'markdown'
        ? collapseDuplicateReportBlocks(textContent)
        : preparePlainTextForViewer(textContent);
    const reportPreview: ReportData = {
      id: file.file_id,
      title: (file.metadata?.title as string) || file.filename,
      content: contentForModal,
      author: 'Pythinker',
      lastModified: file.upload_date ? new Date(file.upload_date).getTime() : Date.now(),
      fileCount: 1,
      sections: extractSectionsFromMarkdown(contentForModal),
      attachments: [file],
    };
    openReport(reportPreview);
  } catch {
    showErrorToast('Failed to open text preview');
  }
};

const closeFilePreview = () => {
  filePreviewOpen.value = false;
  filePreviewFile.value = null;
};

// Handle report file open
const handleReportFileOpen = async (file: FileInfo) => {
  hideFilePanel();
  if (canOpenInReportModal(file)) {
    await openTextFileInReportModal(file);
    return;
  }
  filePreviewFile.value = file;
  filePreviewOpen.value = true;
}

// Handle attached file click (open in modal)
const handleAttachmentFileClick = async (file: FileInfo) => {
  hideFilePanel();
  if (canOpenInReportModal(file)) {
    await openTextFileInReportModal(file);
    return;
  }
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

// ── Extracted event handlers for registry dispatch ──────────────────
const finalizeSession = (
  reason: 'done' | 'stop' | 'reconcile' | 'visibility' | 'retry_reconcile',
  status: SessionStatus = SessionStatus.COMPLETED,
  options: { cleanupStorage?: boolean } = {},
) => {
  if (
    receivedDoneEvent.value &&
    sessionStatus.value === status &&
    isTerminalSessionStatus(status)
  ) {
    return;
  }

  console.log('[FINALIZE]', reason, 'sessionId:', sessionId.value, 'status:', status);

  normalizeTransientTools({
    messages: messages.value,
    toolTimeline: toolTimeline.value,
    lastTool: lastTool.value,
    lastNoMessageTool: lastNoMessageTool.value,
  });

  activeReasoningState.value = 'completed';
  follow.value = false;
  planningProgress.value = null;
  partialResults.value = [];
  isWaitingForReply.value = false;
  clearTakeoverCta();
  dismissConnectionBanner();
  cleanupStreamingState();
  realTime.value = false;

  transitionTo(reason === 'stop' ? 'stopped' : 'completing');

  if (sessionId.value) {
    emitStatusChange(sessionId.value, status);
    if (options.cleanupStorage ?? true) {
      cleanupSessionStorage(sessionId.value);
    }
  }
  sessionStatus.value = status;
  receivedDoneEvent.value = true;
  replay.loadScreenshots();
};

const handleDoneEvent = () => {
  logChatSseDiagnostics('event:done_received', {
    eventId: null,
    queuedAfterDone: streamController.getPendingEventCount(),
  });
  ensureCompletionSuggestions();
  markShortAssistantCompletion();
  finalizeSession('done', SessionStatus.COMPLETED);
};

const handleWaitEvent = (data: unknown) => {
  dismissConnectionBanner();
  isWaitingForReply.value = true;
  const waitData = data as WaitEventData;
  setTakeoverCtaFromMetadata(waitData.wait_reason, waitData.suggest_user_takeover);
  transitionTo('settled')
}

const handleIncomingErrorEvent = (data: unknown) => {
  clearTakeoverCta();
  const errorData = data as ErrorEventData;
  const isRecoverableTimeout = errorData.error_type === 'timeout' && (errorData.recoverable ?? true);
  const isRecoverableStreamGap = errorData.error_code === 'stream_gap_detected';

  if (isRecoverableStreamGap) {
    logChatSseDiagnostics('event:stream_gap_warning_ignored', {
      requestedEventId: errorData.details?.requested_event_id ?? null,
      firstAvailableEventId: errorData.details?.first_available_event_id ?? null,
      checkpointEventId: errorData.checkpoint_event_id ?? null,
    })
    return;
  }

  if (isRecoverableTimeout) {
    lastError.value = {
      message: errorData.error || 'Chat stream timed out',
      type: errorData.error_type ?? null,
      recoverable: true,
      hint: errorData.retry_hint ?? null,
    };
    const code = errorData.error_code ?? '';
    if (code === 'workflow_idle_timeout' || code === 'workflow_wall_clock_timeout') {
      timeoutReason.value = code === 'workflow_idle_timeout' ? 'workflow_idle' : 'workflow_limit';
    } else {
      timeoutReason.value = 'connection';
    }
    transitionTo('timed_out')
  } else {
    transitionTo('error')
    handleErrorEvent(errorData);
  }
}

const handleResearchModeEvent = (data: unknown) => {
  const rmData = data as { research_mode: string };
  sessionResearchMode.value = (rmData.research_mode as agentApi.ResearchMode) || 'deep_research';
}

// ── Observability event handlers (flow lifecycle, verification) ──
// These events provide visibility into backend flow selection and state
// transitions. Currently logged for diagnostics; extend as UI surfaces evolve.

const handleFlowSelectionEvent = (data: unknown) => {
  const fsData = data as import('../types/event').FlowSelectionEventData
  logChatSseDiagnostics('event:flow_selection', {
    flow_mode: fsData.flow_mode,
    model: fsData.model ?? null,
    reason: fsData.reason ?? null,
  })
}

const handleFlowTransitionEvent = (data: unknown) => {
  const ftData = data as import('../types/event').FlowTransitionEventData
  logChatSseDiagnostics('event:flow_transition', {
    from: ftData.from_state,
    to: ftData.to_state,
    reason: ftData.reason ?? null,
    elapsed_ms: ftData.elapsed_ms ?? null,
  })
}

const handleVerificationEvent = (data: unknown) => {
  const vData = data as import('../types/event').VerificationEventData
  logChatSseDiagnostics('event:verification', {
    status: vData.status,
    verdict: vData.verdict ?? null,
    confidence: vData.confidence ?? null,
  })
}

const handleReflectionEvent = (data: unknown) => {
  const rData = data as import('../types/event').ReflectionEventData
  logChatSseDiagnostics('event:reflection', {
    status: rData.status,
    decision: rData.decision ?? null,
    confidence: rData.confidence ?? null,
    trigger_reason: rData.trigger_reason ?? null,
  })
  // Map reflection to quality_checking reasoning stage (same as phase_type mapping)
  if (rData.status === 'triggered') {
    activeReasoningState.value = 'quality_checking'
  }
}

// ── Partial result handler (provisional findings during execution) ──
const handlePartialResultEvent = (data: PartialResultEventData) => {
  partialResults.value.push({
    stepIndex: data.step_index,
    stepTitle: data.step_title,
    headline: data.headline,
    sourcesCount: data.sources_count,
  })
}

// ── Event handler registry (O(1) dispatch replaces 22-branch if/else) ──
const eventRegistry = createEventHandlerRegistry({
  message: (data) => { handleMessageEvent(data as MessageEventData); suggestions.value = []; },
  tool: (data) => handleToolEvent(data as ToolEventData),
  tool_stream: (data) => handleToolStreamEvent(data as ToolStreamEventData),
  tool_progress: (data) => handleToolProgressEvent(data as import('../types/event').ToolProgressEventData),
  step: (data) => handleStepEvent(data as StepEventData),
  phase: (data) => handlePhaseEvent(data as import('../types/event').AgentPhaseEventData),
  thought: (data) => handleThoughtEvent(data as ThoughtEventData),
  done: () => handleDoneEvent(),
  wait: (data) => handleWaitEvent(data),
  error: (data) => handleIncomingErrorEvent(data),
  title: (data) => handleTitleEvent(data as TitleEventData),
  plan: (data) => handlePlanEvent(data as PlanEventData),
  mode_change: (data) => handleModeChangeEvent(data as ModeChangeEventData),
  suggestion: (data) => handleSuggestionEvent(data as SuggestionEventData),
  report: (data) => handleReportEvent(data as ReportEventData),
  stream: (data) => handleStreamEvent(data as StreamEventData),
  progress: (data) => handleProgressEvent(data as ProgressEventData),
  phase_transition: (data) => handlePhaseTransitionEvent(data as PhaseTransitionEventData),
  checkpoint_saved: (data) => handleCheckpointSavedEvent(data as CheckpointSavedEventData),
  skill_delivery: (data) => handleSkillDeliveryEvent(data as SkillDeliveryEventData),
  skill_activation: (data) => handleSkillActivationEvent(data as SkillActivationEventData),
  canvas_update: (data) => handleCanvasUpdateEvent(data as CanvasUpdateEventData),
  workspace: (data) => researchWorkflow.handleWorkspaceEvent(data as WorkspaceEventData),
  research_mode: (data) => handleResearchModeEvent(data),
  mcp_health: (data) => useMcpStatus().handleHealthEvent(data as import('@/api/mcp').McpHealthEventData),
  flow_selection: (data) => handleFlowSelectionEvent(data),
  flow_transition: (data) => handleFlowTransitionEvent(data),
  verification: (data) => handleVerificationEvent(data),
  reflection: (data) => handleReflectionEvent(data),
  partial_result: (data) => handlePartialResultEvent(data as PartialResultEventData),
  eval_metrics: (data) => {
    const metrics = data as import('../types/event').EvalMetricsEventData
    console.debug('[EvalMetrics]', metrics.passed ? 'PASSED' : 'WARN', `hallucination=${metrics.hallucination_score}`)
  },
})

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
  // Dual-write: mirror event time to Pinia connection store
  connectionStore.updateLastRealEventTime()

  // Transition to streaming on first real event
  if (
    responsePhase.value === 'connecting'
    || responsePhase.value === 'reconnecting'
    || responsePhase.value === 'degraded'
  ) {
    // Clear transient/recoverable error state from previous connection attempts
    // to prevent old error banners from flickering on successful reconnect.
    // Preserve non-recoverable errors (rate limits, validation failures) so the
    // user can see them even after an automatic retry delivers events.
    if (lastError.value === null || lastError.value.recoverable) {
      lastError.value = null
    }
    timeoutReason.value = null
    transitionTo('streaming')
  }

  // Dispatch event through registry (O(1) lookup replaces 22-branch if/else)
  const handled = dispatchEvent(eventRegistry, event.event, event.data)
  if (!handled) {
    console.warn(`[SSE] Unhandled event type: ${event.event}`)
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

const handleSubmit = (options: { thinkingMode?: ThinkingMode } = {}) => {
  currentThinkingMode.value = options.thinkingMode || 'auto';
  chat(inputMessage.value, attachments.value, options);
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

  // Track original prompt so we can suppress the guided echo from the server
  agentModeOriginalPrompt.value = originalPrompt;

  const guidedPrompt = `Use full agent mode for this task. First create a clear plan, then execute it:\n\n${originalPrompt}`;
  chat(guidedPrompt, [], { skipOptimistic: true });
};

// Track last sent message to prevent duplicate submissions
let lastSentMessage = '';
let lastSentTime = 0;

const chat = async (
  message: string = '',
  files: FileInfo[] = [],
  options?: { skipOptimistic?: boolean; thinkingMode?: ThinkingMode }
) => {
  const streamAttemptId = beginStreamAttempt();
  if (!sessionId.value) return;
  // Reset user dismissal so the panel auto-opens for the new agent run
  userDismissedPanel.value = false;
  uiStore.resetDismissed()
  toolStore.clearAll()
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
    clearTakeoverCta();
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
    clearTakeoverCta();
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
  if (normalizedMessage || files.length > 0 || followUp) {
    finalReportText.value = '';
  }
  lastHeartbeatAt.value = 0;
  isWaitingForReply.value = false;
  clearTakeoverCta();
  agentModeOriginalPrompt.value = null;
  timeoutReason.value = null;
  activeReasoningState.value = 'idle';
  phaseStripStartTime.value = Date.now();
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
          content_type: file.content_type || '',
          size: file.size,
          upload_date: file.upload_date
        })),
        effectiveSkillIds, // session + per-message skills
        { thinking_mode: options?.thinkingMode },
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

let restoreEpoch = 0;

const invalidateRestoreEpoch = (reason: string) => {
  restoreEpoch += 1;
  console.log('[RESTORE] Invalidate restore epoch', restoreEpoch, 'reason:', reason);
};

type RestoreContext = 'mount' | 'route_update' | 'session_create';

const restoreSession = async (
  targetSessionId: string,
  context: RestoreContext,
) => {
  if (!targetSessionId) {
    showErrorToast(t('Session not found'));
    return;
  }

  const epoch = ++restoreEpoch;
  const shouldAbortRestore = (checkpoint: string): boolean => {
    const reason = getRestoreAbortReason({
      epoch,
      activeEpoch: restoreEpoch,
      targetSessionId,
      currentSessionId: sessionId.value,
    });
    if (!reason) return false;
    console.log('[RESTORE] Stale epoch detected, aborting', {
      checkpoint,
      reason,
      context,
      targetSessionId,
      epoch,
      activeEpoch: restoreEpoch,
      currentSessionId: sessionId.value,
    });
    return true;
  };

  if (shouldAbortRestore('start')) return;

  try {
    // Load lastEventId from sessionStorage for proper event resumption
    const savedEventId = _getPersistedEventId(targetSessionId);
    if (shouldAbortRestore('after_get_persisted_event_id')) return;
    if (savedEventId) {
      lastEventId.value = savedEventId;
      console.log('[RESTORE] Loaded lastEventId from sessionStorage:', savedEventId);
    }

    const session = await agentApi.getSession(targetSessionId);
    if (shouldAbortRestore('after_get_session')) return;

    sessionStatus.value = session.status as SessionStatus;
    sessionResearchMode.value = (session.research_mode as agentApi.ResearchMode) || 'deep_research';
    sessionSource.value = (session.source || 'web').toLowerCase();
    // Set title from session data so it doesn't stay as "New Chat"
    if (session.title?.trim()) {
      title.value = session.title;
    }
    console.log('[RESTORE] Session:', targetSessionId, 'Status:', sessionStatus.value, 'ResearchMode:', sessionResearchMode.value, 'LastEventId:', lastEventId.value);

    // Initialize share mode based on session state
    shareMode.value = session.is_shared ? 'public' : 'private';
    realTime.value = false;

    // Drain any pending batched events before replaying persisted history.
    streamController.flushPendingEvents();

    for (const event of session.events) {
      if (shouldAbortRestore('history_replay')) return;
      if (!shouldReplayHistoryEvent(event.event, sessionStatus.value)) continue;
      handleEvent(event);
    }

    // Flush replayed history immediately so auto-resume evaluates fully
    // hydrated state (prevents footer/order races after refresh).
    streamController.flushPendingEvents();
    if (shouldAbortRestore('after_history_replay')) return;

    realTime.value = true;
    if (sessionStatus.value === SessionStatus.INITIALIZING) {
      await waitForSessionIfInitializing();
      if (shouldAbortRestore('after_wait_for_session_ready')) return;
    }
    if (sessionStatus.value === SessionStatus.RUNNING || sessionStatus.value === SessionStatus.PENDING) {
      transitionTo('connecting'); // Will transition to 'streaming' on first event
      receivedDoneEvent.value = false;

      // Defense-in-depth: if event replay already set status to COMPLETED (via DoneEvent
      // handler), the condition above will be false and we skip auto-resume. But if the
      // server returned "running" AND events didn't include a DoneEvent (edge case),
      // do a lightweight status re-check to avoid restarting a completed task.
      const freshStatus = await agentApi.getSessionStatus(targetSessionId);
      if (shouldAbortRestore('after_status_recheck')) return;
      if (freshStatus && isTerminalSessionStatus(freshStatus.status as SessionStatus)) {
        console.log('[RESTORE] Status re-check shows session is', freshStatus.status, '- not resuming');
        finalizeSession('reconcile', freshStatus.status as SessionStatus);
        return;
      }

      // Check if this session was manually stopped (prevents auto-resume on page refresh)
      // Using sessionStorage: persists on refresh, cleared on tab close
      const stoppedKey = `pythinker-stopped-${targetSessionId}`;
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

      if (shouldAbortRestore('before_auto_resume')) return;

      // No stop flag - safe to auto-resume
      console.log('[RESTORE] No stop flag, auto-resuming session');
      await chat('', [], { skipOptimistic: true });
      if (shouldAbortRestore('after_auto_resume')) return;
    } else if (isTerminalSessionStatus(sessionStatus.value)) {
      // Session already finished — settle immediately and load replay data
      finalizeSession('reconcile', sessionStatus.value);
    }

    if (shouldAbortRestore('before_clear_unread')) return;
    await agentApi.clearUnreadMessageCount(targetSessionId);
  } catch (error) {
    if (shouldAbortRestore('error')) return;
    console.error('[RESTORE] Failed to restore session', { targetSessionId, context, error });
    transitionTo('error');
    showErrorToast(t('Failed to restore session'));
  }
};

onBeforeRouteUpdate(async (to, from) => {
  const targetSessionId = String(to.params.sessionId || '');
  if (skipResetForSessionId.value && skipResetForSessionId.value === targetSessionId) {
    skipResetForSessionId.value = null;
    if (targetSessionId) {
      sessionId.value = targetSessionId;
      // Clear stale search sources from previous session even when skipping full reset
      searchSourcesCache.value = new Map();
    }
    return;
  }
  // Clear stale skip target if navigating elsewhere
  skipResetForSessionId.value = null;

  // Only reset state when actually switching to a different session
  // This prevents cancelling the active chat on same-session route updates
  const prevSessionId = typeof from.params.sessionId === 'string' ? from.params.sessionId : undefined;
  const nextSessionId = typeof to.params.sessionId === 'string' ? to.params.sessionId : undefined;
  const isSwitchingSession = prevSessionId !== nextSessionId;
  if (!isSwitchingSession) return;

  invalidateRestoreEpoch('route_update');

  // Stop the current session if it's still running AND we're switching sessions
  if (prevSessionId && shouldStopSessionOnExit(sessionStatus.value)) {
    try {
      await agentApi.stopSession(prevSessionId);
      emitStatusChange(prevSessionId, SessionStatus.COMPLETED);
    } catch {
      // Non-critical — backend safety net will clean up
    }
  }

  // Only reset state and clear UI when actually switching sessions
  toolPanel.value?.clearContent(); // Clear tool panel content when switching sessions
  hideFilePanel();
  resetState(); // This cancels the chat - only do it when switching sessions

  messages.value = [];
  if (nextSessionId) {
    sessionId.value = nextSessionId;
    await restoreSession(nextSessionId, 'route_update');
    return;
  }

  sessionId.value = undefined;
});

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
  window.addEventListener('resize', handleViewportResize);

  if (typeof ResizeObserver !== 'undefined' && chatContainerRef.value) {
    chatContainerResizeObserver = new ResizeObserver(() => {
      updateChatBottomDockMetrics();
    });
    chatContainerResizeObserver.observe(chatContainerRef.value);
  }
  if (typeof ResizeObserver !== 'undefined' && _chatBottomDockRef.value) {
    chatBottomDockResizeObserver = new ResizeObserver(() => {
      measureChatBottomDock();
    });
    chatBottomDockResizeObserver.observe(_chatBottomDockRef.value);
  }
  await nextTick();
  updateChatBottomDockMetrics();
  handleViewportResize();

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
    // Restore chat mode flag from sessionStorage
    try { if (sessionStorage.getItem(`chatMode:${sessionId.value}`)) isChatModeOverride.value = true; } catch { /* storage unavailable */ }
    // Do not auto-send messages from history.state on existing sessions.
    // Pending initial prompts are handled exclusively via /chat/new bootstrap flow.
    if ((history.state as PendingSessionCreateState | null)?.pendingSessionCreate) {
      history.replaceState({}, document.title);
    }
    await restoreSession(String(routeParams.sessionId), 'mount');
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
  if (!sessionStatus.value || !activeStatuses.includes(sessionStatus.value)) return;

  try {
    const activeSessionId = sessionId.value;
    const status = await agentApi.getSessionStatus(activeSessionId);
    if (sessionId.value !== activeSessionId) return;
    if (status.status !== sessionStatus.value) {
      console.log('[VISIBILITY] Session status changed while away:', sessionStatus.value, '->', status.status);
      const nextStatus = status.status as SessionStatus;
      if (isTerminalSessionStatus(nextStatus)) {
        finalizeSession('visibility', nextStatus);
      } else {
        sessionStatus.value = nextStatus;
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
  invalidateRestoreEpoch('unmount');
  beginStreamAttempt();
  window.removeEventListener('pythinker:insert-chat-message', handleInsertMessage);
  window.removeEventListener('resize', handleViewportResize);
  if (chatContainerResizeObserver) {
    chatContainerResizeObserver.disconnect();
    chatContainerResizeObserver = null;
  }
  if (chatBottomDockResizeObserver) {
    chatBottomDockResizeObserver.disconnect();
    chatBottomDockResizeObserver = null;
  }
  stopSplitterDrag();
  if (cancelCurrentChat.value) {
    cancelCurrentChat.value();
    cancelCurrentChat.value = null;
  }
  if (linkCopiedTimer) {
    clearTimeout(linkCopiedTimer);
    linkCopiedTimer = null;
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

/** Sync screenshot replay index to match the currently navigated tool. */
const syncReplayToTool = (tool: ToolContent) => {
  if (!replay.hasScreenshots.value) return;
  const screenshots = replay.screenshots.value;

  // Exact match by tool_call_id (prefer tool_after for result view)
  let bestIdx = -1;
  for (let i = screenshots.length - 1; i >= 0; i--) {
    if (screenshots[i].tool_call_id === tool.tool_call_id) {
      bestIdx = i;
      if (screenshots[i].trigger === 'tool_after') break;
    }
  }

  // Fallback: closest screenshot by timestamp
  if (bestIdx < 0 && tool.timestamp) {
    let bestDiff = Infinity;
    for (let i = 0; i < screenshots.length; i++) {
      const diff = Math.abs((screenshots[i].timestamp || 0) - tool.timestamp);
      if (diff < bestDiff) {
        bestDiff = diff;
        bestIdx = i;
      }
    }
  }

  if (bestIdx >= 0) {
    replay.currentIndex.value = bestIdx;
  }
};

const showToolFromTimeline = (index: number) => {
  if (toolTimeline.value.length === 0) return;
  if (!canOpenLiveViewPanel.value) return;
  const clampedIndex = Math.max(0, Math.min(index, toolTimeline.value.length - 1));
  const tool = toolTimeline.value[clampedIndex];
  if (!tool) return;
  realTime.value = false;
  if (showToolPanelIfAllowed(tool, false)) {
    panelToolId.value = tool.tool_call_id;
    // Sync screenshot replay to this tool's timeframe
    syncReplayToTool(tool);
  }
}

const handleTimelineStepForward = () => {
  if (!toolTimelineCanStepForward.value) return;
  showToolFromTimeline(toolTimelineIndex.value + 1);
}

const handleTimelineStepBackward = () => {
  if (!toolTimelineCanStepBackward.value) return;
  showToolFromTimeline(toolTimelineIndex.value - 1);
}

const handleTimelineSeek = (progress: number) => {
  if (toolTimeline.value.length === 0) return;
  const maxIndex = toolTimeline.value.length - 1;
  const targetIndex = Math.round((progress / 100) * maxIndex);
  showToolFromTimeline(targetIndex);
}

const handleToolClick = (tool: ToolContent) => {
  realTime.value = false;
  if (!canOpenLiveViewPanel.value) return;
  if (sessionId.value) {
    if (showToolPanelIfAllowed(tool, false)) {
      panelToolId.value = tool.tool_call_id;
      syncReplayToTool(tool);
    }
  }
}

const jumpToRealTime = () => {
  realTime.value = true;
  if (!canOpenLiveViewPanel.value) return;
  if (lastNoMessageTool.value) {
    if (showToolPanelIfAllowed(lastNoMessageTool.value, isLiveTool(lastNoMessageTool.value))) {
      panelToolId.value = lastNoMessageTool.value.tool_call_id;
    }
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

const handleCancel = async () => {
  if (!sessionId.value || isCancelling.value) return
  isCancelling.value = true
  try {
    await agentApi.cancelSession(sessionId.value)
  } catch {
    // Session may have already completed — ignore
  } finally {
    // Reset after a delay to allow the cancellation to propagate
    setTimeout(() => { isCancelling.value = false }, 3000)
  }
}

const handleStop = async () => {
  beginStreamAttempt();
  stopFallbackStatusPolling();
  // Cancel the SSE stream FIRST to prevent any reconnect/resume logic
  if (cancelCurrentChat.value) {
    cancelCurrentChat.value();
    cancelCurrentChat.value = null;
  }
  const activeSessionId = sessionId.value;
  if (activeSessionId) {
    // Clear lastEventId from sessionStorage since session is stopped (use centralized cleanup)
    cleanupSessionStorage(activeSessionId);
    // Mark this session as manually stopped to prevent auto-resume on page refresh
    // Set AFTER cleanup so the flag isn't immediately removed
    sessionStorage.setItem(`pythinker-stopped-${activeSessionId}`, JSON.stringify({ timestamp: Date.now() }));
    // Await the stop request so backend teardown completes before the user
    // can trigger a new message (prevents stop/chat race condition).
    try {
      await agentApi.stopSession(activeSessionId);
    } catch {
      // Non-critical — backend safety net will clean up
    }
  }

  // Reset stale-state indicator immediately before finalization transition.
  isStale.value = false;
  // NO ensureCompletionSuggestions() — user intentionally stopped.
  // Preserve stop marker in sessionStorage so refresh does not auto-resume.
  finalizeSession('stop', SessionStatus.COMPLETED, { cleanupStorage: false });
}

const handleContinueAfterTimeout = () => {
  timeoutReason.value = null;
  chat('Continue the task from where you left off.', []);
};

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
    if (isTerminalSessionStatus(status)) {
      finalizeSession('retry_reconcile', status);
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
      if (linkCopiedTimer) clearTimeout(linkCopiedTimer);
      linkCopiedTimer = setTimeout(() => {
        linkCopiedTimer = null;
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
/* ===== CHAT + LIVE SPLIT LAYOUT ===== */
.chat-split-shell {
  position: relative;
  display: flex;
  flex: 1;
  min-width: 0;
  width: 100%;
  min-height: 100%;
  align-self: stretch;
}

.chat-live-splitter {
  touch-action: none;
  outline: none;
  pointer-events: auto;
  position: relative;
  display: flex;
  justify-content: center;
  align-items: stretch;
}

/* Keyboard focus ring - more prominent than hover state */
.chat-live-splitter:focus-visible::before {
  content: '';
  position: absolute;
  top: 8px;
  bottom: 8px;
  left: -2px;
  right: -2px;
  border: 2px solid var(--status-running, #3b82f6);
  border-radius: 6px;
  opacity: 0.5;
  pointer-events: none;
  animation: pulse-focus-ring 1.5s ease-in-out infinite;
}

@keyframes pulse-focus-ring {
  0%, 100% {
    opacity: 0.5;
  }
  50% {
    opacity: 0.8;
  }
}

.chat-live-splitter-handle {
  transform-origin: center;
}

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

.chat-view-toggle {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px;
  border-radius: 10px;
  border: 1px solid var(--border-main);
  background: var(--background-menu-white);
}

.chat-view-toggle-btn {
  height: 28px;
  padding: 0 10px;
  border-radius: 8px;
  border: 1px solid transparent;
  color: var(--text-secondary);
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 600;
  transition: all 0.15s ease;
}

.chat-view-toggle-btn:hover {
  color: var(--text-primary);
  background: var(--fill-tsp-white-main);
}

.chat-view-toggle-btn-active {
  color: var(--text-primary);
  border-color: var(--border-main);
  background: var(--background-white-main);
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

.chat-source-badge {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 22px;
  border-radius: 9999px;
  padding: 0 8px;
  font-size: 11px;
  font-weight: 600;
  color: #229ed9;
  background: rgba(34, 158, 217, 0.14);
}

.chat-bottom-dock {
  padding-top: 8px;
  z-index: 20;
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
  background: var(--background-gray-main);
}

/* 120-degree diagonal shimmer text effect */
.thinking-text-shimmer {
  background: linear-gradient(
    120deg,
    #222222 0%,
    #222222 40%,
    #b0b0b0 50%,
    #222222 60%,
    #222222 100%
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

/* ===== PLANNING CARD TRANSITION ===== */
.planning-card-enter-active {
  transition: transform 0.35s cubic-bezier(0.34, 1.56, 0.64, 1), opacity 0.3s ease;
}

.planning-card-leave-active {
  transition: transform 0.25s ease, opacity 0.2s ease;
}

.planning-card-enter-from {
  transform: translateY(8px) scale(0.97);
  opacity: 0;
}

.planning-card-leave-to {
  transform: translateY(-6px) scale(0.98);
  opacity: 0;
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
