/**
 * Tests for LoginPage component
 * Tests form validation, authentication flow, and mode switching
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { ref } from 'vue'
import LoginPage from '@/pages/LoginPage.vue'

// Mock vue-i18n
vi.mock('vue-i18n', () => ({
  useI18n: () => ({
    t: (key: string) => key,
  }),
}))

// Mock vue-router
const mockPush = vi.fn()
const mockCurrentRoute = ref({
  query: { redirect: '' },
})

vi.mock('vue-router', () => ({
  useRouter: () => ({
    push: mockPush,
    currentRoute: mockCurrentRoute,
  }),
}))

// Mock auth composable
const mockIsAuthenticated = ref(false)

vi.mock('@/api', () => ({
  useAuth: () => ({
    isAuthenticated: mockIsAuthenticated,
  }),
}))

// Mock lucide-vue-next
vi.mock('lucide-vue-next', () => ({
  Bot: {
    name: 'Bot',
    template: '<span class="mock-bot" />',
    props: ['size'],
  },
}))

// Mock child components
vi.mock('@/components/icons/PythinkerLogoTextIcon.vue', () => ({
  default: {
    name: 'PythinkerLogoTextIcon',
    template: '<span class="mock-logo-text" />',
  },
}))

vi.mock('@/components/login/LoginForm.vue', () => ({
  default: {
    name: 'LoginForm',
    template: '<div class="mock-login-form"><slot /></div>',
    emits: ['success', 'switch-to-register', 'switch-to-reset'],
  },
}))

vi.mock('@/components/login/RegisterForm.vue', () => ({
  default: {
    name: 'RegisterForm',
    template: '<div class="mock-register-form"><slot /></div>',
    emits: ['success', 'switch-to-login'],
  },
}))

vi.mock('@/components/login/ResetPasswordForm.vue', () => ({
  default: {
    name: 'ResetPasswordForm',
    template: '<div class="mock-reset-form"><slot /></div>',
    emits: ['back-to-login'],
  },
}))

describe('LoginPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockIsAuthenticated.value = false
    mockCurrentRoute.value.query.redirect = ''
  })

  it('should render login form by default', () => {
    const wrapper = mount(LoginPage)

    const loginForm = wrapper.findComponent({ name: 'LoginForm' })
    expect(loginForm.exists()).toBe(true)
  })

  it('should show "Login to Pythinker" title by default', () => {
    const wrapper = mount(LoginPage)

    expect(wrapper.text()).toContain('Login to Pythinker')
  })

  it('should render Bot icon', () => {
    const wrapper = mount(LoginPage)

    const botIcon = wrapper.findComponent({ name: 'Bot' })
    expect(botIcon.exists()).toBe(true)
  })

  it('should render logo text icon', () => {
    const wrapper = mount(LoginPage)

    const logoText = wrapper.findComponent({ name: 'PythinkerLogoTextIcon' })
    expect(logoText.exists()).toBe(true)
  })

  it('should switch to register form when emitted', async () => {
    const wrapper = mount(LoginPage)

    const loginForm = wrapper.findComponent({ name: 'LoginForm' })
    loginForm.vm.$emit('switch-to-register')

    await wrapper.vm.$nextTick()

    const registerForm = wrapper.findComponent({ name: 'RegisterForm' })
    expect(registerForm.exists()).toBe(true)
    expect(wrapper.text()).toContain('Register to Pythinker')
  })

  it('should switch to reset password form when emitted', async () => {
    const wrapper = mount(LoginPage)

    const loginForm = wrapper.findComponent({ name: 'LoginForm' })
    loginForm.vm.$emit('switch-to-reset')

    await wrapper.vm.$nextTick()

    const resetForm = wrapper.findComponent({ name: 'ResetPasswordForm' })
    expect(resetForm.exists()).toBe(true)
    expect(wrapper.text()).toContain('Reset Password')
  })

  it('should switch back to login from register', async () => {
    const wrapper = mount(LoginPage)

    // First switch to register
    const loginForm = wrapper.findComponent({ name: 'LoginForm' })
    loginForm.vm.$emit('switch-to-register')
    await wrapper.vm.$nextTick()

    // Then switch back to login
    const registerForm = wrapper.findComponent({ name: 'RegisterForm' })
    registerForm.vm.$emit('switch-to-login')
    await wrapper.vm.$nextTick()

    const newLoginForm = wrapper.findComponent({ name: 'LoginForm' })
    expect(newLoginForm.exists()).toBe(true)
  })

  it('should switch back to login from reset password', async () => {
    const wrapper = mount(LoginPage)

    // First switch to reset
    const loginForm = wrapper.findComponent({ name: 'LoginForm' })
    loginForm.vm.$emit('switch-to-reset')
    await wrapper.vm.$nextTick()

    // Then switch back to login
    const resetForm = wrapper.findComponent({ name: 'ResetPasswordForm' })
    resetForm.vm.$emit('back-to-login')
    await wrapper.vm.$nextTick()

    const newLoginForm = wrapper.findComponent({ name: 'LoginForm' })
    expect(newLoginForm.exists()).toBe(true)
  })

  it('should redirect to home on login success', async () => {
    const wrapper = mount(LoginPage)

    const loginForm = wrapper.findComponent({ name: 'LoginForm' })
    loginForm.vm.$emit('success')

    expect(mockPush).toHaveBeenCalledWith('/')
  })

  it('should redirect to specified path on login success', async () => {
    mockCurrentRoute.value.query.redirect = '/dashboard'

    const wrapper = mount(LoginPage)

    const loginForm = wrapper.findComponent({ name: 'LoginForm' })
    loginForm.vm.$emit('success')

    expect(mockPush).toHaveBeenCalledWith('/dashboard')
  })

  it('should redirect on registration success', async () => {
    const wrapper = mount(LoginPage)

    // Switch to register
    const loginForm = wrapper.findComponent({ name: 'LoginForm' })
    loginForm.vm.$emit('switch-to-register')
    await wrapper.vm.$nextTick()

    // Register success
    const registerForm = wrapper.findComponent({ name: 'RegisterForm' })
    registerForm.vm.$emit('success')

    expect(mockPush).toHaveBeenCalledWith('/')
  })

  it('should redirect when already authenticated on mount', async () => {
    mockIsAuthenticated.value = true

    mount(LoginPage)

    expect(mockPush).toHaveBeenCalledWith('/')
  })

  it('should redirect when authentication state changes', async () => {
    const wrapper = mount(LoginPage)

    expect(mockPush).not.toHaveBeenCalled()

    mockIsAuthenticated.value = true
    await wrapper.vm.$nextTick()

    expect(mockPush).toHaveBeenCalledWith('/')
  })

  it('should have correct layout structure', () => {
    const wrapper = mount(LoginPage)

    // Should have full viewport height
    expect(wrapper.find('.min-h-\\[100vh\\]').exists()).toBe(true)

    // Should have sticky header
    expect(wrapper.find('.sticky').exists()).toBe(true)
  })

  it('should have home link in header', () => {
    const wrapper = mount(LoginPage)

    const homeLink = wrapper.find('a[href="/"]')
    expect(homeLink.exists()).toBe(true)
  })
})
