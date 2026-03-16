import { ZodError, z } from 'zod';
import { normalizeZodIssues, recordSchemaMismatch } from './schemaTelemetry';

export class SchemaValidationError extends Error {
  endpoint: string;
  contractVersion: string;
  tier: 'A' | 'B' | 'C';
  details: ReturnType<typeof normalizeZodIssues>;

  constructor(
    endpoint: string,
    contractVersion: string,
    tier: 'A' | 'B' | 'C',
    error: ZodError,
  ) {
    super(`Schema validation failed for ${endpoint}`);
    this.name = 'SchemaValidationError';
    this.endpoint = endpoint;
    this.contractVersion = contractVersion;
    this.tier = tier;
    this.details = normalizeZodIssues(error.issues);
  }
}

export function validateResponse<T>(
  schema: z.ZodType<T>,
  data: unknown,
  endpoint: string,
  contractVersion: string,
  tier: 'A' | 'B' | 'C' = 'A',
): T {
  const result = schema.safeParse(data);
  if (result.success) {
    return result.data;
  }

  const normalizedIssues = normalizeZodIssues(result.error.issues);
  recordSchemaMismatch({
    endpoint,
    contractVersion,
    tier,
    issues: normalizedIssues,
  });

  if (tier === 'A') {
    throw new SchemaValidationError(endpoint, contractVersion, tier, result.error);
  }

  return data as T;
}
