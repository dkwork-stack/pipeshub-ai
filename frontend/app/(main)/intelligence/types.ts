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

export type TopicStatus = 'open' | 'under_review' | 'planned' | 'in_progress' | 'shipped' | 'declined';
export type Tone = 'frustrated' | 'angry' | 'anxious' | 'neutral' | 'appreciative';
export type Urgency = 'low' | 'medium' | 'high' | 'critical';
export type AskIntent =
  | 'feature_request'
  | 'bug'
  | 'usability'
  | 'performance'
  | 'integration'
  | 'pricing'
  | 'compliance_security'
  | 'other';
export type SpeakerRole = 'customer' | 'agent' | 'unknown';

/** What the customer said beyond the quote — shared by feature-gap and pain-point evidence. */
export type EvidenceAttributes = {
  sentiment: 'Positive' | 'Neutral' | 'Negative' | string;
  tone: Tone | string;
  urgency: Urgency | string;
  intent: AskIntent | string;
  speaker_role: SpeakerRole | string;
  product_area: string | null;
  business_impact: string | null;
  workaround: string | null;
  competitor: string | null;
  churn_risk: boolean;
  source_record_id: string | null;
  extraction_model: string | null;
  prompt_version: string | null;
};

export type TopicTrend = {
  first_seen_at: string | null;
  last_seen_at: string | null;
  mentions_last_30d: number;
  mentions_prev_30d: number;
  negative_share: number;
  high_urgency_count: number;
  churn_risk_count: number;
  competitors: string[];
  tones: Record<string, number>;
  urgencies: Record<string, number>;
};

export type CustomerHealth = {
  negative_share: number;
  churn_risk_count: number;
  high_urgency_count: number;
  last_touch_at: string | null;
  competitors: string[];
  at_risk: boolean;
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
  pain_point_count?: number;
  mention_count: number;
  top_insights: CustomerInsight[];
  health?: CustomerHealth | null;
};

export type Mention = Partial<EvidenceAttributes> & {
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

export type PainPointMention = Partial<EvidenceAttributes> & {
  external_customer_id: string;
  topic_name: string;
  summary: string;
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
  status?: TopicStatus;
  trend?: TopicTrend | null;
};

export type PainPoint = {
  topic_name: string;
  customer_count: number;
  mention_count: number;
  max_confidence: number;
  avg_confidence?: number | null;
  low_confidence_count?: number;
  top_customers: string[];
  status?: TopicStatus;
  trend?: TopicTrend | null;
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
  description?: string | null;
  status?: TopicStatus;
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
  pain_point_count?: number;
  emerging_feature_gaps?: FeatureGap[];
  at_risk_customers?: CustomerSummary[];
  intent_mix?: Record<string, number>;
  tone_mix?: Record<string, number>;
};

export type ErasureResult = {
  customers: number;
  feature_gap_mentions: number;
  pain_point_mentions: number;
  revenue_snapshots: number;
};

export type AuditEntry = {
  actor: string | null;
  action: string;
  target_type: string;
  target_id: string;
  details: Record<string, unknown>;
  created_at: string | null;
};

export type ListFilters = {
  q?: string;
  min_arr?: number;
  source_connector?: string;
  customer_id?: string;
  min_confidence?: number;
  status?: TopicStatus;
  intent?: AskIntent;
  at_risk?: boolean;
  limit?: number;
  offset?: number;
};

export type MentionFilters = {
  customer_id?: string;
  source_connector?: string;
  min_confidence?: number;
};
