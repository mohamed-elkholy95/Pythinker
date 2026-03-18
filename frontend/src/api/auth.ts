// Authentication API service
import { apiClient, ApiResponse } from './client';
import {
  AUTH_CONTRACT_VERSION,
  AuthStatusResponseSchema,
  LoginResponseSchema,
  PasswordPolicySchema,
  RegisterResponseSchema,
  UserSchema,
  VerificationStateSchema,
  VerifyEmailResponseSchema,
} from '@/contracts/auth.schema';
import { validateResponse } from './validatedClient';

/**
 * User role type
 */
export type UserRole = 'admin' | 'user';

/**
 * User response type
 */
export interface User {
  id: string;
  fullname: string;
  email: string;
  role: UserRole;
  is_active: boolean;
  email_verified: boolean;
  totp_enabled: boolean;
  created_at: string;
  updated_at: string;
  last_login_at?: string | null;
}

/**
 * Login request type
 */
export interface LoginRequest {
  email: string;
  password: string;
  totp_code?: string;
}

/**
 * Register request type
 */
export interface RegisterRequest {
  fullname: string;
  email: string;
  password: string;
}

/**
 * Login response type
 */
export interface LoginResponse {
  user?: User;
  access_token?: string;
  refresh_token?: string;
  token_type: string;
  expires_in?: number;
  requires_totp?: boolean;
}

/**
 * Password policy type returned by /auth/status
 */
export interface PasswordPolicy {
  version: number;
  min_length: number;
  max_length: number;
  require_uppercase: boolean;
  require_lowercase: boolean;
  require_digit: boolean;
  require_special: boolean;
}

/**
 * OTP verification state returned by register/reset endpoints
 */
export interface VerificationState {
  expires_at: string;
  resend_available_at: string;
  resends_remaining: number;
}

/**
 * Register response type — triggers email verification flow
 */
export interface RegisterResponse {
  message: string;
  requires_verification: boolean;
  verification_state: VerificationState;
}

/**
 * Verify email request type
 */
export interface VerifyEmailRequest {
  email: string;
  verification_code: string;
}

/**
 * Verify email response type — returns tokens after successful verification
 */
export interface VerifyEmailResponse {
  user: User;
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

/**
 * Change password request type
 */
export interface ChangePasswordRequest {
  old_password: string;
  new_password: string;
}

/**
 * Change fullname request type
 */
export interface ChangeFullnameRequest {
  fullname: string;
}

/**
 * Refresh token request type
 */
export interface RefreshTokenRequest {
  refresh_token: string;
}

/**
 * Refresh token response type
 */
export interface RefreshTokenResponse {
  access_token: string;
  token_type: string;
  expires_in?: number;
}

/**
 * Auth status response type
 */
export interface AuthStatusResponse {
  auth_provider: string;
  password_policy?: PasswordPolicy | null;
}

/**
 * Resource access token request type
 */
export interface AccessTokenRequest {
  resource_type: 'file' | 'sandbox';
  resource_id: string;
  expire_minutes?: number;
}

/**
 * Resource access token response type
 */
export interface AccessTokenResponse {
  access_token: string;
  resource_type: string;
  resource_id: string;
  expires_in: number;
}

/**
 * Send verification code request type
 */
export interface SendVerificationCodeRequest {
  email: string;
}

/**
 * Reset password request type
 */
export interface ResetPasswordRequest {
  email: string;
  verification_code: string;
  new_password: string;
}

/**
 * TOTP setup response type
 */
export interface TotpSetupResponse {
  provisioning_uri: string;
  secret: string;
}

/**
 * TOTP verify request type
 */
export interface TotpVerifyRequest {
  code: string;
}

/**
 * TOTP disable request type
 */
export interface TotpDisableRequest {
  code: string;
}



/**
 * User login
 * @param request Login credentials
 * @returns Login response with user info and tokens
 */
export async function login(request: LoginRequest): Promise<LoginResponse> {
  const response = await apiClient.post<ApiResponse<LoginResponse>>('/auth/login', request);
  return validateResponse(
    LoginResponseSchema,
    response.data.data,
    '/auth/login',
    AUTH_CONTRACT_VERSION,
    'A',
  );
}

/**
 * User registration — triggers email verification flow
 * @param request Registration data
 * @returns Registration response (requires email verification)
 */
export async function register(request: RegisterRequest): Promise<RegisterResponse> {
  const response = await apiClient.post<ApiResponse<RegisterResponse>>('/auth/register', request);
  return validateResponse(
    RegisterResponseSchema,
    response.data.data,
    '/auth/register',
    AUTH_CONTRACT_VERSION,
    'A',
  );
}

/**
 * Verify email with OTP code
 * @param request Email and verification code
 * @returns Tokens after successful verification
 */
export async function verifyEmail(request: VerifyEmailRequest): Promise<VerifyEmailResponse> {
  const response = await apiClient.post<ApiResponse<VerifyEmailResponse>>('/auth/verify-email', request);
  return validateResponse(
    VerifyEmailResponseSchema,
    response.data.data,
    '/auth/verify-email',
    AUTH_CONTRACT_VERSION,
    'A',
  );
}

/**
 * Resend registration verification code
 * @param request Email to resend code to
 * @returns Success response
 */
export async function resendRegistrationCode(request: { email: string }): Promise<VerificationState> {
  const response = await apiClient.post<ApiResponse<VerificationState>>('/auth/resend-registration-code', request);
  return validateResponse(
    VerificationStateSchema,
    response.data.data,
    '/auth/resend-registration-code',
    AUTH_CONTRACT_VERSION,
    'A',
  );
}

/**
 * Get authentication status
 * @returns Current authentication status and configuration
 */
export async function getAuthStatus(): Promise<AuthStatusResponse> {
  const response = await apiClient.get<ApiResponse<AuthStatusResponse>>('/auth/status');
  return validateResponse(
    AuthStatusResponseSchema,
    response.data.data,
    '/auth/status',
    AUTH_CONTRACT_VERSION,
    'A',
  );
}

/**
 * Change user password
 * @param request Change password data
 * @returns Success response
 */
export async function changePassword(request: ChangePasswordRequest): Promise<{}> {
  const response = await apiClient.post<ApiResponse<{}>>('/auth/change-password', request);
  return response.data.data;
}

/**
 * Change user fullname
 * @param request Change fullname data
 * @returns Updated user data
 */
export async function changeFullname(request: ChangeFullnameRequest): Promise<User> {
  const response = await apiClient.post<ApiResponse<User>>('/auth/change-fullname', request);
  return response.data.data;
}

/**
 * Get current user information
 * @returns Current user data
 */
export async function getCurrentUser(): Promise<User> {
  const response = await apiClient.get<ApiResponse<User>>('/auth/me');
  return validateResponse(
    UserSchema,
    response.data.data,
    '/auth/me',
    AUTH_CONTRACT_VERSION,
    'A',
  );
}

/**
 * Get user by ID (admin only)
 * @param userId User ID to fetch
 * @returns User data
 */
export async function getUser(userId: string): Promise<User> {
  const response = await apiClient.get<ApiResponse<User>>(`/auth/user/${userId}`);
  return response.data.data;
}

/**
 * Deactivate user account (admin only)
 * @param userId User ID to deactivate
 * @returns Success response
 */
export async function deactivateUser(userId: string): Promise<{}> {
  const response = await apiClient.post<ApiResponse<{}>>(`/auth/user/${userId}/deactivate`);
  return response.data.data;
}

/**
 * Activate user account (admin only)
 * @param userId User ID to activate
 * @returns Success response
 */
export async function activateUser(userId: string): Promise<{}> {
  const response = await apiClient.post<ApiResponse<{}>>(`/auth/user/${userId}/activate`);
  return response.data.data;
}

/**
 * Refresh access token
 * @param request Refresh token data
 * @returns New access token
 */
export async function refreshToken(request: RefreshTokenRequest): Promise<RefreshTokenResponse> {
  const response = await apiClient.post<ApiResponse<RefreshTokenResponse>>('/auth/refresh', request);
  return response.data.data;
}

/**
 * User logout
 * @returns Success response
 */
export async function logout(): Promise<{}> {
  const response = await apiClient.post<ApiResponse<{}>>('/auth/logout');
  return response.data.data;
}

/**
 * Send verification code for password reset
 * @param request Email to send verification code to
 * @returns Success response
 */
export async function sendVerificationCode(request: SendVerificationCodeRequest): Promise<VerificationState> {
  const response = await apiClient.post<ApiResponse<VerificationState>>('/auth/send-verification-code', request);
  return validateResponse(
    VerificationStateSchema,
    response.data.data,
    '/auth/send-verification-code',
    AUTH_CONTRACT_VERSION,
    'A',
  );
}

/**
 * Reset password with verification code
 * @param request Reset password data including email, verification code and new password
 * @returns Success response
 */
export async function resetPassword(request: ResetPasswordRequest): Promise<{}> {
  const response = await apiClient.post<ApiResponse<{}>>('/auth/reset-password', request);
  return response.data.data;
}

/**
 * Start TOTP 2FA setup — returns provisioning URI for QR code
 * @returns TOTP setup data (provisioning_uri + secret)
 */
export async function totpSetup(): Promise<TotpSetupResponse> {
  const response = await apiClient.post<ApiResponse<TotpSetupResponse>>('/auth/totp/setup');
  return response.data.data;
}

/**
 * Verify TOTP code to complete 2FA setup
 * @param request TOTP verification code
 * @returns Success response
 */
export async function totpVerify(request: TotpVerifyRequest): Promise<{}> {
  const response = await apiClient.post<ApiResponse<{}>>('/auth/totp/verify', request);
  return response.data.data;
}

/**
 * Disable TOTP 2FA
 * @param request Current TOTP code for verification
 * @returns Success response
 */
export async function totpDisable(request: TotpDisableRequest): Promise<{}> {
  const response = await apiClient.post<ApiResponse<{}>>('/auth/totp/disable', request);
  return response.data.data;
}

/**
 * Set authentication token in request headers
 * @param token JWT access token
 */
export function setAuthToken(token: string): void {
  apiClient.defaults.headers.Authorization = `Bearer ${token}`;
}

/**
 * Clear authentication token from request headers
 */
export function clearAuthToken(): void {
  delete apiClient.defaults.headers.Authorization;
}

const canReadStorage = (): boolean =>
  typeof localStorage !== 'undefined' && typeof localStorage.getItem === 'function';

const canWriteStorage = (): boolean =>
  typeof localStorage !== 'undefined' &&
  typeof localStorage.setItem === 'function' &&
  typeof localStorage.removeItem === 'function';

/**
 * Get stored authentication token from localStorage
 * @returns Stored token or null
 */
export function getStoredToken(): string | null {
  if (!canReadStorage()) {
    return null;
  }

  return localStorage.getItem('access_token');
}

/**
 * Store authentication token in localStorage
 * @param token Token to store
 */
export function storeToken(token: string): void {
  if (!canWriteStorage()) {
    return;
  }

  localStorage.setItem('access_token', token);
}

/**
 * Store refresh token in localStorage
 * @param refreshToken Refresh token to store
 */
export function storeRefreshToken(refreshToken: string): void {
  if (!canWriteStorage()) {
    return;
  }

  localStorage.setItem('refresh_token', refreshToken);
}

/**
 * Get stored refresh token from localStorage
 * @returns Stored refresh token or null
 */
export function getStoredRefreshToken(): string | null {
  if (!canReadStorage()) {
    return null;
  }

  return localStorage.getItem('refresh_token');
}

/**
 * Clear stored tokens from localStorage
 */
export function clearStoredTokens(): void {
  if (!canWriteStorage()) {
    return;
  }

  localStorage.removeItem('access_token');
  localStorage.removeItem('refresh_token');
}

/**
 * Legacy localStorage keys from previous auth implementations.
 * These are no longer used — canonical keys are 'access_token' and 'refresh_token'.
 */
const STALE_AUTH_KEYS = ['token', 'auth_token', 'accessToken', 'user'] as const;

/**
 * Migrate and clean up stale auth tokens from localStorage.
 *
 * Previous implementations stored tokens under different keys. This function
 * migrates any valid JWT found under legacy keys to the canonical 'access_token'
 * key, then removes all stale entries.
 *
 * Should be called once on app startup, before initializeAuth().
 */
export function migrateStaleTokens(): void {
  if (!canReadStorage() || !canWriteStorage()) {
    return;
  }

  const canonical = localStorage.getItem('access_token');
  const hasValidCanonical = canonical && canonical.startsWith('eyJ');

  // If no valid canonical token exists, check legacy keys for a JWT to rescue
  if (!hasValidCanonical) {
    for (const key of STALE_AUTH_KEYS) {
      const value = localStorage.getItem(key);
      if (value && value.startsWith('eyJ') && value.length > 50) {
        // Found a valid-looking JWT in a legacy key — promote it
        localStorage.setItem('access_token', value);
        break;
      }
    }
  }

  // Remove all stale keys regardless
  for (const key of STALE_AUTH_KEYS) {
    localStorage.removeItem(key);
  }
}

/**
 * Initialize authentication from stored tokens.
 * This should be called when the app starts.
 *
 * Runs a one-time migration to clean up stale localStorage keys from
 * previous auth implementations, then sets the Authorization header
 * from the canonical 'access_token' key.
 */
export function initializeAuth(): void {
  migrateStaleTokens();
  const token = getStoredToken();
  if (token) {
    setAuthToken(token);
  }
}

// Auth status cache with in-flight promise deduplication
let authStatusCache: AuthStatusResponse | null = null;
let isAuthStatusLoaded = false;
let pendingAuthStatusPromise: Promise<AuthStatusResponse | null> | null = null;

/**
 * Get auth status configuration (cached after first call).
 * Concurrent callers share a single in-flight request to avoid duplicate API calls.
 */
export async function getCachedAuthStatus(): Promise<AuthStatusResponse | null> {
  if (isAuthStatusLoaded) {
    return authStatusCache;
  }

  if (pendingAuthStatusPromise) {
    return pendingAuthStatusPromise;
  }

  pendingAuthStatusPromise = getAuthStatus()
    .then((authStatus) => {
      authStatusCache = authStatus;
      isAuthStatusLoaded = true;
      return authStatusCache;
    })
    .catch((error) => {
      console.warn('Failed to load auth status configuration:', error);
      return null;
    })
    .finally(() => {
      pendingAuthStatusPromise = null;
    });

  return pendingAuthStatusPromise;
}

/**
 * Get auth provider configuration (cached after first call).
 * @returns Auth provider string or null if failed to load
 */
export async function getCachedAuthProvider(): Promise<string | null> {
  const authStatus = await getCachedAuthStatus();
  return authStatus?.auth_provider ?? null;
}

/**
 * Get cached password policy from auth status.
 * Returns null when auth status is unavailable or the current auth provider is not password-based.
 */
export async function getCachedPasswordPolicy(): Promise<PasswordPolicy | null> {
  const authStatus = await getCachedAuthStatus();
  if (authStatus?.auth_provider !== 'password') {
    return null;
  }
  try {
    return validateResponse(
      PasswordPolicySchema,
      authStatus.password_policy ?? null,
      '/auth/status.password_policy',
      AUTH_CONTRACT_VERSION,
      'A',
    );
  } catch (error) {
    console.warn('Failed to validate password policy configuration:', error);
    return null;
  }
}
