<template>
  <form @submit.prevent="handleSubmit" class="flex flex-col items-stretch gap-[20px]">
    <div class="relative">
      <div class="transition-all duration-500 ease-out opacity-100 scale-100">
        <div class="flex flex-col gap-[12px]">
          <div class="flex flex-col items-start">
            <div class="w-full flex items-center justify-between gap-[12px] mb-[8px]">
              <label
                for="verifyCode"
                class="text-[13px] text-[var(--text-primary)] font-medium after:content-[&quot;*&quot;] after:text-[var(--function-error)] after:ml-[4px]"
              >
                <span>{{ t('Enter the verification code sent to') }} <b>{{ props.email }}</b></span>
              </label>
            </div>
            <div class="w-full relative">
              <input
                id="verifyCode"
                v-model="verificationCode"
                :placeholder="t('Enter 6-digit verification code')"
                type="text"
                maxlength="6"
                pattern="[0-9]{6}"
                inputmode="numeric"
                :disabled="isLoading || isResending"
                class="rounded-[10px] overflow-hidden text-sm leading-[22px] text-[var(--text-primary)] h-10 w-full disabled:cursor-not-allowed placeholder:text-[var(--text-disable)] bg-[var(--fill-input-chat)] pt-1 pb-1 pl-3 focus:ring-[1.5px] focus:ring-[var(--border-dark)] pr-[128px] text-center tracking-[0.3em] font-mono text-[18px]"
                :class="{ 'ring-1 ring-[var(--function-error)]': codeError }"
                @input="handleCodeInput"
                @paste="handlePaste"
              >
              <div
                class="absolute w-[120px] z-[30] top-1/2 right-0 -translate-y-1/2 text-center border-l-[1px] border-l-color-[var(--border-main)] leading-[0px]"
              >
                <span
                  v-if="verificationState && resendCountdown > 0"
                  class="inline-block min-w-[60px] text-[var(--text-blue)] text-center text-[14px] leading-[18px] select-none opacity-50 transition-opacity"
                >
                  {{ resendCountdown }}s
                </span>
                <span
                  v-else-if="verificationState && verificationState.resends_remaining <= 0"
                  class="inline-block min-w-[60px] text-[var(--text-blue)] text-center text-[12px] leading-[16px] select-none opacity-50 transition-opacity"
                >
                  {{ t('No resends remaining') }}
                </span>
                <div
                  v-else
                  class="inline-flex min-w-[60px] justify-center items-center gap-[4px] text-[var(--text-blue)] text-[14px] font-[400] tracking-[0px] leading-[22px] select-none flex-1 cursor-pointer hover:opacity-80 active:opacity-70 duration-150"
                  @click="handleResendCode"
                >
                  {{ isResending ? t('Sending Code...') : t('Resend') }}
                </div>
              </div>
            </div>

            <div
              class="text-[13px] text-[var(--function-error)] leading-[18px] overflow-hidden transition-all duration-300 ease-out"
              :class="codeError ? 'opacity-100 max-h-[80px] mt-[2px]' : 'opacity-0 max-h-0 mt-0'"
            >
              {{ codeError }}
            </div>

            <div v-if="verificationMetaText.length > 0" class="mt-[4px] flex flex-col gap-[2px] text-[12px] leading-[16px] text-[var(--text-tertiary)]">
              <span v-for="line in verificationMetaText" :key="line">{{ line }}</span>
            </div>
          </div>

          <button
            type="submit"
            class="inline-flex items-center justify-center whitespace-nowrap font-medium transition-colors h-[40px] px-[16px] rounded-[10px] gap-[6px] text-sm min-w-16 w-full"
            :class="isCodeValid && !isLoading
              ? 'bg-[var(--Button-primary-black)] text-[var(--text-onblack)] hover:opacity-90 active:opacity-80'
              : 'bg-[var(--button-disabled-bg)] text-[var(--button-disabled-text)] cursor-not-allowed'"
            :disabled="!isCodeValid || isLoading"
          >
            <LoaderCircle v-if="isLoading" :size="16" class="animate-spin" />
            <span>{{ isLoading ? t('Verifying...') : t('Verify Email') }}</span>
          </button>
        </div>
      </div>
    </div>

    <div class="text-center text-[13px] leading-[18px] text-[var(--text-tertiary)] mt-[8px]">
      <span
        class="text-[var(--text-secondary)] cursor-pointer select-none hover:opacity-80 active:opacity-70 transition-all underline"
        @click="emits('backToForm')"
      >
        {{ t('Go Back') }}
      </span>
    </div>
  </form>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { LoaderCircle } from 'lucide-vue-next';
import { useAuth } from '@/api';
import { resendRegistrationCode, type VerificationState } from '@/api/auth';
import { getApiErrorCode, getApiErrorNumber } from '@/utils/apiError';
import { toEpochSeconds } from '@/utils/time';
import { showErrorToast, showSuccessToast } from '@/utils/toast';

const { t } = useI18n();

interface Props {
  email: string;
  verificationState: VerificationState | null;
}

const props = defineProps<Props>();

const emits = defineEmits<{
  success: [];
  backToForm: [];
}>();

const { verifyEmail, isLoading } = useAuth();

const verificationCode = ref('');
const codeError = ref('');
const attemptsRemaining = ref<number | null>(null);
const isResending = ref(false);
const verificationState = ref<VerificationState | null>(props.verificationState);
const nowSeconds = ref(Math.floor(Date.now() / 1000));

let timerId: number | null = null;

const isCodeValid = computed(() => /^\d{6}$/.test(verificationCode.value));

const resendCountdown = computed(() => {
  const resendAvailableAt = toEpochSeconds(verificationState.value?.resend_available_at);
  if (resendAvailableAt === null) {
    return 0;
  }
  return Math.max(resendAvailableAt - nowSeconds.value, 0);
});

const expiryCountdown = computed(() => {
  const expiresAt = toEpochSeconds(verificationState.value?.expires_at);
  if (expiresAt === null) {
    return 0;
  }
  return Math.max(expiresAt - nowSeconds.value, 0);
});

const formatDuration = (seconds: number) => {
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  return `${minutes}:${String(remainingSeconds).padStart(2, '0')}`;
};

const verificationMetaText = computed(() => {
  const lines: string[] = [];

  if (verificationState.value) {
    if (expiryCountdown.value > 0) {
      lines.push(t('Code expires in {time}', { time: formatDuration(expiryCountdown.value) }));
    } else {
      lines.push(t('Verification code expired. Request a new code and try again.'));
    }

    if (verificationState.value.resends_remaining > 0) {
      lines.push(t('Resends remaining: {count}', { count: verificationState.value.resends_remaining }));
    } else {
      lines.push(t('No resends remaining'));
    }
  }

  if (attemptsRemaining.value !== null) {
    lines.push(t('Attempts remaining: {count}', { count: attemptsRemaining.value }));
  }

  return lines;
});

const syncClock = () => {
  nowSeconds.value = Math.floor(Date.now() / 1000);
};

const handleCodeInput = (event: Event) => {
  const target = event.target as HTMLInputElement;
  verificationCode.value = target.value.replace(/\D/g, '').slice(0, 6);
  codeError.value = '';
};

const handlePaste = (event: ClipboardEvent) => {
  event.preventDefault();
  const paste = event.clipboardData?.getData('text') || '';
  verificationCode.value = paste.replace(/\D/g, '').slice(0, 6);
  codeError.value = '';
};

const handleResendCode = async () => {
  if (isResending.value) {
    return;
  }

  if (verificationState.value && (resendCountdown.value > 0 || verificationState.value.resends_remaining <= 0)) {
    return;
  }

  isResending.value = true;

  try {
    verificationState.value = await resendRegistrationCode({ email: props.email });
    attemptsRemaining.value = null;
    codeError.value = '';
    verificationCode.value = '';
    showSuccessToast(t('Verification code sent again'));
  } catch {
    showErrorToast(t('Failed to resend verification code. Please try again.'));
  } finally {
    isResending.value = false;
  }
};

const handleSubmit = async () => {
  if (!isCodeValid.value) {
    codeError.value = t('Verification code must be 6 digits');
    return;
  }

  try {
    await verifyEmail({
      email: props.email,
      verification_code: verificationCode.value,
    });

    showSuccessToast(t('Email verified successfully'));
    emits('success');
  } catch (error: unknown) {
    const errorCode = getApiErrorCode(error);
    attemptsRemaining.value = getApiErrorNumber(error, 'attempts_remaining');

    if (errorCode === 'code_invalid') {
      codeError.value = attemptsRemaining.value !== null
        ? t('Invalid verification code. {count} attempt(s) remaining.', { count: attemptsRemaining.value })
        : t('Invalid verification code');
    } else if (errorCode === 'code_expired') {
      codeError.value = t('Verification code expired. Request a new code and try again.');
    } else if (errorCode === 'code_attempts_exhausted') {
      codeError.value = t('Too many incorrect attempts. Request a new code and try again.');
    } else {
      showErrorToast(t('Verification failed, please try again'));
    }

    verificationCode.value = '';
  }
};

watch(
  () => props.verificationState,
  (nextState) => {
    verificationState.value = nextState;
    attemptsRemaining.value = null;
  },
);

onMounted(() => {
  timerId = window.setInterval(syncClock, 1000);
});

onUnmounted(() => {
  if (timerId !== null) {
    clearInterval(timerId);
    timerId = null;
  }
});
</script>
