# Auth Password Policy And OTP Design

## Summary

This design updates the password-auth experience so the backend is the single source of truth for password policy, the frontend renders that policy clearly to users, and the existing registration email-verification boundary remains explicit and reliable before the user reaches the existing TOTP setup flow.

The requested password rule is:

- Minimum 9 characters
- At least 1 uppercase letter
- At least 1 symbol
- No lowercase requirement
- No digit requirement

This design keeps TOTP optional. It does not add forced TOTP enrollment during signup. It preserves the current login challenge flow when a user already has TOTP enabled.

## Problem Statement

The current system has one primary defect and one integration risk:

1. The backend enforces a stronger password policy than the frontend currently displays and validates.
   The result is that registration, password reset, and password change can fail after the user submits a form that looked valid in the UI.
2. The password-policy work must not accidentally blur the existing registration boundary.
   In this codebase, `/register` creates the account and sends an email OTP, while `/verify-email` is the step that issues tokens and authenticates the session.

The defect makes account creation unreliable. The integration risk means the spec must preserve the current register -> verify-email -> authenticated session path clearly.

## Goals

- Make password policy consistent across backend and frontend.
- Make the password requirements visible while the user types.
- Show clear inline validation errors before submission.
- Preserve backend validation as the final authority.
- Preserve the existing registration email-verification boundary.
- Ensure successful email verification continues to sign the user in immediately.
- Keep the existing TOTP setup, verify, disable, and login challenge flows working.

## Non-Goals

- No forced TOTP enrollment during signup.
- No changes to non-password auth providers.
- No redesign of the existing TOTP settings UI.
- No changes to token format or auth-provider selection.

## Current Constraints

- Login must remain permissive on the client side. A stricter password-creation rule must not prevent existing users from attempting login.
- Password creation flows must remain aligned:
  - registration
  - password reset
  - change password
- The codebase already has TOTP setup, verify, disable, and login challenge behavior. This design builds on that existing flow instead of replacing it.

## Recommended Approach

Use the backend as the single source of truth for password policy, expose that policy through the existing auth-status endpoint, and have password-creation screens render and validate against the policy object returned by the server.

This avoids repeating password constants across the frontend, fixes the current mismatch, and keeps future policy changes contained to one source of truth.

## Architecture

### Backend Policy Source

The backend configuration model remains the authoritative location for password policy values.

The configured values will be updated to:

- `password_min_length = 9`
- `password_require_uppercase = true`
- `password_require_lowercase = false`
- `password_require_digit = false`
- `password_require_special = true`

For this change, "symbol" and "special character" mean the same thing and must match the backend's effective regex-based definition:

- `[!@#$%^&*(),.?":{}|<>]`

The existing backend password-complexity validation logic will continue to enforce policy for:

- registration
- password reset
- change password

The backend will also remain responsible for generating the canonical validation message returned on rejection.

### Auth Status Contract

The existing `/api/v1/auth/status` response will be extended with a `password_policy` object.

Proposed response shape:

```json
{
  "auth_provider": "password",
  "password_policy": {
    "min_length": 9,
    "require_uppercase": true,
    "require_lowercase": false,
    "require_digit": false,
    "require_special": true
  }
}
```

Behavioral rules:

- When `auth_provider` is not `"password"`, the frontend may ignore `password_policy`.
- When `auth_provider` is not `"password"`, the backend may return `password_policy: null` or omit it entirely. Frontend consumers must handle both cases.
- When `auth_provider` is `"password"`, password-creation screens should use the returned policy.
- The backend contract should remain backward-compatible for current consumers that only read `auth_provider`.

Contract consumers that must be updated together:

- backend `AuthStatusResponse` schema
- backend `/auth/status` route response construction
- frontend `AuthStatusResponse` type and any response schema validation
- frontend auth-status cache helpers
- frontend password-creation validators that currently rely on hardcoded local rules

### Frontend Password Policy Layer

The frontend will add a dedicated password-policy helper that:

- accepts a password string and a password-policy object
- returns per-rule pass/fail state
- returns a concise user-facing summary message when invalid

This helper will be used only in password-creation flows. It will not replace login validation.

This separation matters because login should not guess whether an existing stored password is compliant with the current creation policy.

The current generic user-input validator is not the correct source of truth for password creation after this change. Planning should either split password validation out of that helper or ensure only the password-creation paths consume the policy-driven validator.

### Registration Authentication Flow

The existing registration lifecycle remains intact:

1. `/register` creates the user and triggers the registration email OTP.
2. `/verify-email` validates the OTP.
3. `/verify-email` returns access and refresh tokens.
4. The frontend stores those tokens and loads authenticated user state.

This design does not move token issuance to `/register` and does not remove email verification from signup.

### TOTP Flow

TOTP remains optional and structurally unchanged.

Expected user flow after this change:

1. User registers with a valid password.
2. User verifies email with the existing 6-digit registration OTP.
3. Successful email verification authenticates the session.
4. User is redirected normally into the authenticated app.
5. User opens Settings and uses the existing TOTP setup flow.
6. Future logins may trigger the existing TOTP challenge path if TOTP is enabled.

No new TOTP enrollment step is inserted into signup.

## Frontend UX Design

### Password Requirement Visualization

Password-creation screens will show a live requirement checklist directly under the password field.

Checklist items for the approved rule:

- At least 9 characters
- Contains an uppercase letter
- Contains a symbol

The checklist should update while the user types and show clear pass/fail state for each requirement.

### Inline Error Messaging

When the password is invalid, the field should show a concise summary such as:

`Password must be at least 9 characters and include 1 uppercase letter and 1 symbol.`

This summary should appear inline before submission. Backend error messages should still be surfaced in the toast if a request is rejected server-side.

### Screens In Scope

The password-policy visualization and validation apply to:

- registration form
- registration verification handoff states where the user moves from password creation to OTP entry
- reset-password verification form
- change-password dialog

The login form remains out of scope for strict password-policy enforcement. It can retain basic presence-oriented validation and the existing TOTP challenge UI.

## Data Flow

### App Startup

1. Frontend calls `/api/v1/auth/status`.
2. Frontend caches `auth_provider`.
3. Frontend also caches `password_policy` for password-auth flows.

### Registration

1. User enters password on registration screen.
2. Frontend evaluates password against cached `password_policy`.
3. Frontend renders live checklist and any inline summary.
4. If valid, frontend submits registration request.
5. Backend validates again.
6. Backend creates the user and triggers registration email verification.
7. Frontend transitions into the existing registration OTP verification step.
8. User submits verification code to `/verify-email`.
9. Backend returns tokens after successful verification.
10. Frontend stores tokens, loads authenticated user state, and redirects into the app.

### Password Reset And Change Password

1. User enters new password.
2. Frontend evaluates password against cached `password_policy`.
3. Frontend blocks invalid submissions with inline guidance.
4. Backend performs final validation and returns canonical errors if needed.

## Error Handling

### Backend Errors

The backend remains authoritative. If frontend and backend ever diverge, backend validation wins.

Expected backend validation failures should return clear API errors for:

- too-short password
- missing uppercase letter
- missing symbol

### Frontend Errors

Frontend should distinguish:

- inline password-policy guidance for local validation
- toast error messages for server-side rejection or transport failures
- existing inline registration verification-code errors for the `/verify-email` step

### Auth Status Fallback

If password policy cannot be loaded but `auth_provider` is `"password"`, the frontend should fail safely rather than inventing a different password policy.

Required fail-safe behavior:

- keep backend validation authoritative
- do not render a locally invented password-policy checklist
- disable submission for registration, reset-password, and change-password screens until the policy is available
- show a clear inline message such as `Unable to load current password requirements. Please retry.`
- keep login unaffected by this failure mode

This should be implemented carefully so it does not create permanent dead ends in the UI. A retry path or policy reload path should be available on password-creation screens.

## Testing Strategy

### Backend Tests

- Verify `/auth/status` includes the password-policy contract.
- Verify registration rejects passwords that miss:
  - minimum length
  - uppercase requirement
  - symbol requirement
- Verify password reset and change password use the same policy.
- Verify error messages remain explicit and stable enough for user display.
- Verify registration still returns a verification-required response instead of tokens.
- Verify `/verify-email` remains the token-issuance boundary.

### Frontend Tests

- Verify password-policy evaluation returns correct per-rule results.
- Verify register, reset-password, and change-password render the requirement checklist and invalid summary correctly.
- Verify the registration form still transitions into the existing email-verification step after successful `/register`.
- Verify successful `/verify-email` continues to store tokens and enter authenticated state.
- Verify login remains permissive and does not adopt the strict password-creation validator.
- Verify redirect-after-email-verification still works once the auth state is actually valid.

## File Impact

Expected areas of change:

- Backend config/auth schema/auth routes/auth service
- Frontend auth API contract and cached auth status handling
- Frontend password validation utilities
- Registration form
- Registration verification form only where it interacts with the post-register handoff or auth-status contract
- Reset password verification form
- Change password dialog
- Auth-status consumers and verification-flow tests

## Risks

### Contract Drift

If the frontend reads stale or incomplete auth-status data, the UI could render the wrong rules.

Mitigation:

- backend-owned contract
- explicit tests around `/auth/status`
- frontend helper keyed to the returned object rather than hardcoded literals

### Over-Applying Validation To Login

If the new validator is reused in login, existing users could be blocked client-side.

Mitigation:

- separate password-creation validation from login validation
- add explicit frontend tests covering that boundary

### Ambiguous Symbol Rule

If the allowed symbol set is not consistent between backend and frontend, users may see false positives or false negatives.

Mitigation:

- frontend should match the backend’s effective symbol definition
- tests should cover representative symbols and non-symbol characters

## Open Decisions Resolved In This Spec

- Password rule is minimum 9 characters, with 1 uppercase letter and 1 symbol.
- Lowercase letters are not required.
- Digits are not required.
- TOTP stays optional.
- Registration must authenticate the user immediately.

## Implementation Readiness

This work is ready for planning after spec review because:

- scope is limited to password-auth flows, the existing registration verification boundary, and the existing TOTP onboarding path
- subsystem boundaries are clear
- success conditions are explicit
- testing and edge cases are identified
