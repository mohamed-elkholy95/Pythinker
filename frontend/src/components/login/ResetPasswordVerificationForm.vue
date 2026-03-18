<template>
  <div class="w-full max-w-[384px] py-[24px] pt-0 px-[12px] relative" style="z-index:1">
    <div class="flex flex-col justify-center gap-[40px] text-[var(--text-primary)] max-sm:gap-[12px]">
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
                    <span>{{ t('Verification code sent to') }} <b>{{ props.email }}</b></span>
                  </label>
                </div>
                <div class="w-full relative">
                  <input
                    id="verifyCode"
                    v-model="formData.verificationCode"
                    :placeholder="t('Enter 6-digit verification code')"
                    type="text"
                    maxlength="6"
                    pattern="[0-9]{6}"
                    inputmode="numeric"
                    :disabled="isLoading || isResending"
                    class="rounded-[10px] overflow-hidden text-sm leading-[22px] text-[var(--text-primary)] h-10 w-full disabled:cursor-not-allowed placeholder:text-[var(--text-disable)] bg-[var(--fill-input-chat)] pt-1 pb-1 pl-3 focus:ring-[1.5px] focus:ring-[var(--border-dark)] pr-[128px]"
                    :class="{ 'ring-1 ring-[var(--function-error)]': validationErrors.verificationCode }"
                    @input="handleVerificationCodeInput"
                    @blur="validateField('verificationCode')"
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
                  :class="validationErrors.verificationCode ? 'opacity-100 max-h-[80px] mt-[2px]' : 'opacity-0 max-h-0 mt-0'"
                >
                  {{ validationErrors.verificationCode }}
                </div>
                <div v-if="verificationMetaText.length > 0" class="mt-[4px] flex flex-col gap-[2px] text-[12px] leading-[16px] text-[var(--text-tertiary)]">
                  <span v-for="line in verificationMetaText" :key="line">{{ line }}</span>
                </div>
              </div>

              <div class="flex flex-col items-start">
                <div class="w-full flex items-center justify-between gap-[12px] mb-[8px]">
                  <label
                    for="new-password"
                    class="text-[13px] text-[var(--text-primary)] font-medium after:content-[&quot;*&quot;] after:text-[var(--function-error)] after:ml-[4px]"
                  >
                    <span>{{ t('New Password') }}</span>
                  </label>
                </div>
                <div class="relative w-full">
                  <input
                    id="new-password"
                    v-model="formData.newPassword"
                    :placeholder="t('Enter your new password')"
                    :type="showNewPassword ? 'text' : 'password'"
                    :disabled="isLoading || isPolicyLoading"
                    class="rounded-[10px] overflow-hidden text-sm leading-[22px] text-[var(--text-primary)] h-10 disabled:cursor-not-allowed placeholder:text-[var(--text-disable)] bg-[var(--fill-input-chat)] pt-1 pr-10 pb-1 pl-3 focus:ring-[1.5px] focus:ring-[var(--border-dark)] w-full"
                    :class="{ 'ring-1 ring-[var(--function-error)]': validationErrors.newPassword }"
                    @input="validateField('newPassword')"
                    @blur="validateField('newPassword')"
                  >
                  <button
                    type="button"
                    class="absolute right-2 top-1/2 transform -translate-y-1/2 p-1 text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] transition-colors"
                    @click="showNewPassword = !showNewPassword"
                  >
                    <Eye v-if="showNewPassword" :size="16" />
                    <EyeOff v-else :size="16" />
                  </button>
                </div>

                <div v-if="passwordPolicy" class="mt-[6px] flex flex-col gap-[2px] transition-all duration-300 ease-out">
                  <div
                    v-for="requirement in passwordRequirements"
                    :key="requirement.key"
                    class="flex items-center gap-[6px] text-[12px] leading-[16px] transition-colors duration-200"
                    :class="requirement.met ? 'text-[var(--function-success,#22c55e)]' : 'text-[var(--text-tertiary)]'"
                  >
                    <Check v-if="requirement.met" :size="12" />
                    <X v-else :size="12" class="opacity-40" />
                    <span>{{ requirement.label }}</span>
                  </div>
                </div>

                <div
                  class="text-[13px] leading-[18px] overflow-hidden transition-all duration-300 ease-out"
                  :class="passwordHintMessage ? 'opacity-100 max-h-[60px] mt-[4px] text-[var(--function-error)]' : 'opacity-0 max-h-0 mt-0'"
                >
                  {{ passwordHintMessage }}
                </div>
              </div>

              <div class="flex flex-col items-start">
                <div class="w-full flex items-center justify-between gap-[12px] mb-[8px]">
                  <label
                    for="confirm-password"
                    class="text-[13px] text-[var(--text-primary)] font-medium after:content-[&quot;*&quot;] after:text-[var(--function-error)] after:ml-[4px]"
                  >
                    <span>{{ t('Confirm Password') }}</span>
                  </label>
                </div>
                <div class="relative w-full">
                  <input
                    id="confirm-password"
                    v-model="formData.confirmPassword"
                    :placeholder="t('Confirm your new password')"
                    :type="showConfirmPassword ? 'text' : 'password'"
                    :disabled="isLoading"
                    class="rounded-[10px] overflow-hidden text-sm leading-[22px] text-[var(--text-primary)] h-10 disabled:cursor-not-allowed placeholder:text-[var(--text-disable)] bg-[var(--fill-input-chat)] pt-1 pr-10 pb-1 pl-3 focus:ring-[1.5px] focus:ring-[var(--border-dark)] w-full"
                    :class="{ 'ring-1 ring-[var(--function-error)]': validationErrors.confirmPassword }"
                    @input="validateField('confirmPassword')"
                    @blur="validateField('confirmPassword')"
                  >
                  <button
                    type="button"
                    class="absolute right-2 top-1/2 transform -translate-y-1/2 p-1 text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] transition-colors"
                    @click="showConfirmPassword = !showConfirmPassword"
                  >
                    <Eye v-if="showConfirmPassword" :size="16" />
                    <EyeOff v-else :size="16" />
                  </button>
                </div>
                <div
                  class="text-[13px] text-[var(--function-error)] leading-[18px] overflow-hidden transition-all duration-300 ease-out"
                  :class="validationErrors.confirmPassword ? 'opacity-100 max-h-[60px] mt-[2px]' : 'opacity-0 max-h-0 mt-0'"
                >
                  {{ validationErrors.confirmPassword }}
                </div>
              </div>

              <button
                type="submit"
                class="inline-flex items-center justify-center whitespace-nowrap font-medium transition-colors h-[40px] px-[16px] rounded-[10px] gap-[6px] text-sm min-w-16 w-full"
                :class="isFormValid && !isLoading
                  ? 'bg-[var(--Button-primary-black)] text-[var(--text-onblack)] hover:opacity-90 active:opacity-80'
                  : 'bg-[var(--button-disabled-bg)] text-[var(--button-disabled-text)] cursor-not-allowed'"
                :disabled="!isFormValid || isLoading"
              >
                <LoaderCircle v-if="isLoading" :size="16" class="animate-spin" />
                <span>{{ isLoading ? t('Updating...') : t('Update Password') }}</span>
              </button>
            </div>
          </div>
        </div>

        <div class="flex flex-col gap-[8px] text-center text-[13px] leading-[18px] text-[var(--text-tertiary)] mt-[8px]">
          <div>
            <span>{{ isPasswordUpdated ? t('Ready to login?') : t('Want to try a different email?') }}</span>
            <span
              class="ms-[8px] text-[var(--text-secondary)] cursor-pointer select-none hover:opacity-80 active:opacity-70 transition-all underline"
              @click="handleBackAction"
            >
              {{ isPasswordUpdated ? t('Back to Login') : t('Go Back') }}
            </span>
          </div>
        </div>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { Check, Eye, EyeOff, LoaderCircle, X } from 'lucide-vue-next';
import { getCachedPasswordPolicy, resetPassword, sendVerificationCode, type PasswordPolicy, type VerificationState } from '@/api/auth';
import { getApiErrorCode, getApiErrorNumber } from '@/utils/apiError';
import { evaluatePasswordPolicy } from '@/utils/passwordPolicy';
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
  backToEmail: [];
  backToLogin: [];
}>();

const isLoading = ref(false);
const isResending = ref(false);
const isPasswordUpdated = ref(false);
const showNewPassword = ref(false);
const showConfirmPassword = ref(false);
const isPolicyLoading = ref(true);
const passwordPolicy = ref<PasswordPolicy | null>(null);
const verificationState = ref<VerificationState | null>(props.verificationState);
const attemptsRemaining = ref<number | null>(null);
const nowSeconds = ref(Math.floor(Date.now() / 1000));

let timerId: number | null = null;
let successRedirectTimer: number | null = null;

const formData = ref({
  verificationCode: '',
  newPassword: '',
  confirmPassword: '',
});

const validationErrors = ref<Record<string, string>>({});

const passwordEvaluation = computed(() => {
  if (!passwordPolicy.value) {
    return {
      isValid: false,
      requirements: [],
      summary: '',
    };
  }
  return evaluatePasswordPolicy(formData.value.newPassword, passwordPolicy.value, t);
});

const passwordRequirements = computed(() => passwordEvaluation.value.requirements);

const passwordPolicyError = computed(() => {
  if (isPolicyLoading.value || passwordPolicy.value) {
    return '';
  }
  return t('Password requirements are unavailable. Please refresh and try again.');
});

const passwordHintMessage = computed(() => {
  return validationErrors.value.newPassword ?? passwordPolicyError.value;
});

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

const isFormValid = computed(() => {
  return Boolean(
    !isLoading.value
    && !isPasswordUpdated.value
    && !isPolicyLoading.value
    && passwordPolicy.value
    && formData.value.verificationCode.trim()
    && formData.value.newPassword.trim()
    && formData.value.confirmPassword.trim()
    && passwordEvaluation.value.isValid
    && Object.keys(validationErrors.value).length === 0,
  );
});

const formatDuration = (seconds: number) => {
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  return `${minutes}:${String(remainingSeconds).padStart(2, '0')}`;
};

const formatVerificationCode = (value: string) => {
  return value.replace(/\D/g, '').slice(0, 6);
};

const handleVerificationCodeInput = (event: Event) => {
  const target = event.target as HTMLInputElement;
  formData.value.verificationCode = formatVerificationCode(target.value);
  validateField('verificationCode');
};

const handlePaste = (event: ClipboardEvent) => {
  event.preventDefault();
  const paste = event.clipboardData?.getData('text') || '';
  formData.value.verificationCode = formatVerificationCode(paste);
  validateField('verificationCode');
};

const validateField = (field: string) => {
  const errors: Record<string, string> = {};

  if (field === 'verificationCode') {
    if (!formData.value.verificationCode.trim()) {
      errors.verificationCode = t('Verification code is required');
    } else if (!/^\d{6}$/.test(formData.value.verificationCode.trim())) {
      errors.verificationCode = t('Verification code must be 6 digits');
    }
  }

  if (field === 'newPassword') {
    if (!formData.value.newPassword) {
      errors.newPassword = t('Password is required');
    } else if (!passwordPolicy.value) {
      errors.newPassword = t('Password requirements are unavailable. Please refresh and try again.');
    } else if (!passwordEvaluation.value.isValid) {
      errors.newPassword = passwordEvaluation.value.summary;
    }
  }

  if (field === 'confirmPassword') {
    if (!formData.value.confirmPassword.trim()) {
      errors.confirmPassword = t('Please confirm your password');
    } else if (formData.value.newPassword !== formData.value.confirmPassword) {
      errors.confirmPassword = t('Passwords do not match');
    }
  }

  Object.keys(errors).forEach((key) => {
    validationErrors.value[key] = errors[key];
  });

  if (!errors[field]) {
    delete validationErrors.value[field];
  }
};

const validateForm = () => {
  validateField('verificationCode');
  validateField('newPassword');
  validateField('confirmPassword');
  return Object.keys(validationErrors.value).length === 0;
};

const syncClock = () => {
  nowSeconds.value = Math.floor(Date.now() / 1000);
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
    verificationState.value = await sendVerificationCode({ email: props.email });
    attemptsRemaining.value = null;
    delete validationErrors.value.verificationCode;
    formData.value.verificationCode = '';
    showSuccessToast(t('Verification code sent again'));
  } catch {
    showErrorToast(t('Failed to resend verification code. Please try again.'));
  } finally {
    isResending.value = false;
  }
};

const handleSubmit = async () => {
  if (!validateForm()) {
    return;
  }

  isLoading.value = true;

  try {
    await resetPassword({
      email: props.email,
      verification_code: formData.value.verificationCode,
      new_password: formData.value.newPassword,
    });

    isPasswordUpdated.value = true;
    showSuccessToast(t('Password updated successfully'));

    successRedirectTimer = window.setTimeout(() => {
      if (isPasswordUpdated.value) {
        emits('success');
      }
    }, 500);
  } catch (error: unknown) {
    const errorCode = getApiErrorCode(error);
    attemptsRemaining.value = getApiErrorNumber(error, 'attempts_remaining');

    if (errorCode === 'code_invalid') {
      validationErrors.value.verificationCode = attemptsRemaining.value !== null
        ? t('Invalid verification code. {count} attempt(s) remaining.', { count: attemptsRemaining.value })
        : t('Invalid verification code');
    } else if (errorCode === 'code_expired') {
      validationErrors.value.verificationCode = t('Verification code expired. Request a new code and try again.');
    } else if (errorCode === 'code_attempts_exhausted') {
      validationErrors.value.verificationCode = t('Too many incorrect attempts. Request a new code and try again.');
    } else {
      showErrorToast(t('Failed to update password. Please try again.'));
    }
  } finally {
    isLoading.value = false;
  }
};

const handleBackAction = () => {
  if (isPasswordUpdated.value) {
    emits('backToLogin');
  } else {
    emits('backToEmail');
  }
};

watch(() => formData.value.newPassword, () => {
  if (formData.value.newPassword || validationErrors.value.newPassword) {
    validateField('newPassword');
  }
  if (formData.value.confirmPassword) {
    validateField('confirmPassword');
  }
});

watch(
  () => props.verificationState,
  (nextState) => {
    verificationState.value = nextState;
    attemptsRemaining.value = null;
  },
);

onMounted(async () => {
  passwordPolicy.value = await getCachedPasswordPolicy();
  isPolicyLoading.value = false;
  timerId = window.setInterval(syncClock, 1000);
});

onUnmounted(() => {
  if (timerId !== null) {
    clearInterval(timerId);
    timerId = null;
  }
  if (successRedirectTimer !== null) {
    clearTimeout(successRedirectTimer);
    successRedirectTimer = null;
  }
});

defineExpose({
  clearForm: () => {
    formData.value = {
      verificationCode: '',
      newPassword: '',
      confirmPassword: '',
    };
    validationErrors.value = {};
    isPasswordUpdated.value = false;
    attemptsRemaining.value = null;
  },
});
</script>
