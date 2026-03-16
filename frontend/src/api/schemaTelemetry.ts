import type { ZodIssue } from 'zod';

export interface SchemaMismatchIssue {
  path: PropertyKey[];
  code: string;
  message: string;
}

export interface SchemaMismatchEvent {
  endpoint: string;
  contractVersion: string;
  tier: 'A' | 'B' | 'C';
  issues: SchemaMismatchIssue[];
}

let frontendSchemaMismatchTotal = 0;

export const getFrontendSchemaMismatchTotal = (): number => frontendSchemaMismatchTotal;

export const __resetSchemaTelemetryForTests = (): void => {
  frontendSchemaMismatchTotal = 0;
};

export const normalizeZodIssues = (issues: ZodIssue[]): SchemaMismatchIssue[] =>
  issues.map((issue) => ({
    path: issue.path,
    code: issue.code,
    message: issue.message,
  }));

export const recordSchemaMismatch = (event: SchemaMismatchEvent): void => {
  frontendSchemaMismatchTotal += 1;
  console.warn('[SchemaMismatch]', event);
  window.dispatchEvent(new CustomEvent<SchemaMismatchEvent>('frontend:schema-mismatch', { detail: event }));
};
