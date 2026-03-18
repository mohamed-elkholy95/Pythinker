<template>
  <Dialog v-model:open="open">
    <DialogContent class="bg-[var(--background-menu-white)] w-[480px]">
      <DialogHeader>
        <DialogTitle>{{ t('Update Password') }}</DialogTitle>
      </DialogHeader>

      <div class="pt-[12px] px-[24px] pb-[24px]">
        <form class="flex flex-col items-stretch gap-[12px]">
          <label class="flex flex-col gap-[8px]">
            <div class="text-[16px] text-[var(--text-secondary)] leading-[24px]">{{ t('Current Password') }}</div>
            <div class="relative w-full">
              <input
                v-model="currentPassword"
                :placeholder="t('Enter current password')"
                :type="showCurrentPassword ? 'text' : 'password'"
                class="rounded-[10px] overflow-hidden text-sm leading-[22px] text-[var(--text-primary)] h-10 w-full disabled:cursor-not-allowed placeholder:text-[var(--text-disable)] pt-1 pb-1 pl-3 focus:ring-[1.5px] focus:ring-[var(--border-dark)] min-h-[48px] bg-[var(--fill-tsp-white-dark)] pr-[48px]"
              >
              <button
                type="button"
                class="text-[var(--icon-tertiary)] absolute z-30 top-[50%] p-[6px] rounded-md transform -translate-y-1/2 cursor-pointer hover:text-[--icon-primary] active:opacity-90 transition-all right-[10px]"
                @click="showCurrentPassword = !showCurrentPassword"
              >
                <Eye v-if="showCurrentPassword" :size="18" />
                <EyeOff v-else :size="18" />
              </button>
            </div>
          </label>

          <label class="flex flex-col gap-[8px]">
            <div class="text-[16px] text-[var(--text-secondary)] leading-[24px]">{{ t('New Password') }}</div>
            <div class="relative w-full">
              <input
                v-model="newPassword"
                :placeholder="t('Enter new password')"
                :type="showNewPassword ? 'text' : 'password'"
                :disabled="isLoading || isPolicyLoading"
                class="rounded-[10px] overflow-hidden text-sm leading-[22px] text-[var(--text-primary)] h-10 w-full disabled:cursor-not-allowed placeholder:text-[var(--text-disable)] pt-1 pb-1 pl-3 focus:ring-[1.5px] focus:ring-[var(--border-dark)] min-h-[48px] bg-[var(--fill-tsp-white-dark)] pr-[48px]"
              >
              <button
                type="button"
                class="text-[var(--icon-tertiary)] absolute z-30 top-[50%] p-[6px] rounded-md transform -translate-y-1/2 cursor-pointer hover:text-[--icon-primary] active:opacity-90 transition-all right-[10px]"
                @click="showNewPassword = !showNewPassword"
              >
                <Eye v-if="showNewPassword" :size="18" />
                <EyeOff v-else :size="18" />
              </button>
            </div>

            <div v-if="passwordPolicy" class="flex flex-col gap-[2px] text-[12px] leading-[16px]">
              <div
                v-for="requirement in passwordRequirements"
                :key="requirement.key"
                class="flex items-center gap-[6px]"
                :class="requirement.met ? 'text-[var(--function-success,#22c55e)]' : 'text-[var(--text-tertiary)]'"
              >
                <Check v-if="requirement.met" :size="12" />
                <X v-else :size="12" class="opacity-40" />
                <span>{{ requirement.label }}</span>
              </div>
            </div>

            <div v-if="passwordHintMessage" class="text-[13px] text-[var(--function-error)] leading-[18px]">
              {{ passwordHintMessage }}
            </div>
          </label>

          <label class="flex flex-col gap-[8px]">
            <div class="text-[16px] text-[var(--text-secondary)] leading-[24px]">{{ t('Confirm New Password') }}</div>
            <div class="relative w-full">
              <input
                v-model="confirmPassword"
                :placeholder="t('Enter new password again')"
                :type="showConfirmPassword ? 'text' : 'password'"
                class="rounded-[10px] overflow-hidden text-sm leading-[22px] text-[var(--text-primary)] h-10 w-full disabled:cursor-not-allowed placeholder:text-[var(--text-disable)] pt-1 pb-1 pl-3 focus:ring-[1.5px] focus:ring-[var(--border-dark)] min-h-[48px] bg-[var(--fill-tsp-white-dark)] pr-[48px]"
              >
              <button
                type="button"
                class="text-[var(--icon-tertiary)] absolute z-30 top-[50%] p-[6px] rounded-md transform -translate-y-1/2 cursor-pointer hover:text-[--icon-primary] active:opacity-90 transition-all right-[10px]"
                @click="showConfirmPassword = !showConfirmPassword"
              >
                <Eye v-if="showConfirmPassword" :size="18" />
                <EyeOff v-else :size="18" />
              </button>
            </div>
            <div v-if="confirmError" class="text-[13px] text-[var(--function-error)] leading-[18px]">
              {{ confirmError }}
            </div>
          </label>
        </form>

        <DialogFooter>
          <DialogClose as-child>
            <button
              type="button"
              class="inline-flex items-center justify-center whitespace-nowrap font-medium transition-colors hover:opacity-90 active:opacity-80 bg-[var(--Button-secondary-gray)] text-[var(--text-primary)] h-[36px] px-[12px] rounded-[10px] gap-[6px] text-sm min-w-[100px] min-h-[40px]"
            >
              {{ t('Cancel') }}
            </button>
          </DialogClose>
          <button
            type="button"
            class="inline-flex items-center justify-center whitespace-nowrap font-medium transition-colors bg-[var(--Button-primary-black)] text-[var(--text-onblack)] h-[36px] px-[12px] rounded-[10px] gap-[6px] text-sm min-w-[100px] min-h-[40px]"
            :class="{ 'opacity-50 cursor-not-allowed hover:opacity-50 active:opacity-50': !isFormValid }"
            :disabled="!isFormValid"
            @click="handleSubmit"
          >
            <LoaderCircle v-if="isLoading" :size="16" class="animate-spin" />
            <span v-else>{{ t('Confirm') }}</span>
            <span v-if="isLoading">{{ t('Processing...') }}</span>
          </button>
        </DialogFooter>
      </div>
    </DialogContent>
  </Dialog>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { Check, Eye, EyeOff, LoaderCircle, X } from 'lucide-vue-next';
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { changePassword, getCachedPasswordPolicy, type PasswordPolicy } from '@/api/auth';
import { getApiErrorMessage } from '@/utils/apiError';
import { evaluatePasswordPolicy } from '@/utils/passwordPolicy';
import { showErrorToast, showSuccessToast } from '@/utils/toast';

const { t } = useI18n();

const open = ref(false);
const isLoading = ref(false);
const isPolicyLoading = ref(true);
const passwordPolicy = ref<PasswordPolicy | null>(null);

const currentPassword = ref('');
const newPassword = ref('');
const confirmPassword = ref('');

const showCurrentPassword = ref(false);
const showNewPassword = ref(false);
const showConfirmPassword = ref(false);

const passwordEvaluation = computed(() => {
  if (!passwordPolicy.value) {
    return {
      isValid: false,
      requirements: [],
      summary: '',
    };
  }
  return evaluatePasswordPolicy(newPassword.value, passwordPolicy.value, t);
});

const passwordRequirements = computed(() => passwordEvaluation.value.requirements);

const passwordPolicyError = computed(() => {
  if (isPolicyLoading.value || passwordPolicy.value) {
    return '';
  }
  return t('Password requirements are unavailable. Please refresh and try again.');
});

const passwordHintMessage = computed(() => {
  if (!passwordPolicy.value) {
    return passwordPolicyError.value;
  }
  if (!newPassword.value) {
    return '';
  }
  return passwordEvaluation.value.isValid ? '' : passwordEvaluation.value.summary;
});

const confirmError = computed(() => {
  if (!confirmPassword.value) {
    return '';
  }
  return newPassword.value === confirmPassword.value ? '' : t('Passwords do not match');
});

const isFormValid = computed(() => {
  return Boolean(
    !isLoading.value
    && !isPolicyLoading.value
    && passwordPolicy.value
    && currentPassword.value.trim()
    && newPassword.value.trim()
    && confirmPassword.value.trim()
    && passwordEvaluation.value.isValid
    && !confirmError.value,
  );
});

const loadPasswordPolicy = async () => {
  isPolicyLoading.value = true;
  passwordPolicy.value = await getCachedPasswordPolicy();
  isPolicyLoading.value = false;
};

const resetForm = () => {
  currentPassword.value = '';
  newPassword.value = '';
  confirmPassword.value = '';
  showCurrentPassword.value = false;
  showNewPassword.value = false;
  showConfirmPassword.value = false;
  isLoading.value = false;
};

const handleSubmit = async () => {
  if (!isFormValid.value) {
    return;
  }

  isLoading.value = true;

  try {
    await changePassword({
      old_password: currentPassword.value,
      new_password: newPassword.value,
    });

    showSuccessToast(t('Password change successful'));
    resetForm();
    open.value = false;
  } catch (error: unknown) {
    showErrorToast(getApiErrorMessage(error) || t('Password change failed'));
  } finally {
    isLoading.value = false;
  }
};

watch(open, (isOpen) => {
  if (isOpen) {
    void loadPasswordPolicy();
  } else {
    resetForm();
  }
});

onMounted(() => {
  void loadPasswordPolicy();
});

defineExpose({
  open: () => {
    resetForm();
    open.value = true;
    void loadPasswordPolicy();
  },
  close: () => {
    resetForm();
    open.value = false;
  },
});
</script>
