import { z } from 'zod';

export const AUTH_CONTRACT_VERSION = '2026-03-05.structured-output-v1';

export const UserSchema = z.object({
  id: z.string(),
  fullname: z.string(),
  email: z.string().email(),
  role: z.enum(['admin', 'user']),
  is_active: z.boolean(),
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
