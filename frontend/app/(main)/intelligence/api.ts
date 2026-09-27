'use client';

import useSWR from 'swr';
import { apiClient, axiosFetcher } from '@/lib/api';
import type {
  CustomerDetail,
  CustomerSummary,
  FeatureGap,
  FeatureGapDetail,
  IntelligenceOverview,
  IntelligenceTopic,
  ListFilters,
  MentionFilters,
  Page,
  PainPoint,
  PainPointDetail,
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
  painPoints: (f: ListFilters) => buildUrl('/pain-points', f),
  painPoint: (name: string, f: MentionFilters = {}) =>
    buildUrl(`/pain-points/${encodeURIComponent(name)}`, f),
  topics: (kind?: string) => buildUrl('/topics', { kind }),
  topic: (id: number) => buildUrl(`/topics/${id}`),
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

export function usePainPoints(filters: ListFilters) {
  return useSWR<Page<PainPoint>>(intelligenceUrls.painPoints(filters), axiosFetcher, swrOptions);
}

export function usePainPoint(name: string | null, filters: MentionFilters = {}) {
  return useSWR<PainPointDetail>(
    name ? intelligenceUrls.painPoint(name, filters) : null,
    axiosFetcher,
    swrOptions,
  );
}

export function useTopics(kind?: 'pain_point' | 'feature_gap') {
  return useSWR<IntelligenceTopic[]>(intelligenceUrls.topics(kind), axiosFetcher, swrOptions);
}

export function useTopic(id: number | null) {
  return useSWR<IntelligenceTopic>(
    id != null ? intelligenceUrls.topic(id) : null,
    axiosFetcher,
    swrOptions,
  );
}

export async function updateTopic(
  id: number,
  body: { guidance?: string | null; aliases?: string[]; canonical_name?: string },
): Promise<IntelligenceTopic> {
  const { data } = await apiClient.patch<IntelligenceTopic>(
    `${INTELLIGENCE_API_BASE}/topics/${id}`,
    body,
  );
  return data;
}

export async function mergeTopic(sourceId: number, targetId: number): Promise<IntelligenceTopic> {
  const { data } = await apiClient.post<IntelligenceTopic>(
    `${INTELLIGENCE_API_BASE}/topics/${sourceId}/merge`,
    { target_id: targetId },
  );
  return data;
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
