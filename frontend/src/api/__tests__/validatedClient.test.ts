import { beforeEach, describe, expect, it, vi } from 'vitest';
import { z } from 'zod';

import {
  __resetSchemaTelemetryForTests,
  getFrontendSchemaMismatchTotal,
} from '../schemaTelemetry';
import { SchemaValidationError, validateResponse } from '../validatedClient';

const TestSchema = z.object({
  value: z.number(),
});

describe('validatedClient', () => {
  beforeEach(() => {
    __resetSchemaTelemetryForTests();
  });

  it('returns parsed data when schema matches', () => {
    const result = validateResponse(
      TestSchema,
      { value: 42 },
      '/test',
      'v1',
      'A',
    );

    expect(result.value).toBe(42);
    expect(getFrontendSchemaMismatchTotal()).toBe(0);
  });

  it('throws SchemaValidationError for tier A mismatch and records telemetry', () => {
    const dispatchSpy = vi.spyOn(window, 'dispatchEvent');

    expect(() =>
      validateResponse(
        TestSchema,
        { value: 'bad' },
        '/test',
        'v1',
        'A',
      ),
    ).toThrow(SchemaValidationError);

    expect(getFrontendSchemaMismatchTotal()).toBe(1);
    expect(dispatchSpy).toHaveBeenCalled();
    dispatchSpy.mockRestore();
  });

  it('returns raw data for tier B mismatch and records telemetry', () => {
    const result = validateResponse(
      TestSchema,
      { value: 'bad' },
      '/test',
      'v1',
      'B',
    ) as unknown as { value: string };

    expect(result.value).toBe('bad');
    expect(getFrontendSchemaMismatchTotal()).toBe(1);
  });
});
