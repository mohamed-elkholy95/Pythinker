import type { SearchResultsEnvelope, SearchResultsPayload } from '@/types/search';

export interface NormalizedSearchResult {
  title: string;
  link: string;
  snippet: string;
}

export interface NormalizedSearchResults {
  results: NormalizedSearchResult[];
  explicit: boolean;
}

const RESULT_KEYS = [
  'results',
  'result',
  'items',
  'search_results',
  'searchResults',
  'documents',
  'deals',
  'coupons'
] as const;

function pickFirstString(source: any, keys: string[]): string {
  for (const key of keys) {
    const value = source?.[key];
    if (typeof value === 'string' && value.trim()) return value;
  }
  return '';
}

function normalizeItem(item: any): NormalizedSearchResult | null {
  if (!item) return null;

  if (typeof item === 'string') {
    return { title: item.trim(), link: '', snippet: '' };
  }

  const source = item.document || item._source || item.resource || item;

  const title =
    pickFirstString(source, ['title', 'name', 'headline']) ||
    pickFirstString(item, ['title', 'name']) ||
    'Untitled result';

  const link =
    pickFirstString(source, ['link', 'url', 'href', 'source', 'website']) ||
    pickFirstString(item, ['link', 'url', 'href', 'source']) ||
    '';

  const snippet =
    pickFirstString(source, ['snippet', 'description', 'summary', 'text', 'content', 'body', 'excerpt']) ||
    pickFirstString(item, ['snippet', 'description', 'summary', 'text', 'content']) ||
    '';

  return { title, link, snippet };
}

function isSearchResultsPayload(payload: any): payload is SearchResultsPayload {
  return !!payload && typeof payload === 'object' && Array.isArray(payload.results) && typeof payload.query === 'string';
}

function hasArrayProperty(payload: any, key: string): boolean {
  if (!payload || typeof payload !== 'object') return false;
  return key in payload && Array.isArray((payload as any)[key]);
}

function findArray(payload: SearchResultsEnvelope | SearchResultsPayload | unknown): {
  items: any[];
  explicit: boolean;
} {
  if (!payload) return { items: [], explicit: false };
  if (Array.isArray(payload)) return { items: payload, explicit: true };

  if (isSearchResultsPayload(payload)) {
    return { items: payload.results, explicit: true };
  }

  for (const key of RESULT_KEYS) {
    if (hasArrayProperty(payload, key)) {
      return { items: (payload as any)[key], explicit: true };
    }

    const value = (payload as any)[key];
    if (value && Array.isArray(value.results)) return { items: value.results, explicit: true };
    if (value && Array.isArray(value.items)) return { items: value.items, explicit: true };
  }

  if (payload && typeof payload === 'object') {
    const record = payload as Record<string, unknown>;
    if (record.data && typeof record.data === 'object') {
      const data = record.data as Record<string, unknown>;
      if (hasArrayProperty(data, 'results')) return { items: (data as { results: unknown[] }).results, explicit: true };
      if (hasArrayProperty(data, 'items')) return { items: (data as { items: unknown[] }).items, explicit: true };
      if (hasArrayProperty(data, 'result')) return { items: (data as { result: unknown[] }).result, explicit: true };
    }
    if (record.hits && typeof record.hits === 'object') {
      const hits = record.hits as Record<string, unknown>;
      if (Array.isArray(hits.hits)) return { items: hits.hits, explicit: true };
    }
  }

  return { items: [], explicit: false };
}

export function normalizeSearchResults(
  payload: SearchResultsEnvelope | SearchResultsPayload | unknown,
  maxResults = 50
): NormalizedSearchResults {
  const { items, explicit } = findArray(payload);
  const normalized = items
    .map(normalizeItem)
    .filter((item): item is NormalizedSearchResult => !!item);

  return {
    results: normalized.slice(0, maxResults),
    explicit
  };
}
