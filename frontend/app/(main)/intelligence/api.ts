'use client';

import useSWR from 'swr';
import { axiosFetcher } from '@/lib/api';
import type {
  CustomerDetail,
  CustomerSummary,
  FeatureGap,
  FeatureGapDetail,
  IntelligenceOverview,
  ListFilters,
  MentionFilters,
  Page,
  SourceConnectorsResponse,
} from './types';

export const INTELLIGENCE_API_BASE = '/api/v1/intelligence-portal';

type QueryValue = string | number | undefined;

function buildUrl(path: string, params: Record<string, QueryValue> = {}): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === '') continue;
    search.set(key, String(value));
  }
  const qs = search.toString();
  return qs ? `${INTELLIGENCE_API_BASE}${path}?${qs}` : `${INTELLIGENCE_API_BASE}${path}`;
}

export const intelligenceUrls = {
  overview: (topN = 5) => buildUrl('/overview', { top_n: topN }),
  sourceConnectors: () => buildUrl('/filters/source-connectors'),
  featureGaps: (f: ListFilters) => buildUrl('/feature-gaps', f),
  featureGap: (name: string, f: MentionFilters = {}) =>
    buildUrl(`/feature-gaps/${encodeURIComponent(name)}`, f),
  customers: (f: ListFilters) => buildUrl('/customers', f),
  customer: (id: string, f: MentionFilters = {}) =>
    buildUrl(`/customers/${encodeURIComponent(id)}`, f),
};

const swrOptions = { revalidateOnFocus: false, keepPreviousData: true } as const;

export function useIntelligenceOverview(topN = 5) {
  return useSWR<IntelligenceOverview>(intelligenceUrls.overview(topN), axiosFetcher, swrOptions);
}

export function useSourceConnectors() {
  const { data, ...rest } = useSWR<SourceConnectorsResponse>(
    intelligenceUrls.sourceConnectors(),
    axiosFetcher,
    swrOptions,
  );
  return { data: data?.source_connectors, ...rest };
}

export function useFeatureGaps(filters: ListFilters) {
  return useSWR<Page<FeatureGap>>(intelligenceUrls.featureGaps(filters), axiosFetcher, swrOptions);
}

export function useFeatureGap(name: string | null, filters: MentionFilters = {}) {
  return useSWR<FeatureGapDetail>(
    name ? intelligenceUrls.featureGap(name, filters) : null,
    axiosFetcher,
    swrOptions,
  );
}

export function useCustomers(filters: ListFilters) {
  return useSWR<Page<CustomerSummary>>(intelligenceUrls.customers(filters), axiosFetcher, swrOptions);
}

export function useCustomer(id: string | null, filters: MentionFilters = {}) {
  return useSWR<CustomerDetail>(
    id ? intelligenceUrls.customer(id, filters) : null,
    axiosFetcher,
    swrOptions,
  );
}
