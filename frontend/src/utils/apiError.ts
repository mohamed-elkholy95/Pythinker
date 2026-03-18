import { AxiosError } from 'axios';

type ErrorObject = Record<string, unknown>;

function asObject(value: unknown): ErrorObject | null {
  return value && typeof value === 'object' ? (value as ErrorObject) : null;
}

export function getApiErrorPayloadData(error: unknown): ErrorObject | null {
  if (error instanceof AxiosError) {
    const response = asObject(error.response?.data);
    return asObject(response?.data);
  }

  const errorObject = asObject(error);
  const details = asObject(errorObject?.details);
  if (details) {
    return asObject(details.data) ?? details;
  }

  return asObject(errorObject?.data);
}

export function getApiErrorCode(error: unknown): string | null {
  const data = getApiErrorPayloadData(error);
  return typeof data?.code === 'string' ? data.code : null;
}

export function getApiErrorNumber(error: unknown, key: string): number | null {
  const data = getApiErrorPayloadData(error);
  const value = data?.[key];
  return typeof value === 'number' ? value : null;
}

export function getApiErrorMessage(error: unknown): string {
  if (error instanceof AxiosError) {
    return String(error.response?.data?.msg ?? error.message ?? '');
  }

  const errorObject = asObject(error);
  const message = errorObject?.message;
  return typeof message === 'string' ? message : '';
}
