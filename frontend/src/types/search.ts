export interface SearchResultItem {
  title: string;
  link: string;
  snippet: string;
}

/**
 * Backend-aligned search payload types (see backend/app/domain/models/search.py)
 */
export interface SearchResultsPayload {
  query: string;
  date_range?: string | null;
  total_results?: number;
  results: SearchResultItem[];
}

/**
 * Common wrapper/envelope variants observed in tool results.
 */
export interface SearchResultsEnvelope {
  data?: SearchResultsPayload | { results?: SearchResultItem[]; items?: SearchResultItem[] };
  results?: SearchResultItem[];
  items?: SearchResultItem[];
  search_results?: SearchResultItem[];
  searchResults?: SearchResultItem[];
}
