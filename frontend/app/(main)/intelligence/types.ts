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
  avg_confidence?: number | null;
  low_confidence_count?: number;
  last_mentioned_at: string | null;
  source_connectors: string[];
};

export type PainPointInsight = {
  topic_name: string;
  mention_count: number;
  max_confidence: number | null;
  avg_confidence?: number | null;
  low_confidence_count?: number;
  last_mentioned_at: string | null;
  source_connectors: string[];
  sentiments: string[];
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

export type PainPointMention = {
  external_customer_id: string;
  topic_name: string;
  summary: string;
  sentiment: string;
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
  pain_point_insights: PainPointInsight[];
  mentions: Mention[];
  pain_point_mentions: PainPointMention[];
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
  max_confidence?: number | null;
  avg_confidence?: number | null;
  low_confidence_count?: number;
};

export type PainPoint = {
  topic_name: string;
  customer_count: number;
  mention_count: number;
  max_confidence: number;
  avg_confidence?: number | null;
  low_confidence_count?: number;
  top_customers: string[];
};

export type SourceConnectorsResponse = {
  source_connectors: string[];
};

export type FeatureGapDetail = FeatureGap & {
  affected_customers: AffectedCustomer[];
  mentions: Mention[];
};

export type PainPointDetail = PainPoint & {
  affected_customers: AffectedCustomer[];
  mentions: PainPointMention[];
};

export type IntelligenceTopic = {
  id: number;
  kind: 'pain_point' | 'feature_gap';
  canonical_name: string;
  aliases: string[];
  guidance: string | null;
  merged_into_id: number | null;
  updated_by: string | null;
  created_at: string | null;
  updated_at: string | null;
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
  min_confidence?: number;
  limit?: number;
  offset?: number;
};

export type MentionFilters = {
  customer_id?: string;
  source_connector?: string;
  min_confidence?: number;
};
