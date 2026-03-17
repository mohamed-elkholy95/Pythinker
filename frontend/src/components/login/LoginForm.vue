<template>
  <div class="w-full max-w-[384px] py-[24px] pt-0 px-[12px] relative" style="z-index:1">
    <div class="flex flex-col justify-center gap-[40px] text-[var(--text-primary)] max-sm:gap-[12px]">
      <form @submit.prevent="handleSubmit" class="flex flex-col items-stretch gap-[20px]">
        <div class="relative">
          <div class="transition-all duration-500 ease-out opacity-100 scale-100">
            <div class="flex flex-col gap-[12px]">

              <!-- TOTP Step -->
              <template v-if="showTotpStep">
                <div class="flex flex-col items-center gap-[8px] mb-[4px]">
                  <div class="w-[48px] h-[48px] rounded-full bg-[var(--fill-blue)] flex items-center justify-center">
                    <ShieldCheck :size="24" class="text-[var(--text-brand)]" />
                  </div>
                  <p class="text-[13px] text-[var(--text-secondary)] text-center leading-[18px]">
                    {{ t('Enter the 6-digit code from your authenticator app') }}
                  </p>
                </div>

                <!-- OTP Input -->
                <div class="flex flex-col items-start">
                  <label for="totp_code"
                    class="text-[13px] text-[var(--text-primary)] font-medium mb-[8px]">
                    <span>{{ t('Verification Code') }}</span>
                  </label>
                  <input v-model="totpCode" ref="totpInputRef"
                    class="rounded-[10px] overflow-hidden text-sm leading-[22px] text-[var(--text-primary)] h-10 disabled:cursor-not-allowed placeholder:text-[var(--text-disable)] bg-[var(--fill-input-chat)] pt-1 pr-1.5 pb-1 pl-3 focus:ring-[1.5px] focus:ring-[var(--border-dark)] w-full text-center tracking-[0.3em] font-mono text-[18px]"
                    id="totp_code" name="totp_code" autocomplete="one-time-code" inputmode="numeric"
                    placeholder="000000" maxlength="6"
                    :disabled="isLoading"
                    @input="onTotpInput">
                </div>

                <!-- Submit TOTP button -->
                <button type="submit"
                  class="inline-flex items-center justify-center whitespace-nowrap font-medium transition-colors h-[40px] px-[16px] rounded-[10px] gap-[6px] text-sm min-w-16 w-full"
                  :class="isTotpValid && !isLoading
                    ? 'bg-[var(--Button-primary-black)] text-[var(--text-onblack)] hover:opacity-90 active:opacity-80'
                    : 'bg-[var(--button-disabled-bg)] text-[var(--button-disabled-text)] cursor-not-allowed'"
                  :disabled="!isTotpValid || isLoading">
                  <LoaderCircle v-if="isLoading" :size="16" class="animate-spin" />
                  <span>{{ isLoading ? t('Verifying...') : t('Verify') }}</span>
                </button>

                <!-- Back link -->
                <div class="text-center">
                  <span
                    class="text-[13px] text-[var(--text-tertiary)] cursor-pointer select-none hover:opacity-80 active:opacity-70 transition-all underline"
                    @click="resetTotpStep">
                    {{ t('Back to login') }}
                  </span>
                </div>
              </template>

              <!-- Normal Login Step -->
              <template v-else>
                <!-- Email field -->
                <div class="flex flex-col items-start">
                  <div class="w-full flex items-center justify-between gap-[12px] mb-[8px]">
                    <label for="email"
                      class="text-[13px] text-[var(--text-primary)] font-medium after:content-[&quot;*&quot;] after:text-[var(--function-error)] after:ml-[4px]">
                      <span>{{ t('Email') }}</span>
                    </label>
                  </div>
                  <input v-model="formData.email"
                    class="rounded-[10px] overflow-hidden text-sm leading-[22px] text-[var(--text-primary)] h-10 disabled:cursor-not-allowed placeholder:text-[var(--text-disable)] bg-[var(--fill-input-chat)] pt-1 pr-1.5 pb-1 pl-3 focus:ring-[1.5px] focus:ring-[var(--border-dark)] w-full"
                    :class="{ 'ring-1 ring-[var(--function-error)]': validationErrors.email }" id="email"
                    name="email" autocomplete="email"
                    placeholder="mail@domain.com" type="email" :disabled="isLoading" @input="validateField('email')"
                    @blur="validateField('email')">
                  <div
                    class="text-[13px] text-[var(--function-error)] leading-[18px] overflow-hidden transition-all duration-300 ease-out"
                    :class="validationErrors.email ? 'opacity-100 max-h-[60px] mt-[2px]' : 'opacity-0 max-h-0 mt-0'">
                    {{ validationErrors.email }}
                  </div>
                </div>

                <!-- Password field -->
                <div class="flex flex-col items-start">
                  <div class="w-full flex items-center justify-between gap-[12px] mb-[8px]">
                    <label for="password"
                      class="text-[13px] text-[var(--text-primary)] font-medium after:content-[&quot;*&quot;] after:text-[var(--function-error)] after:ml-[4px]">
                      <span>{{ t('Password') }}</span>
                    </label>
                    <span
                      class="underline text-[var(--text-tertiary)] text-[13px] leading-[18px] transition-opacity cursor-pointer select-none hover:opacity-80 active:opacity-80"
                      @click="emits('switchToReset')">{{ t('Forgot Password?') }}</span>
                  </div>
                  <div class="relative w-full">
                    <input v-model="formData.password"
                      class="rounded-[10px] overflow-hidden text-sm leading-[22px] text-[var(--text-primary)] h-10 w-full disabled:cursor-not-allowed placeholder:text-[var(--text-disable)] bg-[var(--fill-input-chat)] pt-1 pb-1 pl-3 focus:ring-[1.5px] focus:ring-[var(--border-dark)] pr-[40px]"
                      :class="{ 'ring-1 ring-[var(--function-error)]': validationErrors.password }"
                      id="password" name="password" autocomplete="current-password"
                      :placeholder="t('Enter password')" :type="showPassword ? 'text' : 'password'"
                      :disabled="isLoading" @input="validateField('password')" @blur="validateField('password')">
                    <div
                      class="text-[var(--icon-tertiary)] absolute z-30 right-[6px] top-[50%] p-[6px] rounded-md transform -translate-y-1/2 cursor-pointer hover:text-[--icon-primary] active:opacity-90 transition-all"
                      @click="showPassword = !showPassword">
                      <Eye v-if="showPassword" :size="16" />
                      <EyeOff v-else :size="16" />
                    </div>
                  </div>
                  <div
                    class="text-[13px] text-[var(--function-error)] leading-[18px] overflow-hidden transition-all duration-300 ease-out"
                    :class="validationErrors.password ? 'opacity-100 max-h-[60px] mt-[2px]' : 'opacity-0 max-h-0 mt-0'">
                    {{ validationErrors.password }}
                  </div>
                </div>

                <!-- Submit button -->
                <button type="submit"
                  class="inline-flex items-center justify-center whitespace-nowrap font-medium transition-colors h-[40px] px-[16px] rounded-[10px] gap-[6px] text-sm min-w-16 w-full"
                  :class="isFormValid && !isLoading
                    ? 'bg-[var(--Button-primary-black)] text-[var(--text-onblack)] hover:opacity-90 active:opacity-80'
                    : 'bg-[var(--button-disabled-bg)] text-[var(--button-disabled-text)] cursor-not-allowed'"
                  :disabled="!isFormValid || isLoading">
                  <LoaderCircle v-if="isLoading" :size="16" class="animate-spin" />
                  <span>{{ isLoading ? t('Processing...') : t('Login') }}</span>
                </button>
              </template>
            </div>
          </div>
        </div>

        <!-- Toggle to register -->
        <div v-if="hasRegister && !showTotpStep" class="text-center text-[13px] leading-[18px] text-[var(--text-tertiary)] mt-[8px]">
          <span>{{ t('Don\'t have an account?') }}</span>
          <span
            class="ms-[8px] text-[var(--text-secondary)] cursor-pointer select-none hover:opacity-80 active:opacity-70 transition-all underline"
            @click="emits('switchToRegister')">
            {{ t('Register') }}
          </span>
        </div>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import { Eye, EyeOff, LoaderCircle, ShieldCheck } from 'lucide-vue-next'
import { useAuth } from '@/api'
import { validateUserInput } from '@/utils/auth'
import { showErrorToast, showSuccessToast } from '@/utils/toast'
import { getCachedAuthProvider } from '@/api/auth'

const { t } = useI18n()

// Emits
const emits = defineEmits<{
  success: []
  switchToRegister: []
  switchToReset: []
}>()

const { login, isLoading, authError } = useAuth()
const hasRegister = ref(false)

// Form state
const showPassword = ref(false)
const showTotpStep = ref(false)
const totpCode = ref('')
const totpInputRef = ref<HTMLInputElement | null>(null)

// Form data
const formData = ref({
  email: '',
  password: ''
})

// Validation errors
const validationErrors = ref<Record<string, string>>({})

// TOTP validation
const isTotpValid = computed(() => /^\d{6}$/.test(totpCode.value))

// Clear form
const clearForm = () => {
  formData.value = { email: '', password: '' }
  validationErrors.value = {}
  showTotpStep.value = false
  totpCode.value = ''
}

// Reset TOTP step (go back to login)
const resetTotpStep = () => {
  showTotpStep.value = false
  totpCode.value = ''
}

// Auto-submit when 6 digits entered
const onTotpInput = () => {
  // Strip non-digit characters
  totpCode.value = totpCode.value.replace(/\D/g, '').slice(0, 6)
  if (isTotpValid.value) {
    handleSubmit()
  }
}

// Validate single field
const validateField = (field: string) => {
  const errors: Record<string, string> = {}

  if (field === 'email') {
    const result = validateUserInput({ email: formData.value.email })
    if (result.errors.email) {
      errors.email = result.errors.email
    }
  }

  if (field === 'password') {
    const result = validateUserInput({ password: formData.value.password })
    if (result.errors.password) {
      errors.password = result.errors.password
    }
  }

  // Update error state
  Object.keys(errors).forEach(key => {
    validationErrors.value[key] = errors[key]
  })

  // Clear fixed errors
  if (!errors[field]) {
    delete validationErrors.value[field]
  }
}

// Validate entire form
const validateForm = () => {
  const data = {
    email: formData.value.email,
    password: formData.value.password
  }

  const result = validateUserInput(data)
  validationErrors.value = { ...result.errors }

  return Object.keys(validationErrors.value).length === 0
}

// Check if form is valid
const isFormValid = computed(() => {
  const hasRequiredFields = formData.value.email.trim() && formData.value.password.trim()
  const hasNoErrors = Object.keys(validationErrors.value).length === 0
  return hasRequiredFields && hasNoErrors
})

// Submit form
const handleSubmit = async () => {
  // TOTP step: submit with code
  if (showTotpStep.value) {
    if (!isTotpValid.value) return

    try {
      await login({
        email: formData.value.email,
        password: formData.value.password,
        totp_code: totpCode.value,
      })
      showSuccessToast(t('Login successful! Welcome back'))
      emits('success')
    } catch {
      totpCode.value = ''
      showErrorToast(authError.value || t('Invalid verification code'))
    }
    return
  }

  // Normal login step
  if (!validateForm()) return

  try {
    const response = await login({
      email: formData.value.email,
      password: formData.value.password,
    })

    // Check if TOTP is required
    if (response?.requires_totp) {
      showTotpStep.value = true
      await nextTick()
      totpInputRef.value?.focus()
      return
    }

    showSuccessToast(t('Login successful! Welcome back'))
    emits('success')
  } catch {
    showErrorToast(authError.value || t('Login failed, please try again'))
  }
}

onMounted(async () => {
  const authProvider = await getCachedAuthProvider()
  hasRegister.value = authProvider === 'password'
})

// Expose clearForm method for parent component
defineExpose({
  clearForm
})
</script>