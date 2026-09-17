// Wire contract for /api/v1/intelligence-portal/* — mirrors
// backend/python/app/api/schemas/intelligence_portal.py.

export type PageMeta = {
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
};

export type Page<T> = {
  items: T[];
  page: PageMeta;
};

export type RevenueSummary = {
  source_connector: string;
  mrr: number | null;
  arr: number | null;
  seats_used: number | null;
  seats_licensed: number | null;
  consumed_features: string[];
  renewal_date: string | null;
  snapshot_at: string | null;
};

export type CustomerInsight = {
  feature_name: string;
  mention_count: number;
  max_confidence: number | null;
  last_mentioned_at: string | null;
  source_connectors: string[];
};

export type CustomerSummary = {
  external_customer_id: string;
  customer_name: string;
  latest_revenue: RevenueSummary | null;
  feature_gap_count: number;
  mention_count: number;
  top_insights: CustomerInsight[];
};

export type Mention = {
  external_customer_id: string;
  feature_name: string;
  description: string | null;
  confidence: number | null;
  excerpt: string | null;
  source_connector: string;
  source_type: string | null;
  external_event_id: string | null;
  citation_url: string | null;
  occurred_at: string | null;
};

export type CustomerDetail = CustomerSummary & {
  insights: CustomerInsight[];
  mentions: Mention[];
};

export type AffectedCustomer = {
  external_customer_id: string;
  customer_name: string;
  arr: number | null;
  mrr: number | null;
  mention_count: number;
};

export type FeatureGap = {
  feature_name: string;
  total_arr_at_stake: number;
  total_mrr_at_stake: number;
  customer_count: number;
  mention_count: number;
  score: number;
  /** Customer display names (not full customer objects). */
  top_customers: string[];
};

export type SourceConnectorsResponse = {
  source_connectors: string[];
};

export type FeatureGapDetail = FeatureGap & {
  affected_customers: AffectedCustomer[];
  mentions: Mention[];
};

export type IntelligenceOverview = {
  total_arr_at_stake: number;
  total_mrr_at_stake: number;
  feature_gap_count: number;
  customer_count: number;
  mention_count: number;
  source_connectors: string[];
  top_feature_gaps: FeatureGap[];
  top_customers: CustomerSummary[];
  last_mention_at: string | null;
};

export type ListFilters = {
  q?: string;
  min_arr?: number;
  source_connector?: string;
  customer_id?: string;
  limit?: number;
  offset?: number;
};

export type MentionFilters = {
  customer_id?: string;
  source_connector?: string;
};
