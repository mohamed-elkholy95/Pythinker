import type { PasswordPolicy } from '@/api/auth';

const ASCII_PUNCTUATION_PATTERN = /[!"#$%&'()*+,\-./:;<=>?@[\\\]^_`{|}~]/;

type Translate = (key: string, values?: Record<string, unknown>) => string;

export interface PasswordRequirementState {
  key: string;
  label: string;
  message: string;
  met: boolean;
}

export interface PasswordPolicyEvaluation {
  isValid: boolean;
  requirements: PasswordRequirementState[];
  summary: string;
}

export function evaluatePasswordPolicy(
  password: string,
  policy: PasswordPolicy,
  t: Translate,
): PasswordPolicyEvaluation {
  const requirements: PasswordRequirementState[] = [
    {
      key: 'min_length',
      label: t('At least {count} characters', { count: policy.min_length }),
      message: t('Password must be at least {count} characters long', { count: policy.min_length }),
      met: password.length >= policy.min_length,
    },
    {
      key: 'max_length',
      label: t('No more than {count} characters', { count: policy.max_length }),
      message: t('Password must be no more than {count} characters long', { count: policy.max_length }),
      met: password.length <= policy.max_length,
    },
  ];

  if (policy.require_uppercase) {
    requirements.push({
      key: 'require_uppercase',
      label: t('1 uppercase'),
      message: t('Password must contain at least one uppercase letter'),
      met: /[A-Z]/.test(password),
    });
  }

  if (policy.require_lowercase) {
    requirements.push({
      key: 'require_lowercase',
      label: t('1 lowercase'),
      message: t('Password must contain at least one lowercase letter'),
      met: /[a-z]/.test(password),
    });
  }

  if (policy.require_digit) {
    requirements.push({
      key: 'require_digit',
      label: t('1 number'),
      message: t('Password must contain at least one digit'),
      met: /\d/.test(password),
    });
  }

  if (policy.require_special) {
    requirements.push({
      key: 'require_special',
      label: t('1 symbol'),
      message: t('Password must contain at least one symbol'),
      met: ASCII_PUNCTUATION_PATTERN.test(password),
    });
  }

  const unmetRequirement = requirements.find((requirement) => !requirement.met);
  return {
    isValid: unmetRequirement === undefined,
    requirements,
    summary: unmetRequirement?.message ?? '',
  };
}
