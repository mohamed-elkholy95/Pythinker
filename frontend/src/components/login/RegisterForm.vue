<template>
  <div class="w-full max-w-[384px] py-[24px] pt-0 px-[12px] relative" style="z-index:1">
    <div class="flex flex-col justify-center gap-[40px] text-[var(--text-primary)] max-sm:gap-[12px]">
      <RegisterVerificationForm
        v-if="currentStep === 'verification'"
        :email="registeredEmail"
        :verification-state="verificationState"
        @success="emits('success')"
        @back-to-form="currentStep = 'form'"
      />

      <form v-else @submit.prevent="handleSubmit" class="flex flex-col items-stretch gap-[20px]">
        <div class="relative">
          <div class="transition-all duration-500 ease-out opacity-100 scale-100">
            <div class="flex flex-col gap-[12px]">
              <div class="flex flex-col items-start">
                <div class="w-full flex items-center justify-between gap-[12px] mb-[8px]">
                  <label
                    for="fullname"
                    class="text-[13px] text-[var(--text-primary)] font-medium after:content-[&quot;*&quot;] after:text-[var(--function-error)] after:ml-[4px]"
                  >
                    <span>{{ t('Full Name') }}</span>
                  </label>
                </div>
                <input
                  id="fullname"
                  v-model="formData.fullname"
                  :placeholder="t('Enter your full name')"
                  :disabled="isLoading"
                  class="rounded-[10px] overflow-hidden text-sm leading-[22px] text-[var(--text-primary)] h-10 disabled:cursor-not-allowed placeholder:text-[var(--text-disable)] bg-[var(--fill-input-chat)] pt-1 pr-1.5 pb-1 pl-3 focus:ring-[1.5px] focus:ring-[var(--border-dark)] w-full"
                  :class="{ 'ring-1 ring-[var(--function-error)]': validationErrors.fullname }"
                  @input="validateField('fullname')"
                  @blur="validateField('fullname')"
                >
                <div
                  class="text-[13px] text-[var(--function-error)] leading-[18px] overflow-hidden transition-all duration-300 ease-out"
                  :class="validationErrors.fullname ? 'opacity-100 max-h-[60px] mt-[2px]' : 'opacity-0 max-h-0 mt-0'"
                >
                  {{ validationErrors.fullname }}
                </div>
              </div>

              <div class="flex flex-col items-start">
                <div class="w-full flex items-center justify-between gap-[12px] mb-[8px]">
                  <label
                    for="email"
                    class="text-[13px] text-[var(--text-primary)] font-medium after:content-[&quot;*&quot;] after:text-[var(--function-error)] after:ml-[4px]"
                  >
                    <span>{{ t('Email') }}</span>
                  </label>
                </div>
                <input
                  id="email"
                  v-model="formData.email"
                  placeholder="mail@domain.com"
                  type="email"
                  :disabled="isLoading"
                  class="rounded-[10px] overflow-hidden text-sm leading-[22px] text-[var(--text-primary)] h-10 disabled:cursor-not-allowed placeholder:text-[var(--text-disable)] bg-[var(--fill-input-chat)] pt-1 pr-1.5 pb-1 pl-3 focus:ring-[1.5px] focus:ring-[var(--border-dark)] w-full"
                  :class="{ 'ring-1 ring-[var(--function-error)]': validationErrors.email }"
                  @input="validateField('email')"
                  @blur="validateField('email')"
                >
                <div
                  class="text-[13px] text-[var(--function-error)] leading-[18px] overflow-hidden transition-all duration-300 ease-out"
                  :class="validationErrors.email ? 'opacity-100 max-h-[60px] mt-[2px]' : 'opacity-0 max-h-0 mt-0'"
                >
                  {{ validationErrors.email }}
                </div>
              </div>

              <div class="flex flex-col items-start">
                <div class="w-full flex items-center justify-between gap-[12px] mb-[8px]">
                  <label
                    for="password"
                    class="text-[13px] text-[var(--text-primary)] font-medium after:content-[&quot;*&quot;] after:text-[var(--function-error)] after:ml-[4px]"
                  >
                    <span>{{ t('Password') }}</span>
                  </label>
                </div>
                <div class="relative w-full">
                  <input
                    id="password"
                    v-model="formData.password"
                    :placeholder="t('Enter password')"
                    :type="showPassword ? 'text' : 'password'"
                    :disabled="isLoading || isPolicyLoading"
                    class="rounded-[10px] overflow-hidden text-sm leading-[22px] text-[var(--text-primary)] h-10 w-full disabled:cursor-not-allowed placeholder:text-[var(--text-disable)] bg-[var(--fill-input-chat)] pt-1 pb-1 pl-3 focus:ring-[1.5px] focus:ring-[var(--border-dark)] pr-[40px]"
                    :class="{ 'ring-1 ring-[var(--function-error)]': validationErrors.password }"
                    @input="validateField('password')"
                    @blur="validateField('password')"
                  >
                  <div
                    class="text-[var(--icon-tertiary)] absolute z-30 right-[6px] top-[50%] p-[6px] rounded-md transform -translate-y-1/2 cursor-pointer hover:text-[--icon-primary] active:opacity-90 transition-all"
                    @click="showPassword = !showPassword"
                  >
                    <Eye v-if="showPassword" :size="16" />
                    <EyeOff v-else :size="16" />
                  </div>
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
                    for="confirmPassword"
                    class="text-[13px] text-[var(--text-primary)] font-medium after:content-[&quot;*&quot;] after:text-[var(--function-error)] after:ml-[4px]"
                  >
                    <span>{{ t('Confirm Password') }}</span>
                  </label>
                </div>
                <div class="relative w-full">
                  <input
                    id="confirmPassword"
                    v-model="formData.confirmPassword"
                    :placeholder="t('Enter password again')"
                    :type="showConfirmPassword ? 'text' : 'password'"
                    :disabled="isLoading"
                    class="rounded-[10px] overflow-hidden text-sm leading-[22px] text-[var(--text-primary)] h-10 w-full disabled:cursor-not-allowed placeholder:text-[var(--text-disable)] bg-[var(--fill-input-chat)] pt-1 pb-1 pl-3 focus:ring-[1.5px] focus:ring-[var(--border-dark)] pr-[40px]"
                    :class="{ 'ring-1 ring-[var(--function-error)]': validationErrors.confirmPassword }"
                    @input="validateField('confirmPassword')"
                    @blur="validateField('confirmPassword')"
                  >
                  <div
                    class="text-[var(--icon-tertiary)] absolute z-30 right-[6px] top-[50%] p-[6px] rounded-md transform -translate-y-1/2 cursor-pointer hover:text-[--icon-primary] active:opacity-90 transition-all"
                    @click="showConfirmPassword = !showConfirmPassword"
                  >
                    <Eye v-if="showConfirmPassword" :size="16" />
                    <EyeOff v-else :size="16" />
                  </div>
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
                <span>{{ isLoading ? t('Processing...') : t('Register') }}</span>
              </button>
            </div>
          </div>
        </div>

        <div class="text-center text-[13px] leading-[18px] text-[var(--text-tertiary)] mt-[8px]">
          <span>{{ t('Already have an account?') }}</span>
          <span
            class="ms-[8px] text-[var(--text-secondary)] cursor-pointer select-none hover:opacity-80 active:opacity-70 transition-all underline"
            @click="emits('switchToLogin')"
          >
            {{ t('Login') }}
          </span>
        </div>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { Check, Eye, EyeOff, LoaderCircle, X } from 'lucide-vue-next';
import { useAuth } from '@/api';
import { getCachedPasswordPolicy, type PasswordPolicy, type VerificationState } from '@/api/auth';
import { validateUserInput } from '@/utils/auth';
import { getApiErrorMessage } from '@/utils/apiError';
import { evaluatePasswordPolicy } from '@/utils/passwordPolicy';
import { showErrorToast } from '@/utils/toast';
import RegisterVerificationForm from './RegisterVerificationForm.vue';

const { t } = useI18n();

const emits = defineEmits<{
  success: [];
  switchToLogin: [];
}>();

const { register, isLoading } = useAuth();

const currentStep = ref<'form' | 'verification'>('form');
const registeredEmail = ref('');
const verificationState = ref<VerificationState | null>(null);

const showPassword = ref(false);
const showConfirmPassword = ref(false);
const isPolicyLoading = ref(true);
const passwordPolicy = ref<PasswordPolicy | null>(null);

const formData = ref({
  fullname: '',
  email: '',
  password: '',
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
  return evaluatePasswordPolicy(formData.value.password, passwordPolicy.value, t);
});

const passwordRequirements = computed(() => passwordEvaluation.value.requirements);

const passwordPolicyError = computed(() => {
  if (isPolicyLoading.value || passwordPolicy.value) {
    return '';
  }
  return t('Password requirements are unavailable. Please refresh and try again.');
});

const passwordHintMessage = computed(() => {
  return validationErrors.value.password ?? passwordPolicyError.value;
});

// TODO: Backend registration validation errors arrive as plain `msg` strings
// (from Pydantic ValidationError), not structured error_code values. These
// substring matches are fragile and will break if wording changes. Migrate to
// structured error codes on the backend when feasible.
const getErrorMessage = (error: unknown): string => {
  const raw = getApiErrorMessage(error).toLowerCase();

  if (raw.includes('email already exists')) return t('This email is already registered. Try logging in instead.');
  if (raw.includes('at least')) return t('Password is too short. Use at least 9 characters.');
  if (raw.includes('no more than')) return t('Password is too long. Use 128 characters or fewer.');
  if (raw.includes('uppercase')) return t('Password must include at least 1 uppercase letter.');
  if (raw.includes('lowercase')) return t('Password must include at least 1 lowercase letter.');
  if (raw.includes('digit')) return t('Password must include at least 1 number.');
  if (raw.includes('symbol')) return t('Password must include at least 1 symbol.');
  if (raw.includes('full name')) return t('Please enter your full name (at least 2 characters).');
  if (raw.includes('valid email')) return t('Please enter a valid email address.');
  if (raw.includes('email configuration')) return t('Email service is temporarily unavailable. Please try again later.');

  return getApiErrorMessage(error) || t('Registration failed. Please check your details and try again.');
};

const clearForm = () => {
  formData.value = {
    fullname: '',
    email: '',
    password: '',
    confirmPassword: '',
  };
  validationErrors.value = {};
  currentStep.value = 'form';
  registeredEmail.value = '';
  verificationState.value = null;
};

const validateField = (field: string) => {
  const errors: Record<string, string> = {};

  if (field === 'fullname') {
    const result = validateUserInput({ fullname: formData.value.fullname });
    if (result.errors.fullname) {
      errors.fullname = result.errors.fullname;
    }
  }

  if (field === 'email') {
    const result = validateUserInput({ email: formData.value.email });
    if (result.errors.email) {
      errors.email = result.errors.email;
    }
  }

  if (field === 'password') {
    if (!formData.value.password) {
      errors.password = t('Password is required');
    } else if (!passwordPolicy.value) {
      errors.password = t('Password requirements are unavailable. Please refresh and try again.');
    } else if (!passwordEvaluation.value.isValid) {
      errors.password = passwordEvaluation.value.summary;
    }
  }

  if (field === 'confirmPassword') {
    if (formData.value.password !== formData.value.confirmPassword) {
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
  const result = validateUserInput({
    fullname: formData.value.fullname,
    email: formData.value.email,
  });

  validationErrors.value = { ...result.errors };

  if (!formData.value.password) {
    validationErrors.value.password = t('Password is required');
  } else if (!passwordPolicy.value) {
    validationErrors.value.password = t('Password requirements are unavailable. Please refresh and try again.');
  } else if (!passwordEvaluation.value.isValid) {
    validationErrors.value.password = passwordEvaluation.value.summary;
  }

  if (formData.value.password !== formData.value.confirmPassword) {
    validationErrors.value.confirmPassword = t('Passwords do not match');
  }

  return Object.keys(validationErrors.value).length === 0;
};

const isFormValid = computed(() => {
  const hasRequiredFields = formData.value.fullname.trim()
    && formData.value.email.trim()
    && formData.value.password.trim()
    && formData.value.confirmPassword.trim();

  return Boolean(
    hasRequiredFields
    && !isPolicyLoading.value
    && passwordPolicy.value
    && passwordEvaluation.value.isValid
    && Object.keys(validationErrors.value).length === 0,
  );
});

const handleSubmit = async () => {
  if (!validateForm()) {
    return;
  }

  try {
    const response = await register({
      fullname: formData.value.fullname,
      email: formData.value.email,
      password: formData.value.password,
    });

    registeredEmail.value = formData.value.email;
    verificationState.value = response.verification_state;
    currentStep.value = 'verification';
  } catch (error: unknown) {
    showErrorToast(getErrorMessage(error));
  }
};

onMounted(async () => {
  passwordPolicy.value = await getCachedPasswordPolicy();
  isPolicyLoading.value = false;
});

watch(() => formData.value.password, () => {
  if (formData.value.password || validationErrors.value.password) {
    validateField('password');
  }
  if (formData.value.confirmPassword) {
    validateField('confirmPassword');
  }
});

defineExpose({
  clearForm,
});
</script>
