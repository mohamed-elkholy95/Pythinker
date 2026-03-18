import { z } from 'zod';

export const AUTH_CONTRACT_VERSION = '2026-03-17.auth-password-policy-otp-v1';

export const UserSchema = z.object({
  id: z.string(),
  fullname: z.string(),
  email: z.string().email(),
  role: z.enum(['admin', 'user']),
  is_active: z.boolean(),
  email_verified: z.boolean().default(true),
  totp_enabled: z.boolean().default(false),
  created_at: z.string(),
  updated_at: z.string(),
  last_login_at: z.string().nullish(),
});

export const LoginResponseSchema = z.object({
  user: UserSchema.optional(),
  access_token: z.string().optional(),
  refresh_token: z.string().optional(),
  token_type: z.string(),
  expires_in: z.number().optional(),
  requires_totp: z.boolean().optional(),
});

export const PasswordPolicySchema = z.object({
  version: z.number(),
  min_length: z.number(),
  max_length: z.number(),
  require_uppercase: z.boolean(),
  require_lowercase: z.boolean(),
  require_digit: z.boolean(),
  require_special: z.boolean(),
});

export const VerificationStateSchema = z.object({
  expires_at: z.string(),
  resend_available_at: z.string(),
  resends_remaining: z.number(),
});

export const RegisterResponseSchema = z.object({
  message: z.string(),
  requires_verification: z.boolean(),
  verification_state: VerificationStateSchema,
});

export const VerifyEmailResponseSchema = z.object({
  user: UserSchema,
  access_token: z.string(),
  refresh_token: z.string(),
  token_type: z.string(),
  expires_in: z.number(),
});

export const AuthStatusResponseSchema = z.object({
  auth_provider: z.string(),
  password_policy: PasswordPolicySchema.nullish(),
});
